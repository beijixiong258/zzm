"""Owner draft preview identity. Reads/migration never bind or erase an old trial."""
import hashlib
import json
from fastapi import HTTPException
from .db import new_id, now
from .version_context import is_staff, material_rows, session_access
from .teaching import effective_profile


# Operational availability, storage locations and provider settings are not teaching content.
SESSION_FIELDS = ("id", "title", "subtitle", "learning_objectives", "instructions",
                  "teaching_language", "reference_policy", "groups", "questions", "reference_answers")
MATERIAL_FIELDS = ("title", "kind", "visibility", "source_label", "status", "excerpt", "warning", "url", "extraction_report", "document")
QUESTION_FIELDS = ("id", "group_id", "ordinal", "type", "prompt", "options", "answer_slots", "source_label", "hint", "source_material_ids", "source_links")


def migrate_previews(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS teacher_previews (
      session_id TEXT NOT NULL REFERENCES sessions(id),
      user_id TEXT NOT NULL REFERENCES users(id),
      preview_id TEXT NOT NULL, revision TEXT NOT NULL, bound_at TEXT NOT NULL,
      PRIMARY KEY(session_id,user_id))""")


def saved_revision(conn, detail):
    content = {k: detail.get(k) for k in SESSION_FIELDS}
    content["questions"] = [{**{k: q.get(k) for k in QUESTION_FIELDS},
                             "images": [{k: img.get(k, "") for k in ("label", "url", "alt")} for img in q.get("images", [])]}
                            for q in detail.get("questions", [])]
    content["groups"] = [{k: g.get(k) for k in ("id", "title", "kind", "description")} for g in detail.get("groups", [])]
    content["teaching_profile"] = effective_profile(detail)
    content["materials"] = []
    for row in material_rows(conn, detail):
        raw = json.loads(row["content_json"])
        content["materials"].append({"id": row["id"], **{k: raw.get(k) for k in MATERIAL_FIELDS},
                                     "assets": [{k: a.get(k) for k in ("key", "label", "kind")} for a in raw.get("assets", [])]})
    # Stable material order is meaningful to the live evidence selection.
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def is_preview(detail, user):
    return is_staff(user) and not detail.get("_version_id")


def preview_row(conn, detail, user):
    return conn.execute("SELECT * FROM teacher_previews WHERE session_id=? AND user_id=?", (detail["id"], user["id"])).fetchone()


def pending_preview(conn, sid, uid):
    return any(conn.execute(f"SELECT 1 FROM {table} WHERE session_id=? AND user_id=? AND version_id='' AND status='pending'", (sid, uid)).fetchone()
               for table in ("tutor_requests", "chat_requests"))


def preview_info(conn, detail, user):
    current = saved_revision(conn, detail)
    row = preview_row(conn, detail, user)
    stale = bool(row and row["revision"] != current)
    legacy_work = not row and any(conn.execute(f"SELECT 1 FROM {table} WHERE session_id=? AND user_id=? AND version_id=''", (detail["id"], user["id"])).fetchone()
                                  for table in ("messages", "attempts", "tutor_runs", "chat_requests", "tutor_requests"))
    return {"id": row["preview_id"] if row else None, "revision": row["revision"] if row else None,
            "current_revision": current, "stale": stale, "reset_required": bool(stale or legacy_work),
            "pending": pending_preview(conn, detail["id"], user["id"]), "bound_at": row["bound_at"] if row else None}


def reserve_guard(conn, detail, user, preview_id=None):
    if not is_preview(detail, user):
        return None
    row = preview_row(conn, detail, user)
    if not row:
        if preview_id is not None:
            raise HTTPException(409, "Preview identity no longer exists; reload and reset your preview")
        return None  # Original unmanaged teacher API compatibility.
    if preview_id != row["preview_id"]:
        raise HTTPException(409, "Preview identity is missing or replaced; reload and reset your preview")
    if row["revision"] != saved_revision(conn, detail):
        raise HTTPException(409, "Saved draft changed; this preview is read-only until Reset my preview")
    return {"id": row["preview_id"], "revision": row["revision"]}


def commit_guard(conn, sid, user, accepted):
    if accepted is None:
        return
    detail = session_access(conn, sid, user)
    reserve_guard(conn, detail, user, accepted["id"])
    row = preview_row(conn, detail, user)
    if not row or row["revision"] != accepted["revision"]:
        raise HTTPException(409, "Preview generation or saved revision changed during inference; raw input is retained")


def legacy_write_guard(conn, detail, user, preview_id=None):
    if is_preview(detail, user) and preview_row(conn, detail, user):
        # Synchronous full-preview actions carry a query token. Legacy chat has
        # no such opt-in and remains unavailable for managed preview runs.
        if preview_id is not None:
            return reserve_guard(conn, detail, user, preview_id)
        raise HTTPException(409, "Managed previews require the current preview_id; reload the draft preview before writing")


def reset_preview(conn, detail, user, expected_revision):
    revision = saved_revision(conn, detail)
    if revision != expected_revision:
        raise HTTPException(409, "Saved draft revision changed; reload before resetting your preview")
    sid, uid = detail["id"], user["id"]
    if pending_preview(conn, sid, uid):
        raise HTTPException(409, "Wait for pending guided or chat inference before resetting your preview")
    # Delete only the authenticated staff user's unversioned current run, in FK order.
    for table in ("tutor_requests", "tutor_runs", "chat_requests", "messages", "revisions", "attempts", "workspaces"):
        conn.execute(f"DELETE FROM {table} WHERE session_id=? AND user_id=? AND version_id=''", (sid, uid))
    conn.execute("""INSERT INTO teacher_previews VALUES(?,?,?,?,?)
      ON CONFLICT(session_id,user_id) DO UPDATE SET preview_id=excluded.preview_id,
      revision=excluded.revision,bound_at=excluded.bound_at""", (sid, uid, new_id(), revision, now()))
