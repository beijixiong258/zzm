"""SiliconFlow HTTP contract with synthetic responses; no external model calls."""
from copy import deepcopy
import json

import httpx
import pytest

from backend.aicademiya.ai import ModelFailure
from backend.aicademiya.deployment_config import DEFAULTS, config_environment
from .conftest import expect


KEY = "SYNTHETIC_SILICONFLOW_KEY"
MODEL = "Qwen/Qwen3.8-27B"


@pytest.fixture
def siliconflow(app, admin, monkeypatch):
    config = deepcopy(DEFAULTS)
    config["ai"]["api_key"] = KEY
    for name, value in config_environment(config, {}).items():
        monkeypatch.setenv(name, value)

    def unexpected(request):
        raise AssertionError("This test must not send a model request")

    app.state.tutor.transport = httpx.MockTransport(unexpected)
    return app.state.tutor


def settings(tutor):
    with tutor.db.connect() as conn:
        return tutor.settings(conn)


def response(content="Synthetic final answer", **message):
    return httpx.Response(200, json={"choices": [{
        "finish_reason": "stop", "message": {"role": "assistant", "content": content, **message},
    }]})


def test_text_request_uses_official_endpoint_bearer_and_file_options(siliconflow):
    calls = []

    def handle(request):
        calls.append(request)
        assert str(request.url) == "https://api.siliconflow.cn/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer " + KEY
        assert request.extensions["timeout"] == {"connect": 10, "read": 120, "write": 120, "pool": 120}
        assert json.loads(request.content) == {
            "model": MODEL, "messages": [{"role": "user", "content": "Synthetic question"}],
            "temperature": 0.3, "max_tokens": 900, "stream": False, "enable_thinking": False,
        }
        return response()

    siliconflow.transport = httpx.MockTransport(handle)
    assert siliconflow.complete(settings(siliconflow), [{"role": "user", "content": "Synthetic question"}]) == "Synthetic final answer"
    assert len(calls) == 1


def test_vision_and_structured_output_omit_local_inference_parameters(siliconflow):
    image = {"type": "image_url", "image_url": {"url": "data:image/png;base64,c3ludGhldGlj"}}
    messages = [{"role": "user", "content": [{"type": "text", "text": "Synthetic diagram"}, image]}]
    schema = {"type": "json_schema", "json_schema": {"name": "fixture", "strict": True,
              "schema": {"type": "object", "properties": {"text": {"type": "string"}},
                         "required": ["text"], "additionalProperties": False}}}

    def handle(request):
        payload = json.loads(request.content)
        assert payload["messages"] == messages
        assert payload["response_format"] == schema
        assert payload["max_tokens"] == 2048
        assert not {"cache_prompt", "chat_template_kwargs", "user"} & payload.keys()
        return response('{"text":"Synthetic diagram answer"}')

    siliconflow.transport = httpx.MockTransport(handle)
    result = siliconflow.complete(settings(siliconflow), messages, response_format=schema, max_tokens=2048)
    assert json.loads(result)["text"] == "Synthetic diagram answer"


def test_tool_calls_pass_through_without_becoming_a_final_answer(siliconflow):
    tool = {"type": "function", "function": {"name": "web_search", "parameters": {
        "type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}}
    choice = {"type": "function", "function": {"name": "web_search"}}
    call = {"id": "synthetic-call", "type": "function", "function": {"name": "web_search", "arguments": '{"query":"learning"}'}}

    def handle(request):
        payload = json.loads(request.content)
        assert payload["tools"] == [tool] and payload["tool_choice"] == choice
        assert payload["enable_thinking"] is False
        return response(None, tool_calls=[call])

    siliconflow.transport = httpx.MockTransport(handle)
    message = siliconflow.completion_message(settings(siliconflow), [{"role": "user", "content": "Synthetic search"}], tools=[tool], tool_choice=choice)
    assert message["tool_calls"] == [call]
    with pytest.raises(ModelFailure, match="unfinished"):
        siliconflow.message_text(message)


def test_thinking_budget_is_configurable_and_reasoning_is_not_the_answer(siliconflow, monkeypatch):
    monkeypatch.setenv("AICADEMIYA_AI_ENABLE_THINKING", "true")
    monkeypatch.setenv("AICADEMIYA_AI_THINKING_BUDGET", "2048")
    monkeypatch.setenv("AICADEMIYA_AI_TEMPERATURE", "0")
    monkeypatch.setenv("AICADEMIYA_AI_TIMEOUT_SECONDS", "150")

    def handle(request):
        payload = json.loads(request.content)
        assert payload["enable_thinking"] is True and payload["thinking_budget"] == 2048
        assert payload["temperature"] == 0 and request.extensions["timeout"]["read"] == 150
        return response(reasoning_content="Synthetic internal reasoning")

    siliconflow.transport = httpx.MockTransport(handle)
    assert siliconflow.complete(settings(siliconflow), []) == "Synthetic final answer"


def test_missing_key_is_unconfigured_and_never_sends_requests(siliconflow, admin, student, monkeypatch):
    monkeypatch.setenv("AICADEMIYA_AI_API_KEY", " ")
    model = expect(admin.get("/api/teacher/settings"))
    assert not model["ai"]["configured"] and not model["api_key_set"]
    assert model["ai"]["connection"]["status"] == "not_configured"
    assert expect(student.get("/api/ai/connection"))["status"] == "not_configured"
    assert not expect(admin.post("/api/teacher/settings/test"))["ok"]
    with pytest.raises(ModelFailure, match="ai.api_key"):
        siliconflow.complete(settings(siliconflow), [])


def test_lightweight_check_uses_model_list_and_invalidates_changed_options(siliconflow, admin, student, monkeypatch):
    calls = []

    def handle(request):
        calls.append(request)
        assert request.method == "GET" and str(request.url) == "https://api.siliconflow.cn/v1/models"
        assert request.headers["Authorization"] == "Bearer " + KEY
        return httpx.Response(200, json={"data": [{"id": MODEL}]})

    siliconflow.transport = httpx.MockTransport(handle)
    assert expect(admin.get("/api/ai/connection"))["status"] == "connected"
    assert expect(student.get("/api/ai/connection"))["check_kind"] == "model_listing"
    assert len(calls) == 1
    monkeypatch.setenv("AICADEMIYA_AI_ENABLE_THINKING", "true")
    expect(admin.get("/api/ai/connection"))
    assert len(calls) == 2
    for path in ("/api/bootstrap", "/api/teacher/settings", "/api/ai/connection"):
        result = admin.get(path)
        expect(result)
        assert KEY not in result.text


@pytest.mark.parametrize("status, explanation", [(401, "authentication"), (403, "denied"),
    (404, "not found"), (429, "rate limit"), (503, "overloaded"), (504, "timed out")])
def test_http_errors_are_actionable_without_echoing_secrets(siliconflow, status, explanation):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(status, json={"message": "Sensitive provider body: " + KEY})

    siliconflow.transport = httpx.MockTransport(handle)
    with pytest.raises(ModelFailure) as error:
        siliconflow.complete(settings(siliconflow), [])
    assert f"HTTP {status}" in str(error.value) and explanation in str(error.value)
    assert KEY not in str(error.value) and "Sensitive provider body" not in str(error.value)
    assert len(calls) == 1  # No implicit retries or duplicate billable requests.


@pytest.mark.parametrize("choice", [None,
    {"finish_reason": "length", "message": {"content": "Truncated answer"}},
    {"finish_reason": "stop", "message": {"content": None, "reasoning_content": "Only reasoning"}},
])
def test_incomplete_responses_are_not_accepted_as_answers(siliconflow, choice):
    siliconflow.transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"choices": [choice]}))
    with pytest.raises(ModelFailure):
        siliconflow.complete(settings(siliconflow), [])


def test_student_answer_survives_rate_limit_and_explicit_retry_is_idempotent(siliconflow, student):
    calls = []

    def handle(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, json={"message": "Synthetic rate limit " + KEY})
        return response()

    siliconflow.transport = httpx.MockTransport(handle)
    chat = {"message": "Synthetic saved answer", "question_id": "q1", "intent": "answer", "request_id": "siliconflow-retry"}
    failure = expect(student.post("/api/sessions/s4/chat", json=chat), 502)
    assert "HTTP 429" in failure["detail"] and KEY not in failure["detail"]
    work = expect(student.get("/api/sessions/s4/workspace"))
    assert work["attempts"]["q1"]["answer"] == chat["message"]
    assert len(work["messages"]) == 1 and work["messages"][0]["role"] == "user"
    recovered = expect(student.post("/api/sessions/s4/chat", json=chat))
    assert recovered["messages"][-1]["content"] == "Synthetic final answer"
    assert recovered["messages"][-1]["mode"] == "openai"
    expect(student.post("/api/sessions/s4/chat", json=chat))
    assert len(calls) == 2


def test_uploaded_worksheet_uses_structured_output_and_full_document_budget(siliconflow, teacher):
    draft = {"title": "Synthetic worksheet", "groups": [{"id": "core", "title": "Core", "kind": "core"}],
             "questions": [{"id": "q1", "group_id": "core", "type": "open_response", "prompt": "Explain assessment.",
                            "options": [], "answer_slots": 1, "images": [], "source_label": "Synthetic worksheet", "hint": None}],
             "reference_answers": {"q1": "Synthetic reference."}}

    def handle(request):
        payload = json.loads(request.content)
        assert payload["max_tokens"] == 8192
        assert payload["response_format"] == {"type": "json_object"}
        assert payload["enable_thinking"] is False
        return response(json.dumps(draft))

    siliconflow.transport = httpx.MockTransport(handle)
    result = expect(teacher.post('/api/sessions/s4/worksheet-import/preview',
        files={"file": ("worksheet.txt", b"1. Explain assessment.\nAnswer: Synthetic reference.", "text/plain")},
        data={"use_ai": "true"}))
    assert result["method"] == "llm" and len(result["draft"]["questions"]) == 1
    assert result["material"]["visibility"] == "teacher"
