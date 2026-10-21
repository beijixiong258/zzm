"""Course-file identity and explicit session draft memberships.

materials.session_id is retained origin provenance, never membership authority.
The insert trigger covers legacy positional INSERT callers without schema churn.
"""
from fastapi import HTTPException


def migrate_material_origin(conn):
    if not next(r for r in conn.execute("PRAGMA table_info(materials)") if r["name"] == "session_id")["notnull"]:
        return
    # Initialization calls this before any data transaction. Do not rename the old
    # table: SQLite would rewrite foreign keys in dependent tables to that name.
    if conn.in_transaction:
        raise RuntimeError("Material origin migration requires an idle connection")
    objects = [r[0] for r in conn.execute("SELECT sql FROM sqlite_master WHERE tbl_name='materials' AND type IN ('index','trigger') AND sql IS NOT NULL")]
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("""CREATE TABLE materials_origin_nullable (
            id TEXT PRIMARY KEY, session_id TEXT REFERENCES sessions(id), content_json TEXT NOT NULL,
            file_path TEXT, archived INTEGER NOT NULL DEFAULT 0)""")
        conn.execute("INSERT INTO materials_origin_nullable(rowid,id,session_id,content_json,file_path,archived) SELECT rowid,id,session_id,content_json,file_path,archived FROM materials")
        conn.execute("DROP TABLE materials")
        conn.execute("ALTER TABLE materials_origin_nullable RENAME TO materials")
        for sql in objects:
            conn.execute(sql)
        if conn.execute("PRAGMA foreign_key_check").fetchone():
            raise RuntimeError("Material origin migration found invalid references")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys=ON")


def migrate_material_library(conn):
    # Runs before stage-2's baseline snapshot, and also on existing stage-3 DBs.
    conn.execute("SAVEPOINT stage4_materials")
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS material_courses (
            material_id TEXT PRIMARY KEY REFERENCES materials(id),
            course_id TEXT NOT NULL REFERENCES courses(id))""")
        conn.execute("CREATE INDEX IF NOT EXISTS material_courses_course ON material_courses(course_id,material_id)")
        conn.execute("""CREATE TABLE IF NOT EXISTS session_materials (
            session_id TEXT NOT NULL REFERENCES sessions(id),
            material_id TEXT NOT NULL REFERENCES materials(id),
            PRIMARY KEY(session_id,material_id))""")
        conn.execute("CREATE INDEX IF NOT EXISTS session_materials_material ON session_materials(material_id,session_id)")
        conn.execute("""CREATE TRIGGER IF NOT EXISTS material_membership_same_course
            BEFORE INSERT ON session_materials
            WHEN NOT EXISTS (
                SELECT 1 FROM sessions s JOIN material_courses c ON c.course_id=s.course_id
                WHERE s.id=NEW.session_id AND c.material_id=NEW.material_id)
            BEGIN SELECT RAISE(ABORT,'Material membership must remain in its course'); END""")
        conn.execute("DROP TRIGGER IF EXISTS material_library_insert")
        conn.execute("""CREATE TRIGGER material_library_insert
            AFTER INSERT ON materials BEGIN
                INSERT INTO material_courses(material_id,course_id)
                    SELECT NEW.id,course_id FROM sessions WHERE id=NEW.session_id;
                INSERT INTO session_materials(session_id,material_id)
                    SELECT NEW.session_id,NEW.id WHERE NEW.archived=0 AND NEW.session_id IS NOT NULL;
            END""")
        if not conn.execute("SELECT 1 FROM meta WHERE key='stage4_material_library'").fetchone():
            conn.execute("""INSERT INTO material_courses(material_id,course_id)
                SELECT m.id,s.course_id FROM materials m JOIN sessions s ON s.id=m.session_id""")
            conn.execute("""INSERT INTO session_materials(session_id,material_id)
                SELECT session_id,id FROM materials WHERE archived=0""")
            conn.execute("INSERT INTO meta VALUES('stage4_material_library','1')")
        conn.execute("RELEASE stage4_materials")
    except Exception:
        conn.execute("ROLLBACK TO stage4_materials")
        conn.execute("RELEASE stage4_materials")
        raise


def session_material_rows(conn, sid):
    return conn.execute("""SELECT m.* FROM materials m
        JOIN session_materials sm ON sm.material_id=m.id
        JOIN sessions s ON s.id=sm.session_id
        JOIN material_courses c ON c.material_id=m.id AND c.course_id=s.course_id
        WHERE sm.session_id=? AND s.in_draft=1 AND m.archived=0 ORDER BY m.rowid""", (sid,)).fetchall()


def member_material(conn, sid, mid):
    row = next((r for r in session_material_rows(conn, sid) if r['id'] == mid), None)
    if not row:
        raise HTTPException(404, "Material not found in this session draft")
    return row


def course_material_rows(conn, cid):
    return conn.execute("""SELECT m.* FROM materials m
        JOIN material_courses c ON c.material_id=m.id
        WHERE c.course_id=? AND m.archived=0 ORDER BY m.rowid""", (cid,)).fetchall()


def course_material(conn, cid, mid):
    row = next((r for r in course_material_rows(conn, cid) if r["id"] == mid), None)
    if not row:
        raise HTTPException(404, "Course material not found")
    return row


def linked_session_ids(conn, mid):
    return [r[0] for r in conn.execute("""SELECT s.id FROM sessions s
        JOIN session_materials sm ON sm.session_id=s.id
        WHERE sm.material_id=? AND s.in_draft=1 ORDER BY s.rowid""", (mid,))]


def attach_material(conn, sid, mid, cid):
    row = conn.execute("""SELECT m.*,c.course_id FROM materials m
        JOIN material_courses c ON c.material_id=m.id WHERE m.id=? AND m.archived=0""", (mid,)).fetchone()
    if not row:
        raise HTTPException(404, "Course material not found")
    if row['course_id'] != cid:
        raise HTTPException(422, "Material must belong to the same course")
    conn.execute("INSERT OR IGNORE INTO session_materials(session_id,material_id) VALUES(?,?)", (sid, mid))
    return row


def detach_material(conn, sid, mid):
    conn.execute("DELETE FROM session_materials WHERE session_id=? AND material_id=?", (sid, mid))
