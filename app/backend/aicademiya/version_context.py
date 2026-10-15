"""Authorization and edition selection, separate from learning projections."""
import copy
import json
from datetime import datetime, timezone
from fastapi import HTTPException
from .versions import changed, snapshot
from .db import public_user
from .course_lifecycle import require_live_course, trash_timestamp


def is_staff(user):
    return user["role"] in ("teacher", "admin")


def ensure_teacher(user):
    if not is_staff(user):
        raise HTTPException(403, "Teacher access required")


def course_access(conn, cid, user):
    course = conn.execute("SELECT * FROM courses WHERE id=?", (cid,)).fetchone()
    if not course:
        raise HTTPException(404, "Course not found")
    from .course_staff import live_actor, assigned
    live_actor(conn, user)
    allowed = assigned(conn, cid, user["id"]) if is_staff(user) else conn.execute("SELECT * FROM enrollments WHERE course_id=? AND user_id=?", (cid, user["id"])).fetchone()
    if not allowed:
        raise HTTPException(403, "You do not have access to this course")
    require_live_course(conn, cid)
    if not is_staff(user) and allowed["purge_at"] and datetime.fromisoformat(allowed["purge_at"]) <= datetime.now(timezone.utc):
        raise HTTPException(410, "Archived course records have expired")
    return course


def availability(row, at=None):
    at = at or datetime.now(timezone.utc)
    start, end = row["starts_at"], row["ends_at"]
    if start or end:
        if start and at < datetime.fromisoformat(start.replace("Z", "+00:00")):
            effective, reason = False, "not_started"
        elif end and at >= datetime.fromisoformat(end.replace("Z", "+00:00")):
            effective, reason = False, "ended"
        else:
            effective, reason = True, "scheduled"
    else:
        effective = bool(row["active"])
        reason = "manual_active" if effective else "manual_inactive"
    return {"active": bool(row["active"]), "starts_at": start, "ends_at": end, "effective_active": effective, "availability_reason": reason}


def published_detail(conn, sid, version_id=None):
    """Read only curriculum tables; suitable for parent-owned prefix warmer."""
    row = conn.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
    if not row:
        raise HTTPException(404, "Session not found")
    require_live_course(conn, row["course_id"])
    current = conn.execute("SELECT published_version_id FROM courses WHERE id=?", (row["course_id"],)).fetchone()[0]
    vid = version_id or current
    if not vid:
        raise HTTPException(404, "Course has no published version")
    version, content = snapshot(conn, row["course_id"], vid)
    detail = next((s for s in content["sessions"] if s["id"] == sid and s.get("status") == "published"), None)
    if detail is None:
        raise HTTPException(404, "Session is not published in this version")
    detail = copy.deepcopy(detail)
    detail.update(availability(row))
    detail.update(_version_id=vid, _version_number=version["number"], _current_version_id=current)
    return detail


def ensure_learning_write(detail, user):
    if is_staff(user):
        if detail.get("_version_id"):
            raise HTTPException(409, "Published snapshots are read-only; use the draft preview")
        return
    if detail.get("_version_id") != detail.get("_current_version_id"):
        raise HTTPException(409, "Historical learning editions are read-only")
    if detail.get("_enrollment_archived"):
        raise HTTPException(403, "This course enrollment is archived; learning history remains available")
    if not detail.get("effective_active", True):
        raise HTTPException(409, "This session is inactive; learning history remains available")


def session_access(conn, sid, user, version_id=None, *, write=False):
    row = conn.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
    if not row:
        raise HTTPException(404, "Session not found")
    course = course_access(conn, row["course_id"], user)
    if version_id is not None and not version_id:
        raise HTTPException(422, "version_id must not be blank")
    if is_staff(user) and version_id is None:
        if not row["in_draft"]:
            raise HTTPException(404, "Session was removed from the current draft; select its historical version")
        detail = json.loads(row["content_json"])
        detail.update(availability(row))
        detail.update(_version_id="", _version_number=None, _current_version_id=course["published_version_id"])
    else:
        detail = published_detail(conn, sid, version_id)
        if not is_staff(user):
            vid = detail["_version_id"]
            enrollment = conn.execute("SELECT * FROM enrollments WHERE course_id=? AND user_id=?", (course["id"], user["id"])).fetchone()
            existing = conn.execute("SELECT 1 FROM workspaces WHERE session_id=? AND user_id=? AND version_id=?", (sid, user["id"], vid)).fetchone()
            if (vid != course["published_version_id"] or enrollment["archived_at"]) and not existing:
                raise HTTPException(403, "Only your existing learning history is available")
            detail["_enrollment_archived"] = bool(enrollment["archived_at"])
            if write and version_id is None and conn.execute("SELECT 1 FROM workspaces WHERE session_id=? AND user_id=? AND version_id<>?", (sid, user["id"], vid)).fetchone():
                raise HTTPException(409, "Course edition changed; reload and send the workspace version_id")
    if write:
        ensure_learning_write(detail, user)
    return detail


def observed_detail(conn, sid, uid, owner, version_id=None):
    session = conn.execute("SELECT course_id FROM sessions WHERE id=?", (sid,)).fetchone()
    if not session:
        raise HTTPException(404, "Session not found")
    draft = {"course_id": session[0]}
    course_access(conn, session[0], owner)
    row = conn.execute("SELECT * FROM users WHERE id=? AND role='student'", (uid,)).fetchone()
    if not row or not conn.execute("SELECT 1 FROM enrollments WHERE course_id=? AND user_id=?", (draft["course_id"], uid)).fetchone():
        raise HTTPException(404, "Student not found in this course")
    if version_id is None:
        latest = conn.execute("SELECT version_id FROM workspaces WHERE session_id=? AND user_id=? AND version_id<>'' ORDER BY coalesce(last_active,'') DESC,rowid DESC LIMIT 1", (sid, uid)).fetchone()
        version_id = latest[0] if latest else None
    detail = published_detail(conn, sid, version_id)
    enrollment = conn.execute("SELECT archived_at FROM enrollments WHERE course_id=? AND user_id=?", (draft["course_id"], uid)).fetchone()
    detail["_enrollment_archived"] = bool(enrollment[0])
    return detail, public_user(row, conn)


def public_course(conn, row, teacher=False):
    result = {key: row[key] for key in ("id", "code", "title", "description")}
    vid = row["published_version_id"]
    result["published_version_id"] = vid
    result["published_version_number"] = conn.execute("SELECT number FROM course_versions WHERE id=?", (vid,)).fetchone()[0] if vid else None

    result["trashed_at"] = trash_timestamp(conn, row["id"])
    if teacher:
        result.update(join_code=row["join_code"], has_unpublished_changes=changed(conn, row["id"]))
    elif vid:
        _, content = snapshot(conn, row["id"], vid)
        result.update(content["course"])
    # Operational populations must follow CURRENT roles/accounts, not snapshots.
    result['student_count'] = conn.execute("SELECT count(*) FROM enrollments e JOIN users u ON u.id=e.user_id WHERE e.course_id=? AND e.archived_at IS NULL AND u.archived_at IS NULL AND u.role='student'", (row['id'],)).fetchone()[0]
    for role in ('admin', 'teacher'):
        result[role + '_count'] = conn.execute('''SELECT count(*) FROM course_staff cs JOIN users u ON u.id=cs.user_id
            WHERE cs.course_id=? AND u.role=? AND u.archived_at IS NULL''', (row['id'], role)).fetchone()[0]
    return result


def material_rows(conn, detail):
    if "_materials" in detail:
        return detail["_materials"]
    from .material_library import session_material_rows
    return session_material_rows(conn, detail["id"])


def available_versions(conn, detail, user, staff=False):
    result = []
    for row in conn.execute("SELECT * FROM course_versions WHERE course_id=? ORDER BY number", (detail["course_id"],)):
        if not any(s["id"] == detail["id"] and s.get("status") == "published" for s in json.loads(row["snapshot_json"])["sessions"]):
            continue
        if staff or row["id"] == detail.get("_current_version_id") or conn.execute("SELECT 1 FROM workspaces WHERE session_id=? AND user_id=? AND version_id=?", (detail["id"], user["id"], row["id"])).fetchone():
            result.append({k: row[k] for k in ("id", "number", "label")})
    return result
