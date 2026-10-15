"""Stage7 HTTP/SQLite acceptance; all model/search responses are synthetic fixtures."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import threading

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.aicademiya.ai import ModelFailure, Tutor
from backend.aicademiya.db import issue_session, now
from backend.aicademiya.main import create_app
from backend.aicademiya.service_settings import SEARCH_TEST_QUERY
from backend.aicademiya.web_search import TavilySearch
from .conftest import demo_client, expect, publish
from .test_stage3_guided import ProtocolFixture, configure as configure_lesson
from .test_web_search import ROW, tool_call

SEARCH = "/api/teacher/search-settings"
MODEL = "/api/teacher/settings"
ENV_KEY = "SYNTHETIC_STAGE7_ENVIRONMENT_KEY"
SAVED_KEY = "SYNTHETIC_STAGE7_SAVED_KEY"
MODEL_KEY = "SYNTHETIC_STAGE7_MODEL_KEY"
MODEL_BODY = {"mode": "openai", "base_url": "http://fixture.invalid/v1", "model": "stage7-protocol", "api_key": MODEL_KEY}


def search_fixture(app, *, status=200, rows=None):
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(status, json={"results": [ROW] if rows is None else rows, "error": SAVED_KEY})
    app.state.tutor.search = TavilySearch(httpx.MockTransport(handle))
    return calls


def model_fixture(app, *, status=200):
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(status, json={"choices": [{"message": {"content": "Synthetic model fixture response"}}], "private": MODEL_KEY})
    app.state.tutor.transport = httpx.MockTransport(handle)
    return calls


def assert_safe(response):
    for secret in (ENV_KEY, SAVED_KEY, MODEL_KEY, "fingerprint", "service_ai_revision", "service_search_revision"):
        assert secret not in response.text


def save_search(admin, **changes):
    return expect(admin.put(SEARCH, json={"enabled": True, "api_key": SAVED_KEY, **changes}))


def test_admin_only_routes_have_server_authorization(teacher, student, app):
    search_calls = search_fixture(app)
    model_calls = model_fixture(app)
    for client in (teacher, student):
        for method, path, kwargs in (("GET", SEARCH, {}), ("PUT", SEARCH, {"json": {"api_key": SAVED_KEY}}),
                                     ("POST", SEARCH + "/test", {}), ("GET", MODEL, {}),
                                     ("PUT", MODEL, {"json": MODEL_BODY}), ("POST", MODEL + "/test", {})):
            result = client.request(method, path, **kwargs)
            expect(result, 403)
            assert_safe(result)
    assert not search_calls and not model_calls


def test_search_environment_fallback_no_network_get_save_and_source(app, admin, monkeypatch):
    monkeypatch.setenv("AICADEMIYA_WEB_SEARCH_ENABLED", "true")
    monkeypatch.setenv("TAVILY_API_KEY", ENV_KEY)
    calls = search_fixture(app)
    status = expect(admin.get(SEARCH))
    assert set(status) == {"provider", "enabled", "configured", "api_key_set", "api_key_source", "connection"}
    assert status == {"provider": "tavily", "enabled": True, "configured": True, "api_key_set": True,
                      "api_key_source": "environment", "connection": {"status": "not_checked", "checked_at": None, "message": None}}
    assert expect(admin.put(SEARCH, json={"api_key": "   "})) == status
    assert expect(admin.put(SEARCH, json={})) == status
    assert expect(admin.get("/api/bootstrap"))["ai"]["web_search"] == {"enabled": True, "configured": True, "provider": "tavily"}
    assert not calls
    assert_safe(admin.get(SEARCH))
    with app.state.database.connect() as conn:
        assert not conn.execute("SELECT key FROM settings WHERE key LIKE 'web_search_%'").fetchall()


def test_search_save_keep_replace_clear_blocks_environment_and_restart(app, admin, monkeypatch, catalog, tmp_path):
    monkeypatch.setenv("AICADEMIYA_WEB_SEARCH_ENABLED", "true")
    monkeypatch.setenv("TAVILY_API_KEY", ENV_KEY)
    assert save_search(admin)["api_key_source"] == "saved"
    for body in ({}, {"api_key": ""}, {"api_key": "   "}, {"api_key": None}):
        assert expect(admin.put(SEARCH, json=body))["api_key_source"] == "saved"
        with app.state.database.connect() as conn:
            assert conn.execute("SELECT value FROM settings WHERE key='web_search_api_key'").fetchone()[0] == SAVED_KEY
    cleared = expect(admin.put(SEARCH, json={"clear_api_key": True}))
    assert not cleared["api_key_set"] and not cleared["configured"] and cleared["api_key_source"] == "none"
    assert cleared["connection"] == {"status": "not_configured", "checked_at": None, "message": None}
    expect(admin.post(SEARCH + "/test"), 409)
    restarted = create_app(data_dir=app.state.database.path.parent, catalog_path=catalog, demo_enabled=True, frontend_dir=tmp_path / "no-dist")
    with demo_client(restarted, "admin") as other:
        assert expect(other.get(SEARCH)) == cleared
        assert expect(other.get("/api/bootstrap"))["ai"]["web_search"] == {"enabled": True, "configured": False, "provider": "tavily"}
        assert save_search(other, api_key=ENV_KEY)["api_key_source"] == "saved"
    assert expect(admin.get(SEARCH))["api_key_source"] == "saved"


@pytest.mark.parametrize("body", [{"api_key": SAVED_KEY, "clear_api_key": True}, {"api_key": SAVED_KEY, "unsupported": "secret-field"}, {"api_key": [SAVED_KEY]}])
def test_search_validation_no_secret_echo_and_no_write(admin, app, body):
    with app.state.database.connect() as conn:
        before = list(conn.execute("SELECT * FROM settings ORDER BY key"))
    result = admin.put(SEARCH, json=body)
    expect(result, 422)
    assert_safe(result)
    with app.state.database.connect() as conn:
        assert [tuple(r) for r in before] == [tuple(r) for r in conn.execute("SELECT * FROM settings ORDER BY key")]


@pytest.mark.parametrize("enabled,key", [(False, ""), (False, SAVED_KEY), (True, "")])
def test_search_test_requires_enabled_key_without_network(app, admin, enabled, key):
    expect(admin.put(SEARCH, json={"enabled": enabled, "api_key": key}))
    settings = expect(admin.get(SEARCH))
    assert settings["connection"]["status"] == ("not_checked" if key else "not_configured")
    calls = search_fixture(app)
    expect(admin.post(SEARCH + "/test"), 409)
    assert not calls


@pytest.mark.parametrize("rows", [[ROW], []])
def test_explicit_search_check_is_bounded_fixed_public_persistent(app, admin, catalog, tmp_path, rows):
    save_search(admin)
    calls = search_fixture(app, rows=rows)
    checked = expect(admin.post(SEARCH + "/test"))
    assert checked["ok"] and checked["result_count"] == len(rows)
    connection = checked["connection"]
    assert connection["status"] == "connected" and datetime.fromisoformat(connection["checked_at"]).utcoffset() is not None
    assert len(calls) == 1
    body = json.loads(calls[0].content)
    assert body == {"query": SEARCH_TEST_QUERY, "topic": "general", "search_depth": "basic", "auto_parameters": False,
                    "max_results": 5, "include_answer": False, "include_raw_content": False, "include_images": False, "include_usage": True}
    assert calls[0].headers["Authorization"] == "Bearer " + SAVED_KEY
    assert "PRIVATE" not in body["query"] and "TEACHER_REFERENCE" not in body["query"]
    assert expect(admin.get(SEARCH))["connection"] == connection
    assert len(calls) == 1  # opening/readback is not another charge
    restarted = create_app(data_dir=app.state.database.path.parent, catalog_path=catalog, demo_enabled=True, frontend_dir=tmp_path / "none")
    with demo_client(restarted, "admin") as client:
        assert expect(client.get(SEARCH))["connection"] == connection
    assert_safe(admin.get(SEARCH))


@pytest.mark.parametrize("failure", ["http401", "http429", "timeout", "connect", "invalid"])
def test_search_provider_error_persisted_safe_not_fabricated(app, admin, failure):
    save_search(admin)
    def handle(request):
        if failure == "timeout":
            raise httpx.ReadTimeout(SAVED_KEY, request=request)
        if failure == "connect":
            raise httpx.ConnectError(SAVED_KEY, request=request)
        if failure == "invalid":
            return httpx.Response(200, json={"results": SAVED_KEY})
        return httpx.Response(401 if failure == "http401" else 429, json={"private_provider_error": SAVED_KEY})
    app.state.tutor.search = TavilySearch(httpx.MockTransport(handle))
    result = admin.post(SEARCH + "/test")
    expect(result, 502)
    assert_safe(result)
    assert "result_count" not in result.json()  # failure has no invented hits
    check = expect(admin.get(SEARCH))["connection"]
    assert check["status"] == "error" and check["checked_at"] and check["message"]
    assert_safe(admin.get(SEARCH))


@pytest.mark.parametrize("change", [{"enabled": False}, {"api_key": ENV_KEY}, {"clear_api_key": True}])
def test_search_effective_change_invalidates_check(app, admin, change):
    save_search(admin)
    search_fixture(app)
    checked = expect(admin.post(SEARCH + "/test"))["connection"]
    assert checked["status"] == "connected"
    # A true no-op does not forget the last check.
    assert expect(admin.put(SEARCH, json={"api_key": "  "}))["connection"] == checked
    changed = expect(admin.put(SEARCH, json=change))
    assert changed["connection"]["status"] != "connected" and changed["connection"]["checked_at"] is None


def test_search_environment_change_invalidates_without_mutating_environment(app, admin, monkeypatch):
    monkeypatch.setenv("AICADEMIYA_WEB_SEARCH_ENABLED", "true")
    monkeypatch.setenv("TAVILY_API_KEY", ENV_KEY)
    search_fixture(app)
    assert expect(admin.post(SEARCH + "/test"))["connection"]["status"] == "connected"
    monkeypatch.setenv("TAVILY_API_KEY", SAVED_KEY)
    assert expect(admin.get(SEARCH))["connection"]["status"] == "not_checked"
    save_search(admin, enabled=False)
    import os
    assert os.getenv("TAVILY_API_KEY") == SAVED_KEY and os.getenv("AICADEMIYA_WEB_SEARCH_ENABLED") == "true"


def test_two_app_instances_have_independent_effective_overrides(admin, app, tmp_path, catalog, monkeypatch):
    monkeypatch.setenv("AICADEMIYA_WEB_SEARCH_ENABLED", "true")
    monkeypatch.setenv("TAVILY_API_KEY", ENV_KEY)
    second_app = create_app(data_dir=tmp_path / "second-app", catalog_path=catalog, demo_enabled=True)
    with demo_client(second_app, "admin") as other:
        save_search(admin, enabled=False)
        assert expect(admin.get(SEARCH))["api_key_source"] == "saved"
        inherited = expect(other.get(SEARCH))
        assert inherited["api_key_source"] == "environment" and inherited["enabled"]
        expect(other.put(SEARCH, json={"clear_api_key": True}))
        assert expect(admin.get(SEARCH))["api_key_set"] and not expect(other.get(SEARCH))["api_key_set"]


def test_model_get_never_claims_connected_and_explicit_check_persists(app, admin, student, catalog, tmp_path):
    calls = model_fixture(app)
    saved = expect(admin.put(MODEL, json=MODEL_BODY))
    assert saved["ai"]["configured"] and saved["ai"]["connection"] == {"status": "not_checked", "checked_at": None, "message": None}
    assert not calls
    checked = expect(admin.post(MODEL + "/test"))
    assert checked["ok"] and checked["connection"]["status"] == "connected"
    assert checked["connection"]["checked_at"]
    assert expect(admin.get(MODEL))["ai"]["connection"] == checked["connection"]
    public = expect(student.get("/api/bootstrap"))["ai"]["connection"]
    assert public["status"] == "connected" and public["checked_at"] == checked["connection"]["checked_at"] and public["message"] is None
    assert len(calls) == 1 and json.loads(calls[0].content)["max_tokens"] == 32
    assert calls[0].headers["Authorization"] == "Bearer " + MODEL_KEY
    assert_safe(admin.get(MODEL))
    restarted = create_app(data_dir=app.state.database.path.parent, catalog_path=catalog, demo_enabled=True, frontend_dir=tmp_path / "none")
    with demo_client(restarted, "admin") as other:
        assert expect(other.get(MODEL))["ai"]["connection"] == checked["connection"]


def test_model_explicit_error_sanitized_persisted_and_successful_chat_not_explicit_check(app, admin, student):
    expect(admin.put(MODEL, json=MODEL_BODY))
    model_fixture(app, status=503)
    result = admin.post(MODEL + "/test")
    assert not expect(result)["ok"] and result.json()["connection"]["status"] == "error"
    assert_safe(result)
    assert expect(admin.get(MODEL))["ai"]["connection"] == result.json()["connection"]
    model_fixture(app)
    work = expect(student.post("/api/sessions/s4/chat", json={"message": "synthetic reasoning", "intent": "ask", "question_id": "q1"}))
    assert work["ai"]["connection"]["status"] == "error"  # ordinary inference is not an explicit check
    assert not work["ai"]["last_error"]


@pytest.mark.parametrize("change", [{"model": "changed"}, {"base_url": "http://other.invalid/v1"}, {"api_key": SAVED_KEY}, {"api_key": ""}, {"mode": "demo"}])
def test_model_config_and_key_change_invalidates_preserving_legacy_key_behavior(app, admin, change):
    expect(admin.put(MODEL, json=MODEL_BODY))
    model_fixture(app)
    checked = expect(admin.post(MODEL + "/test"))["connection"]
    same = dict(MODEL_BODY)
    same.pop("api_key")
    assert expect(admin.put(MODEL, json=same))["ai"]["connection"] == checked
    changed = expect(admin.put(MODEL, json={**same, **change}))
    assert changed["ai"]["connection"]["status"] != "connected"
    assert changed["ai"]["connection"]["checked_at"] is None
    if change == {"api_key": ""}:
        assert not changed["api_key_set"]  # old explicit empty model-key clear is preserved


@pytest.mark.parametrize("env_name,new_value", [("AICADEMIYA_AI_MODEL", "changed"), ("AICADEMIYA_AI_BASE_URL", "http://changed.invalid/v1"), ("AICADEMIYA_AI_API_KEY", SAVED_KEY), ("AICADEMIYA_AI_PROVIDER", "changed")])
def test_model_environment_fallback_change_invalidates_check(app, admin, monkeypatch, env_name, new_value):
    for name, value in (("MODE", "openai"), ("BASE_URL", MODEL_BODY["base_url"]), ("MODEL", MODEL_BODY["model"]), ("API_KEY", MODEL_KEY)):
        monkeypatch.setenv("AICADEMIYA_AI_" + name, value)
    model_fixture(app)
    assert expect(admin.post(MODEL + "/test"))["connection"]["status"] == "connected"
    monkeypatch.setenv(env_name, new_value)
    assert expect(admin.get(MODEL))["ai"]["connection"]["status"] == "not_checked"


@pytest.mark.parametrize("service", ["model", "search"])
@pytest.mark.parametrize("provider_ok", [True, False])
@pytest.mark.parametrize("round_trip", [True, False])
def test_concurrent_saved_config_change_rejects_stale_success_and_error(app, admin, service, provider_ok, round_trip):
    path = MODEL if service == "model" else SEARCH
    body = MODEL_BODY if service == "model" else {"enabled": True, "api_key": SAVED_KEY}
    expect(admin.put(path, json=body))
    entered, release = threading.Event(), threading.Event()
    def handle(request):
        entered.set()
        assert release.wait(10), "fixture release timeout"
        data = {"choices": [{"message": {"content": "Synthetic OK"}}]} if service == "model" else {"results": [ROW]}
        return httpx.Response(200 if provider_ok else 503, json=data)
    if service == "model":
        app.state.tutor.transport = httpx.MockTransport(handle)
    else:
        app.state.tutor.search = TavilySearch(httpx.MockTransport(handle))
    with ThreadPoolExecutor(max_workers=1) as worker:
        future = worker.submit(admin.post, path + "/test")
        try:
            assert entered.wait(10), "connection check did not enter fixture"
            changed = {**body, "api_key": ENV_KEY}
            expect(admin.put(path, json=changed))
            if round_trip:
                expect(admin.put(path, json=body))
        finally:
            release.set()
        result = future.result(timeout=10)
    expect(result, 409)
    assert_safe(result)
    current = expect(admin.get(path))
    check = current["ai"]["connection"] if service == "model" else current["connection"]
    assert check == {"status": "not_checked", "checked_at": None, "message": None}
    if service == "model":
        assert current["ai"]["last_error"] is None
    with app.state.database.connect() as conn:
        name = "ai" if service == "model" else "search"
        assert conn.execute("SELECT 1 FROM meta WHERE key=?", (f"service_{name}_connection",)).fetchone() is None


@pytest.mark.parametrize("service", ["model", "search"])
def test_environment_changed_during_explicit_probe_rejects_stale(app, admin, monkeypatch, service):
    if service == "model":
        for name, value in (("MODE", "openai"), ("BASE_URL", MODEL_BODY["base_url"]), ("MODEL", MODEL_BODY["model"]), ("API_KEY", MODEL_KEY)):
            monkeypatch.setenv("AICADEMIYA_AI_" + name, value)
    else:
        monkeypatch.setenv("AICADEMIYA_WEB_SEARCH_ENABLED", "true")
        monkeypatch.setenv("TAVILY_API_KEY", SAVED_KEY)
    def handle(request):
        monkeypatch.setenv("AICADEMIYA_AI_API_KEY" if service == "model" else "TAVILY_API_KEY", ENV_KEY)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Synthetic OK"}}], "results": [ROW]})
    if service == "model":
        app.state.tutor.transport = httpx.MockTransport(handle)
    else:
        app.state.tutor.search = TavilySearch(httpx.MockTransport(handle))
    expect(admin.post((MODEL if service == "model" else SEARCH) + "/test"), 409)


@pytest.mark.parametrize("kind", ["legacy", "guided"])
@pytest.mark.parametrize("actor", ["student", "teacher"])
def test_all_tutor_search_paths_use_same_saved_source_and_keep_planner_public(app, admin, student, teacher, monkeypatch, kind, actor):
    monkeypatch.setenv("TAVILY_API_KEY", ENV_KEY)
    monkeypatch.setenv("AICADEMIYA_WEB_SEARCH_ENABLED", "false")
    client = student if actor == "student" else teacher
    vid = configure_lesson(teacher, phases=["worksheet", "wrap_up"], count=2, delivery="on_request") if kind == "guided" else None
    expect(teacher.patch("/api/sessions/s4", json={"instructions": "PRIVATE_STAGE7_INSTRUCTIONS"}))
    if kind == "guided":
        vid = publish(teacher)["id"] if actor == "student" else ""
    else:
        publish(teacher)
    save_search(admin)
    expect(admin.put(MODEL, json=MODEL_BODY))
    calls, planners = search_fixture(app), []
    fixture = ProtocolFixture()
    def handle(request):
        body = json.loads(request.content)
        if isinstance(body.get("tool_choice"), dict):
            planners.append(body)
            return httpx.Response(200, json={"choices": [{"message": {"content": None, "tool_calls": [tool_call()]}}]})
        if kind == "guided":
            return fixture.handle(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Synthetic retrieved evidence [W1]"}}]})
    app.state.tutor.transport = httpx.MockTransport(handle)
    if kind == "guided":
        query = f"?version_id={vid}" if actor == "student" else ""
        expect(client.post("/api/sessions/s4/tutor/start" + query, json={"request_id": "open-saved"}))
        work = expect(client.post("/api/sessions/s4/tutor/turn" + query, json={"message": "wrong synthetic response", "request_id": "search-saved", "web_search": True}))
    else:
        work = expect(client.post("/api/sessions/s4/chat", json={"message": "Find public evidence", "question_id": "q1", "intent": "ask", "web_search": True}))
    assert len(calls) == 1 and calls[0].headers["Authorization"] == "Bearer " + SAVED_KEY
    assert work["ai"]["web_search"] == {"enabled": True, "configured": True, "provider": "tavily"}
    assert any(c.get("url") == ROW["url"] for c in work["messages"][-1]["citations"])
    for marker in (SAVED_KEY, ENV_KEY, MODEL_KEY, "PRIVATE_STAGE7_INSTRUCTIONS", "TEACHER_REFERENCE_ONLY", "TEACHER_MATERIAL", "demo-student"):
        assert marker not in json.dumps(planners)
    assert expect(admin.get(SEARCH))["connection"]["status"] == "not_checked"  # tutor search is not explicit testing
    expect(admin.put(SEARCH, json={"clear_api_key": True}))
    n = len(planners)
    if kind == "guided":
        expect(client.post("/api/sessions/s4/tutor/turn" + query, json={"message": "wrong synthetic response", "request_id": "cleared", "web_search": True}), 502)
    else:
        expect(client.post("/api/sessions/s4/chat", json={"message": "Find another public source", "intent": "ask", "web_search": True}), 502)
    assert len(calls) == 1 and len(planners) == n  # clear prevents env revival even on live paths


@pytest.mark.parametrize("saved_demo", [True, False])
def test_production_refuses_demo_and_prevents_legacy_environment_runtime_without_rows_loss(tmp_path, catalog, monkeypatch, saved_demo):
    monkeypatch.setenv("AICADEMIYA_AI_MODE", "demo")
    for key in ("AICADEMIYA_AI_BASE_URL", "AICADEMIYA_AI_MODEL", "AICADEMIYA_AI_API_KEY"):
        monkeypatch.setenv(key, "")
    app = create_app(data_dir=tmp_path / "production-isolated", catalog_path=catalog, demo_enabled=False)
    def forbidden(request):
        raise AssertionError("No real model calls allowed")
    app.state.tutor.transport = httpx.MockTransport(forbidden)
    with TestClient(app) as client:
        with app.state.database.connect() as conn:
            conn.execute("INSERT INTO users(id,name,email,role,is_demo) VALUES('stage7-admin','Synthetic administrator','stage7@example.invalid','admin',0)")
            conn.execute("UPDATE courses SET owner_id='stage7-admin'")
            conn.execute("INSERT INTO course_staff SELECT id,'stage7-admin' FROM courses")
            token = issue_session(conn, "stage7-admin")
            if saved_demo:
                conn.execute("INSERT INTO settings VALUES('ai_mode','demo')")
            conn.execute("INSERT INTO workspaces(session_id,user_id,version_id) VALUES('s4','stage7-admin','')")
            conn.execute("INSERT INTO messages(id,session_id,user_id,version_id,role,content,created_at,mode) VALUES('legacy-demo-row','s4','stage7-admin','','assistant','Historical deterministic fixture',?,'demo')", (now(),))
        client.cookies.set("aicademiya_session", token)
        status = expect(client.get(MODEL))["ai"]
        assert status["mode"] == "openai" and not status["configured"] and status["connection"]["status"] == "not_configured"
        expect(client.put(MODEL, json={"mode": "demo", "base_url": "", "model": ""}), 422)
        expect(client.post("/api/sessions/s4/chat", json={"message": "synthetic production refusal", "question_id": "q1", "intent": "ask"}), 502)
        expect(client.post("/api/sessions/s4/tutor/start", json={"request_id": "no-demo-start"}), 502)
        with app.state.database.connect() as conn:
            assert conn.execute("SELECT content,mode FROM messages WHERE id='legacy-demo-row'").fetchone()[:] == ("Historical deterministic fixture", "demo")
            assert conn.execute("SELECT count(*) FROM messages WHERE role='assistant'").fetchone()[0] == 1
            if saved_demo:
                assert conn.execute("SELECT value FROM settings WHERE key='ai_mode'").fetchone()[0] == "demo"


def test_explicit_isolated_demo_remains_labelled_not_connected(app, admin, student):
    def forbidden(*args, **kwargs):
        raise AssertionError("isolated demo must not use a model or Tavily")
    app.state.tutor.complete = forbidden
    app.state.tutor.search.search = forbidden
    checked = expect(admin.post(MODEL + "/test"))
    assert expect(admin.get(MODEL))["ai"]["configured"]  # preserve explicit QA adapter availability
    assert checked["mode"] == "demo" and "no model connectivity" in checked["message"]
    assert checked["connection"] == {"status": "not_configured", "checked_at": None, "message": None}
    work = expect(student.post("/api/sessions/s4/chat", json={"message": "Synthetic QA", "question_id": "q1", "intent": "ask"}))
    assert work["messages"][-1]["mode"] == "demo" and "not an LLM" in work["messages"][-1]["content"]
    with app.state.database.connect() as conn:
        assert conn.execute("SELECT 1 FROM meta WHERE key='service_ai_connection'").fetchone() is None
    tutor = Tutor(app.state.database)
    with app.state.database.connect() as conn:
        assert tutor.settings(conn)["mode"] == "openai"
    with pytest.raises(ModelFailure, match="disabled"):
        tutor.feedback({"mode": "demo"}, work, type("Chat", (), {"question_id": "q1"})())


def test_settings_and_checks_preserve_all_non_operational_rows_and_schema(app, admin, student):
    expect(student.post("/api/sessions/s4/chat", json={"message": "Synthetic retained work", "question_id": "q1", "intent": "answer", "request_id": "preserve-stage7"}))
    def capture(conn):
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {table: [tuple(r) for r in conn.execute(f'SELECT * FROM "{table}" ORDER BY rowid')] for table in tables if table not in ("settings", "meta", "auth_sessions")}
    with app.state.database.connect() as conn:
        conn.execute("INSERT OR IGNORE INTO meta VALUES('kv_scope_secret',?)", ("12" * 32,))
        conn.execute("INSERT INTO settings VALUES('unrelated_setting','unchanged')")
        before = capture(conn)
        schema = conn.execute("PRAGMA user_version").fetchone()[0]
        original_meta = {r[0]: r[1] for r in conn.execute("SELECT * FROM meta")}
    save_search(admin)
    search_fixture(app)
    model_fixture(app)
    expect(admin.put(MODEL, json=MODEL_BODY))
    expect(admin.post(MODEL + "/test"))
    expect(admin.post(SEARCH + "/test"))
    with app.state.database.connect() as conn:
        assert capture(conn) == before
        assert conn.execute("PRAGMA user_version").fetchone()[0] == schema == 9
        assert conn.execute("SELECT value FROM settings WHERE key='unrelated_setting'").fetchone()[0] == "unchanged"
        for key, value in original_meta.items():
            if key not in ("ai_last_error", "ai_last_error_binding"):
                assert conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()[0] == value


def test_legacy_private_error_diagnostic_never_projected(app, admin, student):
    with app.state.database.connect() as conn:
        conn.execute("INSERT OR REPLACE INTO meta VALUES('ai_last_error',?)", (MODEL_KEY + " private legacy provider body",))
    for client, path in ((admin, MODEL), (student, "/api/bootstrap"), (student, "/api/sessions/s4/workspace"), (student, "/api/sessions/s4/export")):
        response = client.get(path)
        expect(response)
        assert_safe(response)
        assert "private legacy provider body" not in response.text
