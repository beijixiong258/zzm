"""Stage8 lifecycle acceptance: isolated synthetic HTTP/SQLite and file evidence only."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from threading import Event

import pytest
from fastapi.testclient import TestClient
from backend.aicademiya.course_lifecycle import TRASH_MESSAGE, migrate_course_lifecycle
from backend.aicademiya.db import issue_session
from backend.aicademiya.main import create_app
from backend.aicademiya.roster import maintenance
from .conftest import expect, publish, question
from .test_stage2_backup import backup_tool, worksheet_docx, commit_payload
from .test_stage3_persistence import records

CID = "synthetic-course"
BASE = f"/api/courses/{CID}"
VER = f"/api/teacher/courses/{CID}/versions"


def trash(teacher, cid=CID):
    return expect(teacher.post(f"/api/courses/{cid}/trash", json={}))


def restore(teacher, cid=CID):
    return expect(teacher.post(f"/api/courses/{cid}/restore", json={}))


def files(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file() and p.suffix not in (".sqlite3",) and not p.name.endswith(("-wal", "-shm"))}


def schema(conn):
    return [tuple(r) for r in conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name")]


def other_course(teacher, student=None, owner=None):
    client = owner or teacher
    course = expect(client.post("/api/courses", json={"code": "OTHER", "title": "Unrelated synthetic course"}))
    sid = expect(client.post(f"/api/courses/{course['id']}/sessions", json={"title": "Unrelated session"}))["id"]
    q = question("other-q"); q.pop("teacher_internal")
    expect(client.patch(f"/api/sessions/{sid}", json={"questions": [q], "status": "published"}))
    vid = publish(client, course["id"])["id"]
    if student:
        expect(student.post("/api/courses/join", json={"join_code": course["join_code"]}))
        expect(student.post(f"/api/sessions/{sid}/answers/other-q?version_id={vid}", json={"answer": "Keep unrelated history"}))
    return course, sid, vid


def cookie_client(app, uid):
    client = TestClient(app)
    with app.state.database.connect() as conn:
        token = issue_session(conn, uid)
    client.cookies.set("aicademiya_session", token)
    return client


def test_owner_metadata_counts_literal_edit_and_published_student_projection(app, teacher, student):
    initial = expect(teacher.get(BASE))
    assert initial["session_count"] == 2 and initial["material_count"] == 4
    assert initial["enrollment_count"] == initial["student_count"] == 2 and initial["trashed_at"] is None
    assert not any(key in initial for key in ("file_path", "assets_dir", "users", "workspaces"))
    original = expect(student.get("/api/courses"))[0]
    old_snapshot = expect(teacher.get(VER+"/"+initial["published_version_id"]))
    updates = {"code": "  Literal CODE  ", "title": "  Exact\n课程 title  ", "description": " \nDescription remains exact\n "}
    edited = expect(teacher.patch(BASE, json=updates))
    assert all(edited[k] == v for k, v in updates.items())
    assert expect(teacher.get(BASE)) == edited
    assert edited["has_unpublished_changes"]
    for key in ("id", "join_code", "published_version_id", "published_version_number"):
        assert edited[key] == initial[key]
    assert expect(student.get("/api/courses"))[0] == original
    assert expect(teacher.get(VER+"/"+initial["published_version_id"])) == old_snapshot
    expect(teacher.patch(BASE, json={"description": ""}))
    newest = publish(teacher)["id"]
    student_course = expect(student.get("/api/courses"))[0]
    assert student_course["title"] == updates["title"] and student_course["description"] == ""
    assert student_course["published_version_id"] == newest
    assert "join_code" not in student_course and "has_unpublished_changes" not in student_course
    assert expect(teacher.get(VER+"/"+initial["published_version_id"])) == old_snapshot
    # Stage11 sessions follow current draft scope; library/enrollment retention
    # remains separately counted without deleting historical identities.
    with app.state.database.connect() as conn:
        conn.execute("UPDATE sessions SET in_draft=0 WHERE id='s2'")
        conn.execute("UPDATE materials SET archived=1 WHERE id='s2-private'")
        conn.execute("UPDATE enrollments SET archived_at=?,purge_at=? WHERE user_id='demo-student-2'", ("2026-01-01T00:00:00+00:00", "2099-01-01T00:00:00+00:00"))
        conn.execute("INSERT OR IGNORE INTO session_materials VALUES('s4','s2-public')")
    counted = expect(teacher.get(BASE))
    assert counted["session_count"] == 1 and counted["material_count"] == 4 and counted["enrollment_count"] == 2
    with app.state.database.connect() as conn:
        assert conn.execute('SELECT count(*) FROM sessions WHERE course_id=?', (CID,)).fetchone()[0] == 2
    assert counted["student_count"] == 1


@pytest.mark.parametrize("payload", [
    {"code": ""}, {"code": " \t\n"}, {"code": "c"*51}, {"code": None},
    {"title": ""}, {"title": " \n"}, {"title": "t"*301}, {"title": None},
    {"description": "d"*10001}, {"description": None},
    {"id": "replacement"}, {"owner_id": "demo-admin"}, {"join_code": "replacement"},
    {"published_version_id": "replacement"}, {"trashed_at": None}, {"student_count": 0}, {"unknown": True},
])
def test_edit_validation_is_atomic_and_extra_fields_rejected(teacher, payload):
    before = expect(teacher.get(BASE))
    expect(teacher.patch(BASE, json={"description": "Must not partially save", **payload}), 422)
    assert expect(teacher.get(BASE)) == before


def test_empty_patch_limits_and_recovery_payloads_are_strict(teacher):
    before = expect(teacher.get(BASE))
    assert expect(teacher.patch(BASE, json={})) == before
    exact = {"code": "c"*50, "title": "t"*300, "description": "d"*10000}
    saved = expect(teacher.patch(BASE, json=exact))
    assert all(saved[k] == v for k, v in exact.items())
    for operation in ("trash", "restore"):
        expect(teacher.post(BASE+"/"+operation, json={"confirm": True}), 422)
    assert expect(teacher.get(BASE))["trashed_at"] is None
    assert teacher.delete(BASE).status_code == 405


@pytest.mark.parametrize("trashed", [False, True])
def test_role_and_ownership_metadata_recovery_content_and_invite_privacy(app, teacher, student, admin, trashed):
    uid = app.state.database.create_teacher("Synthetic outsider", "outsider@example.invalid", "synthetic-test1")
    outsider = cookie_client(app, uid)
    anonymous = TestClient(app)
    own = expect(admin.post("/api/courses", json={"code": "ADMIN", "title": "Admin-owned synthetic course"}))
    assert expect(admin.get(f"/api/courses/{own['id']}"))["id"] == own["id"]
    if trashed:
        trash(teacher)
    for client in (student, admin, outsider, anonymous):
        status = 401 if client is anonymous else 403
        expect(client.get(BASE), status)
        expect(client.patch(BASE, json={"title": "Unauthorized edit"}), status)
        for op in ("trash", "restore"):
            response = client.post(BASE+"/"+op, json={})
            expect(response, status)
            assert TRASH_MESSAGE not in response.text
        response = client.get("/api/sessions/s4")
        if client is student:
            expect(response, 410 if trashed else 200)
        else:
            expect(response, status)
            assert TRASH_MESSAGE not in response.text
    expect(student.get("/api/courses/trash"), 403)
    expect(anonymous.get("/api/courses/trash"), 401)
    expect(teacher.get("/api/courses/missing"), 404)
    expect(teacher.patch("/api/courses/missing", json={"code": "MISSING"}), 404)
    for op in ("trash", "restore"):
        expect(teacher.post("/api/courses/missing/"+op, json={}), 404)
    assert expect(admin.get("/api/courses/trash")) == {"courses": []}
    assert expect(outsider.get("/api/courses/trash")) == {"courses": []}
    # Admin is owner only, never a cross-owner superuser.
    admin_trash = trash(admin, own["id"])
    assert expect(admin.get("/api/courses/trash"))["courses"] == [admin_trash]
    assert restore(admin, own["id"])["trashed_at"] is None
    outsider.close(); anonymous.close()


COMMON_PATHS = [
    ("GET", "/api/courses/{cid}/sessions", None),
    ("GET", "/api/sessions/s4", None),
    ("GET", "/api/sessions/s4/workspace", None),
    ("GET", "/api/sessions/s4/export", None),
    ("GET", "/api/sessions/s4/transcript", None),
    ("GET", "/api/sessions/s4/transcript?format=txt", None),
    ("GET", "/api/sessions/s4/references/q1", None),
    ("POST", "/api/sessions/s4/references/q1", None),
    ("POST", "/api/sessions/s4/answers/q1", {"answer": "Blocked new answer"}),
    ("POST", "/api/sessions/s4/reading", {"group_id": "reading"}),
    ("POST", "/api/sessions/s4/submit", {}),
    ("POST", "/api/sessions/s4/chat", {"message": "Blocked feedback", "intent": "ask", "request_id": "blocked"}),
    ("POST", "/api/sessions/s4/tutor/start", {"request_id": "blocked"}),
    ("POST", "/api/sessions/s4/tutor/turn", {"message": "Blocked guided turn", "request_id": "blocked"}),
    ("GET", "/api/materials/s4-public/download", None),
    ("GET", "/api/materials/s4-public/preview", None),
    ("GET", "/api/materials/s4-private/download", None),
    ("GET", "/api/materials/s4-public/assets/figure.png", None),
]


@pytest.mark.parametrize("historical", [False, True])
@pytest.mark.parametrize("role", ["teacher", "student"])
@pytest.mark.parametrize("method,path,payload", COMMON_PATHS)
def test_every_current_and_historical_learning_content_path_closed(app, teacher, student, monkeypatch, historical, role, method, path, payload):
    old = expect(student.get("/api/sessions/s4/workspace"))["version"]["id"]
    expect(student.post(f"/api/sessions/s4/answers/q1?version_id={old}", json={"answer": "Retained answer"}))
    if historical:
        expect(teacher.patch("/api/sessions/s4", json={"title": "New draft edition"}))
        publish(teacher)
    trash(teacher)
    with app.state.database.connect() as conn:
        before = records(conn)
    def forbidden(*args, **kwargs):
        raise AssertionError("Inference must not run for a trashed course")
    monkeypatch.setattr(app.state.tutor, "complete", forbidden)
    monkeypatch.setattr(app.state.tutor, "feedback", forbidden)
    monkeypatch.setattr("backend.aicademiya.guided_routes.run_lesson", forbidden)
    url = path.format(cid=CID)
    if historical:
        url += ("&" if "?" in url else "?") + "version_id=" + old
    client = teacher if role == "teacher" else student
    response = client.request(method, url, **({"json": payload} if payload is not None else {}))
    assert expect(response, 410) == {"detail": TRASH_MESSAGE}
    with app.state.database.connect() as conn:
        assert records(conn) == before


OWNER_PATHS = [
    ("GET", "/api/courses/{cid}/materials", None),
    ("POST", "/api/courses/{cid}/sessions", {"title": "Blocked new session"}),
    ("PATCH", "/api/courses/{cid}", {"title": "Blocked draft metadata"}),
    ("PATCH", "/api/sessions/s4", {"title": "Blocked draft content"}),
    ("GET", "/api/teacher/courses/{cid}/students", None),
    ("GET", "/api/teacher/courses/{cid}/students?archived=true", None),
    ("POST", "/api/teacher/courses/{cid}/students", {"name": "Blocked new student", "email": "blocked@example.invalid", "temporary_password": "synthetic-test1"}),
    ("POST", "/api/teacher/courses/{cid}/students/archive", {"user_ids": ["demo-student-1"]}),
    ("POST", "/api/teacher/courses/{cid}/students/restore", {"user_ids": ["demo-student-1"]}),
    ("POST", "/api/teacher/courses/{cid}/students/import/missing/commit", {}),
    ("GET", "/api/teacher/sessions/s4/students", None),
    ("GET", "/api/teacher/sessions/s4/students/demo-student-1/workspace", None),
    ("GET", "/api/teacher/sessions/s4/students/demo-student-1/export", None),
    ("POST", "/api/teacher/sessions/s4/students/demo-student-1/review", {"status": "confirmed"}),
    ("GET", "/api/teacher/sessions/s4/preview", None),
    ("POST", "/api/teacher/sessions/s4/preview/reset", {"expected_revision": "blocked"}),
    ("POST", "/api/teacher/sessions/s4/source-review", {}),
    ("POST", "/api/sessions/s4/teaching-preview", {}),
    ("POST", "/api/sessions/s4/materials/attach", {"material_id": "s2-public"}),
    ("PATCH", "/api/sessions/s4/materials/s4-public", {"title": "Blocked title"}),
    ("DELETE", "/api/sessions/s4/materials/s4-public", None),
    ("POST", "/api/sessions/s4/materials/s4-public/reprocess", None),
    ("POST", "/api/sessions/s4/materials/link", {"url": "https://example.invalid/blocked"}),
    ("POST", "/api/sessions/s4/worksheet-import/missing/commit", {"groups": [], "questions": [], "reference_answers": {}, "mode": "replace"}),
    ("GET", "/api/teacher/courses/{cid}/versions", None),
    ("GET", "/api/teacher/courses/{cid}/versions/{vid}", None),
    ("GET", "/api/teacher/courses/{cid}/versions/{vid}/diff", None),
    ("POST", "/api/teacher/courses/{cid}/versions/publish", {}),
    ("POST", "/api/teacher/courses/{cid}/versions/{vid}/restore", {}),
]


@pytest.mark.parametrize("method,path,payload", OWNER_PATHS)
def test_all_owner_authoring_review_roster_material_version_paths_closed(app, teacher, monkeypatch, method, path, payload):
    vid = expect(teacher.get(BASE))["published_version_id"]
    trash(teacher)
    with app.state.database.connect() as conn:
        before = records(conn)
    def forbidden(*args, **kwargs):
        raise AssertionError("No extraction/network allowed after trash")
    monkeypatch.setattr("backend.aicademiya.authoring.link_data", forbidden)
    monkeypatch.setattr("backend.aicademiya.materials.extract_document", forbidden)
    response = teacher.request(method, path.format(cid=CID, vid=vid), **({"json": payload} if payload is not None else {}))
    assert expect(response, 410) == {"detail": TRASH_MESSAGE}
    with app.state.database.connect() as conn:
        assert records(conn) == before


@pytest.mark.parametrize("route", [
    "/api/sessions/s4/materials", "/api/sessions/s4/worksheet-import/preview",
    "/api/teacher/sessions/s4/instruction-import/preview", "/api/teacher/courses/synthetic-course/students/import/preview",
])
def test_upload_and_import_entrypoints_do_not_parse_or_write_after_trash(app, teacher, monkeypatch, route):
    trash(teacher)
    with app.state.database.connect() as conn:
        before = records(conn)
    existing = files(app.state.database.path.parent)
    def forbidden(*args, **kwargs):
        raise AssertionError("No parsing after trash")
    monkeypatch.setattr("backend.aicademiya.materials.extract_document", forbidden)
    monkeypatch.setattr("backend.aicademiya.teacher_workbench_routes.extract_document", forbidden)
    response = teacher.post(route, files={"file": ("fixture.txt", b"Synthetic input")})
    assert expect(response, 410) == {"detail": TRASH_MESSAGE}
    with app.state.database.connect() as conn:
        assert records(conn) == before
    assert files(app.state.database.path.parent) == existing


def test_invite_denied_before_user_enrollment_auth_creation_and_restore_same_invite(app, teacher, student):
    invite = expect(teacher.get(BASE))["join_code"]
    trash(teacher)
    anonymous = TestClient(app)
    with app.state.database.connect() as conn:
        before = records(conn)
    expect(anonymous.post("/api/auth/register", json={"name": "Synthetic new account", "email": "new-trash@example.invalid", "password": "synthetic-test1", "join_code": invite}), 404)
    expect(student.post("/api/courses/join", json={"join_code": invite}), 404)
    assert not anonymous.cookies.get("aicademiya_session")
    with app.state.database.connect() as conn:
        assert records(conn) == before
    assert restore(teacher)["join_code"] == invite
    user = expect(anonymous.post("/api/auth/register", json={"name": "Synthetic new account", "email": "new-trash@example.invalid", "password": "synthetic-test1", "join_code": invite}))["user"]
    assert user["role"] == "student"
    assert expect(anonymous.get("/api/courses"))[0]["id"] == CID
    anonymous.close()


def test_lists_history_and_public_static_assets_are_course_scoped(app, teacher, student):
    first = expect(student.get("/api/sessions/s4/workspace"))["version"]["id"]
    expect(student.post("/api/sessions/s4/answers/q1", json={"answer": "Retain hidden history"}))
    other, sid, other_vid = other_course(teacher, student)
    expect(teacher.post("/api/sessions/s4/answers/q1", json={"answer": "Retain private teacher history"}))
    expect(teacher.post(f"/api/sessions/{sid}/answers/other-q", json={"answer": "Keep teacher history"}))
    student_other_before = expect(student.get(f"/api/sessions/{sid}/workspace?version_id={other_vid}"))
    student_history_before = expect(student.get("/api/history"))
    teacher_history_before = expect(teacher.get("/api/history"))
    assert student.get("/api/assets/plot.png").status_code == 200
    state = trash(teacher)
    assert expect(teacher.get("/api/courses/trash"))["courses"] == [state]
    assert [c["id"] for c in expect(teacher.get("/api/courses"))] == [other["id"]]
    assert [c["id"] for c in expect(student.get("/api/courses"))] == [other["id"]]
    assert expect(student.get("/api/history")) == [h for h in student_history_before if h["course"]["id"] != CID]
    assert expect(teacher.get("/api/history")) == [h for h in teacher_history_before if h["course"]["id"] != CID]
    assert expect(student.get(f"/api/sessions/{sid}/workspace?version_id={other_vid}")) == student_other_before
    assert student.get("/api/assets/plot.png").status_code == 404
    # The same catalog bytes remain available if a live course references them.
    with app.state.database.connect() as conn:
        raw = json.loads(conn.execute("SELECT content_json FROM sessions WHERE id=?", (sid,)).fetchone()[0])
        raw["questions"][0]["images"] = [{"label": "Synthetic shared figure", "url": "/api/assets/plot.png", "alt": "Shared"}]
        conn.execute("UPDATE sessions SET content_json=? WHERE id=?", (json.dumps(raw), sid))
    publish(teacher, other["id"])
    expect(teacher.patch(f"/api/sessions/{sid}", json={"questions": [{**question("other-q"), "teacher_internal": None}]}), 422)
    # Remove draft reference with validated payload; immutable live history still whitelists.
    q = question("other-q"); q.pop("teacher_internal")
    expect(teacher.patch(f"/api/sessions/{sid}", json={"questions": [q]}))
    assert student.get("/api/assets/plot.png").status_code == 200
    trash(teacher, other["id"])
    assert expect(student.get("/api/history")) == []
    assert student.get("/api/assets/plot.png").status_code == 404
    restore(teacher)
    assert student.get("/api/assets/plot.png").status_code == 200
    assert any(h["version"]["id"] == first for h in expect(student.get("/api/history")))


def test_idempotent_trash_restore_preserve_every_original_table_schema_and_file(app, teacher, student, catalog):
    preview = expect(teacher.post("/api/sessions/s4/worksheet-import/preview", files={"file": ("synthetic.docx", worksheet_docx())}))
    expect(teacher.post(f"/api/sessions/s4/worksheet-import/{preview['import_id']}/commit", json=commit_payload(preview)))
    mid = preview["material"]["id"]
    expect(teacher.patch(f"/api/sessions/s4/materials/{mid}", json={"visibility": "student"}))
    first = publish(teacher)["id"]
    work = expect(student.get(f"/api/sessions/s4/workspace?version_id={first}"))
    qid = work["session"]["questions"][0]["id"]
    expect(student.post(f"/api/sessions/s4/answers/{qid}?version_id={first}", json={"answer": "Retain original answer"}))
    expect(student.post(f"/api/sessions/s4/answers/{qid}?version_id={first}", json={"answer": "Retain revised answer"}))
    expect(student.post(f"/api/sessions/s4/references/{qid}?version_id={first}"))
    expect(student.post(f"/api/sessions/s4/chat?version_id={first}", json={"message": "Retain raw transcript", "intent": "ask", "request_id": "legacy-done"}))
    expect(student.post(f"/api/sessions/s4/tutor/start?version_id={first}", json={"request_id": "guided-done"}))
    info = expect(teacher.get("/api/teacher/sessions/s4/preview"))
    expect(teacher.post("/api/teacher/sessions/s4/preview/reset", json={"expected_revision": info["current_revision"]}))
    expect(teacher.post("/api/sessions/s4/worksheet-import/preview", files={"file": ("retained-pending.docx", worksheet_docx())}))
    expect(teacher.patch("/api/sessions/s4", json={"active": False, "starts_at": "2098-01-01T00:00:00+00:00", "ends_at": "2099-01-01T00:00:00+00:00"}))
    with app.state.database.connect() as conn:
        conn.execute("INSERT OR REPLACE INTO settings VALUES('ai_api_key','SYNTHETIC_RETAINED_KEY')")
        conn.execute("INSERT OR REPLACE INTO meta VALUES('kv_scope_secret','SYNTHETIC_RETAINED_NAMESPACE')")
        conn.execute("UPDATE enrollments SET archived_at='2026-01-01T00:00:00+00:00',purge_at='2099-01-01T00:00:00+00:00' WHERE user_id='demo-student-2'")
        before = records(conn)
        original_schema = schema(conn)
        seq = [tuple(r) for r in conn.execute("SELECT * FROM sqlite_sequence ORDER BY name")]
    assert len(before) == 27
    assert all(data["rows"] for name, data in before.items() if name not in ("course_trash", "account_avatars", "feedback", "account_imports", "document_jobs", "document_revisions"))
    assert before["document_jobs"]["rows"] == [] and before["document_revisions"]["rows"] == []
    assert before['account_imports']['rows'] == []
    assert before["account_avatars"]["rows"] == [] and before["feedback"]["rows"] == []
    original_files = files(catalog.parent) | {"data/"+k: v for k, v in files(app.state.database.path.parent).items()}
    metadata = expect(teacher.get(BASE))
    first_trash = trash(teacher)
    assert first_trash["trashed_at"] and first_trash["id"] == metadata["id"]
    assert trash(teacher) == first_trash
    assert expect(teacher.get(BASE)) == first_trash
    with app.state.database.connect() as conn:
        after = records(conn)
        assert {k: v for k, v in after.items() if k != "course_trash"} == {k: v for k, v in before.items() if k != "course_trash"}
        assert len(after["course_trash"]["rows"]) == 1
        assert after["course_trash"]["rows"][0] == (CID, first_trash["trashed_at"], "demo-teacher")
    restored = restore(teacher)
    assert restored == metadata and restore(teacher) == metadata
    with app.state.database.connect() as conn:
        assert records(conn) == before
        assert schema(conn) == original_schema
        assert [tuple(r) for r in conn.execute("SELECT * FROM sqlite_sequence ORDER BY name")] == seq
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
    assert files(catalog.parent) | {"data/"+k: v for k, v in files(app.state.database.path.parent).items()} == original_files
    loaded = expect(student.get(f"/api/sessions/s4/workspace?version_id={first}"))
    assert loaded["attempts"][qid]["answer"] == "Retain revised answer"
    assert loaded["read_only_reason"] == "session_inactive"  # Never forced open by restore.
    expect(student.post(f"/api/sessions/s4/answers/{qid}?version_id={first}", json={"answer": "Still closed"}), 409)


@pytest.mark.parametrize("table", ["chat_requests", "tutor_requests"])
@pytest.mark.parametrize("staff", [False, True])
def test_pending_any_user_and_historical_request_refuses_trash_without_mutation(app, teacher, student, table, staff):
    uid = "demo-teacher" if staff else "demo-student-1"
    old = expect(student.get("/api/sessions/s4/workspace"))["version"]["id"]
    publish(teacher)
    with app.state.database.connect() as conn:
        conn.execute("INSERT OR IGNORE INTO workspaces(session_id,user_id,version_id) VALUES('s4',?,?)", (uid, old))
        if table == "chat_requests":
            conn.execute("INSERT INTO chat_requests(session_id,user_id,version_id,request_id,fingerprint,status,created_at) VALUES('s4',?,?,'pending-fixture','synthetic','pending','2026-01-01')", (uid, old))
        else:
            conn.execute("INSERT INTO tutor_requests VALUES('s4',?,?,'pending-fixture','synthetic','pending','2026-01-01','{}')", (uid, old))
        before = records(conn)
    expect(teacher.post(BASE+"/trash", json={}), 409)
    with app.state.database.connect() as conn:
        assert records(conn) == before
        conn.execute(f"UPDATE {table} SET status='failed' WHERE request_id='pending-fixture'")
    assert trash(teacher)["trashed_at"]


@pytest.mark.parametrize("guided", [False, True])
def test_real_reservation_barrier_trash_conflict_and_unrelated_course_not_blocked(app, teacher, student, monkeypatch, guided):
    other, _, _ = other_course(teacher)
    entered, release = Event(), Event()
    if guided:
        from backend.aicademiya.guided_routes import run_lesson
        def held(*args, **kwargs):
            entered.set()
            assert release.wait(10), "Synthetic test barrier was not released"
            return run_lesson(*args, **kwargs)
        monkeypatch.setattr("backend.aicademiya.guided_routes.run_lesson", held)
        url, body, table = "/api/sessions/s4/tutor/start", {"request_id": "accepted-barrier"}, "tutor_requests"
    else:
        original = app.state.tutor.feedback
        def held(*args, **kwargs):
            entered.set()
            assert release.wait(10), "Synthetic test barrier was not released"
            return original(*args, **kwargs)
        monkeypatch.setattr(app.state.tutor, "feedback", held)
        url, body, table = "/api/sessions/s4/chat", {"request_id": "accepted-barrier", "message": "Accepted synthetic request", "intent": "ask"}, "chat_requests"
    with ThreadPoolExecutor(max_workers=1) as pool:
        job = pool.submit(student.post, url, json=body)
        try:
            assert entered.wait(10), "Request never reached the inference barrier"
            with app.state.database.connect() as conn:
                assert conn.execute(f"SELECT status FROM {table} WHERE request_id='accepted-barrier'").fetchone()[0] == "pending"
            expect(teacher.post(BASE+"/trash", json={}), 409)
            assert trash(teacher, other["id"])["trashed_at"]
            assert not job.done()
        finally:
            release.set()
        completed = expect(job.result(timeout=10))
    assert completed["messages"][-1]["role"] == "assistant"
    assert trash(teacher)["trashed_at"]
    assert expect(student.post(url, json=body), 410) == {"detail": TRASH_MESSAGE}  # Completed retry shortcuts also gated.
    expect(student.post("/api/sessions/s4/tutor/start", json={}), 410)  # Resume-without-ID shortcut.


@pytest.mark.parametrize("guided", [False, True])
def test_commit_live_guard_rejects_out_of_band_marker_without_saved_result(app, teacher, student, monkeypatch, guided):
    # Direct SQL simulates a late administrative boundary, never a production action.
    def mark():
        with app.state.database.connect() as conn:
            conn.execute("INSERT INTO course_trash VALUES(?,?,?)", (CID, "2026-01-01T00:00:00+00:00", "demo-teacher"))
    if guided:
        from backend.aicademiya.guided_routes import run_lesson
        def held(*args, **kwargs):
            result = run_lesson(*args, **kwargs)
            mark()
            return result
        monkeypatch.setattr("backend.aicademiya.guided_routes.run_lesson", held)
        response = student.post("/api/sessions/s4/tutor/start", json={"request_id": "guard"})
    else:
        original = app.state.tutor.feedback
        def held(*args, **kwargs):
            result = original(*args, **kwargs)
            mark()
            return result
        monkeypatch.setattr(app.state.tutor, "feedback", held)
        response = student.post("/api/sessions/s4/chat", json={"request_id": "guard", "message": "Accepted raw input", "intent": "ask"})
    assert expect(response, 410) == {"detail": TRASH_MESSAGE}
    with app.state.database.connect() as conn:
        assert not conn.execute("SELECT 1 FROM messages WHERE role='assistant'").fetchone()
        assert not conn.execute("SELECT 1 FROM attempts").fetchone()


@pytest.mark.parametrize("kind", ["upload", "reprocess", "link", "worksheet", "instruction", "roster"])
def test_async_extraction_paths_recheck_live_at_commit_or_result(app, teacher, monkeypatch, kind):
    with app.state.database.connect() as conn:
        before = records(conn)
    if kind in ("upload", "reprocess", "instruction"):
        if kind == "instruction":
            module = "backend.aicademiya.teacher_workbench_routes"
        else:
            module = "backend.aicademiya.materials"
        import importlib
        original = importlib.import_module(module).extract_document
        def extracting(*args, **kwargs):
            result = original(*args, **kwargs)
            trash(teacher)
            return result
        monkeypatch.setattr(module+".extract_document", extracting)
        if kind == "reprocess":
            response = teacher.post("/api/sessions/s4/materials/s4-public/reprocess")
        else:
            route = "/api/sessions/s4/materials" if kind == "upload" else "/api/teacher/sessions/s4/instruction-import/preview"
            response = teacher.post(route, files={"file": ("synthetic.txt", b"Synthetic text for commit test")})
    elif kind == "link":
        def extracting(*args, **kwargs):
            trash(teacher)
            return {"id": "synthetic-late-link", "title": "Synthetic", "kind": "link", "visibility": "student"}
        monkeypatch.setattr("backend.aicademiya.authoring.link_data", extracting)
        response = teacher.post("/api/sessions/s4/materials/link", json={"url": "https://example.invalid/synthetic"})
    elif kind == "worksheet":
        def extracting(*args, **kwargs):
            trash(teacher)
            return {"title": "Synthetic", "groups": [], "questions": [], "reference_answers": {}, "source_text": "Synthetic", "warnings": [], "assets": []}
        monkeypatch.setattr("backend.aicademiya.worksheet_import.preview_worksheet", extracting)
        response = teacher.post("/api/sessions/s4/worksheet-import/preview", files={"file": ("synthetic.txt", b"1. Synthetic question?")})
    else:
        from backend.aicademiya.roster import parse_rows
        def extracting(*args, **kwargs):
            parsed = parse_rows(*args, **kwargs)
            trash(teacher)
            return parsed
        monkeypatch.setattr("backend.aicademiya.roster.parse_rows", extracting)
        response = teacher.post(f"/api/teacher/courses/{CID}/students/import/preview", files={"file": ("synthetic.csv", b"name,email\nSynthetic,late@example.invalid\n")})
    assert expect(response, 410) == {"detail": TRASH_MESSAGE}
    with app.state.database.connect() as conn:
        after = records(conn)
        assert {k: v for k, v in after.items() if k != "course_trash"} == {k: v for k, v in before.items() if k != "course_trash"}


def test_original_20_table_schema5_migration_is_additive_idempotent_and_restart_safe(app, teacher, student, catalog, tmp_path):
    expect(student.post("/api/sessions/s4/chat", json={"message": "Preserve migration transcript", "intent": "ask", "request_id": "migration"}))
    with app.state.database.connect() as conn:
        conn.execute("INSERT OR REPLACE INTO settings VALUES('ai_api_key','SYNTHETIC_RETAIN_KEY')")
        conn.execute("INSERT OR REPLACE INTO meta VALUES('kv_scope_secret','SYNTHETIC_RETAIN_SECRET')")
        conn.execute("DROP TABLE course_trash")
        conn.execute("DROP TABLE account_avatars")
        conn.execute("DROP TABLE feedback")
        conn.execute("PRAGMA user_version=5")
        original = {k: v for k, v in records(conn).items() if k not in ('course_staff','account_imports','document_jobs','document_revisions')}
        stage11_before = {k: v for k, v in records(conn).items() if k in ('course_staff','account_imports','document_jobs','document_revisions')}
        original_schema = schema(conn)
    assert len(original) == 20
    original_files = files(catalog.parent)
    for _ in range(2):
        app.state.database.initialize(catalog, demo_enabled=False)
    with app.state.database.connect() as conn:
        after = records(conn)
        assert len(after) == 27 and after["course_trash"]["rows"] == []
        assert all(after[k] == v for k, v in stage11_before.items())
        assert after["account_avatars"]["rows"] == [] and after["feedback"]["rows"] == []
        assert all(after[k] == v for k, v in original.items())
        assert [r for r in schema(conn) if r[2] not in ("course_trash", "account_avatars", "feedback")] == original_schema
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 9
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
    marked = trash(teacher)
    # Initialization is independent of mutable startup recovery/retention policy.
    app.state.database.initialize(catalog, demo_enabled=False)
    assert expect(teacher.get(BASE)) == marked
    restarted = create_app(data_dir=app.state.database.path.parent, catalog_path=catalog, demo_enabled=True, frontend_dir=tmp_path/"none")
    with TestClient(restarted) as client:
        client.cookies.update(teacher.cookies)
        assert expect(client.get(BASE)) == marked
        assert expect(client.get("/api/courses")) == []
        expect(client.get("/api/sessions/s4"), 410)
        assert restore(client)["join_code"] == marked["join_code"]
        client.cookies.clear(); client.cookies.update(student.cookies)
        restored_work = expect(client.get("/api/sessions/s4/workspace"))
        assert restored_work["messages"][0]["content"] == "Preserve migration transcript"
    assert files(catalog.parent) == original_files
    assert app.version == "0.11.0" and app.openapi()["info"]["version"] == "0.11.0"


def test_trash_files_assets_staging_and_history_survive_dynamic_backup_relocation(app, teacher, student, catalog, tmp_path):
    preview = expect(teacher.post("/api/sessions/s4/worksheet-import/preview", files={"file": ("synthetic.docx", worksheet_docx())}))
    expect(teacher.post(f"/api/sessions/s4/worksheet-import/{preview['import_id']}/commit", json=commit_payload(preview)))
    mid = preview["material"]["id"]
    expect(teacher.patch(f"/api/sessions/s4/materials/{mid}", json={"visibility": "student"}))
    historic = publish(teacher)["id"]
    work = expect(student.get("/api/sessions/s4/workspace"))
    qid = work["session"]["questions"][0]["id"]
    expect(student.post(f"/api/sessions/s4/answers/{qid}", json={"answer": "Relocated retained history"}))
    image = work["session"]["questions"][0]["images"][0]["url"]
    expected_asset = student.get(image).content
    expected_original = student.get(f"/api/materials/{mid}/download?version_id={historic}").content
    pending = expect(teacher.post("/api/sessions/s4/worksheet-import/preview", files={"file": ("pending.docx", worksheet_docx())}))
    expect(teacher.patch("/api/sessions/s4", json={"title": "Another edition"}))
    publish(teacher)
    state = trash(teacher)
    with app.state.database.connect() as conn:
        before = records(conn)
    backup, restored = tmp_path/"stage8-backup", tmp_path/"stage8-restored"
    backup_tool.backup(app.state.database.path.parent, backup, catalog.parent/"materials")
    report = backup_tool.restore(backup, restored)
    assert report["records_match"] and report["files_match"]
    manifest = json.loads((backup/"manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["tables"]) == set(before) | {"sqlite_sequence"}
    with closing(sqlite3.connect(restored/backup_tool.DB_NAME)) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 9
        for name, data in before.items():
            if name not in ("materials", "course_versions", "import_staging"):
                assert [tuple(r) for r in conn.execute(f'SELECT * FROM "{name}" ORDER BY rowid')] == data["rows"]
    source = app.state.database.path.parent
    hidden_source, hidden_seed = source.with_name("synthetic-source-unavailable"), catalog.parent.with_name("synthetic-seed-unavailable")
    source.rename(hidden_source); catalog.parent.rename(hidden_seed)
    try:
        relocated = create_app(data_dir=restored, catalog_path=catalog, demo_enabled=True, frontend_dir=tmp_path/"none")
        with TestClient(relocated) as client:
            client.cookies.update(teacher.cookies)
            assert expect(client.get(BASE)) == state
            expect(client.get(image), 410)
            expect(client.get(pending["assets"][0]["url"]), 410)
            restore(client)
            assert client.get(pending["assets"][0]["url"]).content == expected_asset
            client.cookies.clear(); client.cookies.update(student.cookies)
            historical = expect(client.get(f"/api/sessions/s4/workspace?version_id={historic}"))
            assert historical["attempts"][qid]["answer"] == "Relocated retained history"
            assert client.get(image).content == expected_asset
            download = client.get(f"/api/materials/{mid}/download?version_id={historic}")
            assert download.status_code == 200 and download.content == expected_original
            assert historical["read_only_reason"] == "historical_version"
    finally:
        hidden_source.rename(source); hidden_seed.rename(catalog.parent)


@pytest.mark.parametrize("global_archived", [False, True])
@pytest.mark.parametrize("enrollment_archived", [False, True])
def test_retention_suppression_keeps_original_deadlines_and_active_courses_unchanged(app, teacher, student, global_archived, enrollment_archived):
    expect(student.post("/api/sessions/s4/chat", json={"message": "Retain transcript under trash", "intent": "ask", "request_id": "retained"}))
    expect(student.post("/api/sessions/s4/tutor/start", json={"request_id": "retained-guided"}))
    other, sid, _ = other_course(teacher, student)
    past = (datetime.now(timezone.utc)-timedelta(days=31)).isoformat()
    deadline = (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
    trash(teacher)
    with app.state.database.connect() as conn:
        # Trash enrollment may be independently active or archived; neither is rewritten.
        if enrollment_archived:
            conn.execute("UPDATE enrollments SET archived_at=?,purge_at=? WHERE course_id=? AND user_id='demo-student-1'", (past, deadline, CID))
        if global_archived:
            conn.execute("UPDATE users SET archived_at=?,purge_at=? WHERE id='demo-student-1'", (past, deadline))
        conn.execute("UPDATE enrollments SET archived_at=?,purge_at=? WHERE course_id=? AND user_id='demo-student-1'", (past, deadline, other["id"]))
        # Unrelated expired identity is still purged normally.
        conn.execute("INSERT INTO users(id,name,email,role,is_demo,archived_at,purge_at) VALUES('expired-other','Synthetic','expired-other@example.invalid','student',1,?,?)", (past, deadline))
        conn.execute("INSERT INTO enrollments(course_id,user_id) VALUES(?,'expired-other')", (other["id"],))
        conn.execute("INSERT INTO workspaces(session_id,user_id) VALUES(?,'expired-other')", (sid,))
        kept_enrollment = tuple(conn.execute("SELECT * FROM enrollments WHERE course_id=? AND user_id='demo-student-1'", (CID,)).fetchone())
        kept_user = tuple(conn.execute("SELECT * FROM users WHERE id='demo-student-1'").fetchone())
        kept = {t: [tuple(r) for r in conn.execute(f"SELECT * FROM {t} WHERE session_id='s4' AND user_id='demo-student-1' ORDER BY rowid")]
                for t in ("workspaces", "messages", "revisions", "attempts", "chat_requests", "tutor_runs", "tutor_requests")}
        dry = maintenance(conn, dry_run=True)
        assert dry["accounts"] == ["expired-other"]
        assert dry["enrollments"] == [{"course_id": other["id"], "user_id": "demo-student-1"}]
        maintenance(conn)
        assert not conn.execute("SELECT 1 FROM users WHERE id='expired-other'").fetchone()
        assert not conn.execute("SELECT 1 FROM workspaces WHERE session_id=?", (sid,)).fetchone()
        assert tuple(conn.execute("SELECT * FROM enrollments WHERE course_id=? AND user_id='demo-student-1'", (CID,)).fetchone()) == kept_enrollment
        assert tuple(conn.execute("SELECT * FROM users WHERE id='demo-student-1'").fetchone()) == kept_user
        for t, rows in kept.items():
            assert [tuple(r) for r in conn.execute(f"SELECT * FROM {t} WHERE session_id='s4' AND user_id='demo-student-1' ORDER BY rowid")] == rows
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
    restore(teacher)
    with app.state.database.connect() as conn:
        # Course restore removes exactly one marker, not independent archive state/deadlines.
        assert tuple(conn.execute("SELECT * FROM enrollments WHERE course_id=? AND user_id='demo-student-1'", (CID,)).fetchone()) == kept_enrollment
        assert tuple(conn.execute("SELECT * FROM users WHERE id='demo-student-1'").fetchone()) == kept_user
        resumed = maintenance(conn)
        assert resumed["accounts"] == (["demo-student-1"] if global_archived else [])
        assert resumed["enrollments"] == ([{"course_id": CID, "user_id": "demo-student-1"}] if enrollment_archived else [])
        assert bool(conn.execute("SELECT 1 FROM workspaces WHERE session_id='s4' AND user_id='demo-student-1'").fetchone()) == (not global_archived and not enrollment_archived)
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()


def test_startup_maintenance_keeps_expired_trash_identity_and_restarts_same_marker(app, teacher, student, catalog, tmp_path):
    expect(student.post("/api/sessions/s4/answers/q1", json={"answer": "Retained across restart"}))
    state = trash(teacher)
    past, deadline = "2026-01-01T00:00:00+00:00", "2026-01-31T00:00:00+00:00"
    with app.state.database.connect() as conn:
        conn.execute("UPDATE users SET archived_at=?,purge_at=? WHERE id='demo-student-1'", (past, deadline))
        conn.execute("UPDATE enrollments SET archived_at=?,purge_at=? WHERE course_id=? AND user_id='demo-student-1'", (past, deadline, CID))
        before = records(conn)
    restarted = create_app(data_dir=app.state.database.path.parent, catalog_path=catalog, demo_enabled=False, frontend_dir=tmp_path/"none")
    with TestClient(restarted):
        with restarted.state.database.connect() as conn:
            assert records(conn) == before
            assert conn.execute("SELECT trashed_at FROM course_trash WHERE course_id=?", (CID,)).fetchone()[0] == state["trashed_at"]
    # Independently archived identity does not regain authentication merely by course restore.
    restore(teacher)
    expect(student.get("/api/auth/me"), 401)


def test_lifecycle_migration_savepoint_failure_keeps_original_schema_and_version(app, teacher):
    with app.state.database.connect() as conn:
        conn.execute("DROP TABLE course_trash")
        conn.execute("PRAGMA user_version=5")
        before, original_schema = records(conn), schema(conn)
        # Fail precisely after CREATE TABLE, proving transactional rollback.
        conn.set_authorizer(lambda action, arg1, arg2, *args: sqlite3.SQLITE_DENY
                            if action == sqlite3.SQLITE_PRAGMA and arg1 == "user_version" and arg2 is not None
                            else sqlite3.SQLITE_OK)
        try:
            with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
                migrate_course_lifecycle(conn)
        finally:
            conn.set_authorizer(None)
        assert records(conn) == before and schema(conn) == original_schema
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 5
        migrate_course_lifecycle(conn)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 6
        assert records(conn)["course_trash"]["rows"] == []
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO course_trash VALUES('missing','2026-01-01','demo-teacher')")


def test_removed_session_shared_historical_material_and_preview_identity_retained(app, teacher, student):
    baseline = expect(teacher.get(BASE))["published_version_id"]
    later = expect(teacher.post(BASE+"/sessions", json={"title": "Synthetic later session"}))["id"]
    preview = expect(teacher.post(f"/api/sessions/{later}/worksheet-import/preview", files={"file": ("synthetic.docx", worksheet_docx())}))
    expect(teacher.post(f"/api/sessions/{later}/worksheet-import/{preview['import_id']}/commit", json=commit_payload(preview)))
    mid = preview["material"]["id"]
    expect(teacher.patch(f"/api/sessions/{later}/materials/{mid}", json={"visibility": "student"}))
    expect(teacher.post("/api/sessions/s4/materials/attach", json={"material_id": mid}))
    expect(teacher.patch(f"/api/sessions/{later}", json={"status": "published"}))
    later_vid = publish(teacher)["id"]
    work = expect(student.get(f"/api/sessions/{later}/workspace?version_id={later_vid}"))
    qid = work["session"]["questions"][0]["id"]
    expect(student.post(f"/api/sessions/{later}/answers/{qid}?version_id={later_vid}", json={"answer": "Keep removed session history"}))
    image = work["session"]["questions"][0]["images"][0]["url"]
    asset_bytes = student.get(image).content
    original_bytes = student.get(f"/api/materials/{mid}/download?version_id={later_vid}").content
    expect(teacher.post(VER+"/"+baseline+"/restore", json={}))
    info = expect(teacher.get("/api/teacher/sessions/s4/preview"))
    bound = expect(teacher.post("/api/teacher/sessions/s4/preview/reset", json={"expected_revision": info["current_revision"]}))["preview"]
    with app.state.database.connect() as conn:
        assert conn.execute("SELECT in_draft FROM sessions WHERE id=?", (later,)).fetchone()[0] == 0
    state = trash(teacher)
    assert state["session_count"] == 2 and state["material_count"] == 5
    with app.state.database.connect() as conn:
        assert conn.execute('SELECT count(*) FROM sessions WHERE course_id=?', (CID,)).fetchone()[0] == 3
    for client in (teacher, student):
        expect(client.get(f"/api/sessions/{later}/workspace?version_id={later_vid}"), 410)
        expect(client.get(f"/api/materials/{mid}/download?version_id={later_vid}"), 410)
        expect(client.get(image), 410)
    restore(teacher)
    assert expect(teacher.get("/api/teacher/sessions/s4/preview")) == bound
    historical = expect(student.get(f"/api/sessions/{later}/workspace?version_id={later_vid}"))
    assert historical["attempts"][qid]["answer"] == "Keep removed session history"
    assert historical["read_only_reason"] == "historical_version"
    assert student.get(image).content == asset_bytes
    assert student.get(f"/api/materials/{mid}/download?version_id={later_vid}").content == original_bytes
    expect(student.get(f"/api/sessions/{later}/workspace"), 404)
    expect(teacher.get(f"/api/sessions/{later}"), 404)


def test_retained_import_commits_refuse_trash_and_resume_unchanged_after_restore(app, teacher):
    staged = expect(teacher.post("/api/sessions/s4/worksheet-import/preview", files={"file": ("synthetic.docx", worksheet_docx())}))
    roster = expect(teacher.post(f"/api/teacher/courses/{CID}/students/import/preview",
                                files={"file": ("synthetic.csv", b"name,email,temporary_password\nSynthetic,retained-new@example.invalid,synthetic-test1\n")}))
    with app.state.database.connect() as conn:
        rows = [tuple(r) for r in conn.execute("SELECT * FROM import_staging ORDER BY rowid")]
    trash(teacher)
    worksheet_url = f"/api/sessions/s4/worksheet-import/{staged['import_id']}/commit"
    roster_url = f"/api/teacher/courses/{CID}/students/import/{roster['import_id']}/commit"
    expect(teacher.post(worksheet_url, json=commit_payload(staged)), 410)
    expect(teacher.post(roster_url, json={}), 410)
    with app.state.database.connect() as conn:
        assert [tuple(r) for r in conn.execute("SELECT * FROM import_staging ORDER BY rowid")] == rows
        assert not conn.execute("SELECT 1 FROM users WHERE email='retained-new@example.invalid'").fetchone()
    restore(teacher)
    expect(teacher.post(worksheet_url, json=commit_payload(staged)))
    assert expect(teacher.post(roster_url, json={})) == {"created": 1, "enrolled": 0, "restored": 0, "skipped": 0}
