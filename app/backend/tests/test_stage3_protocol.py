"""Router scope/prefix/search separation and transition-edge protocol fixtures."""
import json
import httpx
import pytest
from backend.aicademiya.models import TeachingProfile
from .conftest import expect, admin_request, demo_client, publish
from .test_stage3_guided import configure, start, turn, ProtocolFixture, protocol_response, use_fixture


def test_router_guided_stable_prefix_identity_version_purpose_and_600s(app, teacher, student, monkeypatch):
    vid = configure(teacher, phases=["worksheet", "wrap_up"], count=2, delivery="on_request")
    fixture = ProtocolFixture()
    observed_timeout = []
    def handle(req):
        observed_timeout.append(req.extensions["timeout"])
        return fixture.handle(req)
    app.state.tutor.transport = httpx.MockTransport(handle)
    monkeypatch.setenv("AICADEMIYA_AI_PROVIDER", "aicademiya-router")
    expect(admin_request(student, "PUT", "/api/teacher/settings", json={"mode": "openai", "base_url": "http://127.0.0.1:18280/v1", "model": "AIcademiya-64kx3-Qwen3.8-27B", "api_key": ""}))
    start(student, vid)
    expect(turn(student, vid, "wrong first learner input", "a"))
    first = fixture.requests[-1]
    with demo_client(app, index=2) as second:
        start(second, vid)
        expect(turn(second, vid, "wrong distinct learner input", "a"))
        other = fixture.requests[-1]
        assert first["messages"][0] == other["messages"][0]
        assert "first learner input" not in first["messages"][0]["content"]
        assert "distinct learner input" not in other["messages"][0]["content"]
        assert first["user"].startswith("aicv2-") and first["user"] != other["user"]
        env = json.loads(first["messages"][1]["content"])
        assert env["aicademiya_guided_envelope_v1"] is True and env["request"]["message"] == "wrong first learner input"
        assert first["user"] != fixture.requests[0]["user"]  # opening vs turn purpose
        private = json.loads(first["messages"][0]["content"].split("\n")[-1])["private_current_reference"]
        assert private["question_id"] == "q1" and "TEACHER_REFERENCE_ONLY_q2" not in json.dumps(first)
        new = publish(teacher)["id"]
        start(second, new, rid="new-version")
        expect(turn(second, new, "wrong distinct learner input", "new"))
        assert fixture.requests[-1]["user"] != other["user"]
    assert all(x["read"] == 600 and x["connect"] == 10 for x in observed_timeout)


def test_guided_explicit_search_planning_stays_public_and_links_retained(app, teacher, student, monkeypatch):
    vid = configure(teacher, phases=["worksheet", "wrap_up"], count=2, delivery="on_request")
    # Save a private framework and publish it, with its literal absent from search.
    p = TeachingProfile(phases=["worksheet", "wrap_up"], background="PRIVATE_FRAMEWORK_MARKER", reference_delivery="on_request").model_dump()
    expect(teacher.patch("/api/sessions/s4", json={"teaching_profile": p, "instructions": "PRIVATE_ADDITIONAL_MARKER"}))
    vid = publish(teacher)["id"]
    fixture, planners = ProtocolFixture(), []
    def handle(req):
        data = json.loads(req.content)
        if data.get("tool_choice") == {"type": "function", "function": {"name": "web_search"}}:
            planners.append(data)
            return httpx.Response(200, json={"choices": [{"message": {"content": None, "tool_calls": [{"id": "fixture-search", "type": "function", "function": {"name": "web_search", "arguments": json.dumps({"query": "concept evidence"})}}]}}]})
        return fixture.handle(req)
    app.state.tutor.transport = httpx.MockTransport(handle)
    expect(admin_request(student, "PUT", "/api/teacher/settings", json={"mode": "openai", "base_url": "http://fixture.invalid/v1", "model": "search-protocol", "api_key": ""}))
    monkeypatch.setenv("AICADEMIYA_WEB_SEARCH_ENABLED", "true")
    monkeypatch.setenv("TAVILY_API_KEY", "SYNTHETIC_FIXTURE_NOT_A_REAL_KEY")
    calls = []
    def search(query, *, api_key):
        assert api_key == "SYNTHETIC_FIXTURE_NOT_A_REAL_KEY"
        calls.append(query)
        return {"results": [{"url": "https://example.invalid/evidence", "title": "Retrieved fixture source", "content": "Synthetic supplementary evidence."}]}
    monkeypatch.setattr(app.state.tutor.search, "search", search)
    start(student, vid)
    expect(turn(student, vid, "wrong response", "off"))
    assert calls == [] and planners == []
    work = expect(turn(student, vid, "wrong response", "on", web_search=True))
    assert calls == ["concept evidence"] and len(planners) == 1
    for marker in ("PRIVATE_FRAMEWORK_MARKER", "PRIVATE_ADDITIONAL_MARKER", "TEACHER_REFERENCE_ONLY", "TEACHER_MATERIAL_DO_NOT_LEAK"):
        assert marker not in json.dumps(planners)
    assert any(c.get("url") == "https://example.invalid/evidence" for c in work["messages"][-1]["citations"])
    n = len(fixture.requests)
    expect(turn(student, vid, "wrong response", "on", web_search=True))
    assert calls == ["concept evidence"] and len(fixture.requests) == n
    expect(turn(student, vid, "wrong response", "on", web_search=False), 409)


def test_missing_reading_evidence_is_honest_no_private_substitute(teacher, student, app):
    with app.state.database.connect() as conn:
        row = conn.execute("SELECT content_json FROM materials WHERE id='s4-public'").fetchone()
        raw = json.loads(row[0])
        raw["visibility"] = "teacher"
        conn.execute("UPDATE materials SET content_json=? WHERE id='s4-public'", (json.dumps(raw),))
    vid = configure(teacher, phases=["worksheet", "reading", "wrap_up"], count=1)
    start(student, vid)
    work = expect(turn(student, vid, "Because evidence", "reading"))
    assert work["tutor"]["phase"] == "wrap_up" and work["tutor"]["reading"] == {"answered": 0, "total": 0}
    assert "no accessible public reading evidence" in work["messages"][-1]["content"]
    assert "TEACHER_MATERIAL_DO_NOT_LEAK" not in json.dumps(work)


def test_generation_error_retry_has_one_opt_in_message_and_one_quiz_set(app, teacher, student):
    vid = configure(teacher, phases=["worksheet", "quiz", "wrap_up"], count=1)
    fixture = ProtocolFixture()
    use_fixture(app, student, fixture)
    start(student, vid)
    expect(turn(student, vid, "Required supported response", "required"))
    fixture.overrides.extend([lambda st, env: protocol_response(st, env), {"schema_version": 1, "text": "Bad quiz", "items": []}])
    expect(turn(student, vid, "yes", "accept"), 502)
    work = expect(student.get(f"/api/sessions/s4/workspace?version_id={vid}"))
    assert work["tutor"]["phase"] == "quiz_offer" and work["tutor"]["quiz"]["total"] == 0
    assert work["tutor"]["pending_request_id"] is None and work["messages"][-1]["content"] == "yes"
    work = expect(turn(student, vid, "yes", "accept"))
    assert work["tutor"]["quiz"]["total"] == 5 and sum(m["role"] == "user" and m["content"] == "yes" for m in work["messages"]) == 1
    with app.state.database.connect() as conn:
        state = json.loads(conn.execute("SELECT state_json FROM tutor_runs WHERE user_id='demo-student-1' AND version_id=?", (vid,)).fetchone()[0])
        assert len(state["quiz_items"]) == 5 and len({q["id"] for q in state["quiz_items"]}) == 5


def test_accepted_old_version_finishes_but_auto_reference_gate_stays_closed(app, teacher, student):
    vid = configure(teacher, phases=["worksheet", "wrap_up"], count=2)
    fixture = ProtocolFixture()
    use_fixture(app, student, fixture)
    start(student, vid)
    def publish_during_call(static, env):
        from backend.aicademiya.versions import publish as direct_publish
        with app.state.database.connect() as conn:
            direct_publish(conn, "synthetic-course", "demo-teacher")
            conn.execute("UPDATE sessions SET active=0 WHERE id='s4'")
        return protocol_response(static, env)
    fixture.overrides.append(publish_during_call)
    work = expect(turn(student, vid, "Accepted supported old-version answer", "accepted"))
    assert work["version"]["id"] == vid and work["read_only_reason"] == "historical_version"
    assert work["attempts"]["q1"]["answer"] == "Accepted supported old-version answer"
    assert not work["attempts"]["q1"]["reference_revealed"] and "TEACHER_REFERENCE_ONLY_q1" not in work["messages"][-1]["content"]


def test_optional_quiz_not_required_for_explicit_submission(teacher, student):
    vid = configure(teacher, phases=["worksheet", "quiz", "wrap_up"], count=1)
    start(student, vid)
    expect(turn(student, vid, "Because evidence", "answer"))
    work = expect(turn(student, vid, "yes", "optional"))
    assert work["tutor"]["quiz"]["answered"] == 0
    submitted = expect(student.post(f"/api/sessions/s4/submit?version_id={vid}", json={}))
    assert submitted["submission"]["status"] == "submitted"
    expect(turn(student, vid, "1", "not-auto-unlock"), 409)


def test_legacy_answer_edit_reopens_discussion_without_formal_correctness(teacher, student):
    vid = configure(teacher, phases=["worksheet", "quiz", "wrap_up"], count=1)
    start(student, vid)
    expect(turn(student, vid, "Because evidence", "answer"))
    work = expect(turn(student, vid, "yes", "quiz"))
    old_item = work["messages"][-1]["presented_question_id"]
    work = expect(student.post(f"/api/sessions/s4/answers/q1?version_id={vid}", json={"answer": "An explicit revised response"}))
    assert work["tutor"]["phase"] == "worksheet" and work["tutor"]["question_states"]["q1"]["last_outcome"] == "unknown"
    work = expect(turn(student, vid, "Because revised evidence", "revised"))
    assert work["tutor"]["phase"] == "quiz" and work["messages"][-1]["presented_question_id"] == old_item
    assert work["tutor"]["quiz"]["total"] == 5 and work["tutor"]["question_states"]["q1"]["answer_count"] == 3


def test_profile_and_transcript_require_actual_course_owner(app, teacher, student):
    with app.state.database.connect() as conn:
        conn.execute("UPDATE courses SET owner_id='demo-admin' WHERE id='synthetic-course'")
        conn.execute("INSERT INTO course_staff VALUES('synthetic-course','demo-admin')")
        conn.execute("DELETE FROM course_staff WHERE course_id='synthetic-course' AND user_id='demo-teacher'")
    expect(teacher.post("/api/sessions/s4/teaching-preview", json={}), 403)
    expect(teacher.patch("/api/sessions/s4", json={"teaching_profile": TeachingProfile().model_dump()}), 403)
    expect(teacher.get("/api/sessions/s4/transcript"), 403)
    transcript = student.get("/api/sessions/s4/transcript?format=txt")
    assert transcript.status_code == 200 and "AIcademiya raw transcript" in transcript.text


@pytest.mark.parametrize("count", [1, 5])
def test_configured_reading_count_and_reordered_optional_phases(app, teacher, student, count):
    configure(teacher, phases=["worksheet", "reading", "quiz", "wrap_up"], count=1)
    profile = TeachingProfile(phases=["worksheet", "reading", "quiz", "wrap_up"], reading_question_count=count, response_detail="detailed").model_dump()
    expect(teacher.patch("/api/sessions/s4", json={"teaching_profile": profile}))
    preview = expect(teacher.post("/api/sessions/s4/teaching-preview", json={}))
    vid = publish(teacher)["id"]
    fixture = ProtocolFixture()
    use_fixture(app, student, fixture)
    start(student, vid)
    work = expect(turn(student, vid, "Supported worksheet response", "required"))
    assert work["tutor"]["reading"] == {"answered": 0, "total": count}
    static = json.loads(fixture.requests[-1]["messages"][0]["content"].split("\n")[-1])
    assert static["compiled_teaching"] == preview["text"]
    for i in range(count):
        work = expect(turn(student, vid, "A source-grounded reading idea", f"reading-{i}"))
    assert work["tutor"]["phase"] == "quiz_offer" and work["tutor"]["reading"]["answered"] == count
    work = expect(turn(student, vid, "no", "decline"))
    assert work["tutor"]["phase"] == "wrap_up"


def test_reading_generator_must_use_actual_public_labels(app, teacher, student):
    vid = configure(teacher, phases=["worksheet", "reading", "wrap_up"], count=1)
    fixture = ProtocolFixture()
    use_fixture(app, student, fixture)
    start(student, vid)
    fixture.overrides.extend([lambda st, env: protocol_response(st, env), {"schema_version": 1, "text": "Unusable source fixture", "items": [{"prompt": f"Invented {i}", "source_labels": ["NOT_A_PUBLIC_SOURCE"]} for i in range(3)]}])
    expect(turn(student, vid, "Unmodified supported answer", "reading-failure"), 502)
    work = expect(student.get(f"/api/sessions/s4/workspace?version_id={vid}"))
    assert work["tutor"]["phase"] == "worksheet" and work["attempts"] == {}
    assert work["tutor"]["updated_at"] == work["messages"][-1]["created_at"]
    work = expect(turn(student, vid, "Unmodified supported answer", "reading-failure"))
    assert work["tutor"]["phase"] == "reading" and len(work["attempts"]["q1"]["revisions"]) == 1
    assert "NOT_A_PUBLIC_SOURCE" not in json.dumps(work)


def test_failed_opening_retry_without_id_is_resumable_and_not_demo_fallback(app, teacher, student):
    vid = configure(teacher, phases=["worksheet", "wrap_up"], count=1)
    fixture = ProtocolFixture()
    use_fixture(app, student, fixture)
    fixture.overrides.append(httpx.Response(503, text="Synthetic provider failure"))
    expect(student.post(f"/api/sessions/s4/tutor/start?version_id={vid}", json={"request_id": "failed-opening"}), 502)
    work = expect(student.get(f"/api/sessions/s4/workspace?version_id={vid}"))
    assert work["messages"] == [] and work["tutor"]["phase"] == "not_started" and work["tutor"]["pending_request_id"] is None
    assert work["ai"]["last_error"] and work["ai"]["mode"] == "openai"
    work = expect(student.post(f"/api/sessions/s4/tutor/start?version_id={vid}", json={}))
    assert len(work["messages"]) == 1 and len(fixture.requests) == 2
    expect(turn(student, vid, "wrong response", "first"))
    fixture.overrides.append(httpx.Response(503, text="Synthetic turn failure"))
    expect(turn(student, vid, "Preserved raw failed answer", "failed-turn"), 502)
    n = len(fixture.requests)
    resumed = expect(student.post(f"/api/sessions/s4/tutor/start?version_id={vid}", json={}))
    assert resumed["tutor"]["pending_request_id"] is None and len(fixture.requests) == n
    assert resumed["messages"][-1]["question_id"] is None and "intent" not in resumed["messages"][-1]


def test_revisiting_prior_answer_in_optional_phase_preserves_quiz_items(teacher, student):
    vid = configure(teacher, phases=["worksheet", "quiz", "wrap_up"], count=1)
    start(student, vid)
    expect(turn(student, vid, "Because evidence", "answer"))
    work = expect(turn(student, vid, "yes", "quiz"))
    item = work["messages"][-1]["presented_question_id"]
    work = expect(turn(student, vid, "wrong revised answer", "prior-answer", question_id="q1"))
    assert work["tutor"]["phase"] == "worksheet" and work["tutor"]["current_question_id"] == "q1"
    assert work["attempts"]["q1"]["answer"] == "wrong revised answer" and work["tutor"]["quiz"]["status"] == "active"
    work = expect(turn(student, vid, "Because corrected evidence", "retry-prior"))
    assert work["tutor"]["phase"] == "quiz" and work["messages"][-1]["presented_question_id"] == item
    work = expect(turn(student, vid, "Skip remaining practice", "skip-active", action="skip_quiz"))
    assert work["tutor"]["phase"] == "wrap_up" and work["tutor"]["quiz"]["status"] == "skipped"
    assert work["tutor"]["quiz"]["total"] == 5 and work["tutor"]["quiz"]["answered"] == 0
    assert len(expect(turn(student, vid, "Skip remaining practice", "skip-active", action="skip_quiz"))["messages"]) == len(work["messages"])


def test_last_completed_request_id_is_exact_success_evidence_after_reload(app, teacher, student):
    vid = configure(teacher, phases=["worksheet", "wrap_up"], count=1)
    fixture = ProtocolFixture()
    use_fixture(app, student, fixture)
    work = start(student, vid, rid="Exact-Opening-ID")
    assert work["tutor"]["last_completed_request_id"] == "Exact-Opening-ID"
    fixture.overrides.append(httpx.Response(503, text="Fixture failure"))
    expect(turn(student, vid, "Raw supported response", "Exact-Turn-ID"), 502)
    failed = expect(student.get(f"/api/sessions/s4/workspace?version_id={vid}"))
    assert failed["tutor"]["last_completed_request_id"] == "Exact-Opening-ID" and failed["tutor"]["pending_request_id"] is None
    # Deliberately discard the successful POST body, as if the browser lost it.
    response = turn(student, vid, "Raw supported response", "Exact-Turn-ID")
    assert response.status_code == 200
    reloaded = expect(student.get(f"/api/sessions/s4/workspace?version_id={vid}"))
    assert reloaded["tutor"]["last_completed_request_id"] == "Exact-Turn-ID"
    assert reloaded["tutor"]["pending_request_id"] is None and len(reloaded["attempts"]["q1"]["revisions"]) == 1


def test_new_turn_can_replace_failed_request_without_replaying_old_state(app, teacher, student):
    vid = configure(teacher, phases=["worksheet", "wrap_up"], count=1)
    fixture = ProtocolFixture()
    use_fixture(app, student, fixture)
    start(student, vid)
    fixture.overrides.append(httpx.Response(503, text="Provider unavailable"))
    expect(turn(student, vid, "Old unclassified raw message", "old-failed"), 502)
    work = expect(turn(student, vid, "New explicit supported answer", "new-turn"))
    assert work["attempts"]["q1"]["answer"] == "New explicit supported answer"
    assert sum(m["content"] == "Old unclassified raw message" for m in work["messages"]) == 1
    expect(turn(student, vid, "Old unclassified raw message", "old-failed"), 409)
    assert work["tutor"]["last_completed_request_id"] == "new-turn"


def test_failed_optional_generation_never_blocks_required_submission(app, teacher, student):
    vid = configure(teacher, phases=["worksheet", "quiz", "wrap_up"], count=1)
    fixture = ProtocolFixture()
    use_fixture(app, student, fixture)
    start(student, vid)
    expect(turn(student, vid, "Required supported answer", "required"))
    fixture.overrides.extend([lambda st, env: protocol_response(st, env), httpx.Response(503, text="Quiz provider unavailable")])
    expect(turn(student, vid, "yes", "failed-quiz"), 502)
    work = expect(student.post(f"/api/sessions/s4/submit?version_id={vid}", json={}))
    assert work["submission"]["status"] == "submitted" and work["tutor"]["quiz"]["total"] == 0
    expect(turn(student, vid, "yes", "failed-quiz"), 409)
    assert work["messages"][-1]["content"] == "yes" and work["messages"][-1]["role"] == "user"




