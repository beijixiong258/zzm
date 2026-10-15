"""Actual isolated SQLite/API coverage; deterministic demo/protocol, no live model."""
import json
from .conftest import expect
from .test_stage3_guided import configure, start, turn, ProtocolFixture, use_fixture
from backend.aicademiya.guided_state import presentation_text


def assert_parts(message):
    metadata = message["metadata"]
    assert metadata["presentation_text"] == presentation_text(metadata)
    assert message["content"] == metadata["narrative_text"] + metadata["presentation_text"]
    assert "correct_index" not in json.dumps(metadata)
    assert "TEACHER_MATERIAL_DO_NOT_LEAK" not in json.dumps(metadata)


def test_stage4_opening_keeps_raw_content_with_explicit_public_parts(teacher, student):
    vid = configure(teacher, phases=["worksheet", "quiz", "wrap_up"], count=1, delivery="on_request")
    work = start(student, vid)
    message = work["messages"][0]
    assert_parts(message)
    assert "Synthetic teaching question q1" in message["content"]
    assert "Synthetic teaching question q1" not in message["metadata"]["narrative_text"]
    # Independent workspace GET is the durable record, not just the POST response.
    readback = expect(student.get(f"/api/sessions/s4/workspace?version_id={vid}"))
    assert readback["messages"] == work["messages"]


def test_stage4_quiz_feedback_and_next_card_parts_keep_raw_exports(teacher, student):
    vid = configure(teacher, phases=["worksheet", "quiz", "wrap_up"], count=1, delivery="on_request")
    start(student, vid)
    expect(turn(student, vid, "Because evidence supports this explanation", "s4-required"))
    offer = expect(student.get(f"/api/sessions/s4/workspace?version_id={vid}"))
    assert_parts(offer["messages"][-1])
    work = expect(turn(student, vid, "Yes", "s4-accept"))
    assert_parts(work["messages"][-1])
    previous = work["messages"][-1]
    work = expect(turn(student, vid, "B", "s4-quiz-answer"))
    feedback = work["messages"][-1]
    assert_parts(feedback)
    assert "Formative practice:" in feedback["metadata"]["narrative_text"]
    assert feedback["presented_question_id"] != previous["presented_question_id"]
    assert "Optional formative practice:\n" in feedback["content"]
    assert work["tutor"]["last_completed_request_id"] == "s4-quiz-answer"
    readback = expect(student.get(f"/api/sessions/s4/workspace?version_id={vid}"))
    assert readback["messages"] == work["messages"]
    for format in ("txt", "html"):
        response = student.get(f"/api/sessions/s4/transcript?version_id={vid}&format={format}")
        assert response.status_code == 200
        assert feedback["content"] in response.text
    exported = expect(student.get(f"/api/sessions/s4/export?version_id={vid}"))
    assert feedback["content"] in json.dumps(exported, ensure_ascii=False).replace("\\n", "\n")
    # A completed same-ID retry neither generates nor rewrites any stored message.
    retry = expect(turn(student, vid, "B", "s4-quiz-answer"))
    assert retry["messages"] == work["messages"]
    assert retry["tutor"]["quiz"] == work["tutor"]["quiz"]


def test_stage4_failed_raw_message_retry_retains_identity_and_metadata(app, teacher, student):
    vid = configure(teacher, phases=["worksheet", "wrap_up"], count=1, delivery="on_request")
    fixture = ProtocolFixture()
    use_fixture(app, student, fixture)
    initial = start(student, vid)
    fixture.overrides.append("not JSON")
    raw = "  Stage4 raw answer\nwith a second line.  "
    expect(turn(student, vid, raw, "s4-failed"), 502)
    failed = expect(student.get(f"/api/sessions/s4/workspace?version_id={vid}"))
    assert failed["messages"][-1]["content"] == raw
    assert failed["messages"][0] == initial["messages"][0]
    work = expect(turn(student, vid, raw, "s4-failed"))
    assert len([m for m in work["messages"] if m["role"] == "user"]) == 1
    assert_parts(work["messages"][-1])
    assert work["tutor"]["last_completed_request_id"] == "s4-failed"
    before = len(fixture.requests)
    retry = expect(turn(student, vid, raw, "s4-failed"))
    assert retry["messages"] == work["messages"]
    assert len(fixture.requests) == before
    assert raw in student.get(f"/api/sessions/s4/transcript?version_id={vid}&format=txt").text


def test_stage4_automatic_reference_remains_before_exact_presentation_suffix(teacher, student):
    vid = configure(teacher, phases=["worksheet", "wrap_up"], count=2)
    start(student, vid)
    work = expect(turn(student, vid, "Because evidence supports this explanation", "s4-reference"))
    message = work["messages"][-1]
    metadata = message["metadata"]
    suffix = metadata["presentation_text"]
    assert suffix == presentation_text(metadata)
    assert message["content"].endswith(suffix)
    narrative = message["content"][:-len(suffix)]
    assert "Instructor reference comparison (not a formal grade):" in narrative
    assert narrative.startswith(metadata["narrative_text"])
    assert "TEACHER_REFERENCE_ONLY_q1" in narrative
    assert "TEACHER_REFERENCE_ONLY_q2" not in message["content"]
    assert metadata["reference_question_id"] == "q1"
    # Engine metadata predates route-inserted comparison: the UI must not blindly
    # trust narrative_text and lose this eligible comparison.
    assert message["content"] != metadata["narrative_text"] + suffix
    readback = expect(student.get(f"/api/sessions/s4/workspace?version_id={vid}"))
    assert readback["messages"][-1] == message
    assert message["content"] in student.get(f"/api/sessions/s4/transcript?version_id={vid}&format=txt").text


def test_stage4_synthetic_legacy_row_is_not_rewritten_by_reads_or_new_turn(app, teacher, student):
    vid = configure(teacher, phases=["worksheet", "wrap_up"], count=2, delivery="on_request")
    initial = start(student, vid)
    opening = initial["messages"][0]
    # Recreate a genuine pre-stage4 layout in this isolated synthetic database:
    # old records had the raw appended prompt, but no explicit display parts.
    legacy_metadata = dict(opening["metadata"])
    legacy_metadata.pop("narrative_text")
    legacy_metadata.pop("presentation_text")
    with app.state.tutor.db.connect() as conn:
        conn.execute("UPDATE messages SET metadata_json=? WHERE id=?", (json.dumps(legacy_metadata), opening["id"]))
        original = tuple(conn.execute("SELECT id, content, metadata_json, created_at FROM messages WHERE id=?", (opening["id"],)).fetchone())
    for _ in range(2):
        readback = expect(student.get(f"/api/sessions/s4/workspace?version_id={vid}"))
        assert readback["messages"][0]["content"] == opening["content"]
        assert readback["messages"][0]["metadata"] == legacy_metadata
        assert opening["content"] in student.get(f"/api/sessions/s4/transcript?version_id={vid}&format=txt").text
    new = expect(turn(student, vid, "Why does evidence matter?", "s4-new-after-legacy"))
    assert_parts(new["messages"][-1])
    assert new["messages"][0]["metadata"] == legacy_metadata
    with app.state.tutor.db.connect() as conn:
        retained = tuple(conn.execute("SELECT id, content, metadata_json, created_at FROM messages WHERE id=?", (opening["id"],)).fetchone())
    assert retained == original
