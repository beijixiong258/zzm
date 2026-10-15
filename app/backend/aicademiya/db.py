"""SQLite persistence, explicit seed import, and local credentials."""
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

LOG = logging.getLogger(__name__)


def now():
    return datetime.now(timezone.utc).isoformat()


def new_id():
    return secrets.token_hex(16)


def password_hash(password):
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return f"scrypt${salt}${digest}"


def password_matches(password, encoded):
    try:
        _, salt, expected = encoded.split("$")
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('teacher','student')), password_hash TEXT,
 is_demo INTEGER NOT NULL DEFAULT 0,
 must_change_password INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS auth_sessions (
 token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS courses (
 id TEXT PRIMARY KEY, code TEXT NOT NULL, title TEXT NOT NULL, description TEXT NOT NULL,
 owner_id TEXT REFERENCES users(id), join_code TEXT UNIQUE NOT NULL
);
CREATE TABLE IF NOT EXISTS enrollments (
 course_id TEXT NOT NULL REFERENCES courses(id), user_id TEXT NOT NULL REFERENCES users(id),
 PRIMARY KEY(course_id,user_id)
);
CREATE TABLE IF NOT EXISTS sessions (
 id TEXT PRIMARY KEY, course_id TEXT NOT NULL REFERENCES courses(id), content_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS materials (
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), content_json TEXT NOT NULL,
 file_path TEXT, archived INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS workspaces (
 session_id TEXT NOT NULL REFERENCES sessions(id), user_id TEXT NOT NULL REFERENCES users(id),
 selected_reading TEXT, status TEXT NOT NULL DEFAULT 'not_started', submitted_at TEXT,
 reviewed_at TEXT, teacher_note TEXT NOT NULL DEFAULT '', last_active TEXT,
 PRIMARY KEY(session_id,user_id)
);
CREATE TABLE IF NOT EXISTS attempts (
 session_id TEXT NOT NULL, user_id TEXT NOT NULL, question_id TEXT NOT NULL,
 answer TEXT NOT NULL, updated_at TEXT NOT NULL, reference_revealed INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(session_id,user_id,question_id),
 FOREIGN KEY(session_id,user_id) REFERENCES workspaces(session_id,user_id)
);
CREATE TABLE IF NOT EXISTS revisions (
 id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, user_id TEXT NOT NULL,
 question_id TEXT NOT NULL, answer TEXT NOT NULL, created_at TEXT NOT NULL,
 FOREIGN KEY(session_id,user_id,question_id) REFERENCES attempts(session_id,user_id,question_id)
);
CREATE TABLE IF NOT EXISTS messages (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL, session_id TEXT NOT NULL,
 user_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, question_id TEXT,
 created_at TEXT NOT NULL, mode TEXT NOT NULL, intent TEXT, citations_json TEXT NOT NULL DEFAULT '[]',
 FOREIGN KEY(session_id,user_id) REFERENCES workspaces(session_id,user_id)
);
CREATE TABLE IF NOT EXISTS chat_requests (
 session_id TEXT NOT NULL, user_id TEXT NOT NULL, request_id TEXT NOT NULL,
 fingerprint TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
 PRIMARY KEY(session_id,user_id,request_id)
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS messages_workspace ON messages(session_id,user_id,seq);
CREATE INDEX IF NOT EXISTS revisions_workspace ON revisions(session_id,user_id,question_id,id);
"""


class Database:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self, catalog_path, demo_enabled=False):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)
            from .material_library import migrate_material_library
            migrate_material_library(conn)
            from .migrations import migrate, baseline_versions
            migrate(conn)
            from .guided_migration import migrate_guided
            migrate_guided(conn)
            from .teacher_preview import migrate_previews
            migrate_previews(conn)
            from .course_lifecycle import migrate_course_lifecycle
            migrate_course_lifecycle(conn)
            from .account_features_migration import migrate_account_features
            migrate_account_features(conn)
            from .course_staff import migrate_staff, establish_assignment
            migrate_staff(conn)
            from .document_storage import migrate_documents
            migrate_documents(conn)
            if demo_enabled:
                for uid, role, name in [
                    ("demo-teacher", "teacher", "Demo Teacher"),
                    ("demo-student-1", "student", "Demo Student 1"),
                    ("demo-student-2", "student", "Demo Student 2"),
                    ("demo-admin", "admin", "Demo Admin"),
                ]:
                    conn.execute("INSERT OR IGNORE INTO users(id,name,email,role,is_demo) VALUES(?,?,?,?,1)",
                                 (uid, name, f"{uid}@example.invalid", role))
            if not conn.execute("SELECT 1 FROM meta WHERE key='catalog_imported'").fetchone():
                path = Path(catalog_path)
                if not path.is_file():
                    LOG.warning("Sample catalog missing at %s; courses can still be authored. Supply sample_data/catalog.json.", path)
                else:
                    self._seed(conn, path, demo_enabled)
                    baseline_versions(conn)
            if demo_enabled:
                claimed = conn.execute("UPDATE courses SET owner_id='demo-teacher' WHERE owner_id IS NULL RETURNING id").fetchall()
                for row in claimed:
                    establish_assignment(conn, row[0], 'demo-teacher')
                seeded = conn.execute("SELECT value FROM meta WHERE key='seed_course_id'").fetchone()
                if seeded and conn.execute("SELECT 1 FROM courses WHERE id=? AND owner_id='demo-teacher'", (seeded[0],)).fetchone():
                    for uid in ("demo-student-1", "demo-student-2"):
                        conn.execute("INSERT OR IGNORE INTO enrollments(course_id,user_id) VALUES(?,?)", (seeded[0], uid))

    def _seed(self, conn, path, demo_enabled):
        catalog = json.loads(path.read_text(encoding="utf-8-sig"))
        if catalog.get("schema_version") != 1:
            raise ValueError("Unsupported sample catalog schema_version")
        course = catalog["course"]
        teacher = conn.execute("SELECT id FROM users WHERE role='teacher' AND is_demo=0 LIMIT 1").fetchone()
        owner = teacher[0] if teacher else ("demo-teacher" if demo_enabled else None)
        conn.execute("INSERT OR IGNORE INTO courses(id,code,title,description,owner_id,join_code) VALUES(?,?,?,?,?,?)", (
            course["id"], course["code"], course["title"], course.get("description", ""), owner,
            secrets.token_urlsafe(8)))
        if owner:
            from .course_staff import establish_assignment
            establish_assignment(conn, course['id'], owner)
        for session in catalog["sessions"]:
            detail = dict(session)
            materials = detail.pop("materials", [])
            detail["course_id"] = course["id"]
            conn.execute("INSERT OR IGNORE INTO sessions(id,course_id,content_json) VALUES(?,?,?)", (detail["id"], course["id"], json.dumps(detail)))
            for material in materials:
                item = dict(material)
                relative = item.pop("file_path", None)
                file_path = None
                if relative:
                    resolved = (path.parent / relative).resolve()
                    if not resolved.is_relative_to(path.parent.resolve() / "materials"):
                        raise ValueError("Seed material must be under sample_data/materials")
                    file_path = str(resolved)
                conn.execute("INSERT OR IGNORE INTO materials VALUES(?,?,?,?,0)", (
                    item["id"], detail["id"], json.dumps(item), file_path))
        conn.execute("INSERT INTO meta VALUES('catalog_imported',?)", (now(),))
        conn.execute("INSERT INTO meta VALUES('seed_course_id',?)", (course["id"],))

    def create_teacher(self, name, email, password):
        from .models import validate_new_password
        validate_new_password(password)
        with self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            uid = new_id()
            conn.execute("INSERT INTO users(id,name,email,role,password_hash) VALUES(?,?,?,'teacher',?)",
                         (uid, name, email.strip().lower(), password_hash(password)))
            from .course_staff import establish_assignment
            for row in conn.execute("UPDATE courses SET owner_id=? WHERE owner_id IS NULL RETURNING id", (uid,)).fetchall():
                establish_assignment(conn, row[0], uid)
            return uid

    def create_admin(self, name, email, password):
        from .models import validate_new_password
        validate_new_password(password)
        if not name.strip() or not 1 <= len(name.strip()) <= 100 or "@" not in email or " " in email or len(email) > 254:
            raise ValueError("Provide a name and valid email")
        with self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            uid = new_id()
            conn.execute("INSERT INTO users(id,name,email,role,password_hash) VALUES(?,?,?,'admin',?)",
                         (uid, name.strip(), email.strip().lower(), password_hash(password)))
            # Bootstrap only the unassigned seed; never take another teacher's course.
            from .course_staff import establish_assignment
            for row in conn.execute("UPDATE courses SET owner_id=? WHERE owner_id IS NULL AND id=(SELECT value FROM meta WHERE key='seed_course_id') RETURNING id", (uid,)).fetchall():
                establish_assignment(conn, row[0], uid)
            return uid

    def promote_teacher(self, email):
        with self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute("SELECT * FROM users WHERE email=? AND role='teacher' AND archived_at IS NULL", (email.strip().lower(),)).fetchone()
            if not row:
                raise ValueError("An active teacher with that email is required")
            conn.execute("UPDATE users SET role='admin' WHERE id=?", (row["id"],))
            conn.execute("DELETE FROM auth_sessions WHERE user_id=?", (row["id"],))
            return row["id"]


def issue_session(conn, uid):
    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode()).hexdigest()
    expires = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    conn.execute("INSERT INTO auth_sessions VALUES(?,?,?)", (digest, uid, expires))
    return token


def public_user(row, conn=None):
    result = {**{key: row[key] for key in ("id", "name", "email", "role")},
              "must_change_password": bool(row["must_change_password"]), "is_demo": bool(row["is_demo"])}
    if conn is not None:
        from .account_avatars import avatar_url
        result["avatar_url"] = avatar_url(conn, row["id"])
    return result
