"""Contract-level tests: persistence, permissions, student lifecycle, editing."""
import json
from fastapi.testclient import TestClient
from backend.aicademiya.main import create_app
from .conftest import demo_client, expect, question, publish


def test_health_bootstrap_cookie_and_auth(app):
    with TestClient(app) as client:
        assert expect(client.get("/api/health")) == {"status": "ok"}
        boot = expect(client.get("/api/bootstrap"))
        assert boot["app_name"] == "AIcademiya" and boot["demo_enabled"]
        assert boot["default_locale"] == "en" and boot["ai"]["mode"] == "demo"
        expect(client.get("/api/auth/me"), 401)
        response = client.post("/api/auth/demo", json={"role": "student"})
        assert "HttpOnly" in response.headers["set-cookie"] and "SameSite=lax" in response.headers["set-cookie"]
        assert expect(client.get("/api/auth/me"))["user"]["role"] == "student"
        token = client.cookies.get("aicademiya_session")
        expect(client.post("/api/auth/logout"))
        client.cookies.set("aicademiya_session", token)
        expect(client.get("/api/auth/me"), 401)


def test_student_projection_and_download_authorization(student, teacher):
    course = expect(student.get("/api/courses"))[0]
    assert "join_code" not in course and course["student_count"] == 2
    for url in ("/api/sessions/s4", "/api/sessions/s4/workspace", "/api/sessions/s4/export"):
        response = student.get(url)
        expect(response)
        for token in ("TEACHER_REFERENCE", "TEACHER_MATERIAL", "TEACHER_RESEARCH", "DO_NOT_LEAK", "Private synthetic key"):
            assert token not in response.text
    detail = expect(teacher.get("/api/sessions/s4"))
    assert detail["reference_answers"]["q1"] == "TEACHER_REFERENCE_ONLY_q1"
    assert len(detail["materials"]) == 2
    expect(student.get("/api/materials/s4-private/download"), 403)
    assert student.get("/api/materials/s4-public/download").content == b"Synthetic reading"
    assert teacher.get("/api/materials/s4-private/download").content == b"Private synthetic key"


def test_full_lifecycle_revision_reveal_submit_reopen_confirm(student, teacher):
    expect(student.post("/api/sessions/s4/references/q1"), 409)
    expect(student.post("/api/sessions/s4/answers/q1", json={"answer": "   "}), 422)
    work = expect(student.post("/api/sessions/s4/answers/q1", json={"answer": "Initial synthetic response"}))
    assert work["attempts"]["q1"]["revision_count"] == 0
    assert not work["attempts"]["q1"]["reference_revealed"]
    reference = expect(student.post("/api/sessions/s4/references/q1"))
    assert reference["reference"] == "TEACHER_REFERENCE_ONLY_q1"
    work = expect(student.post("/api/sessions/s4/answers/q1", json={"answer": "Revised synthetic response"}))
    assert work["attempts"]["q1"]["revision_count"] == 1
    assert len(work["attempts"]["q1"]["revisions"]) == 2
    assert work["attempts"]["q1"]["reference_revealed"]
    expect(student.post("/api/sessions/s4/submit", json={}), 409)
    expect(teacher.post("/api/teacher/sessions/s4/students/demo-student-1/review", json={"status": "confirmed", "note": "Cannot confirm early"}), 409)
    for i in range(2, 23):
        expect(student.post(f"/api/sessions/s4/answers/q{i}", json={"answer": "A nonempty answer; correctness is not required"}))
    work = expect(student.post("/api/sessions/s4/submit", json={}))
    assert work["progress"]["answered"] == work["progress"]["total"] == 22
    assert work["submission"]["status"] == "submitted"
    expect(student.post("/api/sessions/s4/answers/q1", json={"answer": "Locked"}), 409)
    work = expect(teacher.post("/api/teacher/sessions/s4/students/demo-student-1/review", json={"status": "needs_revision", "note": "Add evidence"}))
    assert work["submission"]["status"] == "needs_revision"
    expect(student.post("/api/sessions/s4/answers/q1", json={"answer": "More evidence"}))
    expect(student.post("/api/sessions/s4/submit", json={}))
    work = expect(teacher.post("/api/teacher/sessions/s4/students/demo-student-1/review", json={"status": "confirmed", "note": "Completion confirmed, no grade"}))
    assert work["submission"]["status"] == "confirmed" and work["submission"]["reviewed_at"]
    assert work["attempts"]["q1"]["revision_count"] == 2
    expect(student.post("/api/sessions/s4/chat", json={"message": "Change answer", "question_id": "q1", "intent": "answer"}), 409)
    assert expect(student.get("/api/sessions/s4/workspace"))["submission"]["status"] == "confirmed"


def test_two_students_and_teacher_preview_are_distinct(app, student, teacher):
    expect(student.post("/api/sessions/s4/answers/q1", json={"answer": "STUDENT_ONE_PRIVATE_RESPONSE"}))
    expect(teacher.post("/api/sessions/s4/answers/q1", json={"answer": "TEACHER_PREVIEW_RESPONSE"}))
    preview = expect(teacher.get("/api/sessions/s4/workspace"))
    assert preview["user"]["id"] == "demo-teacher"
    assert preview["attempts"]["q1"]["answer"] == "TEACHER_PREVIEW_RESPONSE"
    observed = expect(teacher.get("/api/teacher/sessions/s4/students/demo-student-1/workspace"))
    assert observed["user"]["id"] == "demo-student-1" and observed["attempts"]["q1"]["answer"] == "STUDENT_ONE_PRIVATE_RESPONSE"
    with demo_client(app, index=2) as second:
        work = expect(second.get("/api/sessions/s4/workspace"))
        assert not work["attempts"] and "STUDENT_ONE" not in json.dumps(work)
        expect(second.get("/api/teacher/sessions/s4/students/demo-student-1/workspace"), 403)
        expect(second.get("/api/teacher/sessions/s4/students/demo-student-1/export"), 403)
    rows = expect(teacher.get("/api/teacher/sessions/s4/students"))
    assert len(rows) == 2 and {r["answered"] for r in rows} == {0, 1}
    own_export = teacher.get("/api/sessions/s4/export")
    assert "STUDENT_ONE" not in own_export.text and "TEACHER_PREVIEW" in own_export.text
    assert "attachment" in own_export.headers["content-disposition"]
    assert "STUDENT_ONE" in teacher.get("/api/teacher/sessions/s4/students/demo-student-1/export").text


def test_reading_selection_counts_only_active_path_and_preserves_other_branch(student, teacher):
    summaries = expect(student.get("/api/courses/synthetic-course/sessions"))
    assert next(s for s in summaries if s["id"] == "s2")["question_count"] == 14
    for i in range(1, 10):
        expect(student.post(f"/api/sessions/s2/answers/core{i}", json={"answer": "Core response"}))
    expect(student.post("/api/sessions/s2/submit", json={}), 409)
    expect(student.post("/api/sessions/s2/answers/pong1", json={"answer": "Not selected"}), 409)
    work = expect(student.post("/api/sessions/s2/reading", json={"group_id": "II-Pong"}))
    assert work["progress"]["total"] == 14 and len(work["progress"]["active_question_ids"]) == 14
    for i in range(1, 6):
        expect(student.post(f"/api/sessions/s2/answers/pong{i}", json={"answer": "Pong response"}))
    work = expect(student.post("/api/sessions/s2/reading", json={"group_id": "II-Bray"}))
    assert work["progress"]["answered"] == 9 and work["progress"]["total"] == 14
    assert "pong1" in work["attempts"] and "pong1" not in work["progress"]["active_question_ids"]
    expect(student.post("/api/sessions/s2/submit", json={}), 409)
    for i in range(1, 6):
        expect(student.post(f"/api/sessions/s2/answers/bray{i}", json={"answer": "Bray response"}))
    expect(student.post("/api/sessions/s2/submit", json={}))
    expect(teacher.post("/api/teacher/sessions/s2/students/demo-student-1/review", json={"status": "confirmed", "note": "One reading completed"}))
    expect(student.post("/api/sessions/s2/reading", json={"group_id": "II-Pong"}), 409)
    expect(teacher.post("/api/teacher/sessions/s2/students/demo-student-1/review", json={"status": "needs_revision", "note": "Reopened"}))
    work = expect(student.post("/api/sessions/s2/reading", json={"group_id": "II-Pong"}))
    assert work["progress"]["answered"] == 14


def test_chat_intent_and_idempotency(student):
    ask = {"message": "Why does the concept matter?", "question_id": "q1", "intent": "ask", "request_id": "ask-1"}
    work = expect(student.post("/api/sessions/s4/chat", json=ask))
    assert not work["attempts"] and len(work["messages"]) == 2
    assert work["messages"][0]["intent"] == "ask"
    assert "not an LLM" in work["messages"][1]["content"] and work["messages"][1]["mode"] == "demo"
    work = expect(student.post("/api/sessions/s4/chat", json=ask))
    assert len(work["messages"]) == 2
    expect(student.post("/api/sessions/s4/chat", json={**ask, "message": "Different content"}), 409)
    answer = {"message": "An explanation and example", "question_id": "q1", "intent": "answer", "request_id": "answer-1"}
    work = expect(student.post("/api/sessions/s4/chat", json=answer))
    assert work["attempts"]["q1"]["answer"] == answer["message"] and len(work["messages"]) == 4
    work = expect(student.post("/api/sessions/s4/chat", json=answer))
    assert work["attempts"]["q1"]["revision_count"] == 0 and len(work["messages"]) == 4
    expect(student.post("/api/sessions/s4/chat", json={"message": "Missing qid", "intent": "answer"}), 422)


def test_reference_policies_never_bypass_attempt(student, teacher):
    expect(teacher.patch("/api/sessions/s4", json={"reference_policy": "after_feedback"}))
    publish(teacher)
    expect(student.post("/api/sessions/s4/answers/q1", json={"answer": "Attempt"}))
    expect(student.post("/api/sessions/s4/references/q1"), 409)
    expect(student.post("/api/sessions/s4/chat", json={"message": "Please give a hint", "question_id": "q1", "intent": "ask"}))
    expect(student.post("/api/sessions/s4/references/q1"))
    expect(student.post("/api/sessions/s4/references/q2"), 409)
    expect(teacher.patch("/api/sessions/s4", json={"reference_policy": "after_submit"}))
    version = publish(teacher)["id"]
    suffix = "?version_id=" + version
    expect(student.get("/api/sessions/s4/workspace" + suffix))
    expect(student.post("/api/sessions/s4/answers/q1" + suffix, json={"answer": "Fresh edition attempt"}))
    expect(student.post("/api/sessions/s4/references/q1" + suffix), 409)
    for i in range(2, 23):
        expect(student.post(f"/api/sessions/s4/answers/q{i}" + suffix, json={"answer": "Any nonempty explanation"}))
    expect(student.post("/api/sessions/s4/submit" + suffix, json={}))
    expect(student.post("/api/sessions/s4/references/q1" + suffix))


def test_course_and_session_creation_publishing_editing_and_permissions(student, teacher):
    expect(student.post("/api/courses", json={"title": "No", "code": "NO", "description": ""}), 403)
    course = expect(teacher.post("/api/courses", json={"title": "New course", "code": "NEW", "description": "Teacher-authored"}))
    cid = course["id"]
    expect(student.get(f"/api/courses/{cid}/sessions"), 403)
    expect(student.post("/api/courses/join", json={"join_code": course["join_code"]}))
    draft = expect(teacher.post(f"/api/courses/{cid}/sessions", json={"title": "Editable draft", "number": 3}))
    sid = draft["id"]
    assert draft["status"] == "draft" and draft["groups"][0]["id"] == "core"
    assert not expect(student.get(f"/api/courses/{cid}/sessions"))
    expect(student.get(f"/api/sessions/{sid}"), 404)
    q = question("new-q")
    q.pop("teacher_internal")
    detail = expect(teacher.patch(f"/api/sessions/{sid}", json={"questions": [q], "reference_answers": {"new-q": "Teacher edited reference"}, "status": "published", "title": "Published edit"}))
    assert detail["title"] == "Published edit" and detail["question_count"] == 1
    expect(student.get(f"/api/sessions/{sid}"), 404)
    publish(teacher, cid)
    expect(student.get(f"/api/sessions/{sid}"))
    expect(student.patch(f"/api/sessions/{sid}", json={"title": "Not allowed"}), 403)
    expect(teacher.patch(f"/api/sessions/{sid}", json={"questions": [q, q]}), 422)
    expect(teacher.patch(f"/api/sessions/{sid}", json={"reference_answers": {"unknown": "no"}}), 422)
    expect(teacher.patch(f"/api/sessions/{sid}", json={"unknown_metadata": "Not accepted"}), 422)


def test_restart_preserves_answers_messages_and_teacher_edits(app, student, teacher, catalog, tmp_path):
    expect(teacher.patch("/api/sessions/s4", json={"title": "Persisted teacher edit"}))
    publish(teacher)
    expect(student.post("/api/sessions/s4/chat", json={"message": "Persisted synthetic answer", "question_id": "q1", "intent": "answer", "request_id": "persist"}))
    expect(student.post("/api/sessions/s4/references/q1"))
    token = student.cookies.get("aicademiya_session")
    restarted = create_app(data_dir=tmp_path / "data", catalog_path=catalog, demo_enabled=True)
    with TestClient(restarted) as client:
        client.cookies.set("aicademiya_session", token)
        work = expect(client.get("/api/sessions/s4/workspace"))
        assert work["session"]["title"] == "Persisted teacher edit"
        assert work["attempts"]["q1"]["reference_revealed"] and len(work["messages"]) == 2
        assert work["attempts"]["q1"]["answer"] == "Persisted synthetic answer"
        assert len(expect(client.get("/api/courses"))) == 1


def test_safe_assets_and_unknown_api(student):
    assert student.get("/api/assets/plot.png").content.startswith(b"\x89PNG")
    expect(student.get("/api/assets/not-listed.png"), 404)
    expect(student.get("/api/assets/%2E%2E%2Fmaterials%2Fkey.txt"), 404)
    expect(student.get("/api/assets/C:%5CWindows%5Cwin.ini"), 404)
    assert expect(student.get("/api/unknown"), 404) == {"detail": "API route not found"}
    expect(student.post("/api/sessions/s4/answers/q1", json={"answer": "CSRF"}, headers={"Origin": "https://unrelated.invalid"}), 403)


def test_nondemo_real_registration_login_invite_and_teacher_scoping(tmp_path, catalog, monkeypatch):
    monkeypatch.setenv("AICADEMIYA_AI_MODE", "openai")
    app = create_app(data_dir=tmp_path / "real-data", catalog_path=catalog, demo_enabled=False)
    with TestClient(app) as setup:
        assert not expect(setup.get("/api/bootstrap"))["demo_enabled"]
        expect(setup.post("/api/auth/demo", json={"role": "teacher"}), 403)
        # Explicitly synthetic fixture passwords, not user credentials.
        first_id = app.state.database.create_teacher("Synthetic teacher", "teacher@example.invalid", "fixture-password-not-real1")
        app.state.database.create_teacher("Other synthetic teacher", "other@example.invalid", "fixture-password-not-real1")
        expect(setup.post("/api/auth/login", json={"email": "teacher@example.invalid", "password": "fixture-password-not-real1"}))
        assert expect(setup.get("/api/auth/me"))["user"]["id"] == first_id
        course = expect(setup.get("/api/courses"))[0]
        with TestClient(app) as real_student:
            expect(real_student.post("/api/auth/register", json={"name": "Synthetic student", "email": "student@example.invalid", "password": "fixture-password-not-real1", "join_code": "missing"}), 404)
            registered = expect(real_student.post("/api/auth/register", json={"name": "Synthetic student", "email": "student@example.invalid", "password": "fixture-password-not-real1", "join_code": course["join_code"]}))
            assert registered["user"]["role"] == "student"
            expect(real_student.get("/api/courses"))
            expect(real_student.post("/api/courses/join", json={"join_code": course["join_code"]}))
            expect(real_student.post("/api/auth/logout"))
            expect(real_student.post("/api/auth/login", json={"email": "student@example.invalid", "password": "incorrect-synthetic"}), 401)
            expect(real_student.post("/api/auth/login", json={"email": "student@example.invalid", "password": "fixture-password-not-real1"}))
            expect(real_student.get("/api/teacher/settings"), 403)
        with TestClient(app) as other:
            expect(other.post("/api/auth/login", json={"email": "other@example.invalid", "password": "fixture-password-not-real1"}))
            assert not expect(other.get("/api/courses"))
            expect(other.get("/api/sessions/s4"), 403)
            expect(other.get("/api/teacher/sessions/s4/students"), 403)


def test_demo_cookies_invalid_when_demo_disabled(app, student, catalog, tmp_path):
    token = student.cookies.get("aicademiya_session")
    real = create_app(data_dir=tmp_path / "data", catalog_path=catalog, demo_enabled=False)
    with TestClient(real) as client:
        client.cookies.set("aicademiya_session", token)
        expect(client.get("/api/auth/me"), 401)
        expect(client.post("/api/auth/login", json={"email": "demo-teacher@example.invalid", "password": "any-synthetic"}), 401)


def test_missing_catalog_can_author_and_educ_data_dir(tmp_path, monkeypatch):
    data = tmp_path / "env-data"
    monkeypatch.setenv("AICADEMIYA_DATA_DIR", str(data))
    monkeypatch.setenv("AICADEMIYA_DEMO_ENABLED", "false")
    app = create_app(catalog_path=tmp_path / "absent.json")
    with TestClient(app) as client:
        expect(client.get("/api/health"))
        assert app.state.database.path == data / "aicademiya.sqlite3"
        with app.state.database.connect() as conn:
            assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 0
            assert conn.execute("SELECT count(*) FROM courses").fetchone()[0] == 0


def test_validation_errors_have_string_detail_and_no_secrets(app):
    with TestClient(app) as client:
        response = client.post("/api/auth/login", json={"email": "x", "password": "SYNTHETIC_SECRET_VALUE", "extra": "SYNTHETIC_SECRET_EXTRA"})
        assert response.status_code == 422 and isinstance(response.json()["detail"], str)
        assert "SYNTHETIC_SECRET" not in response.text
