"""Temporary-account auth contract; all identities and passwords are synthetic."""
import hashlib
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.aicademiya.db import SCHEMA, issue_session, now, password_hash, password_matches
from backend.aicademiya.main import COOKIE_NAME, create_app
from .conftest import expect


TEMP_PASSWORD = "synthetic-temporary-password1"
NEW_PASSWORD = "synthetic-chosen-password2"
STUDENT_EMAIL = "temporary-student@example.invalid"
COURSE_ID = "synthetic-course"
PROVISION_URL = f"/api/teacher/courses/{COURSE_ID}/students"


def provision(teacher, **overrides):
    payload = {"name": "Synthetic temporary student", "email": STUDENT_EMAIL,
               "temporary_password": TEMP_PASSWORD, **overrides}
    return teacher.post(PROVISION_URL, json=payload)


def login(client, password=TEMP_PASSWORD, email=STUDENT_EMAIL):
    return client.post("/api/auth/login", json={"email": email, "password": password})


@pytest.fixture
def forced_student(app, teacher):
    user = expect(provision(teacher))["user"]
    with TestClient(app) as client:
        assert expect(login(client))["user"] == user
        yield client


def test_provision_creates_real_scrypt_account_and_enrollment(app, teacher):
    teacher_token = teacher.cookies.get(COOKIE_NAME)
    response = provision(teacher, name="  Synthetic temporary student  ", email=STUDENT_EMAIL.upper())
    created = expect(response)
    user = created["user"]
    assert created["course_id"] == COURSE_ID
    assert set(user) == {"id", "name", "email", "role", "must_change_password", "is_demo", "avatar_url"}
    assert user["avatar_url"] is None
    assert user["name"] == "Synthetic temporary student" and user["email"] == STUDENT_EMAIL
    assert user["role"] == "student" and user["must_change_password"] is True
    assert "set-cookie" not in response.headers and teacher.cookies.get(COOKIE_NAME) == teacher_token
    assert TEMP_PASSWORD not in response.text and "password_hash" not in response.text
    with app.state.database.connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
        assert row["is_demo"] == 0 and row["must_change_password"] == 1
        assert row["password_hash"].startswith("scrypt$") and password_matches(TEMP_PASSWORD, row["password_hash"])
        assert row["password_hash"] not in response.text
        assert conn.execute("SELECT 1 FROM enrollments WHERE course_id=? AND user_id=?", (COURSE_ID, user["id"])).fetchone()
        assert not conn.execute("SELECT 1 FROM auth_sessions WHERE user_id=?", (user["id"],)).fetchone()
    roster = expect(teacher.get("/api/teacher/sessions/s4/students"))
    assert next(row["user"] for row in roster if row["user"]["id"] == user["id"]) == user
    observed = expect(teacher.get(f"/api/teacher/sessions/s4/students/{user['id']}/workspace"))
    assert observed["user"]["must_change_password"] is True


# Valid bodies ensure 403 comes from auth, never endpoint validation or role checks.
PROTECTED_REQUESTS = [
    ("GET", "/api/courses", {}),
    ("POST", "/api/courses", {"json": {"title": "Blocked", "code": "NO", "description": ""}}),
    ("POST", "/api/courses/join", {"json": {"join_code": "unused"}}),
    ("GET", f"/api/courses/{COURSE_ID}/sessions", {}),
    ("POST", f"/api/courses/{COURSE_ID}/sessions", {"json": {"title": "Blocked"}}),
    ("POST", PROVISION_URL, {"json": {"name": "Blocked", "email": "blocked@example.invalid", "temporary_password": TEMP_PASSWORD}}),
    ("GET", "/api/sessions/s4", {}),
    ("PATCH", "/api/sessions/s4", {"json": {"title": "Blocked"}}),
    ("GET", "/api/sessions/s4/workspace", {}),
    ("POST", "/api/sessions/s2/reading", {"json": {"group_id": "II-Pong"}}),
    ("POST", "/api/sessions/s4/answers/q1", {"json": {"answer": "Blocked"}}),
    ("POST", "/api/sessions/s4/chat", {"json": {"message": "Blocked", "question_id": "q1", "intent": "ask"}}),
    ("POST", "/api/sessions/s4/references/q1", {}),
    ("POST", "/api/sessions/s4/submit", {"json": {}}),
    ("GET", "/api/sessions/s4/export", {}),
    ("GET", "/api/teacher/sessions/s4/students", {}),
    ("GET", "/api/teacher/sessions/s4/students/demo-student-1/workspace", {}),
    ("POST", "/api/teacher/sessions/s4/students/demo-student-1/review", {"json": {"status": "confirmed", "note": "Blocked"}}),
    ("GET", "/api/teacher/sessions/s4/students/demo-student-1/export", {}),
    ("POST", "/api/sessions/s4/materials", {"files": {"file": ("synthetic.txt", b"Blocked", "text/plain")}}),
    ("DELETE", "/api/sessions/s4/materials/s4-public", {}),
    ("GET", "/api/materials/s4-public/download", {}),
    ("GET", "/api/materials/s4-private/download", {}),
    ("GET", "/api/teacher/settings", {}),
    ("PUT", "/api/teacher/settings", {"json": {"mode": "demo", "base_url": "", "model": ""}}),
    ("POST", "/api/teacher/settings/test", {}),
]


@pytest.mark.parametrize("method,url,kwargs", PROTECTED_REQUESTS,
                         ids=[f"{method} {url}" for method, url, _ in PROTECTED_REQUESTS])
def test_forced_change_blocks_every_protected_endpoint(forced_student, method, url, kwargs):
    response = forced_student.request(method, url, **kwargs)
    assert response.status_code == 403
    assert response.json() == {"detail": "Password change required"}


def test_gate_runs_before_side_effects_or_model_calls(app, forced_student):
    with app.state.database.connect() as conn:
        before = {table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                  for table in ("users", "courses", "sessions", "materials", "workspaces", "attempts", "messages", "chat_requests")}
    for method, url, kwargs in PROTECTED_REQUESTS:
        expect(forced_student.request(method, url, **kwargs), 403)
    with app.state.database.connect() as conn:
        after = {table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] for table in before}
    assert before == after


def test_forced_login_me_public_endpoints_and_logout_remain_available(app, forced_student):
    me = expect(forced_student.get("/api/auth/me"))
    assert me["user"]["must_change_password"] is True
    token = forced_student.cookies.get(COOKIE_NAME)
    assert expect(forced_student.get("/api/health")) == {"status": "ok"}
    assert expect(forced_student.get("/api/bootstrap"))["demo_enabled"] is True
    assert forced_student.get("/api/assets/plot.png").status_code == 403
    assert expect(forced_student.post("/api/auth/logout")) == {"ok": True}
    assert forced_student.cookies.get(COOKIE_NAME) is None
    forced_student.cookies.set(COOKIE_NAME, token)
    expect(forced_student.get("/api/auth/me"), 401)
    forced_student.cookies.clear()  # Remove the manually replayed, domainless cookie.
    assert expect(forced_student.post("/api/auth/demo", json={"role": "student"}))["user"]["must_change_password"] is False
    expect(forced_student.get("/api/courses"))


@pytest.mark.parametrize("current,new,status", [
    ("synthetic-wrong-password", NEW_PASSWORD, 400),
    ("", NEW_PASSWORD, 400),
    (TEMP_PASSWORD, TEMP_PASSWORD, 400),
    (TEMP_PASSWORD, "x" * 9, 422),
    (TEMP_PASSWORD, "x" * 513, 422),
])
def test_failed_change_preserves_flag_hash_and_sessions(app, forced_student, current, new, status):
    uid = expect(forced_student.get("/api/auth/me"))["user"]["id"]
    token = forced_student.cookies.get(COOKIE_NAME)
    with app.state.database.connect() as conn:
        old_hash = conn.execute("SELECT password_hash FROM users WHERE id=?", (uid,)).fetchone()[0]
        sessions = [tuple(row) for row in conn.execute("SELECT * FROM auth_sessions WHERE user_id=?", (uid,))]
    response = forced_student.post("/api/auth/change-password", json={"current_password": current, "new_password": new})
    expect(response, status)
    assert isinstance(response.json()["detail"], str) and "set-cookie" not in response.headers
    for secret in (TEMP_PASSWORD, NEW_PASSWORD, "synthetic-wrong-password", "x" * 513, old_hash):
        assert secret not in response.text
    assert forced_student.cookies.get(COOKIE_NAME) == token
    assert expect(forced_student.get("/api/auth/me"))["user"]["must_change_password"] is True
    with app.state.database.connect() as conn:
        assert conn.execute("SELECT password_hash FROM users WHERE id=?", (uid,)).fetchone()[0] == old_hash
        assert [tuple(row) for row in conn.execute("SELECT * FROM auth_sessions WHERE user_id=?", (uid,))] == sessions
    expect(forced_student.get("/api/courses"), 403)


def test_change_rotates_cookie_revokes_all_old_sessions_and_preserves_other_users(app, teacher, forced_student):
    uid = expect(forced_student.get("/api/auth/me"))["user"]["id"]
    first_token = forced_student.cookies.get(COOKIE_NAME)
    with TestClient(app) as second, TestClient(app) as replay:
        assert expect(login(second))["user"]["must_change_password"] is True
        second_token = second.cookies.get(COOKIE_NAME)
        assert first_token != second_token
        response = forced_student.post("/api/auth/change-password", json={"current_password": TEMP_PASSWORD, "new_password": NEW_PASSWORD})
        changed = expect(response)["user"]
        assert changed["id"] == uid and changed["must_change_password"] is False
        fresh_token = forced_student.cookies.get(COOKIE_NAME)
        assert fresh_token not in (first_token, second_token)
        assert "HttpOnly" in response.headers["set-cookie"] and "SameSite=lax" in response.headers["set-cookie"]
        assert TEMP_PASSWORD not in response.text and NEW_PASSWORD not in response.text
        assert expect(forced_student.get("/api/auth/me"))["user"] == changed
        assert expect(forced_student.get("/api/courses"))[0]["id"] == COURSE_ID
        assert expect(forced_student.get("/api/sessions/s4/workspace"))["user"] == changed
        expect(second.get("/api/auth/me"), 401)
        expect(second.post("/api/auth/change-password", json={"current_password": NEW_PASSWORD, "new_password": TEMP_PASSWORD}), 401)
        for old in (first_token, second_token):
            replay.cookies.clear()
            replay.cookies.set(COOKIE_NAME, old)
            expect(replay.get("/api/auth/me"), 401)
            expect(replay.get("/api/courses"), 401)
        with app.state.database.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
            assert row["must_change_password"] == 0
            assert password_matches(NEW_PASSWORD, row["password_hash"]) and not password_matches(TEMP_PASSWORD, row["password_hash"])
            tokens = conn.execute("SELECT token_hash FROM auth_sessions WHERE user_id=?", (uid,)).fetchall()
            assert [row[0] for row in tokens] == [hashlib.sha256(fresh_token.encode()).hexdigest()]
        expect(teacher.get("/api/auth/me"))
        expect(login(replay), 401)
        assert expect(login(replay, NEW_PASSWORD))["user"]["must_change_password"] is False
        expect(replay.get("/api/courses"))


@pytest.mark.parametrize("new_length", [8, 512])
def test_new_password_accepts_both_length_boundaries(app, forced_student, new_length):
    chosen = "n" * (new_length - 1) + "1"
    changed = expect(forced_student.post("/api/auth/change-password", json={"current_password": TEMP_PASSWORD, "new_password": chosen}))
    assert changed["user"]["must_change_password"] is False
    expect(login(forced_student, chosen))


@pytest.mark.parametrize("temporary_length", [8, 512])
def test_temporary_password_accepts_both_length_boundaries(app, teacher, temporary_length):
    temporary = "t" * (temporary_length - 1) + "1"
    user = expect(provision(teacher, temporary_password=temporary))["user"]
    with TestClient(app) as client:
        assert expect(login(client, temporary))["user"] == user
        expect(client.get("/api/courses"), 403)


@pytest.mark.parametrize("override", [
    {"name": " "}, {"name": ""}, {"name": "n" * 101},
    {"email": "not-an-email"}, {"email": "bad @example.invalid"}, {"email": "x" * 255},
    {"temporary_password": "x" * 9}, {"temporary_password": "x" * 513},
    {"must_change_password": False}, {"role": "teacher"},
])
def test_provision_validation_matches_registration_and_cannot_override_role(app, teacher, override):
    response = provision(teacher, **override)
    expect(response, 422)
    assert TEMP_PASSWORD not in response.text and "x" * 513 not in response.text
    with app.state.database.connect() as conn:
        assert conn.execute("SELECT count(*) FROM users WHERE is_demo=0").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM enrollments").fetchone()[0] == 2


def test_provision_requires_course_owner_and_teacher_role(app, teacher, student):
    expect(provision(student), 403)
    with TestClient(app) as anonymous:
        expect(provision(anonymous), 401)
    other_id = app.state.database.create_teacher("Other synthetic teacher", "other-auth@example.invalid", TEMP_PASSWORD)
    with TestClient(app) as other:
        assert expect(login(other, email="other-auth@example.invalid"))["user"]["id"] == other_id
        expect(provision(other), 403)
        with app.state.database.connect() as conn:
            assert not conn.execute("SELECT 1 FROM users WHERE email=?", (STUDENT_EMAIL,)).fetchone()
    expect(teacher.post("/api/teacher/courses/absent/students", json={"name": "Synthetic", "email": STUDENT_EMAIL, "temporary_password": TEMP_PASSWORD}), 404)


@pytest.mark.parametrize("existing_kind", ["temporary", "registered", "teacher", "demo"])
def test_existing_email_conflict_never_resets_or_takes_over(app, teacher, existing_kind):
    email = STUDENT_EMAIL
    if existing_kind == "temporary":
        uid = expect(provision(teacher))["user"]["id"]
    elif existing_kind == "registered":
        course = expect(teacher.get("/api/courses"))[0]
        with TestClient(app) as client:
            uid = expect(client.post("/api/auth/register", json={"name": "Synthetic self-registered", "email": email,
                         "password": TEMP_PASSWORD, "join_code": course["join_code"]}))["user"]["id"]
    elif existing_kind == "teacher":
        uid = app.state.database.create_teacher("Existing synthetic teacher", email, TEMP_PASSWORD)
    else:
        uid, email = "demo-student-1", "demo-student-1@example.invalid"
    another_course = expect(teacher.post("/api/courses", json={"title": "Another synthetic course", "code": "OTHER"}))
    with app.state.database.connect() as conn:
        before_user = tuple(conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())
        before_enrollments = [tuple(row) for row in conn.execute("SELECT * FROM enrollments ORDER BY course_id,user_id")]
    response = teacher.post(f"/api/teacher/courses/{another_course['id']}/students", json={
        "name": "Replacement attempt", "email": email.upper(), "temporary_password": NEW_PASSWORD})
    expect(response, 409 if existing_kind == 'teacher' else 200)
    assert NEW_PASSWORD not in response.text and TEMP_PASSWORD not in response.text
    with app.state.database.connect() as conn:
        assert tuple(conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()) == before_user
        current = [tuple(row) for row in conn.execute("SELECT * FROM enrollments ORDER BY course_id,user_id")]
        expected = before_enrollments if existing_kind == 'teacher' else sorted(before_enrollments + [(another_course['id'], uid, None, None)])
        assert current == expected


def test_invite_registration_teacher_and_demo_exemptions(app, teacher, student):
    course = expect(teacher.get("/api/courses"))[0]
    with TestClient(app) as invited:
        user = expect(invited.post("/api/auth/register", json={"name": "Synthetic invited", "email": "invited-auth@example.invalid",
                      "password": TEMP_PASSWORD, "join_code": course["join_code"]}))["user"]
        assert user["must_change_password"] is False
        assert expect(invited.get("/api/auth/me"))["user"] == user
        expect(invited.get("/api/courses"))
        expect(invited.get("/api/sessions/s4/workspace"))
        # Optional password change is also supported for non-forced real accounts.
        assert expect(invited.post("/api/auth/change-password", json={"current_password": TEMP_PASSWORD,
                      "new_password": NEW_PASSWORD}))["user"]["must_change_password"] is False
    real_id = app.state.database.create_teacher("Synthetic real teacher", "real-auth@example.invalid", TEMP_PASSWORD)
    with TestClient(app) as real_teacher:
        assert expect(login(real_teacher, email="real-auth@example.invalid"))["user"]["must_change_password"] is False
        expect(real_teacher.get("/api/teacher/settings"), 403)
        assert expect(real_teacher.post("/api/auth/change-password", json={"current_password": TEMP_PASSWORD,
                      "new_password": NEW_PASSWORD}))["user"]["id"] == real_id
        expect(real_teacher.get("/api/teacher/settings"), 403)
    for demo_client in (teacher, student):
        demo_user = expect(demo_client.get("/api/auth/me"))["user"]
        assert demo_user["must_change_password"] is False
        expect(demo_client.post("/api/auth/change-password", json={"current_password": TEMP_PASSWORD, "new_password": NEW_PASSWORD}), 400)
        with app.state.database.connect() as conn:
            row = conn.execute("SELECT password_hash,must_change_password FROM users WHERE id=?", (demo_user["id"],)).fetchone()
            assert row[0] is None and row[1] == 0
        expect(demo_client.get("/api/courses"))


def test_change_requires_valid_session(app):
    with TestClient(app) as client:
        body = {"current_password": TEMP_PASSWORD, "new_password": NEW_PASSWORD}
        expect(client.post("/api/auth/change-password", json=body), 401)
        client.cookies.set(COOKIE_NAME, "synthetic-invalid-cookie")
        expect(client.post("/api/auth/change-password", json=body), 401)


def test_forced_flag_and_changed_password_survive_restart(app, teacher, catalog, tmp_path):
    user = expect(provision(teacher))["user"]
    restarted = create_app(data_dir=tmp_path / "data", catalog_path=catalog, demo_enabled=True, frontend_dir=tmp_path / "dist")
    with TestClient(restarted) as client:
        assert expect(login(client))["user"] == user
        expect(client.get("/api/courses"), 403)
        expect(client.post("/api/auth/change-password", json={"current_password": TEMP_PASSWORD, "new_password": NEW_PASSWORD}))
        fresh = client.cookies.get(COOKIE_NAME)
    again = create_app(data_dir=tmp_path / "data", catalog_path=catalog, demo_enabled=True, frontend_dir=tmp_path / "dist")
    with TestClient(again) as client:
        client.cookies.set(COOKIE_NAME, fresh)
        assert expect(client.get("/api/auth/me"))["user"]["must_change_password"] is False
        expect(client.get("/api/courses"))
        expect(login(client), 401)
        expect(login(client, NEW_PASSWORD))


def test_legacy_schema_migration_preserves_all_rows_and_sessions(tmp_path, catalog):
    data = tmp_path / "legacy-data"
    data.mkdir()
    path = data / "aicademiya.sqlite3"
    # The exact previous users schema, plus unchanged non-auth tables.
    legacy_users = """CREATE TABLE users (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('teacher','student')), password_hash TEXT,
        is_demo INTEGER NOT NULL DEFAULT 0
    );"""
    legacy_schema = legacy_users + SCHEMA[SCHEMA.index("CREATE TABLE IF NOT EXISTS auth_sessions"):]
    with sqlite3.connect(path) as conn:
        conn.executescript(legacy_schema)
        conn.execute("INSERT INTO users VALUES(?,?,?,?,?,?)", ("legacy-teacher", "Legacy synthetic teacher", "legacy-teacher@example.invalid", "teacher", password_hash(TEMP_PASSWORD), 0))
        conn.execute("INSERT INTO users VALUES(?,?,?,?,?,?)", ("legacy-student", "Legacy synthetic student", "legacy-student@example.invalid", "student", password_hash(TEMP_PASSWORD), 0))
        conn.execute("INSERT INTO users VALUES(?,?,?,?,?,?)", ("demo-student-1", "Legacy synthetic demo", "demo-student-1@example.invalid", "student", None, 1))
        conn.execute("INSERT INTO courses VALUES(?,?,?,?,?,?)", (COURSE_ID, "LEGACY", "Edited legacy course", "Retain content", "legacy-teacher", "legacy-invite"))
        conn.execute("INSERT INTO enrollments VALUES(?,?)", (COURSE_ID, "legacy-student"))
        detail = json.loads(catalog.read_text(encoding="utf-8"))["sessions"][0]
        detail["title"] = "Edited legacy session"
        conn.execute("INSERT INTO sessions VALUES(?,?,?)", ("s4", COURSE_ID, json.dumps(detail)))
        conn.execute("INSERT INTO materials VALUES(?,?,?,?,?)", ("legacy-material", "s4", '{"title":"Edited material"}', None, 1))
        conn.execute("INSERT INTO workspaces(session_id,user_id,status,last_active) VALUES(?,?,?,?)", ("s4", "legacy-student", "in_progress", now()))
        conn.execute("INSERT INTO attempts VALUES(?,?,?,?,?,?)", ("s4", "legacy-student", "q1", "Existing synthetic answer", now(), 1))
        conn.execute("INSERT INTO revisions(session_id,user_id,question_id,answer,created_at) VALUES(?,?,?,?,?)", ("s4", "legacy-student", "q1", "Original synthetic answer", now()))
        conn.execute("INSERT INTO messages(id,session_id,user_id,role,content,created_at,mode) VALUES(?,?,?,?,?,?,?)", ("legacy-message", "s4", "legacy-student", "user", "Existing synthetic chat", now(), "demo"))
        conn.execute("INSERT INTO chat_requests VALUES(?,?,?,?,?,?)", ("s4", "legacy-student", "legacy-request", "synthetic-fingerprint", "done", now()))
        conn.execute("INSERT INTO settings VALUES(?,?)", ("ai_mode", "demo"))
        conn.execute("INSERT INTO meta VALUES(?,?)", ("catalog_imported", "synthetic-prior-import"))
        conn.execute("INSERT INTO meta VALUES(?,?)", ("seed_course_id", COURSE_ID))
        conn.execute("INSERT INTO meta VALUES(?,?)", ("kv_scope_secret", "12" * 32))
        old_cookie = issue_session(conn, "legacy-student")
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        before = {table: conn.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall() for table in tables}
        original_columns = {table: [r[1] for r in conn.execute(f"PRAGMA table_info({table})")] for table in tables}
    for _ in range(2):
        migrated = create_app(data_dir=data, catalog_path=catalog, demo_enabled=False, frontend_dir=tmp_path / "dist")
        with TestClient(migrated) as client:
            with migrated.state.database.connect() as conn:
                columns = {row["name"]: row for row in conn.execute("PRAGMA table_info(users)")}
                assert columns["must_change_password"]["notnull"] == 1 and columns["must_change_password"]["dflt_value"] == "0"
                for table, old_rows in before.items():
                    names = ",".join(original_columns[table])
                    rows = [tuple(row) for row in conn.execute(f"SELECT {names} FROM {table} ORDER BY rowid")]
                    if table == "meta":
                        rows = [r for r in rows if r[0] in {old[0] for old in old_rows}]
                    assert rows == old_rows
                baseline = conn.execute("SELECT published_version_id FROM courses WHERE id=?", (COURSE_ID,)).fetchone()[0]
                assert baseline
                for table in ("workspaces", "attempts", "revisions", "messages", "chat_requests"):
                    assert {r[0] for r in conn.execute(f"SELECT version_id FROM {table}")} == {baseline}
                assert conn.execute("SELECT count(*) FROM course_versions").fetchone()[0] == 1
                assert conn.execute("SELECT role FROM users WHERE id='legacy-teacher'").fetchone()[0] == "teacher"
                assert not conn.execute("PRAGMA foreign_key_check").fetchall()
            client.cookies.set(COOKIE_NAME, old_cookie)
            assert expect(client.get("/api/auth/me"))["user"]["must_change_password"] is False
            work = expect(client.get("/api/sessions/s4/workspace"))
            assert work["session"]["title"] == "Edited legacy session"
            assert work["attempts"]["q1"]["answer"] == "Existing synthetic answer"
            assert work["messages"][0]["content"] == "Existing synthetic chat"
            expect(client.get("/api/courses"))
