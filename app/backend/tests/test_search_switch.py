"""Per-message switch semantics for students/teachers and mandatory source links."""
import pytest
from .conftest import expect, publish
from .test_web_search import configure, ROW


@pytest.mark.parametrize("actor", ["student", "teacher"])
def test_user_switch_requires_search_and_links_even_when_model_omits_citations(app, teacher, student, monkeypatch, actor):
    state = configure(app, teacher, monkeypatch)
    state["final_text"] = "Synthetic fixture deliberately omits all citation markers and links."
    state["rows"] = [ROW, {**ROW, "url": "https://example.org/second", "title": "Second public source"}]
    client = teacher if actor == "teacher" else student
    work = expect(client.post("/api/sessions/s4/chat", json={"message": "Look up supporting evidence", "question_id": "q1", "intent": "ask", "web_search": True}))
    assert len(state["model"]) == 2 and len(state["search"]) == 1
    assert "TEACHER_REFERENCE_ONLY" not in str(state["model"][0])
    assert work["messages"][-1]["content"] == state["final_text"]
    urls = [c["url"] for c in work["messages"][-1]["citations"]]
    assert urls == [r["url"] for r in state["rows"]]
    assert expect(client.get("/api/sessions/s4/export"))["messages"][-1]["citations"] == work["messages"][-1]["citations"]
    off = expect(client.post("/api/sessions/s4/chat", json={"message": "Now continue offline", "question_id": "q1", "intent": "ask", "web_search": False}))
    assert len(state["model"]) == 3 and len(state["search"]) == 1
    assert "tools" not in state["model"][-1]
    assert not off["messages"][-1]["citations"]


@pytest.mark.parametrize("server_enabled", [False, True])
def test_omitted_switch_defaults_off_and_skips_search_even_without_key(app, teacher, student, monkeypatch, server_enabled):
    state = configure(app, teacher, monkeypatch)
    monkeypatch.setenv("AICADEMIYA_WEB_SEARCH_ENABLED", str(server_enabled).lower())
    monkeypatch.delenv("TAVILY_API_KEY")
    expect(student.post("/api/sessions/s4/chat", json={"message": "Explain the topic", "question_id": "q1", "intent": "ask"}))
    assert len(state["model"]) == 1 and not state["search"]
    assert "tools" not in state["model"][0]


def test_disabled_server_does_not_silently_ignore_requested_search(app, teacher, student, monkeypatch):
    state = configure(app, teacher, monkeypatch)
    monkeypatch.setenv("AICADEMIYA_WEB_SEARCH_ENABLED", "false")
    error = expect(student.post("/api/sessions/s4/chat", json={"message": "Search this", "question_id": "q1", "intent": "ask", "web_search": True}), 502)
    assert "disabled in server configuration" in error["detail"]
    assert not state["model"] and not state["search"]


def test_legacy_and_explicit_off_retries_match_but_changing_switch_requires_new_id(app, teacher, student, monkeypatch):
    state = configure(app, teacher, monkeypatch)
    body = {"message": "An offline question", "question_id": "q1", "intent": "ask", "request_id": "legacy-off-id"}
    expect(student.post("/api/sessions/s4/chat", json=body))
    expect(student.post("/api/sessions/s4/chat", json={**body, "web_search": False}))
    expect(student.post("/api/sessions/s4/chat", json={**body, "web_search": True}), 409)
    assert len(state["model"]) == 1 and not state["search"]


@pytest.mark.parametrize("language,notice", [("en", "Web search returned no usable sources."), ("zh", "本次联网搜索未找到可用来源。")])
def test_empty_search_is_explicit_and_does_not_invent_urls(app, teacher, student, monkeypatch, language, notice):
    state = configure(app, teacher, monkeypatch)
    state["rows"] = []
    state["final_text"] = "Synthetic fixture with no source statements."
    expect(teacher.patch("/api/sessions/s4", json={"teaching_language": language}))
    publish(teacher)
    work = expect(student.post("/api/sessions/s4/chat", json={"message": "Search this topic", "question_id": "q1", "intent": "ask", "web_search": True}))
    assert work["messages"][-1]["content"].endswith(notice)
    assert not work["messages"][-1]["citations"]
