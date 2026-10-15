"""Stage9 genuine21-table migration, FK purge and real BLOB CLI/HTTP restarts."""
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.aicademiya.account_features_migration import migrate_account_features
from backend.aicademiya.db import Database
from backend.aicademiya.main import COOKIE_NAME
from backend.aicademiya.roster import maintenance
from .conftest import expect, publish
from .test_stage2_backup import backup_tool, worksheet_docx, commit_payload
from .test_stage3_persistence import records
from .test_stage8_course_lifecycle import schema, files
from .test_stage9_account_avatars import image_bytes, upload
from .test_stage9_feedback import create, patch

APP_ROOT = Path(__file__).resolve().parents[2]


def old_stage8(conn):
    # Only the new empty tables are removed; actual Stage8 columns, constraints,
    # indexes, triggers and data are retained, not synthesized approximations.
    assert conn.execute("SELECT count(*) FROM account_avatars").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM feedback").fetchone()[0] == 0
    conn.execute("DROP TABLE account_avatars")
    conn.execute("DROP TABLE feedback")
    conn.execute("PRAGMA user_version=6")


def test_old21_tables_all_populated_preserved_no_backfill_repeat_startup(app, teacher, student, catalog, tmp_path):
    preview = expect(teacher.post("/api/sessions/s4/worksheet-import/preview", files={"file": ("synthetic.docx", worksheet_docx())}))
    expect(teacher.post(f"/api/sessions/s4/worksheet-import/{preview['import_id']}/commit", json=commit_payload(preview)))
    first = publish(teacher)["id"]
    work = expect(student.get(f"/api/sessions/s4/workspace?version_id={first}"))
    qid = work["session"]["questions"][0]["id"]
    for answer in ("Old answer", "Old revised answer"):
        expect(student.post(f"/api/sessions/s4/answers/{qid}?version_id={first}", json={"answer": answer}))
    expect(student.post(f"/api/sessions/s4/chat?version_id={first}", json={"message": "Saved synthetic history", "intent": "ask", "request_id": "old-chat"}))
    expect(student.post(f"/api/sessions/s4/tutor/start?version_id={first}", json={"request_id": "old-guided"}))
    info = expect(teacher.get("/api/teacher/sessions/s4/preview"))
    expect(teacher.post("/api/teacher/sessions/s4/preview/reset", json={"expected_revision": info["current_revision"]}))
    expect(teacher.post("/api/sessions/s4/worksheet-import/preview", files={"file": ("pending.docx", worksheet_docx())}))
    expect(teacher.post("/api/courses/synthetic-course/trash", json={}))
    with app.state.database.connect() as conn:
        conn.execute("INSERT OR REPLACE INTO settings VALUES('ai_api_key','SYNTHETIC_PRESERVE_ONLY')")
        conn.execute("INSERT OR REPLACE INTO meta VALUES('kv_scope_secret','SYNTHETIC_NAMESPACE_PRESERVE')")
        old_stage8(conn)
        original = {k: v for k, v in records(conn).items() if k not in ('course_staff','account_imports','document_jobs','document_revisions')}
        stage11_before = {k: v for k, v in records(conn).items() if k in ('course_staff','account_imports','document_jobs','document_revisions')}
        original_schema = schema(conn)
        seq = [tuple(r) for r in conn.execute("SELECT * FROM sqlite_sequence ORDER BY name")]
    assert len(original) == 21 and all(item["rows"] for item in original.values())
    original_files = files(catalog.parent) | {"data/" + k: v for k, v in files(app.state.database.path.parent).items()}
    for _ in range(2):
        app.state.database.initialize(catalog, demo_enabled=False)
        with app.state.database.connect() as conn:
            current = records(conn)
            assert len(current) == 27
            assert {k: current[k] for k in original} == original
            assert {k: current[k] for k in stage11_before} == stage11_before
            assert current["account_avatars"]["rows"] == [] and current["feedback"]["rows"] == []
            assert [item for item in schema(conn) if item[2] not in ("account_avatars", "feedback")] == original_schema
            assert [tuple(r) for r in conn.execute("SELECT * FROM sqlite_sequence ORDER BY name")] == seq
            assert conn.execute("PRAGMA user_version").fetchone()[0] == 9
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert not conn.execute("PRAGMA foreign_key_check").fetchall()
    assert files(catalog.parent) | {"data/" + k: v for k, v in files(app.state.database.path.parent).items()} == original_files
    assert app.version == app.openapi()["info"]["version"] == "0.11.0"
    assert expect(student.get("/api/auth/me"))["user"]["avatar_url"] is None
    assert expect(student.get("/api/feedback"))["total"] == 0
    report = {"old_tables": len(original), "old_tables_populated": all(item["rows"] for item in original.values()),
              "new_tables": len(current), "old_named_columns_rows_and_schema_equal": True,
              "new_tables_empty_no_backfill": True, "original_files_equal": True,
              "schema": 9, "integrity": "ok", "foreign_key_violations": 0}
    (tmp_path / "stage9-migration-evidence.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


@pytest.mark.parametrize("failure", ["second-table", "schema-version"])
def test_atomic_migration_failure_retains_old21_and_enclosing_transaction(app, teacher, failure):
    with app.state.database.connect() as conn:
        old_stage8(conn)
    with app.state.database.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("INSERT INTO settings VALUES('outer-transaction','preserve')")
        before, original_schema = records(conn), schema(conn)
        def authorize(action, arg1, arg2, dbname, trigger):
            denied = (failure == "second-table" and action == sqlite3.SQLITE_CREATE_TABLE and arg1 == "feedback") or (
                failure == "schema-version" and action == sqlite3.SQLITE_PRAGMA and arg1 == "user_version" and arg2 == "7")
            return sqlite3.SQLITE_DENY if denied else sqlite3.SQLITE_OK
        conn.set_authorizer(authorize)
        try:
            with pytest.raises(sqlite3.DatabaseError):
                migrate_account_features(conn)
        finally:
            conn.set_authorizer(None)
        assert records(conn) == before and schema(conn) == original_schema
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 6
        assert conn.in_transaction
        assert conn.execute("SELECT value FROM settings WHERE key='outer-transaction'").fetchone()[0] == "preserve"
        migrate_account_features(conn)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 7
        assert len(records(conn)) == 27


def test_global_purge_avatar_cascade_feedback_anonymizes_and_scoped_purge_preserves(student, teacher, admin, app):
    own = expect(create(student, message="Authored text must remain byte-for-byte"))
    own_url = expect(upload(student))["user"]["avatar_url"]
    other = expect(create(teacher))
    other_url = expect(upload(teacher))["user"]["avatar_url"]
    expect(student.post("/api/sessions/s4/tutor/start", json={"request_id": "purge-run"}))
    at = datetime.now(timezone.utc)
    past = (at - timedelta(days=31)).isoformat()
    deadline = (at - timedelta(days=1)).isoformat()
    with app.state.database.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("UPDATE enrollments SET archived_at=?,purge_at=? WHERE user_id='demo-student-1'", (past, deadline))
        scoped = maintenance(conn, at=at)
        assert scoped["accounts"] == [] and len(scoped["enrollments"]) == 1
        assert conn.execute("SELECT 1 FROM account_avatars WHERE user_id='demo-student-1'").fetchone()
        assert conn.execute("SELECT author_id FROM feedback WHERE id=?", (own["id"],)).fetchone()[0] == "demo-student-1"
        conn.execute("UPDATE users SET archived_at=?,purge_at=? WHERE id='demo-student-1'", (past, deadline))
        before = records(conn)
        dry = maintenance(conn, at=at, dry_run=True)
        assert dry["accounts"] == ["demo-student-1"] and records(conn) == before
        purged = maintenance(conn, at=at)
        assert purged["accounts"] == ["demo-student-1"]
        assert not conn.execute("SELECT 1 FROM users WHERE id='demo-student-1'").fetchone()
        assert not conn.execute("SELECT 1 FROM account_avatars WHERE user_id='demo-student-1'").fetchone()
        assert not conn.execute("SELECT 1 FROM auth_sessions WHERE user_id='demo-student-1'").fetchone()
        assert conn.execute("SELECT author_id FROM feedback WHERE id=?", (own["id"],)).fetchone()[0] is None
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
    anonymized = expect(admin.get("/api/admin/feedback/" + own["id"]))
    assert anonymized == {**own, "author": None}
    assert expect(patch(admin, own["id"], reply="Still retained for human review"))["author"] is None
    assert expect(admin.get("/api/admin/feedback/" + other["id"])) == other
    assert teacher.get(other_url).status_code == 200
    expect(teacher.get(own_url), 404)
    expect(student.get("/api/auth/me"), 401)
    expect(student.get("/api/feedback"), 401)
    assert expect(admin.get("/api/admin/feedback"))["total"] == 2


def cli(command, *args):
    result = subprocess.run([sys.executable, "-I", "-S", str(APP_ROOT / "tools" / "backup_data.py"), command, *map(str, args)],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@contextmanager
def http_server(data, catalog, log):
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    source = "import sys,uvicorn; from backend.aicademiya.main import create_app; uvicorn.run(create_app(data_dir=sys.argv[1],catalog_path=sys.argv[2],frontend_dir=sys.argv[3],demo_enabled=True),host='127.0.0.1',port=int(sys.argv[4]),log_level='warning')"
    env = os.environ.copy()
    env.update(AICADEMIYA_AI_MODE="demo", AICADEMIYA_WEB_SEARCH_ENABLED="false", AICADEMIYA_DEMO_ENABLED="true")
    env.pop("TAVILY_API_KEY", None)
    env.pop("AICADEMIYA_AI_API_KEY", None)
    with log.open("w", encoding="utf-8") as output:
        process = subprocess.Popen([sys.executable, "-c", source, str(data), str(catalog), str(data / "no-frontend"), str(port)],
                                   cwd=APP_ROOT, env=env, stdout=output, stderr=subprocess.STDOUT)
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10, trust_env=False) as client:
                deadline = time.monotonic() + 30
                while True:
                    assert process.poll() is None, f"Owned HTTP server exited; see {log}"
                    try:
                        if client.get("/api/health").status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    if time.monotonic() >= deadline:
                        raise AssertionError("Owned HTTP server health timed out")
                    time.sleep(0.05)
                yield client, process
        finally:
            if os.name == "nt":
                # A Windows venv launcher can own a separate Python child. End
                # this exact owned tree before the launcher loses its children.
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
            else:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=10)
            assert process.poll() is not None
    deadline = time.monotonic() + 5
    while True:
        with socket.socket() as check:
            check.settimeout(0.2)
            closed = check.connect_ex(("127.0.0.1", port)) != 0
        if closed:
            break
        assert time.monotonic() < deadline, "Owned listener survived cleanup"
        time.sleep(0.05)


def test_actual_blob_backup_restore_unavailable_sources_two_http_processes(student, teacher, admin, app, catalog, tmp_path):
    saved = expect(upload(student, image_bytes(metadata=True)))["user"]
    expect(upload(teacher, image_bytes("WEBP", color="red", metadata=True)))
    item = expect(create(student, category="bug", subject="Backup retained", message="Raw synthetic <text>\n remains"))
    reviewed = expect(patch(admin, item["id"], reply="Human reply survives restore"))
    source, backup, restored = app.state.database.path.parent, tmp_path / "backup", tmp_path / "restored"
    app.state.tutor.kv_scope(saved, "synthetic-stage9-backup", "test")
    with app.state.database.connect() as conn:
        before = records(conn)
        original_schema = schema(conn)
        secret = conn.execute("SELECT value FROM meta WHERE key='kv_scope_secret'").fetchone()[0]
        image = conn.execute("SELECT content FROM account_avatars WHERE user_id=?", (saved["id"],)).fetchone()[0]
    backup_result = cli("backup", "--data-dir", source, "--materials-root", catalog.parent / "materials", "--destination", backup)
    restore_result = cli("restore", "--source", backup, "--destination", restored)
    assert restore_result["records_match"] and restore_result["files_match"]
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["tables"]) == set(before) | {"sqlite_sequence"} and len(manifest["tables"]) == 28
    assert manifest["tables"]["account_avatars"]["count"] == 2
    assert manifest["tables"]["feedback"]["count"] == 1
    with closing(sqlite3.connect(restored / backup_tool.DB_NAME)) as conn:
        assert schema(conn) == original_schema
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 9
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        for table in before:
            if table not in ("materials", "course_versions", "import_staging"):
                assert [tuple(r) for r in conn.execute(f'SELECT * FROM "{table}" ORDER BY rowid')] == before[table]["rows"]
        assert conn.execute("SELECT typeof(content) FROM account_avatars LIMIT 1").fetchone()[0] == "blob"
    hidden_source, hidden_seed = source.with_name("unavailable-source"), catalog.parent.with_name("unavailable-seed")
    source.rename(hidden_source); catalog.parent.rename(hidden_seed)
    pids, states, stopped = [], [], []
    try:
        for index in range(2):
            with http_server(restored, catalog, tmp_path / f"stage9-http-{index}.log") as (client, process):
                pids.append(process.pid)
                client.cookies.set(COOKIE_NAME, student.cookies.get(COOKIE_NAME))
                me = expect(client.get("/api/auth/me"))["user"]
                assert client.get(me["avatar_url"]).status_code == 200
                assert expect(client.get("/api/feedback/requests/" + item["request_id"])) == reviewed
                assert expect(create(client, category="bug", subject="Backup retained", message="Raw synthetic <text>\n remains")) == reviewed
                assert expect(client.get("/api/feedback"))["total"] == 1
                if index == 0:
                    assert me == saved and client.get(saved["avatar_url"]).content == image
                    changed = expect(upload(client, image_bytes(color="blue")))["user"]
                    assert changed["avatar_url"] != saved["avatar_url"]
                    expect(client.get(saved["avatar_url"]), 404)
                    assert expect(client.get("/api/auth/me"))["user"] == changed
                else:
                    assert me == changed
                    expect(client.get(saved["avatar_url"]), 404)
                    removed = expect(client.delete("/api/auth/avatar"))["user"]
                    assert removed["avatar_url"] is None and expect(client.get("/api/auth/me"))["user"] == removed
                    expect(client.get(changed["avatar_url"]), 404)
                    assert expect(client.delete("/api/auth/avatar"))["user"] == removed
                client.cookies.clear(); client.cookies.set(COOKIE_NAME, admin.cookies.get(COOKIE_NAME))
                assert expect(client.get("/api/admin/feedback/" + item["id"])) == reviewed
                if index == 0:
                    reviewed = expect(patch(client, item["id"], revision=2, reply="Human reply after actual restore"))
                    assert expect(client.get("/api/admin/feedback/" + item["id"])) == reviewed
                else:
                    expect(patch(client, item["id"], revision=2, reply="stale after process restart"), 409)
                    assert expect(client.get("/api/admin/feedback/" + item["id"])) == reviewed
                states.append({"process": index + 1, "avatar_readback": True, "feedback_readback": True,
                               "feedback_revision": reviewed["revision"], "schema": 9})
            stopped.append(process.poll() is not None)
        db = Database(restored / backup_tool.DB_NAME)
        with db.connect() as conn:
            assert len(records(conn)) == 27 and not conn.execute("PRAGMA foreign_key_check").fetchall()
            assert conn.execute("SELECT value FROM meta WHERE key='kv_scope_secret'").fetchone()[0] == secret
            assert conn.execute("SELECT count(*) FROM feedback").fetchone()[0] == 1
        assert len(set(pids)) == 2 and all(stopped)
    finally:
        hidden_source.rename(source); hidden_seed.rename(catalog.parent)
    evidence = {"backup_records_match": restore_result["records_match"], "backup_files_match": restore_result["files_match"],
                "application_tables": 25, "inventory_tables": 26, "avatar_blob_rows_backed_up": 2,
                "all_non_path_table_rows_equal_before_http_mutation": True, "all_schema_equal": True,
                "sources_unavailable": True, "actual_process_pids": pids, "processes_stopped": stopped,
                "http_restart_states": states, "hmac_preserved": True, "provider_calls": 0}
    (tmp_path / "stage9-backup-http-evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
