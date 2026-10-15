"""Stage-2 accounts/retention/import acceptance; synthetic isolated SQLite only."""
import io
import json
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from backend.aicademiya import manage_admin
from backend.aicademiya.db import password_matches
from backend.aicademiya.roster import maintenance
from .conftest import expect, publish, question, demo_client

CID = "synthetic-course"
BASE = f"/api/teacher/courses/{CID}/students"
PASSWORD = "synthetic-fixture1"


def csv_preview(teacher, text, cid=CID, default=PASSWORD):
    data = {"default_temporary_password": default} if default is not None else {}
    return teacher.post(f"/api/teacher/courses/{cid}/students/import/preview", data=data, files={"file": ("synthetic.csv", text.encode())})


def enrolled_student(app, teacher, email="stage2-student@example.invalid"):
    c = expect(teacher.get("/api/courses"))[0]
    client = TestClient(app)
    user = expect(client.post("/api/auth/register", json={"name": "Synthetic student", "email": email, "password": PASSWORD, "join_code": c["join_code"]}))["user"]
    return client, user


def test_admin_settings_and_owned_courses_not_global_records(admin, teacher, student):
    for client in (teacher, student):
        expect(client.get("/api/teacher/settings"), 403)
        expect(client.put("/api/teacher/settings", json={"mode": "demo", "base_url": "", "model": ""}), 403)
        expect(client.post("/api/teacher/settings/test"), 403)
        expect(client.get("/api/admin/teachers"), 403)
        expect(client.get("/api/admin/students"), 403)
    expect(admin.get("/api/teacher/settings"))
    assert expect(admin.post("/api/teacher/settings/test"))["mode"] == "demo"
    assert not expect(admin.get("/api/courses"))
    for url in ("/api/sessions/s4", "/api/teacher/sessions/s4/students", BASE):
        expect(admin.get(url), 403)
    course = expect(admin.post("/api/courses", json={"title": "Admin's own course", "code": "ADMIN"}))
    assert expect(admin.get("/api/courses"))[0]["id"] == course["id"]
    expect(teacher.get(f"/api/courses/{course['id']}/sessions"), 403)


def test_promotion_teacher_only_revokes_sessions_and_preserves_ownership(app, admin, teacher, student):
    original = expect(teacher.get("/api/courses"))[0]
    assert {x["id"] for x in expect(admin.get("/api/admin/teachers"))} == {"demo-teacher"}
    expect(teacher.post("/api/admin/teachers/demo-teacher/promote", json={}), 403)
    expect(admin.post("/api/admin/teachers/demo-student-1/promote", json={}), 422)
    promoted = expect(admin.post("/api/admin/teachers/demo-teacher/promote", json={}))["user"]
    assert promoted["role"] == "admin"
    expect(teacher.get("/api/auth/me"), 401)
    expect(teacher.post("/api/auth/demo", json={"role": "teacher"}))
    assert expect(teacher.get("/api/courses"))[0]["id"] == original["id"]
    assert not expect(admin.get("/api/courses"))
    expect(admin.post("/api/admin/teachers/demo-teacher/promote", json={}), 422)
    expect(student.post("/api/auth/register", json={"name": "Admin exploit", "email": "x@example.invalid", "password": PASSWORD, "join_code": original["join_code"], "role": "admin"}), 422)
    expect(admin.post("/api/admin/create", json={}), 405)
    assert not any(route.path == "/api/admin/create" for route in app.routes)


@pytest.mark.parametrize("role", ["teacher", "student", "admin"])
def test_profile_name_only_saved_and_read_back(app, role):
    with demo_client(app, role) as client:
        before = expect(client.get("/api/auth/me"))["user"]
        updated = expect(client.patch("/api/auth/profile", json={"name": "  Synthetic updated name  "}))["user"]
        assert updated == {**before, "name": "Synthetic updated name"}
        assert expect(client.get("/api/auth/me"))["user"] == updated
        for extra in ({"email": "other@example.invalid"}, {"role": "admin"}, {"unknown": True}):
            expect(client.patch("/api/auth/profile", json={"name": "No change", **extra}), 422)
        expect(client.patch("/api/auth/profile", json={"name": " "}), 422)
        assert expect(client.get("/api/auth/me"))["user"] == updated


def test_local_admin_cli_create_promote_and_password_policy(app, teacher, monkeypatch, capsys):
    monkeypatch.setenv("AICADEMIYA_DATA_DIR", str(app.state.database.path.parent))
    prompts = []
    def masked(prompt):
        prompts.append(prompt)
        return PASSWORD
    monkeypatch.setattr(manage_admin, "getpass", masked)
    assert manage_admin.main(["create", "--email", "local-admin@example.invalid", "--name", "Synthetic local admin"]) == 0
    output = capsys.readouterr().out
    assert "created locally" in output and PASSWORD not in output and len(prompts) == 2
    with app.state.database.connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE email='local-admin@example.invalid'").fetchone()
        assert row["role"] == "admin" and password_matches(PASSWORD, row["password_hash"])
        assert conn.execute("SELECT role FROM users WHERE id='demo-teacher'").fetchone()[0] == "teacher"
    assert manage_admin.main(["promote", "--email", "demo-teacher@example.invalid"]) == 0
    expect(teacher.get("/api/auth/me"), 401)
    with pytest.raises(SystemExit):
        manage_admin.main(["create", "--email", "x@example.invalid", "--name", "X", "--password", PASSWORD])
    with pytest.raises(ValueError):
        app.state.database.create_admin("Bad", "bad@example.invalid", "letters-only")
    with TestClient(app) as real:
        expect(real.post("/api/auth/login", json={"email": "local-admin@example.invalid", "password": PASSWORD}))
        old_cookie = real.cookies.get("aicademiya_session")
        expect(real.post("/api/auth/change-password", json={"current_password": "wrong-fixture1", "new_password": "new-fixture2"}), 400)
        expect(real.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": "new-fixture2"}))
        assert real.cookies.get("aicademiya_session") != old_cookie
        expect(real.get("/api/teacher/settings"))


def test_archive_course_scope_retention_restore_and_shared_account(app, teacher, student):
    other = expect(teacher.post("/api/courses", json={"title": "Synthetic second course", "code": "TWO"}))
    expect(student.post("/api/courses/join", json={"join_code": other["join_code"]}))
    sid = expect(teacher.post(f"/api/courses/{other['id']}/sessions", json={"title": "Other session"}))["id"]
    q = question("other-q"); q.pop("teacher_internal")
    expect(teacher.patch(f"/api/sessions/{sid}", json={"questions": [q], "status": "published"}))
    publish(teacher, other["id"])
    expect(student.post("/api/sessions/s4/answers/q1", json={"answer": "First course evidence"}))
    expect(student.post(f"/api/sessions/{sid}/answers/other-q", json={"answer": "Other course evidence"}))
    expect(teacher.post(BASE+"/archive", json={"user_ids": ["demo-student-1", "missing"]}), 404)
    assert not expect(teacher.get(BASE+"?archived=true"))
    assert expect(teacher.post(BASE+"/archive", json={"user_ids": ["demo-student-1"]})) == {"affected_ids": ["demo-student-1"]}
    item = expect(teacher.get(BASE+"?archived=true"))[0]
    assert item["has_work"] and (datetime.fromisoformat(item["purge_at"])-datetime.fromisoformat(item["archived_at"])).days == 30
    assert expect(student.get("/api/sessions/s4/workspace"))["read_only_reason"] == "enrollment_archived"
    expect(student.post("/api/sessions/s4/answers/q1", json={"answer": "Blocked"}), 403)
    invite = expect(teacher.get("/api/courses"))[0]["join_code"]
    expect(student.post("/api/courses/join", json={"join_code": invite}), 403)
    assert expect(student.get(f"/api/sessions/{sid}/workspace"))["attempts"]["other-q"]["answer"] == "Other course evidence"
    expect(student.get("/api/auth/me"))
    expect(teacher.post(BASE+"/restore", json={"user_ids": ["demo-student-1"]}))
    assert not expect(teacher.get(BASE+"?archived=true"))
    with app.state.database.connect() as conn:
        result = maintenance(conn, at=datetime.now(timezone.utc)+timedelta(days=31))
        assert not result["accounts"] and not result["enrollments"]
    assert expect(student.get("/api/sessions/s4/workspace"))["attempts"]["q1"]["answer"] == "First course evidence"


def test_course_expiry_sql_only_preserves_other_courses_files_and_users(app, teacher, student):
    expect(student.post("/api/sessions/s4/answers/q1", json={"answer": "Scoped work"}))
    other = expect(teacher.post("/api/courses", json={"title": "Other enrollment", "code": "KEEP"}))
    expect(student.post("/api/courses/join", json={"join_code": other["join_code"]}))
    expect(teacher.post(BASE+"/archive", json={"user_ids": ["demo-student-1"]}))
    future = datetime.now(timezone.utc)+timedelta(days=31)
    with app.state.database.connect() as conn:
        original_materials = [tuple(r) for r in conn.execute("SELECT * FROM materials")]
        version_count = conn.execute("SELECT count(*) FROM course_versions").fetchone()[0]
        dry = maintenance(conn, at=future, dry_run=True)
        assert dry["enrollments"] == [{"course_id": CID, "user_id": "demo-student-1"}]
        assert conn.execute("SELECT count(*) FROM attempts").fetchone()[0] == 1
        maintenance(conn, at=future)
        assert not conn.execute("SELECT 1 FROM workspaces WHERE user_id='demo-student-1'").fetchone()
        assert conn.execute("SELECT 1 FROM users WHERE id='demo-student-1'").fetchone()
        assert conn.execute("SELECT 1 FROM enrollments WHERE course_id=? AND user_id='demo-student-1'", (other["id"],)).fetchone()
        assert conn.execute("SELECT 1 FROM enrollments WHERE course_id=? AND user_id='demo-student-2'", (CID,)).fetchone()
        assert [tuple(r) for r in conn.execute("SELECT * FROM materials")] == original_materials
        assert conn.execute("SELECT count(*) FROM course_versions").fetchone()[0] == version_count
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
    expect(teacher.post(BASE+"/restore", json={"user_ids": ["demo-student-1"]}), 404)


def test_global_archive_login_revocation_restore_and_expiry(app, teacher, admin):
    client, user = enrolled_student(app, teacher)
    uid = user["id"]
    expect(client.post("/api/sessions/s4/answers/q1", json={"answer": "Global account evidence"}))
    expect(teacher.post("/api/admin/students/archive", json={"user_ids": [uid]}), 403)
    expect(admin.post("/api/admin/students/archive", json={"user_ids": [uid, "demo-teacher"]}), 404)
    expect(client.get("/api/auth/me"))
    expect(admin.post("/api/admin/students/archive", json={"user_ids": [uid]}))
    expect(client.get("/api/auth/me"), 401)
    expect(client.post("/api/auth/login", json={"email": user["email"], "password": PASSWORD}), 401)
    assert next(x for x in expect(admin.get("/api/admin/students?archived=true")) if x["user"]["id"] == uid)["has_work"]
    expect(admin.post("/api/admin/students/restore", json={"user_ids": [uid]}))
    expect(client.post("/api/auth/login", json={"email": user["email"], "password": PASSWORD}))
    assert expect(client.get("/api/sessions/s4/workspace"))["attempts"]["q1"]["answer"] == "Global account evidence"
    expect(admin.post("/api/admin/students/archive", json={"user_ids": [uid]}))
    with app.state.database.connect() as conn:
        maintenance(conn, at=datetime.now(timezone.utc)+timedelta(days=31))
        assert not conn.execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone()
        assert not conn.execute("SELECT 1 FROM attempts WHERE user_id=?", (uid,)).fetchone()
        assert conn.execute("SELECT count(*) FROM materials").fetchone()[0] == 4
        assert conn.execute("SELECT count(*) FROM course_versions").fetchone()[0] == 1
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
    expect(admin.post("/api/admin/students/restore", json={"user_ids": [uid]}), 404)
    client.close()


def test_import_preview_hash_only_create_skip_enroll_restore_atomic(app, teacher, student):
    text = "name,email,temporary_password\nNew synthetic,new-import@example.invalid,synthetic-column2\nUnchanged,demo-student-1@example.invalid,ignored-existing-secret3\n"
    response = csv_preview(teacher, text)
    preview = expect(response)
    assert [r["action"] for r in preview["rows"]] == ["create", "skip"] and preview["valid_count"] == 2
    for secret in (PASSWORD, "synthetic-column2", "ignored-existing-secret3", "password_hash"):
        assert secret not in response.text
    with app.state.database.connect() as conn:
        raw = conn.execute("SELECT payload_json FROM import_staging WHERE id=?", (preview["import_id"],)).fetchone()[0]
        assert "scrypt$" in raw and "synthetic-column2" not in raw and "ignored-existing-secret3" not in raw
        before = tuple(conn.execute("SELECT * FROM users WHERE id='demo-student-1'").fetchone())
    counts = expect(teacher.post(BASE+f"/import/{preview['import_id']}/commit", json={}))
    assert counts == {"created": 1, "enrolled": 0, "restored": 0, "skipped": 1}
    with app.state.database.connect() as conn:
        new = conn.execute("SELECT * FROM users WHERE email='new-import@example.invalid'").fetchone()
        assert new["must_change_password"] and password_matches("synthetic-column2", new["password_hash"])
        assert tuple(conn.execute("SELECT * FROM users WHERE id='demo-student-1'").fetchone()) == before
    other = expect(teacher.post("/api/courses", json={"title": "Import enrollment target", "code": "IMP"}))
    preview = expect(csv_preview(teacher, "name,email\nKeep original,demo-student-1@example.invalid\n", other["id"], default=None))
    assert preview["rows"][0]["action"] == "enroll"
    counts = expect(teacher.post(f"/api/teacher/courses/{other['id']}/students/import/{preview['import_id']}/commit", json={}))
    assert counts["enrolled"] == 1
    expect(teacher.post(BASE+"/archive", json={"user_ids": ["demo-student-1"]}))
    preview = expect(csv_preview(teacher, "name,email\nRetained,demo-student-1@example.invalid\n", default=None))
    assert preview["rows"][0]["action"] == "restore"
    assert expect(teacher.post(BASE+f"/import/{preview['import_id']}/commit", json={}))["restored"] == 1


@pytest.mark.parametrize("text", [
    "name,email\nNew,no-password@example.invalid\n",
    "name,email\nTeacher,demo-teacher@example.invalid\n",
    "name,email,temporary_password\nBad,bad@example.invalid,no-digit-password\n",
    "name,email\nDuplicate,same@example.invalid\nDuplicate,same@example.invalid\n",
])
def test_import_errors_block_all_commit_and_never_echo_secrets(app, teacher, text):
    preview = expect(csv_preview(teacher, text, default=None))
    assert preview["error_count"] >= 1
    expect(teacher.post(BASE+f"/import/{preview['import_id']}/commit", json={}), 422)
    with app.state.database.connect() as conn:
        assert conn.execute("SELECT count(*) FROM users WHERE is_demo=0").fetchone()[0] == 0


def test_import_staging_scope_expiry_conflict_revalidation(app, teacher, admin):
    preview = expect(csv_preview(teacher, "name,email\nFirst,conflict@example.invalid\nSecond,other-new@example.invalid\n"))
    iid = preview["import_id"]
    expect(admin.post(BASE+f"/import/{iid}/commit", json={}), 403)
    expect(teacher.post(BASE, json={"name": "Changed account", "email": "conflict@example.invalid", "temporary_password": PASSWORD}))
    expect(teacher.post(BASE+f"/import/{iid}/commit", json={}), 409)
    with app.state.database.connect() as conn:
        assert not conn.execute("SELECT 1 FROM users WHERE email='other-new@example.invalid'").fetchone()
        conn.execute("UPDATE import_staging SET expires_at=? WHERE id=?", ((datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(), iid))
    expect(teacher.post(BASE+f"/import/{iid}/commit", json={}), 410)


def test_startup_expiry_and_local_dry_run_use_only_synthetic_scope(app, teacher, monkeypatch, capsys):
    from backend.aicademiya.main import create_app
    from fastapi.testclient import TestClient
    client, user = enrolled_student(app, teacher, email="expiry-startup@example.invalid")
    uid = user["id"]
    expect(client.post("/api/sessions/s4/answers/q1", json={"answer": "Expired synthetic record"}))
    prior = (datetime.now(timezone.utc)-timedelta(days=31)).isoformat()
    deadline = (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
    with app.state.database.connect() as conn:
        conn.execute("UPDATE users SET archived_at=?,purge_at=? WHERE id=?", (prior, deadline, uid))
    monkeypatch.setenv("AICADEMIYA_DATA_DIR", str(app.state.database.path.parent))
    assert manage_admin.main(["maintenance", "--dry-run"]) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["dry_run"] and preview["accounts"] == [uid]
    with app.state.database.connect() as conn:
        assert conn.execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone()
    restarted = create_app(data_dir=app.state.database.path.parent, catalog_path=app.state.catalog_path, demo_enabled=False)
    with TestClient(restarted):
        with restarted.state.database.connect() as conn:
            assert not conn.execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone()
            assert not conn.execute("SELECT 1 FROM attempts WHERE user_id=?", (uid,)).fetchone()
            assert conn.execute("SELECT count(*) FROM materials").fetchone()[0] == 4
            assert not conn.execute("PRAGMA foreign_key_check").fetchall()
    client.close()


def test_real_xlsx_roster_and_limits(teacher):
    from openpyxl import Workbook
    book = Workbook(); sheet = book.active
    sheet.append(["name", "email", "temporary_password"])
    sheet.append(["Synthetic XLSX", "xlsx@example.invalid", PASSWORD])
    output = io.BytesIO(); book.save(output)
    response = teacher.post(BASE+"/import/preview", files={"file": ("synthetic.xlsx", output.getvalue())})
    preview = expect(response)
    assert preview["rows"][0]["action"] == "create" and PASSWORD not in response.text
    assert expect(teacher.post(BASE+f"/import/{preview['import_id']}/commit", json={}))["created"] == 1
    excess = "name,email\n" + "X,x@example.invalid\n" * 1001
    expect(csv_preview(teacher, excess), 413)
    expect(csv_preview(teacher, "bad_header,email\nX,x@example.invalid\n"), 422)
    expect(teacher.post(BASE+"/import/preview", files={"file": ("broken.xlsx", b"not an archive")}), 422)
