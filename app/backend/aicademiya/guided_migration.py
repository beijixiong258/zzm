"""Additive stage-3 migration: never rewrite old content or learning records."""
from .migrations import add_column


def migrate_guided(conn):
    conn.execute("SAVEPOINT stage3")
    try:
        add_column(conn, "messages", "metadata_json", "TEXT NOT NULL DEFAULT '{}'")
        conn.execute("""CREATE TABLE IF NOT EXISTS tutor_runs (
          session_id TEXT NOT NULL, user_id TEXT NOT NULL, version_id TEXT NOT NULL,
          state_json TEXT NOT NULL,
          PRIMARY KEY(session_id,user_id,version_id),
          FOREIGN KEY(session_id,user_id,version_id) REFERENCES workspaces(session_id,user_id,version_id) ON DELETE CASCADE)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS tutor_requests (
          session_id TEXT NOT NULL, user_id TEXT NOT NULL, version_id TEXT NOT NULL,
          request_id TEXT NOT NULL, fingerprint TEXT NOT NULL, status TEXT NOT NULL,
          created_at TEXT NOT NULL, plan_json TEXT NOT NULL,
          PRIMARY KEY(session_id,user_id,version_id,request_id),
          FOREIGN KEY(session_id,user_id,version_id) REFERENCES workspaces(session_id,user_id,version_id) ON DELETE CASCADE)""")
        conn.execute("INSERT OR IGNORE INTO meta VALUES('stage3_schema','3')")
        conn.execute("PRAGMA user_version=3")
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Stage-3 migration found inconsistent foreign keys; original transaction retained")
        conn.execute("RELEASE stage3")
    except Exception:
        conn.execute("ROLLBACK TO stage3")
        conn.execute("RELEASE stage3")
        raise
