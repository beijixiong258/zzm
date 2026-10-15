"""Repeatable, transactional stage-2 migration of the actual previous SQLite schema."""
import json
from .versions import publish

LEARNING = {
    "workspaces": """session_id TEXT NOT NULL REFERENCES sessions(id), user_id TEXT NOT NULL REFERENCES users(id),
 selected_reading TEXT, status TEXT NOT NULL DEFAULT 'not_started', submitted_at TEXT,
 reviewed_at TEXT, teacher_note TEXT NOT NULL DEFAULT '', last_active TEXT, version_id TEXT NOT NULL DEFAULT '',
 PRIMARY KEY(session_id,user_id,version_id)""",
    "attempts": """session_id TEXT NOT NULL, user_id TEXT NOT NULL, question_id TEXT NOT NULL,
 answer TEXT NOT NULL, updated_at TEXT NOT NULL, reference_revealed INTEGER NOT NULL DEFAULT 0,
 version_id TEXT NOT NULL DEFAULT '', PRIMARY KEY(session_id,user_id,version_id,question_id),
 FOREIGN KEY(session_id,user_id,version_id) REFERENCES workspaces(session_id,user_id,version_id)""",
    "revisions": """id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, user_id TEXT NOT NULL,
 question_id TEXT NOT NULL, answer TEXT NOT NULL, created_at TEXT NOT NULL, version_id TEXT NOT NULL DEFAULT '',
 FOREIGN KEY(session_id,user_id,version_id,question_id) REFERENCES attempts(session_id,user_id,version_id,question_id)""",
    "messages": """seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL, session_id TEXT NOT NULL,
 user_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, question_id TEXT,
 created_at TEXT NOT NULL, mode TEXT NOT NULL, intent TEXT, citations_json TEXT NOT NULL DEFAULT '[]',
 version_id TEXT NOT NULL DEFAULT '', FOREIGN KEY(session_id,user_id,version_id) REFERENCES workspaces(session_id,user_id,version_id)""",
    "chat_requests": """session_id TEXT NOT NULL, user_id TEXT NOT NULL, request_id TEXT NOT NULL,
 fingerprint TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, version_id TEXT NOT NULL DEFAULT '',
 PRIMARY KEY(session_id,user_id,version_id,request_id),
 FOREIGN KEY(session_id,user_id,version_id) REFERENCES workspaces(session_id,user_id,version_id)""",
}


def add_column(conn, table, column, spec):
    if column not in {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {spec}")


def baseline_versions(conn):
    for c in conn.execute("SELECT * FROM courses WHERE published_version_id IS NULL").fetchall():
        details = [json.loads(r[0]) for r in conn.execute("SELECT content_json FROM sessions WHERE course_id=?", (c["id"],))]
        if any(s.get("status") == "published" for s in details):
            publish(conn, c["id"], c["owner_id"], "Initial edition")


def migrate(conn):
    if conn.execute("SELECT 1 FROM meta WHERE key='stage2_schema'").fetchone():
        add_column(conn, "sessions", "in_draft", "INTEGER NOT NULL DEFAULT 1")
        return
    # SQLite cannot change CHECK constraints or composite PKs in place. Rebuild
    # under one explicit transaction, with all original rows copied by column name.
    conn.commit()
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        conn.execute("BEGIN IMMEDIATE")
        add_column(conn, "users", "must_change_password", "INTEGER NOT NULL DEFAULT 0")
        add_column(conn, "users", "archived_at", "TEXT")
        add_column(conn, "users", "purge_at", "TEXT")
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()[0]
        sql = sql.replace("CREATE TABLE users", "CREATE TABLE users_stage2").replace("CREATE TABLE IF NOT EXISTS users", "CREATE TABLE users_stage2")
        sql = sql.replace("'teacher','student'", "'teacher','student','admin'")
        conn.execute(sql)
        conn.execute("INSERT INTO users_stage2 SELECT * FROM users")
        conn.execute("DROP TABLE users")
        conn.execute("ALTER TABLE users_stage2 RENAME TO users")
        for t in ("users", "enrollments"):
            add_column(conn, t, "archived_at", "TEXT")
            add_column(conn, t, "purge_at", "TEXT")
        add_column(conn, "courses", "published_version_id", "TEXT")
        add_column(conn, "sessions", "in_draft", "INTEGER NOT NULL DEFAULT 1")
        for column, spec in (("active", "INTEGER NOT NULL DEFAULT 1"), ("starts_at", "TEXT"), ("ends_at", "TEXT")):
            add_column(conn, "sessions", column, spec)
        conn.execute("""CREATE TABLE course_versions (
 id TEXT PRIMARY KEY, course_id TEXT NOT NULL REFERENCES courses(id), number INTEGER NOT NULL,
 label TEXT NOT NULL, created_at TEXT NOT NULL, created_by TEXT, snapshot_json TEXT NOT NULL,
 UNIQUE(course_id,number))""")
        baseline_versions(conn)
        for table, definition in LEARNING.items():
            columns = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]
            conn.execute(f"CREATE TABLE {table}_stage2 ({definition})")
            names = ",".join(columns)
            # Bind genuine legacy student records to the saved original snapshot.
            expression = """coalesce((SELECT c.published_version_id FROM sessions s JOIN courses c ON c.id=s.course_id
 WHERE s.id=old.session_id AND (SELECT role FROM users WHERE id=old.user_id)='student'),'')"""
            conn.execute(f"INSERT INTO {table}_stage2({names},version_id) SELECT {names},{expression} FROM {table} old")
            conn.execute(f"DROP TABLE {table}")
            conn.execute(f"ALTER TABLE {table}_stage2 RENAME TO {table}")
        conn.execute("CREATE INDEX messages_workspace ON messages(session_id,user_id,version_id,seq)")
        conn.execute("CREATE INDEX revisions_workspace ON revisions(session_id,user_id,version_id,question_id,id)")
        conn.execute("""CREATE TABLE import_staging (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), course_id TEXT NOT NULL REFERENCES courses(id),
 session_id TEXT REFERENCES sessions(id), kind TEXT NOT NULL, expires_at TEXT NOT NULL, payload_json TEXT NOT NULL)""")
        # Snapshots are immutable even for accidental direct SQL updates.
        conn.execute("CREATE TRIGGER immutable_version_update BEFORE UPDATE ON course_versions BEGIN SELECT RAISE(ABORT,'Course versions are immutable'); END")
        conn.execute("CREATE TRIGGER immutable_version_delete BEFORE DELETE ON course_versions BEGIN SELECT RAISE(ABORT,'Course versions are immutable'); END")
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise ValueError("Stage-2 migration found inconsistent legacy foreign keys; original transaction restored")
        conn.execute("INSERT INTO meta VALUES('stage2_schema','2')")
        conn.execute("PRAGMA user_version=2")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute("PRAGMA foreign_keys=ON")
