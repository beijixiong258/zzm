"""CPU-only backup/restore tests, including committed WAL and original uploads."""
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

APP = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("backup_data", APP / "tools" / "backup_data.py")
backup_tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup_tool)


@pytest.fixture
def data(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    uploads = root / "uploads"
    uploads.mkdir()
    (uploads / "lesson.txt").write_text("original uploaded lesson", encoding="utf-8")
    external = tmp_path / "seed-materials"
    external.mkdir()
    (external / "reference.txt").write_text("private teacher material", encoding="utf-8")
    conn = sqlite3.connect(root / backup_tool.DB_NAME)
    conn.executescript("""
    PRAGMA journal_mode=WAL;
    PRAGMA wal_autocheckpoint=0;
    CREATE TABLE users(id TEXT PRIMARY KEY, role TEXT);
    CREATE TABLE messages(seq INTEGER PRIMARY KEY, user_id TEXT REFERENCES users(id), content TEXT);
    CREATE TABLE materials(id TEXT PRIMARY KEY, file_path TEXT);
    CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);
    CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT);
    """)
    conn.executemany("INSERT INTO users VALUES(?, 'student')", [(str(i),) for i in range(8)])
    conn.execute("INSERT INTO messages VALUES(1,'0','actual saved conversation')")
    conn.execute("INSERT INTO materials VALUES('upload',?)", (str(uploads / "lesson.txt"),))
    conn.execute("INSERT INTO materials VALUES('seed',?)", (str(external / "reference.txt"),))
    conn.execute("INSERT INTO meta VALUES('kv_scope_secret','synthetic-installation-secret')")
    conn.execute("INSERT INTO settings VALUES('ai_api_key','synthetic-model-key')")
    conn.commit()
    yield root, external, conn
    conn.close()


def test_live_wal_backup_restore_and_private_files(data, tmp_path):
    root, external, live = data
    assert (root / (backup_tool.DB_NAME + "-wal")).stat().st_size > 0
    original = live.execute("SELECT * FROM materials ORDER BY id").fetchall()
    result = backup_tool.backup(root, tmp_path / "backup", external)
    assert result["table_counts"]["users"] == 8
    assert result["table_counts"]["messages"] == 1
    restored = backup_tool.restore(tmp_path / "backup", tmp_path / "restore")
    assert restored["records_match"] and restored["files_match"]
    assert live.execute("SELECT * FROM materials ORDER BY id").fetchall() == original
    with sqlite3.connect(tmp_path / "restore" / backup_tool.DB_NAME) as conn:
        assert conn.execute("SELECT value FROM meta").fetchone()[0] == "synthetic-installation-secret"
        assert conn.execute("SELECT value FROM settings").fetchone()[0] == "synthetic-model-key"
        assert conn.execute("SELECT content FROM messages").fetchone()[0] == "actual saved conversation"
        for (file_path,) in conn.execute("SELECT file_path FROM materials"):
            assert Path(file_path).is_relative_to(tmp_path / "restore")
            assert Path(file_path).is_file()
    manifest_text = (tmp_path / "backup" / "manifest.json").read_text(encoding="utf-8")
    assert "synthetic-installation-secret" not in manifest_text
    assert "synthetic-model-key" not in manifest_text
    if os.name != "nt":
        for directory in (tmp_path / "backup", tmp_path / "restore"):
            assert directory.stat().st_mode & 0o077 == 0
            for p in directory.rglob("*"):
                assert p.stat().st_mode & 0o077 == 0


def test_refuses_existing_destination(data, tmp_path):
    root, external, _ = data
    with pytest.raises(ValueError, match="outside"):
        backup_tool.backup(root, root, external)
    backup_tool.backup(root, tmp_path / "backup", external)
    with pytest.raises(ValueError, match="new directory"):
        backup_tool.restore(tmp_path / "backup", root)
    assert (root / "uploads" / "lesson.txt").read_text() == "original uploaded lesson"


def test_corrupt_backup_is_not_restored(data, tmp_path):
    root, external, _ = data
    backup_tool.backup(root, tmp_path / "backup", external)
    (tmp_path / "backup" / "uploads" / "lesson.txt").write_text("tampered")
    with pytest.raises(ValueError, match="verification failed"):
        backup_tool.restore(tmp_path / "backup", tmp_path / "restore")
    assert not (tmp_path / "restore").exists()


def test_missing_material_fails_without_complete_manifest(data, tmp_path):
    root, external, _ = data
    (root / "uploads" / "lesson.txt").unlink()
    with pytest.raises(ValueError, match="regular file"):
        backup_tool.backup(root, tmp_path / "backup", external)
    assert not (tmp_path / "backup" / "manifest.json").exists()


def test_external_material_requires_permitted_root(data, tmp_path):
    root, _, _ = data
    with pytest.raises(ValueError, match="explicit permitted"):
        backup_tool.backup(root, tmp_path / "backup")


def test_manifest_traversal_rejected(data, tmp_path):
    root, external, _ = data
    backup_tool.backup(root, tmp_path / "backup", external)
    path = tmp_path / "backup" / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["files"]["../outside"] = {"bytes": 0, "sha256": ""}
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="manifest path"):
        backup_tool.restore(path.parent, tmp_path / "restore")


def test_cli_backup_restore_and_no_secret_output(data, tmp_path):
    root, external, _ = data
    script = APP / "tools" / "backup_data.py"
    b = subprocess.run([sys.executable, str(script), "backup", "--data-dir", str(root),
                        "--destination", str(tmp_path / "backup"), "--materials-root", str(external)],
                       capture_output=True, text=True)
    assert b.returncode == 0, b.stderr
    assert json.loads(b.stdout)["integrity"] == "ok"
    r = subprocess.run([sys.executable, str(script), "restore", "--source", str(tmp_path / "backup"),
                        "--destination", str(tmp_path / "restore")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["records_match"] is True
    assert "synthetic-model-key" not in b.stdout + b.stderr + r.stdout + r.stderr


def test_foreign_key_violation_rejected(data, tmp_path):
    root, external, conn = data
    conn.execute("INSERT INTO messages VALUES(2,'nonexistent','bad')")
    conn.commit()
    with pytest.raises(ValueError, match="foreign key"):
        backup_tool.backup(root, tmp_path / "backup", external)


def test_source_change_during_copy_rejected(tmp_path, monkeypatch):
    source = tmp_path / "source.txt"
    source.write_text("before")
    original = backup_tool.shutil.copyfileobj
    def changed(src, dst):
        original(src, dst)
        source.write_text("after")
    monkeypatch.setattr(backup_tool.shutil, "copyfileobj", changed)
    with pytest.raises(ValueError, match="changed"):
        backup_tool.copy_private(source, tmp_path / "copy.txt")
