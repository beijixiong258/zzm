"""Bounded search/tool protocol and privacy checks. All network responses are fixtures."""
import json

import httpx
import pytest

from backend.aicademiya.web_search import TavilySearch, SearchFailure, web_citations
from .conftest import expect, admin_request, publish

KEY = "SYNTHETIC_TAVILY_TEST_KEY"
ROW = {"title": "Synthetic public source", "url": "https://example.org/assessment", "content": "Synthetic public evidence about assessment quality."}


def tool_call(query="language assessment reliability", call_id="search-1"):
    return {"id": call_id, "type": "function", "function": {"name": "web_search", "arguments": json.dumps({"query": query})}}


def configure(app, teacher, monkeypatch, *, calls=None, no_search=False, search_status=200):
    monkeypatch.setenv("AICADEMIYA_WEB_SEARCH_ENABLED", "true")
    monkeypatch.setenv("TAVILY_API_KEY", KEY)
    expect(admin_request(teacher, "PUT", "/api/teacher/settings", json={"mode": "openai", "base_url": "http://fixture.invalid/v1", "model": "protocol-fixture"}))
    expect(teacher.patch("/api/sessions/s4", json={"instructions": "PRIVATE_INSTRUCTION_SENTINEL"}))
    publish(teacher)
    state = {"model": [], "search": [], "search_status": search_status, "rows": [ROW],
             "final_text": "Synthetic protocol feedback supported by [W1], not unknown [W99]."}

    def model(request):
        body = json.loads(request.content)
        state["model"].append(body)
        if isinstance(body.get("tool_choice"), dict):
            message = {"content": "NO_SEARCH"} if no_search else {"content": None, "tool_calls": calls if calls is not None else [tool_call()]}
        else:
            message = {"content": state["final_text"]}
        return httpx.Response(200, json={"choices": [{"message": message}]})

    def search(request):
        state["search"].append(request)
        return httpx.Response(state["search_status"], json={"results": state["rows"], "usage": {"credits": 1}, "private_error": KEY})

    app.state.tutor.transport = httpx.MockTransport(model)
    app.state.tutor.search = TavilySearch(transport=httpx.MockTransport(search))
    return state


def test_real_app_tool_protocol_persists_source_and_keeps_planner_public(app, teacher, student, monkeypatch):
    state = configure(app, teacher, monkeypatch)
    body = {"message": "Find a public source about validity and reliability", "question_id": "q1", "intent": "ask", "web_search": True, "request_id": "search-request"}
    work = expect(student.post("/api/sessions/s4/chat", json=body))
    assert len(state["model"]) == 2 and len(state["search"]) == 1
    planner, final = state["model"]
    assert planner["tools"][0]["function"]["name"] == "web_search"
    assert planner["tool_choice"] == {"type": "function", "function": {"name": "web_search"}}
    assert "MUST call web_search" in planner["messages"][0]["content"]
    for private in ("TEACHER_REFERENCE_ONLY", "PRIVATE_INSTRUCTION_SENTINEL", "TEACHER_MATERIAL", KEY, "demo-student"):
        assert private not in json.dumps(planner)
    assert "TEACHER_REFERENCE_ONLY_q1" in json.dumps(final) and "PRIVATE_INSTRUCTION_SENTINEL" in json.dumps(final)
    assert "TEACHER_REFERENCE_ONLY_q2" not in json.dumps(final)
    assert final["tool_choice"] == "none"
    assert final["messages"][-2]["role"] == "assistant" and final["messages"][-1]["role"] == "tool"
    assert final["messages"][-1]["tool_call_id"] == "search-1"
    assert "untrusted" in final["messages"][0]["content"] and "Before reference_revealed is true" in final["messages"][0]["content"]
    request = state["search"][0]
    payload = json.loads(request.content)
    assert str(request.url) == "https://api.tavily.com/search" and request.headers["Authorization"] == "Bearer " + KEY
    assert payload["query"] == "language assessment reliability"
    assert payload["search_depth"] == "basic" and payload["max_results"] == 5
    assert payload["include_answer"] is False and payload["include_raw_content"] is False and payload["auto_parameters"] is False
    assert not work["attempts"]
    citation = work["messages"][-1]["citations"][0]
    assert len(work["messages"][-1]["citations"]) == 1
    assert citation == {"source_label": "[W1] Synthetic public source", "url": ROW["url"], "text": ROW["content"], "kind": "web"}
    for route in ("/api/sessions/s4/workspace", "/api/sessions/s4/export"):
        response = student.get(route)
        assert expect(response)["messages"][-1]["citations"] == [citation]
        assert KEY not in response.text and "PRIVATE_INSTRUCTION_SENTINEL" not in response.text
    expect(student.post("/api/sessions/s4/chat", json=body))
    assert len(state["model"]) == 2 and len(state["search"]) == 1  # idempotent completed request
    expect(student.post("/api/sessions/s4/references/q1"), 409)


def test_model_cannot_silently_decline_user_enabled_search(app, teacher, student, monkeypatch):
    state = configure(app, teacher, monkeypatch, no_search=True)
    error = expect(student.post("/api/sessions/s4/chat", json={"message": "Explain the course concept", "question_id": "q1", "intent": "ask", "web_search": True}), 502)
    assert "did not call web_search" in error["detail"]
    assert len(state["model"]) == 1 and not state["search"]


def test_demo_never_plans_or_searches_even_when_enabled(app, teacher, student, monkeypatch):
    state = configure(app, teacher, monkeypatch)
    expect(admin_request(teacher, "PUT", "/api/teacher/settings", json={"mode": "demo", "base_url": "", "model": ""}))
    work = expect(student.post("/api/sessions/s4/chat", json={"message": "Search online", "question_id": "q1", "intent": "ask", "web_search": True}))
    assert work["messages"][-1]["mode"] == "demo" and not state["model"] and not state["search"]
    assert work["ai"]["web_search"] == {"enabled": True, "configured": True, "provider": "tavily"}
    assert KEY not in student.get("/api/bootstrap").text and KEY not in admin_request(teacher, "GET", "/api/teacher/settings").text


def test_search_failure_retains_answer_and_retry_is_idempotent(app, teacher, student, monkeypatch):
    state = configure(app, teacher, monkeypatch, search_status=429)
    body = {"message": "My synthetic answer. Please check a source.", "question_id": "q1", "intent": "answer", "web_search": True, "request_id": "search-retry"}
    error = expect(student.post("/api/sessions/s4/chat", json=body), 502)
    assert "HTTP 429" in error["detail"] and KEY not in error["detail"]
    assert len(state["model"]) == 1  # no fabricated final answer
    work = expect(student.get("/api/sessions/s4/workspace"))
    assert len(work["messages"]) == 1 and work["attempts"]["q1"]["answer"] == body["message"]
    state["search_status"] = 200
    work = expect(student.post("/api/sessions/s4/chat", json=body))
    assert len(work["messages"]) == 2 and work["attempts"]["q1"]["revision_count"] == 0


@pytest.mark.parametrize("calls", [
    [tool_call(call_id=f"s{i}") for i in range(3)],
    [tool_call(), tool_call()],
    [{"id": "bad", "type": "function", "function": {"name": "exec", "arguments": "{}"}}],
    [{"id": "bad", "type": "function", "function": {"name": "web_search", "arguments": "not json"}}],
    [tool_call("x" * 401)],
    [tool_call(), tool_call("", "s2")],
])
def test_invalid_or_excess_tool_calls_are_rejected_before_search(app, teacher, student, monkeypatch, calls):
    state = configure(app, teacher, monkeypatch, calls=calls)
    expect(student.post("/api/sessions/s4/chat", json={"message": "Search a public topic", "question_id": "q1", "intent": "ask", "web_search": True}), 502)
    assert not state["search"]


def test_duplicate_queries_have_one_charge_and_two_valid_tool_responses(app, teacher, student, monkeypatch):
    state = configure(app, teacher, monkeypatch, calls=[tool_call(call_id="s1"), tool_call(call_id="s2")])
    expect(student.post("/api/sessions/s4/chat", json={"message": "Search a public topic", "question_id": "q1", "intent": "ask", "web_search": True}))
    assert len(state["search"]) == 1
    assert [m["tool_call_id"] for m in state["model"][-1]["messages"] if m["role"] == "tool"] == ["s1", "s2"]


def test_missing_key_fails_before_any_model_call(app, teacher, student, monkeypatch):
    state = configure(app, teacher, monkeypatch)
    monkeypatch.delenv("TAVILY_API_KEY")
    error = expect(student.post("/api/sessions/s4/chat", json={"message": "Search a public topic", "question_id": "q1", "intent": "ask", "web_search": True}), 502)
    assert "not configured" in error["detail"] and not state["model"] and not state["search"]


@pytest.mark.parametrize("kind", ["timeout", "connect", "bad_json", "invalid_shape", "http401"])
def test_tavily_failures_do_not_expose_provider_content(monkeypatch, kind):
    monkeypatch.setenv("TAVILY_API_KEY", KEY)
    def handle(request):
        if kind == "timeout": raise httpx.ReadTimeout(KEY, request=request)
        if kind == "connect": raise httpx.ConnectError(KEY, request=request)
        if kind == "bad_json": return httpx.Response(200, text=KEY)
        if kind == "invalid_shape": return httpx.Response(200, json={"results": KEY})
        return httpx.Response(401, json={"detail": KEY})
    with pytest.raises(SearchFailure) as raised:
        TavilySearch(httpx.MockTransport(handle)).search("public topic")
    assert KEY not in str(raised.value)


def test_bounded_results_safe_urls_and_explicit_source_ids(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", KEY)
    rows = [{**ROW, "url": "javascript:alert(1)"}, {**ROW, "url": "file:///etc/passwd"}, ROW, ROW,
            *[{**ROW, "url": f"https://example.org/{i}", "content": "a"*5000} for i in range(10)]]
    client = TavilySearch(httpx.MockTransport(lambda request: httpx.Response(200, json={"results": rows})))
    found = client.search("public topic")["results"]
    assert len(found) == 5 and len({x["url"] for x in found}) == 5
    assert all(len(x["content"]) <= 1800 for x in found)
    sources = [{"id": "W1", **ROW}]
    assert web_citations(sources)[0]["url"] == ROW["url"]
    assert not web_citations([])


def test_empty_tavily_results_are_valid_not_fabricated(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", KEY)
    client = TavilySearch(httpx.MockTransport(lambda request: httpx.Response(200, json={"results": []})))
    assert client.search("public topic")["results"] == []
