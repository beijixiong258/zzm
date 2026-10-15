"""Clean release integrity and real HTTP boot; synthetic demo QA, no providers."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
import http.cookiejar

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("v2_release_builder", ROOT / "tools/build_v2_release.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


@pytest.fixture(scope="module")
def release(tmp_path_factory):
    work = tmp_path_factory.mktemp("v2-release")
    # Optional exact artifact under test; avoids claiming a sibling build was
    # the one whose packaged app was booted.
    manifest = os.getenv("AICADEMIYA_QA_RELEASE_MANIFEST")
    if manifest:
        result = {**builder.verify(manifest), "manifest": manifest}
    else:
        result = builder.build(ROOT, work / "output", "pytest")
    verified = builder.verify(result["manifest"], work / "extracted")
    return work, result, Path(verified["extracted_root"])


def test_archive_allowlist_and_private_split(release):
    _, result, extracted = release
    manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
    names = set(manifest["files"])
    assert "backend/aicademiya/main.py" in names
    assert "backend/__init__.py" in names
    assert "tools/start-linux.sh" in names
    assert "RUNTIME_V2.md" in names
    assert "BACKUP-RESTORE-V2.md" in names
    assert "sample_data/catalog.json" in names
    assert "backend/aicademiya/visual_context.py" in names
    assert "tools/document_stage12/page_vision_runtime.py" in names
    assert {"tools/material_stage15/"+n for n in ("__init__.py", "adapter.py", "prepared.py", "provenance.py", "page_worker.py")} <= names
    assert not {"README.md", "DEPLOYMENT.md", "DEPLOYMENT_V2_PLAN.md", "BACKUP-RESTORE.md", ".env", "STAGE2_CHECKPOINT.md"} & names
    assert not any("tests" in Path(n).parts or n.endswith((".sqlite3", ".pyc")) for n in names)
    assert not any(n.startswith(("backend/educ7703/", "backend/akademiya/")) for n in names)
    for name, info in manifest["files"].items():
        assert info["component"] == ("private_seed" if name.startswith("sample_data/") else "code")
        data = (extracted / name).read_bytes()
        assert len(data) == info["bytes"]
        assert hashlib.sha256(data).hexdigest() == info["sha256"]
        if name.endswith(".sh"):
            assert info["mode"] == 0o755
    assert (extracted / "tools/start-linux.sh").read_bytes() == (ROOT / "runtime_v2/start-linux.sh").read_bytes()
    catalog = json.loads((extracted / "sample_data/catalog.json").read_text(encoding="utf-8"))
    assert catalog["course"]["id"] == "educ7703"
    assert catalog["course"]["code"] == "EDUC7703"
    assert "DEPLOYMENT.md" not in (extracted / "tools/start-linux.sh").read_text()
    assert 'str(APP / "data-v2")' in (extracted / "tools/warm_aicademiya_prefix.py").read_text()


def test_extracted_page_worker_imports_without_development_tree(release):
    work, _, extracted = release
    env = {**os.environ, "PYTHONPATH": str(extracted), "PYTHONDONTWRITEBYTECODE": "1", "CUDA_VISIBLE_DEVICES": ""}
    process = subprocess.run([sys.executable, "-B", str(extracted/"tools/material_stage15/page_worker.py"), "--help"],
                             cwd=work, env=env, capture_output=True, text=True, timeout=25)
    assert process.returncode == 0, process.stderr
    assert "--prepared-dir" in process.stdout and "--vlm-url" in process.stdout


def test_unlisted_source_files_are_not_collected(tmp_path, release):
    _, _, extracted = release
    # Construct a source fixture without copying user data or the development tree.
    fixture = tmp_path / "source"
    import shutil
    shutil.copytree(extracted, fixture)
    for name in (".env", "local-settings-v2.json", "backend/aicademiya/credentials.json",
                 "backend/aicademiya/unlisted.py", "sample_data/materials/student/unreferenced.pdf",
                 "frontend/dist/secrets.json", "frontend/dist/assets/secrets.json", "frontend/dist/assets/secrets.js",
                 "backend/educ7703/main.py", "data-v2/aicademiya.sqlite3", "history/events.json"):
        path = fixture / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("SYNTHETIC_EXCLUSION_SENTINEL", encoding="utf-8")
    files = builder.collect(fixture)
    assert not any(b"SYNTHETIC_EXCLUSION_SENTINEL" in item["data"] for item in files.values())


@pytest.mark.parametrize("name", ["../outside", "/absolute", "C:/outside", "C:\\outside", "a/../b", "a//b", "./a", "a\\b", ""])
def test_unsafe_paths_rejected(name):
    with pytest.raises(ValueError):
        builder.safe_path(name)


def test_archive_tampering_rejected(tmp_path, release):
    _, result, _ = release
    import shutil
    target = tmp_path / "copy"
    shutil.copytree(Path(result["manifest"]).parent, target)
    manifest_path = target / Path(result["manifest"]).name
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    archive = target / manifest["archives"]["code"]["name"]
    with archive.open("ab") as stream:
        stream.write(b"TAMPERED")
    with pytest.raises(ValueError, match="Archive SHA256/size"):
        builder.verify(manifest_path, tmp_path / "must-not-exist")
    assert not (tmp_path / "must-not-exist").exists()


@pytest.mark.parametrize("attack", ["traversal", "symlink", "duplicate", "extra", "member_hash", "mode", "missing"])
def test_rehashed_hostile_archive_rejected(tmp_path, release, attack):
    # Even a replacement checksum cannot turn unexpected/unsafe members into files.
    _, result, _ = release
    original = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
    import shutil
    target = tmp_path / attack
    shutil.copytree(Path(result["manifest"]).parent, target)
    manifest_path = target / Path(result["manifest"]).name
    archive_path = target / original["archives"]["code"]["name"]
    with tarfile.open(archive_path, "r:gz") as archive:
        members = [(m, archive.extractfile(m).read()) for m in archive]
    with tarfile.open(archive_path, "w:gz") as archive:
        for index, (member, data) in enumerate(members):
            if index == 0:
                if attack == "traversal":
                    member.name = original["release"] + "/../escape"
                elif attack == "symlink":
                    member.type = tarfile.SYMTYPE
                    member.linkname = "../../escape"
                    member.size = 0
                elif attack == "member_hash":
                    data = b"x" * len(data)
                elif attack == "mode":
                    member.mode = 0o777
                elif attack == "missing":
                    continue
            archive.addfile(member, io.BytesIO(data) if member.isfile() else None)
        if attack in ("duplicate", "extra"):
            member, data = members[-1]
            if attack == "extra":
                member.name = original["release"] + "/unlisted.txt"
            archive.addfile(member, io.BytesIO(data))
    original["archives"]["code"].update(bytes=archive_path.stat().st_size, sha256=builder.sha256_file(archive_path))
    manifest_path.write_text(json.dumps(original), encoding="utf-8")
    with pytest.raises(ValueError):
        builder.verify(manifest_path, tmp_path / "not-created")
    assert not (tmp_path / "not-created").exists()


def test_existing_destinations_and_unsafe_tag_rejected(tmp_path, release):
    work, result, _ = release
    with pytest.raises(ValueError):
        builder.verify(result["manifest"], work / "extracted")
    with pytest.raises(ValueError):
        builder.build(ROOT, tmp_path / "unsafe", "../escape")
    existing = tmp_path / "existing-output"
    existing.mkdir()
    with pytest.raises(ValueError):
        builder.build(ROOT, existing, "again")


def test_missing_seed_original_is_a_build_failure(tmp_path, release):
    _, _, extracted = release
    import shutil
    fixture = tmp_path / "source"
    shutil.copytree(extracted, fixture)
    catalog = json.loads((fixture / "sample_data/catalog.json").read_text(encoding="utf-8"))
    catalog["sessions"][0]["materials"][0]["file_path"] = "materials/student/absent.pdf"
    (fixture / "sample_data/catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    with pytest.raises(ValueError):
        builder.build(fixture, tmp_path / "output", "missing")
    assert not (tmp_path / "output").exists()


def test_new_compiled_chunk_requires_explicit_allowlist(tmp_path, release):
    _, _, extracted = release
    import shutil
    fixture = tmp_path / "source"
    shutil.copytree(extracted, fixture)
    (fixture / "frontend/dist/assets/NewFeature-testtest.js").write_text("SYNTHETIC_NEW_CHUNK", encoding="utf-8")
    with pytest.raises(ValueError, match="explicit runtime allowlist"):
        builder.collect(fixture)


def test_actual_extracted_runtime_http_and_seed_paths(release):
    work, result, extracted = release
    data_root = work / "fresh-synthetic-data"
    env = {k: v for k, v in os.environ.items() if not k.startswith("AICADEMIYA_") and k not in ("TAVILY_API_KEY", "PYTHONPATH")}
    env.update(AICADEMIYA_DATA_DIR=str(data_root), AICADEMIYA_DEMO_ENABLED="true",
               AICADEMIYA_AI_MODE="openai", AICADEMIYA_AI_BASE_URL="", AICADEMIYA_AI_MODEL="",
               AICADEMIYA_AI_API_KEY="", AICADEMIYA_AI_PROVIDER="", AICADEMIYA_WEB_SEARCH_ENABLED="false",
               TAVILY_API_KEY="", AICADEMIYA_COOKIE_SECURE="false", PYTHONPATH="",
               PYTHONDONTWRITEBYTECODE="1", TEMP=str(work), TMP=str(work), TMPDIR=str(work))
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = "http://127.0.0.1:" + str(port)
    log_path = work / "packaged-boot.log"
    checks, downloads, figures = [], [], []
    jar = http.cookiejar.CookieJar()
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(jar))

    def request(path, payload=None):
        req = urllib.request.Request(base + path, data=json.dumps(payload).encode() if payload is not None else None,
                                     headers={"Content-Type": "application/json"} if payload is not None else {})
        with client.open(req, timeout=15) as response:
            content = response.read()
            checks.append({"method": "POST" if payload is not None else "GET", "path": path, "status": response.status})
            return content

    with log_path.open("wb") as log:
        process = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.aicademiya.main:app",
                                    "--app-dir", str(extracted), "--host", "127.0.0.1", "--port", str(port),
                                    "--workers", "1"], cwd=extracted, env=env, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 45
            while True:
                try:
                    assert json.loads(request("/api/health"))["status"] == "ok"
                    break
                except (urllib.error.URLError, ConnectionError):
                    if process.poll() is not None or time.monotonic() > deadline:
                        pytest.fail("Packaged server did not boot; see " + str(log_path))
                    time.sleep(0.15)
            bootstrap = json.loads(request("/api/bootstrap"))
            assert bootstrap["app_name"] == "AIcademiya" and bootstrap["default_locale"] == "en"
            assert bootstrap["demo_enabled"] is True
            assert bootstrap["ai"]["configured"] is False
            assert bootstrap["ai"]["web_search"]["enabled"] is False
            html = request("/")
            assert b"AIcademiya" in html
            for asset_path in sorted(set(re.findall(r'(?:src|href)="(/[^"?#]+)"', html.decode()))):
                assert request(asset_path) == (extracted / "frontend/dist" / asset_path.lstrip("/")).read_bytes()
            user = json.loads(request("/api/auth/demo", {"role": "teacher"}))["user"]
            assert user["is_demo"] is True and user["role"] == "teacher"
            assert any(cookie.name == "aicademiya_session" for cookie in jar)
            assert json.loads(request("/api/auth/me"))["user"]["id"] == user["id"]
            courses = json.loads(request("/api/courses"))
            assert any(c["id"] == "educ7703" and c["code"] == "EDUC7703" for c in courses)
            sessions = json.loads(request("/api/courses/educ7703/sessions"))
            assert len(sessions) == 2
            catalog = json.loads((extracted / "sample_data/catalog.json").read_text(encoding="utf-8"))
            figure_urls = set()
            for session in catalog["sessions"]:
                detail = json.loads(request("/api/sessions/" + session["id"]))
                assert len(detail["questions"]) == len(session["questions"])
                for question in detail["questions"]:
                    figure_urls.update(image["url"] for image in question.get("images", []))
                for material in session["materials"]:
                    downloaded = request("/api/materials/" + material["id"] + "/download")
                    expected = (extracted / "sample_data" / material["file_path"]).read_bytes()
                    assert downloaded == expected
                    downloads.append({"id": material["id"], "bytes": len(downloaded), "sha256": hashlib.sha256(downloaded).hexdigest()})
            for url in sorted(figure_urls):
                figure = request(url)
                assert figure == (extracted / "sample_data/assets" / url.rsplit("/", 1)[-1]).read_bytes()
                figures.append({"path": url, "bytes": len(figure)})
            assert len(figures) == 3 and len(downloads) == 13
            student = json.loads(request("/api/auth/demo", {"role": "student", "student_index": 1}))["user"]
            assert student["is_demo"] is True
            assert len(json.loads(request("/api/courses/educ7703/sessions"))) == 2
            assert json.loads(request("/api/sessions/session-4"))["questions"]
            assert request("/api/materials/s4-worksheet/download") == (extracted / "sample_data/materials/student/s4-worksheet.docx").read_bytes()
            assert request("/api/assets/s4-graph-a.png")
            try:
                request("/api/materials/s4-answer-key/download")
                pytest.fail("Student received private teacher material")
            except urllib.error.HTTPError as error:
                assert error.code in (403, 404)
                checks.append({"method": "GET", "path": "/api/materials/s4-answer-key/download", "status": error.code})
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)

    db = data_root / "aicademiya.sqlite3"
    assert db.is_file() and db.resolve().is_relative_to(work.resolve())
    backup_spec = importlib.util.spec_from_file_location("packaged_backup", extracted / "tools/backup_data.py")
    backup_tool = importlib.util.module_from_spec(backup_spec)
    backup_spec.loader.exec_module(backup_tool)
    bound_paths = []
    def check_path(key, value, kind, assets):
        path = Path(value).resolve()
        assert path.is_relative_to(extracted.resolve())
        assert not path.is_relative_to(ROOT.resolve())
        assert path.is_file() if kind == "file" else path.is_dir()
        bound_paths.append({"location": json.loads(key), "relative": path.relative_to(extracted).as_posix()})
        return value
    backup_tool.visit_database(db, check_path)
    assert len(bound_paths) >= 13
    with sqlite3.connect(db) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT count(*) FROM users WHERE is_demo=0").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM settings").fetchone()[0] == 0
    backup_run = subprocess.run([sys.executable, str(extracted / "tools/backup_data.py"), "backup",
                                 "--data-dir", str(data_root), "--materials-root", str(extracted / "sample_data"),
                                 "--destination", str(work / "packaged-data-backup")],
                                cwd=extracted, env=env, capture_output=True, text=True, timeout=30, check=True)
    backup_result = json.loads(backup_run.stdout)
    restore_run = subprocess.run([sys.executable, str(extracted / "tools/backup_data.py"), "restore",
                                  "--source", str(work / "packaged-data-backup"),
                                  "--destination", str(work / "packaged-restored-data")],
                                 cwd=extracted, env=env, capture_output=True, text=True, timeout=30, check=True)
    restore_result = json.loads(restore_run.stdout)
    assert backup_result["integrity"] == restore_result["integrity"] == "ok"
    assert restore_result["records_match"] is True and restore_result["files_match"] is True
    warm_run = subprocess.run([sys.executable, str(extracted / "tools/warm_aicademiya_prefix.py"),
                               "--db", str(db)], cwd=extracted, env=env, capture_output=True,
                              text=True, timeout=30, check=True)
    warm_result = json.loads(warm_run.stdout)
    assert warm_result["action"] == "list_only" and warm_result["topics"]
    report = {"release": result["release"], "manifest": str(result["manifest"]), "extracted_root": str(extracted), "database": str(db),
              "http_checks": checks, "http_request_count": len(checks), "original_downloads": downloads,
              "packaged_backup_cli": backup_result, "packaged_restore_cli": restore_result,
              "packaged_warm_cli": {"action": warm_result["action"], "topic_count": len(warm_result["topics"])},
              "figures": figures, "bound_resource_paths": bound_paths, "resource_paths_inside_extracted_release": True,
              "model_requests": 0, "search_requests": 0, "source_tree_renamed": False,
              "scope": "Local Windows boot with existing venv; not Linux/systemd or remote deployment proof."}
    report_path = work / "packaged-boot-report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Packaged runtime HTTP report: " + str(report_path))
