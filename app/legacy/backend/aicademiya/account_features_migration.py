"""Stage9 additive account features; retain every original table/row unchanged."""


def migrate_account_features(conn):
    conn.execute("SAVEPOINT account_features")
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS account_avatars (
            user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            content BLOB NOT NULL,
            sha256 TEXT NOT NULL,
            updated_at TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS feedback (
            id TEXT PRIMARY KEY,
            author_id TEXT REFERENCES users(id) ON DELETE SET NULL,
            request_id TEXT NOT NULL,
            category TEXT NOT NULL CHECK(category IN ('bug','idea','general')),
            subject TEXT NOT NULL,
            message TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'new' CHECK(status IN ('new','reviewed')),
            reply TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            revision INTEGER NOT NULL DEFAULT 1 CHECK(revision >= 1),
            UNIQUE(author_id,request_id))""")
        conn.execute("PRAGMA user_version=7")
        conn.execute("RELEASE account_features")
    except Exception:
        conn.execute("ROLLBACK TO account_features")
        conn.execute("RELEASE account_features")
        raise
