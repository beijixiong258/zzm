"""AIcademiya-router protocol fixtures only: no GPU, cloud or paid search calls."""
import json
import re

import httpx
import pytest

from backend.aicademiya.ai import ModelFailure, Tutor
from .conftest import demo_client, expect, admin_request, publish
from .test_web_search import configure as configure_search

ROUTER = {"mode": "openai", "base_url": "http://127.0.0.1:18280/v1", "model": "AIcademiya-64kx3-Qwen3.8-27B"}


def configure(app, teacher, monkeypatch):
    monkeypatch.setenv("AICADEMIYA_AI_PROVIDER", "aicademiya-router")
    expect(admin_request(teacher, "PUT", "/api/teacher/settings", json=ROUTER))
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Synthetic router feedback"}}]})
    app.state.tutor.transport = httpx.MockTransport(handle)
    return requests


def send(client, sid="s4", rid=None, version_id=None, **extra):
    suffix = "?version_id=" + version_id if version_id else ""
    return client.post(f"/api/sessions/{sid}/chat" + suffix, json={"message": "Explain the concept", "question_id": None,
                       "intent": "ask", **({"request_id": rid} if rid else {}), **extra})


def test_scope_is_stable_private_and_isolates_users_activities_teacher(app, teacher, student, monkeypatch):
    requests = configure(app, teacher, monkeypatch)
    expect(send(student))
    first = json.loads(requests[-1].content)["user"]
    expect(student.post("/api/auth/logout"))
    expect(student.post("/api/auth/demo", json={"role": "student", "student_index": 1}))
    expect(send(student))
    assert json.loads(requests[-1].content)["user"] == first
    expect(send(student, "s2"))
    other_activity = json.loads(requests[-1].content)["user"]
    with demo_client(app, index=2) as second:
        expect(send(second))
        other_student = json.loads(requests[-1].content)["user"]
    expect(send(teacher))
    preview = json.loads(requests[-1].content)["user"]
    assert len({first, other_activity, other_student, preview}) == 4
    assert re.fullmatch(r"aicv2-[0-9a-f]{64}", first)
    assert "demo-student" not in first and "@" not in first
    for request in requests:
        body = json.loads(request.content)
        assert str(request.url) == ROUTER["base_url"] + "/chat/completions"
        assert body["model"] == "AIcademiya-64kx3-Qwen3.8-27B" and body["stream"] is False
        assert request.extensions["timeout"] == {"connect": 10, "read": 600, "write": 600, "pool": 600}
    assert "aicv2-" not in student.get("/api/sessions/s4/workspace").text
    assert "kv_scope_secret" not in admin_request(teacher, "GET", "/api/teacher/settings").text
    # New Tutor / new server process still reads the same installation secret.
    restarted = Tutor(app.state.database)
    version = expect(student.get("/api/sessions/s4/workspace"))["version"]["id"]
    assert restarted.kv_scope({"id": "demo-student-1", "role": "student"}, "s4:version:" + version) == first


def test_untrusted_scope_and_user_cannot_authorize_or_select_snapshot(app, teacher, student, monkeypatch):
    requests = configure(app, teacher, monkeypatch)
    expect(send(student, user="attacker-scope"), 422)
    expect(send(student, kv_scope="attacker-scope"), 422)
    expect(student.post("/api/sessions/s4/chat", headers={"X-KV-Scope": "attacker-scope"},
                        json={"message": "Explain", "intent": "ask"}))
    assert json.loads(requests[-1].content)["user"] != "attacker-scope"
    with demo_client(app) as client:
        expect(client.post("/api/auth/logout"))
        expect(send(client), 401)
    assert len(requests) == 1


def test_router_probe_scope_is_distinct_and_completed_retry_does_not_call_provider(app, teacher, student, monkeypatch):
    requests = configure(app, teacher, monkeypatch)
    expect(send(student, rid="router-idempotent"))
    expect(send(student, rid="router-idempotent"))
    assert len(requests) == 1
    expect(send(teacher))
    preview_scope = json.loads(requests[-1].content)["user"]
    assert expect(admin_request(teacher, "POST", "/api/teacher/settings/test"))["ok"] is True
    assert json.loads(requests[-1].content)["user"] != preview_scope


def test_timeout_retains_answer_and_safe_retry(app, teacher, student, monkeypatch):
    requests = configure(app, teacher, monkeypatch)
    def timeout(request):
        assert request.extensions["timeout"]["read"] == 600
        raise httpx.ReadTimeout("SECRET_PROVIDER_DETAIL", request=request)
    app.state.tutor.transport = httpx.MockTransport(timeout)
    body = {"message": "Synthetic answer", "question_id": "q1", "intent": "answer", "request_id": "router-timeout"}
    error = expect(student.post("/api/sessions/s4/chat", json=body), 502)
    assert "timed out" in error["detail"] and "SECRET_PROVIDER_DETAIL" not in error["detail"]
    work = expect(student.get("/api/sessions/s4/workspace"))
    assert work["attempts"]["q1"]["answer"] == body["message"] and len(work["messages"]) == 1
    def recovered(request):
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Recovered fixture"}}]})
    app.state.tutor.transport = httpx.MockTransport(recovered)
    work = expect(student.post("/api/sessions/s4/chat", json=body))
    assert len(work["messages"]) == 2 and work["attempts"]["q1"]["revision_count"] == 0


@pytest.mark.parametrize("flag,base,model", [
    ("", ROUTER["base_url"], ROUTER["model"]),
    ("aicademiya-router", "https://api.openai.com/v1", ROUTER["model"]),
    ("aicademiya-router", ROUTER["base_url"], "cloud-model"),
])
def test_other_providers_keep_legacy_payload_and_timeout(app, teacher, student, monkeypatch, flag, base, model):
    requests = configure(app, teacher, monkeypatch)
    monkeypatch.setenv("AICADEMIYA_AI_PROVIDER", flag)
    expect(admin_request(teacher, "PUT", "/api/teacher/settings", json={"mode": "openai", "base_url": base, "model": model}))
    expect(send(student))
    assert "user" not in json.loads(requests[0].content)
    assert requests[0].extensions["timeout"]["read"] == 60


def test_demo_never_calls_router_or_creates_scope_secret(app, teacher, student, monkeypatch):
    requests = configure(app, teacher, monkeypatch)
    expect(admin_request(teacher, "PUT", "/api/teacher/settings", json={**ROUTER, "mode": "demo"}))
    expect(send(student))
    assert not requests
    with app.state.database.connect() as conn:
        assert conn.execute("SELECT 1 FROM meta WHERE key='kv_scope_secret'").fetchone() is None


def test_router_fails_closed_without_scope(app, teacher, monkeypatch):
    configure(app, teacher, monkeypatch)
    with pytest.raises(ModelFailure, match="server-derived"):
        app.state.tutor.complete({**ROUTER, "api_key": ""}, [{"role": "user", "content": "fixture"}])


def test_search_planner_scope_is_distinct_from_private_tutor_scope(app, teacher, student, monkeypatch):
    state = configure_search(app, teacher, monkeypatch)
    monkeypatch.setenv("AICADEMIYA_AI_PROVIDER", "aicademiya-router")
    expect(admin_request(teacher, "PUT", "/api/teacher/settings", json=ROUTER))
    expect(send(student, web_search=True))
    planner, final = state["model"]
    assert planner["user"] != final["user"]
    assert "TEACHER_REFERENCE_ONLY" not in json.dumps(planner)
    assert all(re.fullmatch(r"aicv2-[0-9a-f]{64}", body["user"]) for body in state["model"])
