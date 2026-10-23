"""Actual stage-2 schema preservation, stage-3 backup/restore and recovery."""
import json
import sqlite3
from contextlib import closing
from fastapi.testclient import TestClient
from backend.aicademiya.guided_migration import migrate_guided
from backend.aicademiya.main import create_app
from backend.aicademiya.roster import purge_learning
from .conftest import expect
from .test_stage2_backup import backup_tool
from .test_stage3_guided import configure, start, turn, ProtocolFixture, use_fixture


def records(conn):
    names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    return {name: {"columns": [r[1] for r in conn.execute(f'PRAGMA table_info("{name}")')], "rows": [tuple(r) for r in conn.execute(f'SELECT * FROM "{name}" ORDER BY rowid')]} for name in names}


def downgrade_synthetic_schema(conn):
    """Create the genuine previous table layout, not a guessed migration stub."""
    conn.execute("DROP TABLE tutor_requests")
    conn.execute("DROP TABLE tutor_runs")
    conn.execute("ALTER TABLE messages DROP COLUMN metadata_json")
    conn.execute("DELETE FROM meta WHERE key='stage3_schema'")
    conn.execute("PRAGMA user_version=2")


def test_stage2_to_stage3_preserves_all_named_columns_and_secret(app, teacher, student, catalog):
    old = expect(student.get("/api/sessions/s4/workspace"))["version"]["id"]
    expect(student.post(f"/api/sessions/s4/answers/q1?version_id={old}", json={"answer": "Synthetic old response"}))
    expect(student.post(f"/api/sessions/s4/chat?version_id={old}", json={"message": "Old clarification", "intent": "ask", "question_id": "q1", "request_id": "old-request"}))
    expect(student.post(f"/api/sessions/s4/references/q1?version_id={old}"))
    with app.state.database.connect() as conn:
        conn.execute("INSERT OR REPLACE INTO meta VALUES('kv_scope_secret',?)", ("12" * 32,))
        conn.execute("INSERT OR REPLACE INTO settings VALUES('ai_api_key','SYNTHETIC_ONLY_MIGRATION_KEY')")
        conn.execute("UPDATE users SET password_hash='SYNTHETIC_HASH_PRESERVE' WHERE id='demo-student-1'")
        downgrade_synthetic_schema(conn)
        before = records(conn)
    app.state.database.initialize(catalog, demo_enabled=True)
    app.state.database.initialize(catalog, demo_enabled=True)
    with app.state.database.connect() as conn:
        after = records(conn)
        for table, evidence in before.items():
            names = ",".join('"' + x + '"' for x in evidence["columns"])
            original_projection = [tuple(r) for r in conn.execute(f'SELECT {names} FROM "{table}"' + (" WHERE key<>'stage3_schema'" if table == "meta" else "") + " ORDER BY rowid")]
            assert original_projection == evidence["rows"], table
        assert after["tutor_runs"]["rows"] == [] and after["tutor_requests"]["rows"] == []
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 9
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        assert conn.execute("SELECT snapshot_json FROM course_versions WHERE id=?", (old,)).fetchone()[0] == next(r[-1] for r in before["course_versions"]["rows"] if r[0] == old)
    work = start(student, old)
    assert work["attempts"]["q1"]["answer"] == "Synthetic old response" and work["attempts"]["q1"]["reference_revealed"]
    assert work["tutor"]["question_states"]["q1"]["last_outcome"] == "unknown"


def test_migration_fk_failure_rolls_back_additions(app, teacher, student):
    with app.state.database.connect() as conn:
        downgrade_synthetic_schema(conn)
    with closing(sqlite3.connect(app.state.database.path)) as conn, conn:
        conn.row_factory = sqlite3.Row
        # Explicitly corrupt ONLY the disposable synthetic migration fixture.
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("INSERT INTO auth_sessions VALUES('synthetic-invalid','absent-user','2099-01-01')")
        try:
            migrate_guided(conn)
        except ValueError as exc:
            assert "inconsistent foreign keys" in str(exc)
        else:
            raise AssertionError("Invalid migration should not succeed")
        assert "metadata_json" not in {r[1] for r in conn.execute("PRAGMA table_info(messages)")}
        assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name='tutor_runs'").fetchone()
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
        conn.execute("DELETE FROM auth_sessions WHERE token_hash='synthetic-invalid'")
    app.state.database.initialize(app.state.catalog_path, demo_enabled=True)


def test_backup_restore_guided_keys_requests_transcript_and_resume(app, teacher, student, catalog, tmp_path):
    vid = configure(teacher, count=1)
    start(student, vid)
    expect(turn(student, vid, "Because public evidence", "worksheet"))
    work = expect(turn(student, vid, "yes", "quiz-accept"))
    work = expect(turn(student, vid, "1", "quiz-answer"))
    root = app.state.database.path.parent
    with app.state.database.connect() as conn:
        secret = app.state.tutor.kv_scope(work["user"], "synthetic-backup", "test")
        before = records(conn)
        for row in conn.execute("SELECT plan_json FROM tutor_requests"):
            plan = json.loads(row[0])
            assert "_materials" not in plan["detail"]
    backup, restored = tmp_path / "stage3-backup", tmp_path / "stage3-restore"
    backup_tool.backup(root, backup, catalog.parent / "materials")
    report = backup_tool.restore(backup, restored)
    assert report["records_match"] and report["files_match"]
    with closing(sqlite3.connect(restored / backup_tool.DB_NAME)) as conn:
        # File relocation belongs only to the pre-existing material/snapshot
        # bindings. New guided tables are preserved byte-for-byte.
        for name in ("tutor_runs", "tutor_requests", "messages", "attempts", "revisions", "meta", "users", "settings", "workspaces"):
            assert [tuple(r) for r in conn.execute(f'SELECT * FROM "{name}" ORDER BY rowid')] == before[name]["rows"]
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 9
    hidden = root.with_name("synthetic-source-unavailable")
    root.rename(hidden)
    try:
        restored_app = create_app(data_dir=restored, catalog_path=catalog, demo_enabled=True, frontend_dir=tmp_path / "no-frontend")
        with TestClient(restored_app) as reader:
            reader.cookies.update(student.cookies)
            resumed = expect(reader.post(f"/api/sessions/s4/tutor/start?version_id={vid}", json={}))
            assert resumed["tutor"] == work["tutor"] and resumed["messages"] == work["messages"]
            assert restored_app.state.tutor.kv_scope(work["user"], "synthetic-backup", "test") == secret
            for i in range(1, 5):
                resumed = expect(turn(reader, vid, "1", f"remaining-{i}"))
            assert resumed["tutor"]["quiz"]["answered"] == 5 and resumed["tutor"]["phase"] == "reading"
            assert reader.get(f"/api/sessions/s4/transcript?version_id={vid}&format=txt").status_code == 200
            material = next(m for m in resumed["session"]["materials"] if m.get("download_url"))
            assert reader.get(material["download_url"]).status_code == 200
    finally:
        hidden.rename(root)


def test_startup_recovers_only_pending_then_same_id_retry(app, teacher, student, tmp_path, catalog):
    vid = configure(teacher, phases=["worksheet", "wrap_up"], count=1)
    fixture = ProtocolFixture()
    use_fixture(app, student, fixture)
    start(student, vid)
    fixture.overrides.append(http_error())
    expect(turn(student, vid, "Recoverable raw response", "crash-retry"), 502)
    with app.state.database.connect() as conn:
        conn.execute("UPDATE tutor_requests SET status='pending' WHERE request_id='crash-retry'")
    resumed_app = create_app(data_dir=app.state.database.path.parent, catalog_path=catalog, demo_enabled=True, frontend_dir=tmp_path / "none", ai_transport=fixture_transport(fixture))
    with TestClient(resumed_app) as client:
        client.cookies.update(student.cookies)
        resumed = expect(client.get(f"/api/sessions/s4/workspace?version_id={vid}"))
        assert resumed["tutor"]["pending_request_id"] is None
        done = expect(turn(client, vid, "Recoverable raw response", "crash-retry"))
        assert len(done["messages"]) == 3 and done["attempts"]["q1"]["answer"] == "Recoverable raw response"


def http_error():
    import httpx
    return httpx.Response(503, text="Synthetic unavailable provider")


def fixture_transport(fixture):
    import httpx
    return httpx.MockTransport(fixture.handle)


def test_scoped_retention_includes_guided_state_without_curriculum_deletion(app, teacher, student):
    vid = configure(teacher, phases=["worksheet", "wrap_up"], count=1)
    start(student, vid)
    expect(turn(student, vid, "Because evidence", "retention"))
    with app.state.database.connect() as conn:
        snapshots = [tuple(r) for r in conn.execute("SELECT * FROM course_versions")]
        purge_learning(conn, "demo-student-1", "synthetic-course")
        assert not conn.execute("SELECT 1 FROM tutor_runs WHERE user_id='demo-student-1'").fetchone()
        assert not conn.execute("SELECT 1 FROM tutor_requests WHERE user_id='demo-student-1'").fetchone()
        assert [tuple(r) for r in conn.execute("SELECT * FROM course_versions")] == snapshots
        assert conn.execute("SELECT 1 FROM materials").fetchone()
