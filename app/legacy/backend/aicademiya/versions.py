"""Immutable curriculum snapshots. Runtime availability is deliberately separate."""
import copy
import json
from fastapi import HTTPException
from .db import new_id, now
from .material_library import session_material_rows

OPERATIONAL = {"active", "starts_at", "ends_at", "effective_active", "availability_reason"}


def draft_snapshot(conn, cid):
    row = conn.execute("SELECT * FROM courses WHERE id=?", (cid,)).fetchone()
    course = {k: row[k] for k in ("id", "code", "title", "description")}
    sessions = []
    for row in conn.execute("SELECT * FROM sessions WHERE course_id=? AND in_draft=1 ORDER BY rowid", (cid,)):
        detail = json.loads(row["content_json"])
        detail = {k: v for k, v in detail.items() if k not in OPERATIONAL and not k.startswith("_")}
        detail["_materials"] = [dict(m) for m in session_material_rows(conn, row["id"])]
        sessions.append(detail)
    return {"course": course, "sessions": sessions}


def snapshot(conn, cid, vid):
    row = conn.execute("SELECT * FROM course_versions WHERE id=? AND course_id=?", (vid, cid)).fetchone()
    if not row:
        raise HTTPException(404, "Course version not found")
    return row, json.loads(row["snapshot_json"])


def version_entry(row):
    return {k: row[k] for k in ("id", "number", "label", "created_at", "created_by")}


def changed(conn, cid):
    current = conn.execute("SELECT published_version_id FROM courses WHERE id=?", (cid,)).fetchone()[0]
    if not current:
        return True
    _, saved = snapshot(conn, cid, current)
    return saved != draft_snapshot(conn, cid)


def publish(conn, cid, uid, label=None, content=None):
    content = content if content is not None else draft_snapshot(conn, cid)
    # Only attached curriculum files participate: unrelated library uploads do
    # not block an otherwise publishable edition. A failed retry with a valid
    # older revision also remains publishable.
    for session in content.get("sessions", []):
        for material in session.get("_materials", []):
            raw = json.loads(material["content_json"])
            if raw.get("processing") == "full_document" and not raw.get("document"):
                raise HTTPException(409, "Attached complete document must finish processing before publication")
    number = conn.execute("SELECT coalesce(max(number),0)+1 FROM course_versions WHERE course_id=?", (cid,)).fetchone()[0]
    vid = new_id()
    conn.execute("INSERT INTO course_versions(id,course_id,number,label,created_at,created_by,snapshot_json) VALUES(?,?,?,?,?,?,?)",
                 (vid, cid, number, label or f"Version {number}", now(), uid, json.dumps(content, ensure_ascii=False)))
    conn.execute("UPDATE courses SET published_version_id=? WHERE id=?", (vid, cid))
    return version_entry(conn.execute("SELECT * FROM course_versions WHERE id=?", (vid,)).fetchone())


def restore(conn, cid, vid, uid, label=None):
    _, content = snapshot(conn, cid, vid)
    # Explicit restore invalidates accepted work even in an A→B→A identity
    # sequence. Old successful revisions and their assets are never deleted.
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='document_jobs' AND type='table'").fetchone():
        conn.execute("""UPDATE document_jobs SET status='failed',finished_at=?,error=?
            WHERE status IN ('queued','running') AND material_id IN
            (SELECT material_id FROM material_courses WHERE course_id=?)""",
            (now(), "Document processing was superseded by course restore", cid))
    content = copy.deepcopy(content)
    course = content["course"]
    conn.execute("UPDATE courses SET code=?,title=?,description=? WHERE id=?",
                 (course["code"], course["title"], course["description"], cid))
    # Retain relational identity and assets for old runs, but remove absent sessions
    # from the current draft rather than smuggling them into the restored snapshot.
    conn.execute("UPDATE sessions SET in_draft=0 WHERE course_id=?", (cid,))
    conn.execute("DELETE FROM session_materials WHERE session_id IN (SELECT id FROM sessions WHERE course_id=?)", (cid,))
    restored_materials = set()
    for detail in content["sessions"]:
        materials = detail.pop("_materials", [])
        conn.execute("INSERT INTO sessions(id,course_id,content_json,in_draft) VALUES(?,?,?,1) ON CONFLICT(id) DO UPDATE SET content_json=excluded.content_json,in_draft=1",
                     (detail["id"], cid, json.dumps(detail)))
        for m in materials:
            if m["id"] not in restored_materials:
                # One shared course-file property is restored once, not archived
                # or overwritten repeatedly for each session using the same ID.
                conn.execute("INSERT INTO materials(id,session_id,content_json,file_path,archived) VALUES(?,?,?,?,0) ON CONFLICT(id) DO UPDATE SET content_json=excluded.content_json,file_path=excluded.file_path,archived=0",
                             (m["id"], m.get("session_id", detail["id"]), m["content_json"], m["file_path"]))
                restored_materials.add(m["id"])
            conn.execute("INSERT OR IGNORE INTO session_materials(session_id,material_id) VALUES(?,?)", (detail["id"], m["id"]))
    # The new immutable snapshot is now the restored curriculum, without changing availability.
    return publish(conn, cid, uid, label or f"Restored from {vid}")


def comparison_snapshot(content):
    """Readable comparison data without private filesystem/storage encoding."""
    result = copy.deepcopy(content)
    from .document_storage import public_document
    material_fields = {"id", "title", "kind", "visibility", "source_label", "status", "excerpt", "warning", "url", "source_input", "managed", "extraction", "extracted_at", "extraction_report", "assets", "document"}
    for session in result.get("sessions", []):
        session["_materials"] = [
            {"id": row["id"], "metadata": {k: v for k, v in json.loads(row["content_json"]).items() if k in material_fields}}
            for row in session.get("_materials", [])
        ]
        for material in session["_materials"]:
            if material["metadata"].get("document"):
                material["metadata"]["document"] = public_document(material["metadata"]["document"])
    return result


def diff(before, after, path=""):
    result = []
    if path.endswith(".content_json") and isinstance(before, str) and isinstance(after, str):
        try:
            return diff(json.loads(before), json.loads(after), path.removesuffix(".content_json") + ".metadata")
        except ValueError:
            pass
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(before.keys() | after.keys()):
            result.extend(diff(before.get(key), after.get(key), f"{path}.{key}" if path else key))
    elif isinstance(before, list) and isinstance(after, list):
        # ID-keyed sections produce readable stable paths instead of positional churn.
        if all(isinstance(x, dict) and "id" in x for x in before + after):
            left, right = {x["id"]: x for x in before}, {x["id"]: x for x in after}
            for key in sorted(left.keys() | right.keys()):
                result.extend(diff(left.get(key), right.get(key), f"{path}[{key}]"))
            if [x["id"] for x in before] != [x["id"] for x in after]:
                result.append({"path": path + ".order", "before": list(left), "after": list(right)})
        elif before != after:
            result.append({"path": path, "before": before, "after": after})
    elif before != after:
        result.append({"path": path, "before": before, "after": after})
    return result
