"""Ownership checks and public projections; never return raw catalog JSON."""
import json
from fastapi import HTTPException
from .db import new_id, now, public_user
from .version_context import (is_staff, ensure_teacher, course_access, session_access, public_course, material_rows, available_versions)
from urllib.parse import urlencode

SUMMARY_FIELDS = ("id", "course_id", "title", "subtitle", "number", "status", "estimated_minutes", "learning_objectives")
QUESTION_FIELDS = ("id", "group_id", "ordinal", "type", "prompt", "options", "answer_slots", "images", "source_label", "hint")
MATERIAL_FIELDS = ("id", "title", "kind", "visibility", "source_label", "status", "excerpt", "warning", "url", "extraction", "extracted_at", "extraction_report")


def student_access(conn, detail, uid):
    row = conn.execute("SELECT * FROM users WHERE id=? AND role='student'", (uid,)).fetchone()
    if not row or not conn.execute("SELECT 1 FROM enrollments WHERE course_id=? AND user_id=?", (detail["course_id"], uid)).fetchone():
        raise HTTPException(404, "Student not found in this course")
    return public_user(row, conn)


def reading_groups(detail):
    return [g["id"] for g in detail.get("groups", []) if g.get("kind") == "reading"]


def active_questions(detail, selected):
    branches = set(reading_groups(detail))
    return [q for q in detail.get("questions", []) if q["group_id"] not in branches or q["group_id"] == selected]


def expected_count(detail):
    branches = reading_groups(detail)
    core = len(active_questions(detail, None))
    counts = [sum(q["group_id"] == branch for q in detail.get("questions", [])) for branch in branches]
    return core + (max(counts) if counts else 0)


def summary(detail, student_status=None):
    defaults = {"subtitle": "", "number": 1, "status": "draft", "estimated_minutes": 40, "learning_objectives": []}
    result = {key: detail.get(key, defaults.get(key)) for key in SUMMARY_FIELDS}
    result["question_count"] = expected_count(detail)
    result.update({k: detail.get(k, v) for k, v in {"active": True, "starts_at": None, "ends_at": None, "effective_active": True, "availability_reason": "manual_active"}.items()})
    if student_status is not None:
        result["student_status"] = student_status
    return result


def public_material(row, teacher=False, version_id=None):
    raw = json.loads(row["content_json"])
    if not teacher and (raw.get("visibility") != "student" or raw.get("kind") == "answer_key"):
        return None
    result = {key: raw.get(key) for key in MATERIAL_FIELDS}
    from .document_storage import public_document
    result["document"] = public_document(raw.get("document"))
    result["warning"] = raw.get("warning")
    result["source_relative_path"] = raw.get("source_relative_path")
    suffix = "?" + urlencode({"version_id": version_id}) if version_id else ""
    result["download_url"] = f"/api/materials/{row['id']}/download{suffix}" if row["file_path"] else None
    result["preview_url"] = f"/api/materials/{row['id']}/preview{suffix}"
    from pathlib import Path
    extension = Path(row["file_path"]).suffix.lower() if row["file_path"] else ""
    result["source_format"] = extension.lstrip('.') or None
    result["preview_kind"] = "link" if raw.get("kind") == "link" else "pdf" if extension == ".pdf" else "image" if extension in (".png", ".jpg", ".jpeg", ".webp") else "text"
    return result


def public_detail(conn, detail, teacher=False, student_status=None):
    result = summary(detail, student_status)
    result.update({
        # Teaching instructions can contain teacher notes or embedded answer keys.
        "instructions": detail.get("instructions", "") if teacher else "",
        "reference_policy": detail.get("reference_policy", "after_attempt"),
        "teaching_language": detail.get("teaching_language", "en"),
        "groups": [{key: group[key] for key in ("id", "title", "kind", "description") if key in group} for group in detail.get("groups", [])],
        "questions": [], "materials": [],
    })
    for question in detail.get("questions", []):
        item = {key: question[key] for key in QUESTION_FIELDS if key in question}
        item.setdefault("options", [])
        item.setdefault("answer_slots", 1)
        item.setdefault("source_label", "")
        item["images"] = [{key: image.get(key, "") for key in ("label", "url", "alt")} for image in question.get("images", [])]
        if teacher:
            item.update(source_material_ids=question.get("source_material_ids", []), source_links=question.get("source_links", []))
        for image in item["images"]:
            if detail.get("_version_id") and image["url"].startswith("/api/materials/"):
                image["url"] = image["url"].split("?", 1)[0] + "?" + urlencode({"version_id": detail["_version_id"]})
        result["questions"].append(item)
    for row in material_rows(conn, detail):
        material = public_material(row, teacher, detail.get("_version_id"))
        if material:
            result["materials"].append(material)
    if teacher:
        from .teaching import effective_profile
        result["teaching_profile"] = effective_profile(detail)
        result["reference_answers"] = detail.get("reference_answers", {})
    return result


def ensure_workspace(conn, sid, uid, version_id=""):
    conn.execute("INSERT OR IGNORE INTO workspaces(session_id,user_id,version_id) VALUES(?,?,?)", (sid, uid, version_id))
    return conn.execute("SELECT * FROM workspaces WHERE session_id=? AND user_id=? AND version_id=?", (sid, uid, version_id)).fetchone()


def editable(workspace):
    if workspace["status"] in ("submitted", "confirmed"):
        raise HTTPException(409, "This submission is locked; ask the teacher to request revisions")


def active_question(detail, workspace, qid):
    question = next((q for q in active_questions(detail, workspace["selected_reading"]) if q["id"] == qid), None)
    if not question:
        raise HTTPException(409, "Question is not on the active path; choose its reading first")
    return question


def mark_active(conn, sid, uid, answer_change=False, version_id=""):
    if answer_change:
        conn.execute("UPDATE workspaces SET status=CASE WHEN status='needs_revision' THEN status ELSE 'in_progress' END,last_active=? WHERE session_id=? AND user_id=? AND version_id=?", (now(), sid, uid, version_id))
    else:
        conn.execute("UPDATE workspaces SET status=CASE WHEN status='not_started' THEN 'in_progress' ELSE status END,last_active=? WHERE session_id=? AND user_id=? AND version_id=?", (now(), sid, uid, version_id))


def save_answer(conn, sid, uid, qid, answer, version_id=""):
    stamp = now()
    conn.execute("INSERT INTO attempts(session_id,user_id,question_id,answer,updated_at,version_id) VALUES(?,?,?,?,?,?) ON CONFLICT(session_id,user_id,version_id,question_id) DO UPDATE SET answer=excluded.answer,updated_at=excluded.updated_at", (sid, uid, qid, answer, stamp, version_id))
    conn.execute("INSERT INTO revisions(session_id,user_id,question_id,answer,created_at,version_id) VALUES(?,?,?,?,?,?)", (sid, uid, qid, answer, stamp, version_id))
    mark_active(conn, sid, uid, answer_change=True, version_id=version_id)
    row = conn.execute("SELECT state_json FROM tutor_runs WHERE session_id=? AND user_id=? AND version_id=?", (sid, uid, version_id)).fetchone()
    if row:
        guided = json.loads(row[0])
        if qid in guided["question_states"]:
            qs = guided["question_states"][qid]
            qs.update(status="in_progress", last_outcome="unknown", answer_count=conn.execute("SELECT count(*) FROM revisions WHERE session_id=? AND user_id=? AND version_id=? AND question_id=?", (sid, uid, version_id, qid)).fetchone()[0])
            if guided["started_at"] and guided["phase"] != "warmup":
                guided["phase"] = "worksheet"
                guided["current_question_id"] = qid
            conn.execute("UPDATE tutor_runs SET state_json=? WHERE session_id=? AND user_id=? AND version_id=?", (json.dumps(guided), sid, uid, version_id))


def save_message(conn, sid, uid, role, content, qid, mode, intent=None, citations=None, version_id=""):
    mid = new_id()
    conn.execute("INSERT INTO messages(id,session_id,user_id,role,content,question_id,created_at,mode,intent,citations_json,version_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (mid, sid, uid, role, content, qid, now(), mode, intent, json.dumps(citations or []), version_id))
    return mid


def workspace_response(conn, detail, user, ai, teacher_detail=False):
    sid, uid, vid = detail["id"], user["id"], detail.get("_version_id", "")
    state = ensure_workspace(conn, sid, uid, vid)
    attempts = {}
    for row in conn.execute("SELECT * FROM attempts WHERE session_id=? AND user_id=? AND version_id=? ORDER BY rowid", (sid, uid, vid)):
        revisions = [dict(item) for item in conn.execute("SELECT answer,created_at FROM revisions WHERE session_id=? AND user_id=? AND version_id=? AND question_id=? ORDER BY id", (sid, uid, vid, row["question_id"]))]
        attempts[row["question_id"]] = {"question_id": row["question_id"], "answer": row["answer"], "revision_count": max(0, len(revisions) - 1), "updated_at": row["updated_at"], "reference_revealed": bool(row["reference_revealed"]), "revisions": revisions}
    messages = []
    for row in conn.execute("SELECT * FROM messages WHERE session_id=? AND user_id=? AND version_id=? ORDER BY seq", (sid, uid, vid)):
        item = {key: row[key] for key in ("id", "role", "content", "question_id", "created_at", "mode")}
        if row["intent"]:
            item["intent"] = row["intent"]
        item["citations"] = json.loads(row["citations_json"])
        if row["metadata_json"] != "{}":
            item["metadata"] = json.loads(row["metadata_json"])
            presented = item["metadata"].get("presented_question")
            if presented:
                item["presented_question_id"] = presented["id"]
        messages.append(item)
    ids = [q["id"] for q in active_questions(detail, state["selected_reading"])]
    answered = sum(bool(attempts.get(qid, {}).get("answer", "").strip()) for qid in ids)
    current = next((qid for qid in ids if not attempts.get(qid, {}).get("answer", "").strip()), ids[-1] if ids else None)
    reason = None
    if not is_staff(user):
        if vid != detail.get("_current_version_id"):
            reason = "historical_version"
        elif detail.get("_enrollment_archived"):
            reason = "enrollment_archived"
        elif not detail.get("effective_active", True):
            reason = "session_inactive"
        elif state["status"] in ("submitted", "confirmed"):
            reason = "submission_locked"
    elif vid:
        reason = "published_snapshot"
    from .teacher_preview import is_preview, preview_info
    preview = preview_info(conn, detail, user) if is_preview(detail, user) else None
    if preview and preview["stale"]:
        reason = "preview_stale"
    from .guided_state import public_state
    return {**({"preview": preview} if preview is not None else {}), "tutor": public_state(conn, detail, user, state), "session": public_detail(conn, detail, teacher_detail, state["status"]), "user": user,
            "selected_reading": state["selected_reading"], "attempts": attempts, "messages": messages,
            "progress": {"answered": answered, "total": len(ids), "active_question_ids": ids, "current_question_id": current},
            "submission": {key: state[key] for key in ("status", "submitted_at", "reviewed_at", "teacher_note")}, "ai": ai,
            "version": {"id": vid or None, "number": detail.get("_version_number"), "is_current": bool(vid and vid == detail.get("_current_version_id")), "is_draft": not bool(vid)},
            "available_versions": available_versions(conn, detail, user, teacher_detail), "read_only": bool(reason), "read_only_reason": reason}
