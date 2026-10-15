"""Truthful source review: live selector equality, budgets, IDs and read-only scope."""
import json
import re
import pytest
from backend.aicademiya.ai import bounded_evidence, Tutor
from backend.aicademiya.authoring import selected_tutor_materials
from backend.aicademiya.version_context import session_access
from .conftest import expect
from .test_stage3_guided import configure, ProtocolFixture, use_fixture
from .test_stage3_persistence import records
from .test_stage6_preview import guided

URL = "/api/teacher/sessions/s4/source-review"


def old_bounded_evidence(materials, question=None, *, private=False, budget=32000):
    """Independent frozen Stage4 reference to guard model-prompt byte preservation."""
    eligible = [m for m in materials if m.get("kind") != "answer_key" and m.get("status") in ("ready", "needs_review") and m.get("excerpt") and (private or m.get("visibility") == "student")]
    words = set(re.findall(r"[A-Za-z]{3,}", (question or {}).get("prompt", "").lower()))
    if len(eligible) <= 8:
        ranked = [(0, i, m, m["excerpt"][:4000]) for i, m in enumerate(eligible)]
    else:
        ranked = []
        for index, material in enumerate(eligible):
            text = material["excerpt"][:50000]
            chunks = [text[n:n+2000] for n in range(0, len(text), 1500)]
            score, snippet = max(((len(words & set(re.findall(r"[A-Za-z]{3,}", chunk.lower()))), chunk) for chunk in chunks), key=lambda pair: pair[0])
            ranked.append((score, index, material, snippet))
        ranked.sort(key=lambda x: (-x[0], x[1]))
    context = []
    for _, _, material, snippet in ranked:
        if budget <= 0:
            break
        snippet = snippet[:min(4000, budget)]
        item = {"source_label": material.get("source_label", ""), "excerpt": snippet}
        if material.get("warning"):
            item["warning"] = material["warning"][:500]
        context.append(item)
        budget -= len(snippet)
    return context


def add_material(app, mid, text="Evidence.", **extra):
    raw = {"id": mid, "title": "Repeated title", "source_label": "DUPLICATE LABEL", "kind": "reading", "visibility": "student", "status": "ready", "excerpt": text, **extra}
    with app.state.database.connect() as conn:
        conn.execute("INSERT INTO materials VALUES(?,?,?,?,0)", (mid, "s4", json.dumps(raw), None))
    return mid


def assign(teacher, ids):
    detail = expect(teacher.get("/api/sessions/s4"))
    questions = detail["questions"][:1]
    questions[0]["prompt"] = "Explain targetalpha targetbeta with evidence."
    questions[0]["source_material_ids"] = ids
    expect(teacher.patch("/api/sessions/s4", json={"questions": questions}))


@pytest.mark.parametrize("count,budget,private", [(0,32000,False),(8,32000,False),(18,32000,False),(18,3501,False),(8,8000,True),(18,7001,True)])
def test_shared_evidence_refactor_preserves_exact_old_json_bytes(count, budget, private):
    materials = [{"id": f"real-{i}", "source_label": "Same label", "status": "needs_review", "visibility": "teacher" if private else "student", "kind": "reading", "excerpt": ("noise " * 830 + ("targetalpha targetbeta " if i % 2 else "unrelated ") + " tail " * 1000), "warning": "示例 warning" * 90} for i in range(count)]
    materials += [{"id":"key","kind":"answer_key","status":"ready","visibility":"teacher","excerpt":"DO_NOT_AGGREGATE"}, {"id":"broken","kind":"reading","status":"error","visibility":"student","excerpt":"not eligible"}]
    q = {"prompt": "targetalpha targetbeta"}
    expected = old_bounded_evidence(materials, q, private=private, budget=budget)
    actual = bounded_evidence(materials, q, private=private, budget=budget)
    assert json.dumps(actual, ensure_ascii=False).encode("utf-8") == json.dumps(expected, ensure_ascii=False).encode("utf-8")
    assert all(set(x) <= {"source_label", "excerpt", "warning"} for x in actual)


def test_review_actual_ids_duplicate_labels_live_equality_ranking_and_budget(teacher, app, tmp_path):
    configure(teacher, phases=["worksheet", "wrap_up"], count=1)
    public = [add_material(app, f"public-{i}", "noise " * 900 + " targetalpha targetbeta " + "tail " * 1000) for i in range(18)]
    private = [add_material(app, f"private-{i}", "Private conceptual context " * 300, visibility="teacher", kind="reference") for i in range(5)]
    key = add_material(app, "selected-key", "PRIVATE_KEY_NEVER_AGGREGATE", visibility="teacher", kind="answer_key")
    worksheet = add_material(app, "selected-worksheet", "PRIVATE_WORKSHEET_NEVER_AGGREGATE", visibility="teacher", kind="worksheet")
    unreadable = add_material(app, "unreadable", "", status="error")
    unselected = add_material(app, "unselected", "UNSELECTED_SENTINEL")
    unattached = add_material(app, "unattached-library", "UNATTACHED_SENTINEL")
    expect(teacher.delete(f"/api/sessions/s4/materials/{unattached}"))
    assign(teacher, public + private + [key, worksheet, unreadable])
    # Authoritative ID is the actual row ID, never JSON's optional/malformed ID or label.
    with app.state.database.connect() as conn:
        raw = json.loads(conn.execute("SELECT content_json FROM materials WHERE id=?", (public[0],)).fetchone()[0])
        raw["id"] = "misleading-legacy-json-id"
        conn.execute("UPDATE materials SET content_json=? WHERE id=?", (json.dumps(raw), public[0]))
    review = expect(teacher.post(URL, json={"question_id": "q1", "phase": "worksheet"}))
    assert review["scope"] == "saved_draft" and review["budgets"] == {"public_chars":32000,"private_chars":8000,"request_bytes":60000}
    assert len(review["public_evidence"]) == 16 and sum(len(x["excerpt"]) for x in review["public_evidence"]) == 32000
    assert len(review["private_evidence"]) == 2 and sum(len(x["excerpt"]) for x in review["private_evidence"]) == 8000
    assert review["public_evidence"][0]["material_id"] == public[0]
    assert len({x["material_id"] for x in review["public_evidence"]}) == 16
    assert len({x["source_label"] for x in review["public_evidence"]}) == 1
    rows = {x["id"]: x for x in review["materials"]}
    assert unattached not in rows and not rows[unselected]["selected"] and not rows[unselected]["included"]
    assert rows[key]["role"] == "answer_key" and not rows[key]["included"]
    assert rows[worksheet]["role"] == "private_worksheet" and not rows[worksheet]["included"]
    assert "Unreadable" in rows[unreadable]["reason"]
    assert "budget" in rows[public[-1]]["reason"] and not rows[public[-1]]["included"]
    assert review["private_reference"]["question_id"] == "q1"
    with app.state.database.connect() as conn:
        actor = dict(conn.execute("SELECT * FROM users WHERE id='demo-teacher'").fetchone())
        detail = session_access(conn, "s4", actor)
        selected_public, selected_private = selected_tutor_materials(conn, detail, "q1")
        q = detail["questions"][0]
        assert [{k:v for k,v in x.items() if k != "material_id"} for x in review["public_evidence"]] == bounded_evidence(selected_public, q)
        assert [{k:v for k,v in x.items() if k != "material_id"} for x in review["private_evidence"]] == bounded_evidence(selected_private, q, private=True, budget=8000)
    provider = ProtocolFixture()
    use_fixture(app, teacher, provider)
    expect(guided(teacher, None))
    expect(guided(teacher, None, "Why should evidence matter?", "sources-live"))
    static = json.loads(provider.requests[-1]["messages"][0]["content"].split("\n")[-1])
    assert static["public_evidence"] == [{k:v for k,v in x.items() if k != "material_id"} for x in review["public_evidence"]]
    assert static["private_selected_evidence"] == [{k:v for k,v in x.items() if k != "material_id"} for x in review["private_evidence"]]
    (tmp_path / "source-review-verification.json").write_text(json.dumps({"real_material_ids": [x["material_id"] for x in review["public_evidence"]], "duplicate_labels": True, "public_chars":32000,"private_chars":8000,"live_protocol_evidence_equal":True,"unattached_library_excluded":True}, indent=2), encoding="utf-8")


def test_unsaved_instruction_overlay_saved_sources_no_write_or_inference(teacher, student, admin, app, monkeypatch):
    q = expect(teacher.get("/api/sessions/s4"))["questions"][0]
    q["source_material_ids"] = ["s4-public"]
    expect(teacher.patch("/api/sessions/s4", json={"questions": [q]}))
    with app.state.database.connect() as conn:
        before = records(conn)
    def forbidden(*a, **kw):
        raise AssertionError("Read-only source review must not infer or search")
    monkeypatch.setattr(app.state.tutor, "complete", forbidden)
    monkeypatch.setattr(app.state.tutor, "search_context", forbidden)
    overlay = expect(teacher.post(URL, json={"instructions":"Explicit UNSAVED_OVERLAY", "question_id":"q1", "reference_policy":"after_submit"}))
    assert overlay["scope"] == "unsaved_instruction_overlay" and "UNSAVED_OVERLAY" in overlay["compiled"]["text"]
    assert overlay["private_reference"]["eligibility"] == "after_submit"
    assert [x["material_id"] for x in overlay["public_evidence"]] == ["s4-public"]
    expect(student.post(URL, json={}), 403)
    expect(admin.post(URL, json={}), 403)
    expect(teacher.post(URL, json={"instructions":None}), 422)
    expect(teacher.post(URL, json={"question_id":"not-saved"}), 404)
    expect(teacher.post(URL, json={"questions":[]}), 422)
    expect(teacher.post(URL, json={"phase":"quiz_offer"}), 422)
    with app.state.database.connect() as conn:
        assert records(conn) == before
    saved = expect(teacher.post(URL, json={"question_id":"q1"}))
    assert overlay["saved_revision"] == saved["saved_revision"] and "UNSAVED_OVERLAY" not in saved["compiled"]["text"]
    assert str(app.state.database.path.parent) not in json.dumps(saved)


@pytest.mark.parametrize("phase", ["quiz", "reading"])
def test_optional_phase_public_pool_private_exclusions_match_live_generation(teacher, app, phase):
    configure(teacher, phases=["worksheet", phase, "wrap_up"], count=1)
    extra = add_material(app, "extra-public", "A session-wide public source not assigned to q1.")
    private = add_material(app, "private-reading", "OPTIONAL_PRIVATE_SENTINEL", visibility="teacher", kind="reference")
    assign(teacher, ["s4-public", private])
    review = expect(teacher.post(URL, json={"question_id":"q1", "phase":phase}))
    assert extra in {x["material_id"] for x in review["public_evidence"]}
    assert review["private_evidence"] == [] and review["private_reference"] is None
    private_row = next(x for x in review["materials"] if x["id"] == private)
    assert private_row["selected"] and not private_row["included"] and "optional" in private_row["reason"]
    provider = ProtocolFixture()
    use_fixture(app, teacher, provider)
    expect(guided(teacher, None))
    expect(guided(teacher, None, "Required substantive evidence.", "finish-required"))
    if phase == "quiz":
        expect(guided(teacher, None, "yes", "optional-yes"))
    generation = next(json.loads(r["messages"][0]["content"].split("\n")[-1]) for r in provider.requests if '"task": "' + phase + '_generate"' in r["messages"][0]["content"])
    assert generation["public_evidence"] == [{k:v for k,v in x.items() if k != "material_id"} for x in review["public_evidence"]]
    assert "private_selected_evidence" not in generation and "private_current_reference" not in generation
    assert "OPTIONAL_PRIVATE_SENTINEL" not in json.dumps(generation)


def test_missing_goals_questions_reference_reading_and_real_request_limit_warnings(teacher, app):
    p = {"phases":["worksheet","reading","wrap_up"], "background":"中" * 8000,"student_profile":"中" * 8000,"response_strategies":"中" * 8000,"reading_focus":"中" * 8000}
    expect(teacher.patch("/api/sessions/s4", json={"questions":[],"learning_objectives":[],"teaching_profile":p,"instructions":"中" * 30000}))
    expect(teacher.delete("/api/sessions/s4/materials/s4-public"))
    review = expect(teacher.post(URL, json={}))
    text = "\n".join(review["warnings"])
    assert "No learning goals" in text and "No configured worksheet" in text and "without usable public evidence" in text
    assert "alone exceed" in text and not review["public_evidence"]
    assert len(review["compiled"]["text"]) > 30000  # Never silently modify/truncate saved content.
    with app.state.database.connect() as conn:
        detail = json.loads(conn.execute("SELECT content_json FROM sessions WHERE id='s4'").fetchone()[0])
        assert detail["instructions"] == "中" * 30000


def test_saved_source_link_identity_and_blank_reference_without_refetch(teacher, app, monkeypatch):
    mid = add_material(app, "saved-link", "Real stored linked excerpt.", kind="link", url="https://example.invalid/saved-source")
    with app.state.database.connect() as conn:
        detail = json.loads(conn.execute("SELECT content_json FROM sessions WHERE id='s4'").fetchone()[0])
        detail["questions"][0]["source_material_ids"] = []
        detail["questions"][0]["source_links"] = ["https://example.invalid/saved-source"]
        detail["reference_answers"]["q1"] = "   "
        conn.execute("UPDATE sessions SET content_json=? WHERE id='s4'", (json.dumps(detail),))
    def forbidden(*args, **kwargs):
        raise AssertionError("Stored source review must not refetch a link")
    from backend.aicademiya import authoring
    monkeypatch.setattr(authoring, "link_data", forbidden)
    result = expect(teacher.post(URL, json={"question_id":"q1"}))
    assert [x["material_id"] for x in result["public_evidence"]] == [mid]
    assert result["private_reference"] is None
    assert any("No instructor reference" in x for x in result["warnings"])
