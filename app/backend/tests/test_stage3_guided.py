"""Stage-3 synthetic SQLite + genuine HTTP adapter/protocol coverage; no live AI."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import httpx
import pytest
from fastapi.testclient import TestClient
from backend.aicademiya.models import TeachingProfile
from .conftest import expect, publish, admin_request, demo_client


def configure(teacher, *, sid="s4", phases=None, count=2, delivery="after_sufficient_answer", policy="after_attempt"):
    detail = expect(teacher.get(f"/api/sessions/{sid}"))
    p = TeachingProfile(phases=phases or ["worksheet", "quiz", "reading", "wrap_up"], reference_delivery=delivery).model_dump()
    questions = detail["questions"][:count]
    expect(teacher.patch(f"/api/sessions/{sid}", json={"questions": questions, "teaching_profile": p, "reference_policy": policy}))
    return publish(teacher)["id"]


def start(student, vid, sid="s4", rid="opening"):
    return expect(student.post(f"/api/sessions/{sid}/tutor/start?version_id={vid}", json={"request_id": rid}))


def turn(student, vid, message, rid, sid="s4", **extra):
    return student.post(f"/api/sessions/{sid}/tutor/turn?version_id={vid}", json={"message": message, "request_id": rid, **extra})


def protocol_response(static, envelope):
    """Labelled scripted model fixture, never evidence of real-model pedagogy."""
    task, phase = static["task"], static["phase"]
    if task == "quiz_generate":
        return {"schema_version": 1, "text": "[HTTP protocol fixture] Five optional items.", "items": [{"prompt": f"Fixture quiz {i+1}", "options": ["Evidence", "No evidence"], "correct_index": 0, "explanation": "Consult the evidence."} for i in range(5)]}
    if task == "reading_generate":
        label = static["public_evidence"][0]["source_label"]
        return {"schema_version": 1, "text": "[HTTP protocol fixture] Public reading discussion.", "items": [{"prompt": f"Fixture reading {i+1}", "source_labels": [label]} for i in range(static["reading_question_count"])]}
    q = static["current_question"]
    msg = envelope["request"].get("message", "")
    intent = "none"
    outcome = "unknown"
    qid = None
    if task == "turn":
        if phase == "quiz_offer":
            intent = "accept_quiz" if msg == "yes" else "decline_quiz" if msg == "no" else "ask"
        elif q:
            qid = q["id"]
            asking = msg.startswith(("Why", "How", "Could")) or envelope["request"].get("action") in ("hint", "review_question")
            intent = "ask" if asking else "mixed" if "?" in msg else "answer"
            outcome = "unknown" if asking else "needs_retry" if "wrong" in msg else "sufficient"
    return {"schema_version": 1, "text": "[HTTP protocol fixture] Specific formative guidance.", "intent": intent, "question_id": qid, "outcome": outcome}


class ProtocolFixture:
    def __init__(self):
        self.requests = []
        self.overrides = []

    def handle(self, request):
        assert request.url.path.endswith("/v1/chat/completions")
        body = json.loads(request.content)
        self.requests.append(body)
        static = json.loads(body["messages"][0]["content"].split("\n")[-1])
        envelope = json.loads(body["messages"][1]["content"])
        if self.overrides:
            value = self.overrides.pop(0)
            if callable(value):
                value = value(static, envelope)
            if isinstance(value, httpx.Response):
                return value
            if isinstance(value, Exception):
                raise value
        else:
            value = protocol_response(static, envelope)
        content = value if isinstance(value, str) else json.dumps(value)
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": content}}]})


def use_fixture(app, student, fixture):
    app.state.tutor.transport = httpx.MockTransport(fixture.handle)
    expect(admin_request(student, "PUT", "/api/teacher/settings", json={"mode": "openai", "base_url": "http://fixture.invalid/v1", "model": "scripted-protocol", "api_key": ""}))


def test_profile_new_legacy_preview_publication_and_privacy(teacher, student, app):
    legacy = expect(teacher.get("/api/sessions/s4"))
    assert legacy["teaching_profile"]["reference_delivery"] == "on_request"
    old = expect(student.get("/api/sessions/s4/workspace"))["version"]["id"]
    profile = TeachingProfile(background="PRIVATE_PROFILE_SENTINEL", response_detail="detailed", idle_hint_seconds=20, presentation="paced").model_dump()
    saved = expect(teacher.patch("/api/sessions/s4", json={"teaching_profile": profile}))
    assert saved["teaching_profile"] == profile
    preview = expect(teacher.post("/api/sessions/s4/teaching-preview", json={"teaching_profile": profile, "instructions": "UNSAVED_ADDITIONAL", "reference_policy": "after_submit"}))
    assert "PRIVATE_PROFILE_SENTINEL" in preview["text"] and "UNSAVED_ADDITIONAL" in preview["text"] and "after_submit" in preview["text"]
    assert expect(teacher.get("/api/sessions/s4"))["instructions"] != "UNSAVED_ADDITIONAL"
    expect(student.post("/api/sessions/s4/teaching-preview", json={}), 403)
    before = expect(student.get(f"/api/sessions/s4/workspace?version_id={old}"))
    assert before["tutor"]["presentation"] == "full" and "PRIVATE_PROFILE_SENTINEL" not in json.dumps(before)
    new = publish(teacher)["id"]
    after = expect(student.get(f"/api/sessions/s4/workspace?version_id={new}"))
    assert after["tutor"]["presentation"] == "paced" and after["tutor"]["idle_hint_seconds"] == 20
    assert "teaching_profile" not in after["session"] and "PRIVATE_PROFILE_SENTINEL" not in json.dumps(after)
    historic = expect(teacher.get(f"/api/teacher/courses/synthetic-course/versions/{old}"))
    assert historic["sessions"][0]["teaching_profile"]["reference_delivery"] == "on_request"
    created = expect(teacher.post("/api/courses/synthetic-course/sessions", json={"title": "New synthetic session"}))
    assert created["teaching_profile"]["reference_delivery"] == "after_sufficient_answer"


@pytest.mark.parametrize("invalid", [
    {"unknown": "x"}, {"schema_version": True}, {"schema_version": "1"}, {"reading_question_count": 0},
    {"reading_question_count": 6}, {"reading_question_count": "3"}, {"idle_hint_seconds": 1},
    {"phases": ["worksheet", "worksheet", "wrap_up"]}, {"phases": ["worksheet", "warmup", "wrap_up"]},
    {"phases": ["quiz", "worksheet", "wrap_up"]}, {"phases": ["reading", "worksheet", "wrap_up"]},
    {"phases": ["worksheet"]}, {"background": "x" * 8001}, {"reference_delivery": "automatic"},
])
def test_profile_validation_consistent(teacher, invalid):
    for path, method in (("/api/sessions/s4", "patch"), ("/api/sessions/s4/teaching-preview", "post"), ("/api/courses/synthetic-course/sessions", "post")):
        data = {"teaching_profile": invalid}
        if "courses" in path:
            data["title"] = "Synthetic"
        expect(getattr(teacher, method)(path, json=data), 422)


def test_demo_progressive_mixed_followup_images_reference_and_resume(teacher, student):
    vid = configure(teacher, phases=["worksheet", "quiz", "wrap_up"])
    work = start(student, vid)
    assert work["tutor"]["current_question_id"] == "q1"
    opening = work["messages"][0]
    assert "Deterministic demo" in opening["content"] and opening["presented_question_id"] == "q1"
    assert opening["metadata"]["presented_question"]["images"][0]["url"] == "/api/assets/plot.png"
    assert "IMAGE_METADATA_DO_NOT_LEAK" not in json.dumps(opening)
    assert len(start(student, vid, rid="new-opening-id")["messages"]) == 1
    for i in range(3):
        work = expect(turn(student, vid, "wrong response", f"wrong-{i}"))
        assert work["tutor"]["current_question_id"] == "q1" and not work["attempts"]["q1"]["reference_revealed"]
        work = expect(turn(student, vid, "Please give a hint", f"hint-{i}", action="hint"))
    assert work["tutor"]["question_states"]["q1"]["answer_count"] == 3
    assert work["tutor"]["question_states"]["q1"]["hint_count"] == 3
    mixed = "My answer is supported because evidence fits. Why is this example useful?"
    work = expect(turn(student, vid, mixed, "mixed"))
    assert work["attempts"]["q1"]["answer"] == mixed
    assert work["tutor"]["completed_question_ids"] == ["q1"] and work["tutor"]["current_question_id"] == "q2"
    assert work["messages"][-1]["question_id"] == "q1" and work["messages"][-1]["presented_question_id"] == "q2"
    assert work["attempts"]["q1"]["reference_revealed"]
    text = work["messages"][-1]["content"]
    assert text.index("Instructor reference") < text.index("Synthetic teaching question q2")
    work = expect(turn(student, vid, "Why does the prior example help?", "previous", action="review_question", question_id="q1"))
    assert work["attempts"]["q1"]["answer"] == mixed and "q2" not in work["attempts"]
    assert work["tutor"]["current_question_id"] == "q2" and work["messages"][-1]["presented_question_id"] == "q1"
    before = len(work["messages"])
    assert len(expect(turn(student, vid, mixed, "mixed"))["messages"]) == before
    expect(turn(student, vid, "changed", "mixed"), 409)
    work = expect(turn(student, vid, "Because evidence supports the concept", "second"))
    assert work["tutor"]["phase"] == "quiz_offer"
    assert work["submission"]["status"] == "in_progress"
    work = expect(turn(student, vid, "no", "decline"))
    assert work["tutor"]["phase"] == "wrap_up" and work["tutor"]["quiz"]["status"] == "skipped"
    summary = work["messages"][-1]["metadata"]["summary"]
    assert summary["worksheet_discussed"] == 2 and summary["worksheet_total"] == 2
    assert summary["recorded_answer_turns"] == 5 and summary["help_turns"] == 4
    assert "2 of 2 configured worksheet questions discussed" in work["messages"][-1]["content"]
    work = expect(turn(student, vid, "Finish", "finish"))
    assert work["tutor"]["phase"] == "complete" and work["submission"]["status"] != "submitted"
    work = expect(student.post(f"/api/sessions/s4/submit?version_id={vid}", json={}))
    assert work["submission"]["status"] == "submitted"
    reviewed = expect(teacher.post(f"/api/teacher/sessions/s4/students/demo-student-1/review?version_id={vid}", json={"status": "confirmed", "note": "Teacher explicitly checked."}))
    assert reviewed["submission"]["status"] == "confirmed"
    assert len(start(student, vid)["messages"]) == len(work["messages"])
    expect(turn(student, vid, "Again", "locked"), 409)


def test_protocol_http_optional_quiz_reading_separate_and_bounded(app, teacher, student):
    vid = configure(teacher, count=1)
    fixture = ProtocolFixture()
    use_fixture(app, student, fixture)
    work = start(student, vid)
    assert len(fixture.requests) == 1 and fixture.requests[0]["stream"] is False
    work = expect(turn(student, vid, "My supported answer", "required"))
    assert work["tutor"]["phase"] == "quiz_offer"
    work = expect(turn(student, vid, "yes", "accept"))
    assert work["tutor"]["quiz"] == {"status": "active", "answered": 0, "total": 5, "correct": 0}
    assert "correct_index" not in json.dumps(work) and "private_formative_key" not in json.dumps(work)
    n = len(fixture.requests)
    assert expect(turn(student, vid, "yes", "accept"))["tutor"]["phase"] == "quiz" and len(fixture.requests) == n
    for i in range(5):
        work = expect(turn(student, vid, "1" if i % 2 == 0 else "2", f"quiz-{i}"))
    assert work["tutor"]["quiz"] == {"status": "completed", "answered": 5, "total": 5, "correct": 3}
    assert work["tutor"]["phase"] == "reading" and work["tutor"]["reading"] == {"answered": 0, "total": 3}
    assert list(work["attempts"]) == ["q1"] and work["progress"]["answered"] == 1
    for i in range(3):
        work = expect(turn(student, vid, "Public reading idea with evidence", f"reading-{i}"))
    assert work["tutor"]["phase"] == "wrap_up" and work["tutor"]["reading"]["answered"] == 3
    text = student.get(f"/api/sessions/s4/transcript?version_id={vid}&format=txt").text
    assert text.count("| formative=") == 8 and "My supported answer" in text and "Fixture quiz" in text
    assert "correct_index" not in text and "TEACHER_MATERIAL_DO_NOT_LEAK" not in text
    for request in fixture.requests:
        assert request["messages"][0]["role"] == "system" and request["messages"][1]["role"] == "user"
        assert "TEACHER_MATERIAL_DO_NOT_LEAK" not in json.dumps(request)
        static = json.loads(request["messages"][0]["content"].split("\n")[-1])
        if static["phase"] != "worksheet":
            assert "private_current_reference" not in static


@pytest.mark.parametrize("bad", ["not JSON", "{}", "{\"schema_version\":2}", "```json\n{}\n```", "empty-http", "unfinished", "unknown-question", "unrevealed-key", "unexpected-field"])
def test_protocol_errors_fail_visibly_and_idempotent_retry(app, teacher, student, bad):
    vid = configure(teacher, phases=["worksheet", "wrap_up"], count=1, delivery="on_request")
    fixture = ProtocolFixture()
    use_fixture(app, student, fixture)
    initial = start(student, vid)
    if bad == "empty-http":
        value = httpx.Response(200, json={"choices": []})
    elif bad == "unfinished":
        value = httpx.Response(200, json={"choices": [{"message": {"content": "", "tool_calls": [{"id": "x"}]}}]})
    elif bad in ("unknown-question", "unrevealed-key", "unexpected-field"):
        def value(static, env):
            row = protocol_response(static, env)
            if bad == "unknown-question":
                row["question_id"] = "invented-q"
            elif bad == "unrevealed-key":
                row["text"] = "TEACHER_REFERENCE_ONLY_q1"
            else:
                row["submit"] = True
            return row
    else:
        value = bad
    fixture.overrides.append(value)
    failed = turn(student, vid, "Unmodified raw answer", "failure")
    expect(failed, 502)
    work = expect(student.get(f"/api/sessions/s4/workspace?version_id={vid}"))
    assert work["messages"][-1]["content"] == "Unmodified raw answer" and work["messages"][-1]["role"] == "user"
    assert work["attempts"] == {} and work["tutor"]["pending_request_id"] is None
    assert work["tutor"]["phase"] == initial["tutor"]["phase"]
    work = expect(turn(student, vid, "Unmodified raw answer", "failure"))
    assert len(work["messages"]) == 3 and work["attempts"]["q1"]["answer"] == "Unmodified raw answer"
    assert len(work["attempts"]["q1"]["revisions"]) == 1
    n = len(fixture.requests)
    expect(turn(student, vid, "Unmodified raw answer", "failure"))
    assert len(fixture.requests) == n


def test_actual_socket_provider_503_then_same_id_retry(app, teacher, student):
    vid = configure(teacher, phases=["worksheet", "wrap_up"], count=1)
    records = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            records.append(request)
            static = json.loads(request["messages"][0]["content"].split("\n")[-1])
            env = json.loads(request["messages"][1]["content"])
            failed = static["task"] == "turn" and len(records) == 2
            self.send_response(503 if failed else 200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            result = {"choices": [{"message": {"content": json.dumps(protocol_response(static, env))}}]}
            self.wfile.write(json.dumps(result).encode())
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        expect(admin_request(student, "PUT", "/api/teacher/settings", json={"mode": "openai", "base_url": f"http://127.0.0.1:{server.server_port}/v1", "model": "socket-protocol-fixture", "api_key": ""}))
        start(student, vid)
        expect(turn(student, vid, "Actual HTTP raw answer", "socket"), 502)
        work = expect(turn(student, vid, "Actual HTTP raw answer", "socket"))
        assert len(records) == 3 and work["attempts"]["q1"]["answer"] == "Actual HTTP raw answer"
        assert len(work["messages"]) == 3
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def test_concurrent_pending_is_real_and_blocks_legacy_mutations(app, teacher, student):
    vid = configure(teacher, phases=["worksheet", "wrap_up"], count=2)
    fixture = ProtocolFixture()
    use_fixture(app, student, fixture)
    start(student, vid)
    entered, release = threading.Event(), threading.Event()
    def blocked(static, env):
        entered.set()
        assert release.wait(10)
        return protocol_response(static, env)
    fixture.overrides.append(blocked)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(turn, student, vid, "Supported answer", "pending")
        try:
            assert entered.wait(10)
            work = expect(student.get(f"/api/sessions/s4/workspace?version_id={vid}"))
            assert work["tutor"]["pending_request_id"] == "pending"
            resumed = expect(student.post(f"/api/sessions/s4/tutor/start?version_id={vid}", json={}))
            assert resumed["tutor"]["pending_request_id"] == "pending"
            expect(turn(student, vid, "Supported answer", "pending"), 409)
            expect(turn(student, vid, "Other", "different"), 409)
            expect(student.post(f"/api/sessions/s4/answers/q1?version_id={vid}", json={"answer": "Legacy conflicting edit"}), 409)
            expect(student.post(f"/api/sessions/s4/submit?version_id={vid}", json={}), 409)
        finally:
            release.set()
        done = expect(future.result(timeout=15))
    assert done["tutor"]["pending_request_id"] is None and len(done["messages"]) == 3


def test_raw_export_real_time_escape_and_authorization(teacher, student, app):
    vid = configure(teacher, phases=["worksheet", "wrap_up"], count=1, delivery="on_request")
    before = datetime.now().astimezone()
    work = start(student, vid)
    raw = "  Because <script>alert('x')</script> & evidence\nsecond line  "
    work = expect(turn(student, vid, raw, "html"))
    after = datetime.now().astimezone()
    assert before <= datetime.fromisoformat(work["tutor"]["started_at"]) <= after
    assert before <= datetime.fromisoformat(work["tutor"]["updated_at"]) <= after
    assert work["tutor"]["elapsed_seconds"] == int((datetime.fromisoformat(work["tutor"]["updated_at"]) - datetime.fromisoformat(work["tutor"]["started_at"])).total_seconds())
    txt = student.get(f"/api/sessions/s4/transcript?version_id={vid}&format=txt")
    assert txt.status_code == 200 and raw in txt.text and vid in txt.text and work["messages"][-2]["created_at"] in txt.text
    exported = student.get(f"/api/sessions/s4/transcript?version_id={vid}&format=html")
    assert "<script>" not in exported.text and "&lt;script&gt;" in exported.text and "sandbox" in exported.headers["content-security-policy"]
    assert "attachment" in exported.headers["content-disposition"]
    expect(student.get(f"/api/sessions/s4/transcript?format=json"), 422)
    with TestClient(app) as anonymous:
        expect(anonymous.get(f"/api/sessions/s4/transcript?version_id={vid}"), 401)


@pytest.mark.parametrize("policy,delivery,revealed", [("after_attempt", "after_sufficient_answer", True), ("after_feedback", "after_sufficient_answer", True), ("after_submit", "after_sufficient_answer", False), ("after_attempt", "on_request", False)])
def test_reference_delivery_respects_existing_eligibility(teacher, student, policy, delivery, revealed):
    vid = configure(teacher, phases=["worksheet", "wrap_up"], count=1, policy=policy, delivery=delivery)
    start(student, vid)
    work = expect(turn(student, vid, "Because evidence supports it", "answer"))
    assert work["attempts"]["q1"]["reference_revealed"] is revealed
    if policy == "after_submit":
        expect(student.post(f"/api/sessions/s4/references/q1?version_id={vid}"), 409)
        expect(student.post(f"/api/sessions/s4/submit?version_id={vid}", json={}))
    expect(student.post(f"/api/sessions/s4/references/q1?version_id={vid}"))


def test_selected_reading_and_empty_required_no_invention(teacher, student):
    vid = configure(teacher, sid="s2", phases=["worksheet", "wrap_up"], count=19)
    work = start(student, vid, sid="s2")
    for i in range(1, 10):
        work = expect(turn(student, vid, "Because public evidence", f"core-{i}", sid="s2"))
    assert work["tutor"]["phase"] == "worksheet" and work["tutor"]["current_question_id"] is None
    assert work["messages"][-1]["metadata"]["kind"] == "reading_choice"
    work = expect(turn(student, vid, "Pong", "branch", sid="s2"))
    assert work["selected_reading"] == "II-Pong" and work["tutor"]["current_question_id"] == "pong1"
    assert "bray1" not in work["tutor"]["question_states"]
    expect(turn(student, vid, "Because evidence", "inactive-branch", sid="s2", question_id="bray1"), 409)
    # New empty session remains empty, rather than getting made-up required work.
    created = expect(teacher.post("/api/courses/synthetic-course/sessions", json={"title": "Empty", "teaching_profile": TeachingProfile(phases=["worksheet", "wrap_up"]).model_dump()}))
    sid = created["id"]
    expect(teacher.patch(f"/api/sessions/{sid}", json={"status": "published"}))
    fresh = publish(teacher)["id"]
    empty = start(student, fresh, sid=sid)
    assert empty["tutor"]["phase"] == "wrap_up" and empty["progress"]["total"] == 0
    assert empty["session"]["questions"] == [] and "No required questions" in empty["messages"][0]["content"]
    expect(student.post(f"/api/sessions/{sid}/submit?version_id={fresh}", json={}))


def test_warmup_legacy_attempts_unknown_and_readonly_resume(teacher, student):
    old = expect(student.get("/api/sessions/s4/workspace"))["version"]["id"]
    expect(student.post(f"/api/sessions/s4/answers/q1?version_id={old}", json={"answer": "Existing saved work is not correctness"}))
    work = start(student, old)
    assert work["tutor"]["phase"] == "warmup" and work["attempts"]["q1"]["answer"] == "Existing saved work is not correctness"
    work = expect(turn(student, old, "Ready", "warmup"))
    assert work["tutor"]["current_question_id"] == "q1" and work["tutor"]["completed_question_ids"] == []
    assert work["tutor"]["question_states"]["q1"]["last_outcome"] == "unknown"
    expect(teacher.patch("/api/sessions/s4", json={"active": False}))
    assert start(student, old)["read_only"] and len(start(student, old)["messages"]) == 3
    expect(turn(student, old, "Because evidence", "closed"), 409)
    expect(teacher.patch("/api/sessions/s4", json={"active": True}))
    fresh = publish(teacher)["id"]
    assert fresh != old and start(student, old)["read_only_reason"] == "historical_version"
    expect(turn(student, old, "Because evidence", "historical"), 409)


def test_pure_ask_cannot_overwrite_even_bad_classifier(app, teacher, student):
    vid = configure(teacher, phases=["worksheet", "wrap_up"], count=2, delivery="on_request")
    fixture = ProtocolFixture()
    use_fixture(app, student, fixture)
    start(student, vid)
    saved = expect(turn(student, vid, "First answer", "first"))
    def bad_classifier(static, envelope):
        return {"schema_version": 1, "text": "[HTTP fixture] Clarification.", "intent": "answer", "question_id": "q1", "outcome": "sufficient"}
    fixture.overrides.append(bad_classifier)
    work = expect(turn(student, vid, "Why did the earlier example help?", "ask"))
    assert work["attempts"]["q1"]["answer"] == saved["attempts"]["q1"]["answer"] and "q2" not in work["attempts"]
    assert work["tutor"]["current_question_id"] == "q2" and len(work["attempts"]["q1"]["revisions"]) == 1
