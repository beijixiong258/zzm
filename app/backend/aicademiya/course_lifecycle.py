"""Owner metadata and recoverable operational trash; never delete curriculum/work."""
from fastapi import Depends, HTTPException
from . import models as m
from .db import now

TRASH_MESSAGE = "Course is in trash. Restore it to continue."


def migrate_course_lifecycle(conn):
    # One additive table only: no course-column changes, backfill or timer.
    conn.execute("SAVEPOINT course_lifecycle")
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS course_trash (
            course_id TEXT PRIMARY KEY REFERENCES courses(id),
            trashed_at TEXT NOT NULL,
            trashed_by TEXT NOT NULL REFERENCES users(id))""")
        conn.execute("PRAGMA user_version=6")
        conn.execute("RELEASE course_lifecycle")
    except Exception:
        conn.execute("ROLLBACK TO course_lifecycle")
        conn.execute("RELEASE course_lifecycle")
        raise


def trash_timestamp(conn, cid):
    row = conn.execute("SELECT trashed_at FROM course_trash WHERE course_id=?", (cid,)).fetchone()
    return row[0] if row else None


def require_live_course(conn, cid):
    """Call only after role/ownership/enrollment authorization (or curriculum-only lookup)."""
    if trash_timestamp(conn, cid) is not None:
        raise HTTPException(410, TRASH_MESSAGE)


def owner_metadata(conn, cid, user):
    # This is the sole allow-trashed authorization, not a content-access option.
    from .version_context import ensure_teacher
    ensure_teacher(user)
    row = conn.execute("SELECT * FROM courses WHERE id=?", (cid,)).fetchone()
    if not row:
        raise HTTPException(404, "Course not found")
    from .course_staff import require_assigned
    require_assigned(conn, cid, user)
    return row


def course_details(conn, row):
    from .version_context import public_course
    cid = row["id"]
    return {**public_course(conn, row, True),
            "trashed_at": trash_timestamp(conn, cid),
            "session_count": conn.execute("SELECT count(*) FROM sessions WHERE course_id=? AND in_draft=1", (cid,)).fetchone()[0],
            # Canonical course-file IDs, not the number of session associations.
            "material_count": conn.execute("SELECT count(*) FROM material_courses WHERE course_id=?", (cid,)).fetchone()[0],
            "enrollment_count": conn.execute("SELECT count(*) FROM enrollments WHERE course_id=?", (cid,)).fetchone()[0]}


def register_course_lifecycle_routes(app, db, teacher_user):
    # Register the literal route before the dynamic metadata route.
    @app.get("/api/courses/trash")
    def course_trash(user=Depends(teacher_user)):
        with db.connect() as conn:
            conn.execute("BEGIN")
            from .course_staff import live_actor
            live_actor(conn, user, staff=True)
            rows = conn.execute("""SELECT c.* FROM courses c JOIN course_trash t ON t.course_id=c.id
                WHERE EXISTS (SELECT 1 FROM course_staff cs WHERE cs.course_id=c.id AND cs.user_id=?)
                ORDER BY t.trashed_at DESC,c.rowid DESC""", (user["id"],)).fetchall()
            return {"courses": [course_details(conn, row) for row in rows]}

    @app.get("/api/courses/{course_id}")
    def metadata(course_id: str, user=Depends(teacher_user)):
        with db.connect() as conn:
            conn.execute("BEGIN")
            return course_details(conn, owner_metadata(conn, course_id, user))

    @app.patch("/api/courses/{course_id}")
    def patch(course_id: str, payload: m.CoursePatch, user=Depends(teacher_user)):
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            owner_metadata(conn, course_id, user)
            require_live_course(conn, course_id)
            values = payload.model_dump(exclude_unset=True)
            # Keys are restricted by the validated payload; text is kept literally.
            for key, value in values.items():
                conn.execute(f"UPDATE courses SET {key}=? WHERE id=?", (value, course_id))
            return course_details(conn, owner_metadata(conn, course_id, user))

    @app.post("/api/courses/{course_id}/trash")
    def trash(course_id: str, payload: m.Empty, user=Depends(teacher_user)):
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = owner_metadata(conn, course_id, user)
            if trash_timestamp(conn, course_id) is None:
                # Same writer reservation as guided/legacy request acceptance.
                for table in ("tutor_requests", "chat_requests"):
                    if conn.execute(f"""SELECT 1 FROM {table} r JOIN sessions s ON s.id=r.session_id
                        WHERE s.course_id=? AND r.status='pending' LIMIT 1""", (course_id,)).fetchone():
                        raise HTTPException(409, "Wait for pending guided or chat feedback before moving this course to trash")
                conn.execute("INSERT INTO course_trash(course_id,trashed_at,trashed_by) VALUES(?,?,?)", (course_id, now(), user["id"]))
            return course_details(conn, row)

    @app.post("/api/courses/{course_id}/restore")
    def restore(course_id: str, payload: m.Empty, user=Depends(teacher_user)):
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = owner_metadata(conn, course_id, user)
            conn.execute("DELETE FROM course_trash WHERE course_id=?", (course_id,))
            return course_details(conn, row)
