"""Immutable editions, historical runs, availability and selected context fixtures."""
import io
import json
import sqlite3
from datetime import datetime, timedelta, timezone
import httpx
import pytest
from backend.aicademiya.ai import published_prefix, bounded_evidence
from backend.aicademiya.version_context import availability
from .conftest import expect, publish, question, demo_client

CID = "synthetic-course"
VERSIONS = f"/api/teacher/courses/{CID}/versions"


def pinned(student):
    return expect(student.get("/api/sessions/s4/workspace"))["version"]["id"]


def q1_only(teacher):
    q = question("q1"); q.pop("teacher_internal")
    expect(teacher.patch("/api/sessions/s4", json={"questions": [q], "reference_answers": {"q1": "Edition two private reference"}}))
    return publish(teacher)["id"]


def test_drafts_publication_immutable_history_stale_write_and_original_reference(app, teacher, student):
    first = pinned(student)
    expect(student.post("/api/sessions/s4/answers/q1?version_id="+first, json={"answer": "Original student reasoning"}))
    expect(student.post("/api/sessions/s4/references/q1?version_id="+first))
    initial = expect(teacher.get(VERSIONS+"/"+first))
    expect(teacher.patch("/api/sessions/s4", json={"title": "Second edition draft", "instructions": "NEW_PRIVATE_INSTRUCTIONS", "reference_answers": {"q1": "New private reference"}}))
    assert expect(student.get("/api/sessions/s4/workspace"))["session"]["title"] != "Second edition draft"
    listing = expect(teacher.get(VERSIONS))
    assert listing["has_unpublished_changes"] and listing["current_version_id"] == first
    diffs = expect(teacher.get(VERSIONS+"/"+first+"/diff"))["changes"]
    assert any(x["path"].endswith(".title") and x["after"] == "Second edition draft" for x in diffs)
    second = publish(teacher)["id"]
    latest = expect(student.get("/api/sessions/s4/workspace"))
    assert latest["version"]["id"] == second and not latest["attempts"] and not latest["read_only"]
    expect(student.post("/api/sessions/s4/answers/q1", json={"answer": "Old open page"}), 409)
    expect(student.post("/api/sessions/s4/answers/q1?version_id=", json={"answer": "Blank version exploit"}), 422)
    new = expect(student.post("/api/sessions/s4/answers/q1?version_id="+second, json={"answer": "New edition reasoning"}))
    assert new["attempts"]["q1"]["revision_count"] == 0
    old = expect(student.get("/api/sessions/s4/workspace?version_id="+first))
    assert old["read_only"] and old["read_only_reason"] == "historical_version"
    assert old["attempts"]["q1"]["answer"] == "Original student reasoning"
    assert {v["id"] for v in old["available_versions"]} == {first, second}
    assert expect(student.get("/api/sessions/s4/references/q1?version_id="+first))["reference"] == "TEACHER_REFERENCE_ONLY_q1"
    expect(student.post("/api/sessions/s4/answers/q1?version_id="+first, json={"answer": "Rewrite history"}), 409)
    expect(student.get("/api/sessions/s4/references/q1?version_id="+second), 403)
    assert expect(teacher.get(VERSIONS+"/"+first)) == initial
    assert not expect(teacher.get(VERSIONS))["has_unpublished_changes"]
    with demo_client(app, index=2) as other:
        expect(other.get("/api/sessions/s4/workspace?version_id="+first), 403)
        assert [v["id"] for v in expect(other.get("/api/sessions/s4/workspace"))["available_versions"]] == [second]
    with app.state.database.connect() as conn:
        for table in ("workspaces", "attempts", "revisions"):
            assert {r[0] for r in conn.execute(f"SELECT version_id FROM {table} WHERE user_id='demo-student-1'")} == {first, second}
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE course_versions SET label='Overwrite' WHERE id=?", (first,))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM course_versions WHERE id=?", (first,))
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()


def test_request_ids_messages_revisions_and_preview_are_version_bound(teacher, student):
    first = pinned(student)
    body = {"message": "Original answer", "question_id": "q1", "intent": "answer", "request_id": "reusable-per-edition"}
    expect(student.post("/api/sessions/s4/chat?version_id="+first, json=body))
    second = q1_only(teacher)
    latest = expect(student.post("/api/sessions/s4/chat?version_id="+second, json={**body, "message": "New edition answer"}))
    assert len(latest["messages"]) == 2 and latest["attempts"]["q1"]["revision_count"] == 0
    again = expect(student.post("/api/sessions/s4/chat?version_id="+second, json={**body, "message": "New edition answer"}))
    assert again["messages"] == latest["messages"]
    old = expect(student.get("/api/sessions/s4/export?version_id="+first))
    assert old["attempts"]["q1"]["answer"] == "Original answer" and len(old["messages"]) == 2
    preview = expect(teacher.post("/api/sessions/s4/answers/q1", json={"answer": "Staff draft preview"}))
    assert preview["version"]["is_draft"] and preview["version"]["id"] is None
    assert "Staff draft preview" not in student.get("/api/sessions/s4/workspace").text
    assert all(h["version"]["id"] is None for h in expect(teacher.get("/api/history")))
    history = expect(student.get("/api/history"))
    assert {h["version"]["id"] for h in history} == {first, second}
    assert all(h["answered"] == 1 for h in history)


def test_old_submissions_review_restore_removed_sessions_and_history(teacher, student):
    baseline = pinned(student)
    version = q1_only(teacher)
    expect(student.post("/api/sessions/s4/answers/q1?version_id="+version, json={"answer": "Submitted old edition"}))
    expect(student.post("/api/sessions/s4/submit?version_id="+version, json={}))
    expect(teacher.patch("/api/sessions/s4", json={"title": "A new draft after submission"}))
    publish(teacher)
    observed = expect(teacher.get("/api/teacher/sessions/s4/students/demo-student-1/workspace"))
    assert observed["version"]["id"] == version and observed["submission"]["status"] == "submitted"
    reviewed = expect(teacher.post("/api/teacher/sessions/s4/students/demo-student-1/review?version_id="+version, json={"status": "confirmed", "note": "Version-specific completion"}))
    assert reviewed["submission"]["status"] == "confirmed"
    # Add a new session with work, then restore a version that did not contain it.
    sid = expect(teacher.post(f"/api/courses/{CID}/sessions", json={"title": "Later session"}))["id"]
    q = question("later-q"); q.pop("teacher_internal")
    expect(teacher.patch(f"/api/sessions/{sid}", json={"questions": [q], "status": "published"}))
    later = publish(teacher)["id"]
    expect(student.post(f"/api/sessions/{sid}/answers/later-q?version_id="+later, json={"answer": "Keep this removed session's history"}))
    start = (datetime.now(timezone.utc)-timedelta(days=1)).isoformat()
    end = (datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
    expect(teacher.patch("/api/sessions/s4", json={"active": False, "starts_at": start, "ends_at": end}))
    restored = expect(teacher.post(VERSIONS+"/"+baseline+"/restore", json={"label": "Restore without erasing history"}))
    assert restored["number"] > 4 and restored["id"] != baseline
    state = expect(teacher.get("/api/sessions/s4"))
    assert state["starts_at"] == start and state["ends_at"] == end and not state["active"] and state["effective_active"]
    assert state["question_count"] == 22
    assert not expect(teacher.get(VERSIONS))["has_unpublished_changes"]
    expect(student.get(f"/api/sessions/{sid}/workspace"), 404)
    historical = expect(student.get(f"/api/sessions/{sid}/workspace?version_id="+later))
    assert historical["attempts"]["later-q"]["answer"].startswith("Keep this")
    history = expect(student.get("/api/history"))
    assert any(h["session"]["id"] == sid and h["version"]["id"] == later and h["answered"] == 1 for h in history)
    assert expect(teacher.get(f"/api/teacher/sessions/{sid}/students/demo-student-1/workspace?version_id="+later))["version"]["id"] == later
    assert expect(student.get("/api/sessions/s4/workspace?version_id="+version))["submission"]["status"] == "confirmed"


@pytest.mark.parametrize("method,path,payload", [
    ("POST", "/answers/q1", {"answer": "Blocked answer"}),
    ("POST", "/chat", {"message": "Blocked question", "question_id": "q1", "intent": "ask"}),
    ("POST", "/chat", {"message": "Blocked answer", "question_id": "q1", "intent": "answer"}),
    ("POST", "/reading", {"group_id": "arbitrary-reading"}),
    ("POST", "/references/q1", None),
    ("POST", "/submit", {}),
])
def test_inactive_write_gates_keep_history_export_and_revealed_reference(teacher, student, method, path, payload):
    vid = pinned(student)
    suffix = "?version_id="+vid
    expect(student.post("/api/sessions/s4/answers/q1"+suffix, json={"answer": "Saved before closure"}))
    expect(student.post("/api/sessions/s4/references/q1"+suffix))
    expect(teacher.patch("/api/sessions/s4", json={"active": False}))
    expect(student.request(method, "/api/sessions/s4"+path+suffix, **({"json": payload} if payload is not None else {})), 409)
    assert expect(student.get("/api/sessions/s4/workspace"+suffix))["read_only_reason"] == "session_inactive"
    assert expect(student.get("/api/sessions/s4/export"+suffix))["attempts"]["q1"]["answer"] == "Saved before closure"
    assert expect(student.get("/api/sessions/s4/references/q1"+suffix))["reference"] == "TEACHER_REFERENCE_ONLY_q1"
    expect(student.get("/api/sessions/s4/references/q2"+suffix), 409)
    assert not expect(teacher.get(f"/api/teacher/courses/{CID}/students?archived=true"))
    expect(teacher.post("/api/sessions/s4/answers/q1", json={"answer": "Teacher preview remains editable"}))


def test_schedule_priority_boundary_validation_and_immediate_operation(teacher, student):
    current = datetime.now(timezone.utc)
    previous, later = (current-timedelta(hours=1)).isoformat(), (current+timedelta(hours=1)).isoformat()
    listing = expect(teacher.get(VERSIONS))
    expect(teacher.patch("/api/sessions/s4", json={"active": False, "starts_at": previous, "ends_at": later}))
    assert expect(student.get("/api/sessions/s4"))["availability_reason"] == "scheduled"
    expect(student.post("/api/sessions/s4/answers/q1", json={"answer": "Schedule overrides manual off"}))
    expect(teacher.patch("/api/sessions/s4", json={"active": True, "starts_at": later, "ends_at": None}))
    assert expect(student.get("/api/sessions/s4"))["availability_reason"] == "not_started"
    expect(student.post("/api/sessions/s4/answers/q1", json={"answer": "Too soon"}), 409)
    expect(teacher.patch("/api/sessions/s4", json={"starts_at": None, "ends_at": previous}))
    assert expect(student.get("/api/sessions/s4"))["availability_reason"] == "ended"
    expect(teacher.patch("/api/sessions/s4", json={"starts_at": later, "ends_at": previous}), 422)
    expect(teacher.patch("/api/sessions/s4", json={"starts_at": "2026-10-05T12:00:00"}), 422)
    assert expect(teacher.get(VERSIONS))["has_unpublished_changes"] == listing["has_unpublished_changes"]
    assert availability({"active": False, "starts_at": current.isoformat(), "ends_at": later}, current)["effective_active"]
    assert not availability({"active": True, "starts_at": previous, "ends_at": current.isoformat()}, current)["effective_active"]
    expect(teacher.patch("/api/sessions/s4", json={"starts_at": None, "ends_at": None, "active": True}))
    assert expect(student.get("/api/sessions/s4"))["availability_reason"] == "manual_active"


def test_inflight_chat_finishes_original_edition_after_closure_and_publish(app, teacher, student, admin):
    first = pinned(student)
    expect(admin.put("/api/teacher/settings", json={"mode": "openai", "base_url": "http://protocol.invalid/v1", "model": "labelled-protocol-fixture"}))
    captures = []
    def handler(request):
        captures.append(json.loads(request.content))
        expect(teacher.patch("/api/sessions/s4", json={"active": False, "title": "Changed while accepted request runs"}))
        publish(teacher)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Accepted fixture response finishes"}}]})
    app.state.tutor.transport = httpx.MockTransport(handler)
    work = expect(student.post("/api/sessions/s4/chat?version_id="+first, json={"message": "Accepted answer", "question_id": "q1", "intent": "answer", "request_id": "inflight"}))
    assert work["version"]["id"] == first and work["messages"][-1]["content"] == "Accepted fixture response finishes"
    assert work["session"]["title"] != "Changed while accepted request runs"
    assert len(captures) == 1
    assert expect(student.get("/api/sessions/s4/workspace?version_id="+first))["messages"] == work["messages"]


def test_selected_sources_snapshots_router_scope_and_student_free_prefix(app, teacher, student, admin, monkeypatch):
    monkeypatch.setenv("AICADEMIYA_AI_PROVIDER", "aicademiya-router")
    expect(admin.put("/api/teacher/settings", json={"mode": "openai", "base_url": "http://127.0.0.1:18280/v1", "model": "AIcademiya-64kx3-Qwen3.8-27B"}))
    item = expect(teacher.post("/api/sessions/s4/materials", files={"file": ("selected.txt", b"SELECTED_SOURCE_SENTINEL formative reliability evidence")}))
    q = question("q1"); q.pop("teacher_internal"); q["source_material_ids"] = [item["id"]]
    expect(teacher.patch("/api/sessions/s4", json={"questions": [q], "reference_answers": {"q1": "Selected edition key"}}))
    first = publish(teacher)["id"]
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Labelled static protocol response"}}]})
    app.state.tutor.transport = httpx.MockTransport(handler)
    expect(student.post("/api/sessions/s4/chat?version_id="+first, json={"message": "Private student answer one", "question_id": "q1", "intent": "answer"}))
    body = json.loads(calls[-1].content)
    system = body["messages"][0]
    assert "SELECTED_SOURCE_SENTINEL" in system["content"] and "Conceptual evidence available" not in system["content"]
    assert "TEACHER_MATERIAL_DO_NOT_LEAK" not in system["content"] and "Private student answer" not in system["content"]
    with app.state.database.connect() as conn:
        denied = {"users", "workspaces", "attempts", "messages", "revisions", "chat_requests", "enrollments", "auth_sessions", "settings", "meta"}
        conn.set_authorizer(lambda action, table, *args: sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_READ and table in denied else sqlite3.SQLITE_OK)
        assert published_prefix(conn, "s4", "q1") == system
    expect(teacher.patch("/api/sessions/s4/materials/"+item["id"], json={"title": "New material title"}))
    # An unpublished material edit changes neither snapshot nor shared prefix.
    expect(student.post("/api/sessions/s4/chat?version_id="+first, json={"message": "Different private answer", "question_id": "q1", "intent": "answer"}))
    assert json.loads(calls[-1].content)["messages"][0] == system
    expect(teacher.patch("/api/sessions/s4", json={"title": "Next edition"}))
    second = publish(teacher)["id"]
    expect(student.post("/api/sessions/s4/chat?version_id="+second, json={"message": "Third private answer", "question_id": "q1", "intent": "answer"}))
    assert json.loads(calls[-1].content)["user"] != body["user"]
    assert calls[-1].extensions["timeout"]["read"] == 600
    for url in ("/api/sessions/s4/workspace", "/api/sessions/s4/export"):
        assert "source_material_ids" not in student.get(url).text


def test_reference_read_after_switching_branch_and_historical_seed_diagrams(teacher, student):
    version = expect(student.get("/api/sessions/s2/workspace"))["version"]["id"]
    suffix = "?version_id="+version
    expect(student.post("/api/sessions/s2/reading"+suffix, json={"group_id": "II-Pong"}))
    expect(student.post("/api/sessions/s2/answers/pong1"+suffix, json={"answer": "Earlier branch response"}))
    reference = expect(student.post("/api/sessions/s2/references/pong1"+suffix))
    expect(student.post("/api/sessions/s2/reading"+suffix, json={"group_id": "II-Bray"}))
    assert expect(student.get("/api/sessions/s2/references/pong1"+suffix)) == reference
    expect(student.post("/api/sessions/s2/references/pong1"+suffix), 409)
    # Seed assets remain resolvable from saved versions even after draft removes all images.
    questions = expect(teacher.get("/api/sessions/s4"))["questions"]
    for q in questions:
        q["images"] = []
    expect(teacher.patch("/api/sessions/s4", json={"questions": questions}))
    assert student.get("/api/assets/plot.png").content.startswith(b"\x89PNG")


def test_all_eligible_sources_considered_beyond_eight_with_bounded_prompt():
    materials = [{"visibility": "student", "kind": "reading", "status": "ready", "source_label": f"Source {n}", "excerpt": "Generic unrelated material "*200} for n in range(20)]
    materials[-1]["excerpt"] = "reliability formative assessment validity "*300
    evidence = bounded_evidence(materials, {"prompt": "Explain reliability and validity in formative assessment"})
    assert evidence[0]["source_label"] == "Source 19"
    assert sum(len(m["excerpt"]) for m in evidence) <= 32000
