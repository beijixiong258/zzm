"""Stage6 preview guards exercised through real authenticated API and SQLite.

All inference is explicit deterministic demo or an in-process scripted protocol.
"""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
import threading
import httpx
import pytest
from fastapi.testclient import TestClient
from backend.aicademiya.db import issue_session, now
from backend.aicademiya.main import create_app
from backend.aicademiya.models import TeachingProfile
from .conftest import expect, demo_client, publish
from .test_stage3_guided import ProtocolFixture, use_fixture, configure, start, turn
from .test_stage3_persistence import records
from .test_stage2_backup import backup_tool

BASE = "/api/teacher/sessions/s4/preview"


def reset(teacher, sid="s4"):
    info = expect(teacher.get(f"/api/teacher/sessions/{sid}/preview"))
    return expect(teacher.post(f"/api/teacher/sessions/{sid}/preview/reset", json={"expected_revision": info["current_revision"]}))


def guided(teacher, identity, message=None, rid="opening"):
    data = {"request_id": rid, "preview_id": identity}
    if message is not None:
        data["message"] = message
    return teacher.post("/api/sessions/s4/tutor/" + ("start" if message is None else "turn"), json=data)


def test_readonly_identity_no_adoption_legacy_export_and_explicit_reset(teacher, student, app):
    initial = expect(teacher.get(BASE))
    assert set(initial) == {"id", "revision", "current_revision", "stale", "reset_required", "pending", "bound_at"}
    assert initial["id"] is None and not initial["reset_required"]
    with app.state.database.connect() as conn:
        before = records(conn)
    assert expect(teacher.get(BASE)) == initial
    with app.state.database.connect() as conn:
        assert records(conn) == before  # GET is entirely read-only.
    legacy = expect(teacher.post("/api/sessions/s4/tutor/start", json={"request_id": "legacy-opening"}))
    assert legacy["preview"]["id"] is None and legacy["preview"]["reset_required"]
    assert teacher.get("/api/sessions/s4/transcript?format=txt").status_code == 200
    assert teacher.get("/api/sessions/s4/export").json()["messages"] == legacy["messages"]
    expect(teacher.post(BASE + "/reset", json={"expected_revision": "old"}), 409)
    assert expect(teacher.get("/api/sessions/s4/workspace"))["messages"] == legacy["messages"]
    fresh = reset(teacher)
    assert fresh["preview"]["id"] and fresh["preview"]["bound_at"]
    assert fresh["preview"]["revision"] == fresh["preview"]["current_revision"]
    assert not fresh["preview"]["reset_required"] and not fresh["messages"] and not fresh["attempts"]
    assert fresh["tutor"]["phase"] == "not_started"
    pid = fresh["preview"]["id"]
    expect(teacher.post("/api/sessions/s4/tutor/start", json={}), 409)
    expect(guided(teacher, "wrong"), 409)
    work = expect(guided(teacher, pid))
    assert len(expect(guided(teacher, pid))["messages"]) == len(work["messages"])
    newer = reset(teacher)
    assert newer["preview"]["id"] != pid
    expect(guided(teacher, pid, "Queued old answer because evidence.", "late"), 409)
    assert not expect(teacher.get("/api/sessions/s4/workspace"))["messages"]
    assert "preview" not in expect(student.get("/api/sessions/s4/workspace"))


@pytest.mark.parametrize("edit", [
    {"instructions": "Meaningful instruction change"}, {"learning_objectives": ["Changed objective"]},
    {"reference_policy": "after_submit"}, {"teaching_language": "zh"},
    {"reference_answers": {"q1": "Changed private reference"}}, {"title": "Changed activity"},
    {"teaching_profile": TeachingProfile(response_detail="detailed").model_dump()},
])
def test_saved_teaching_edits_stale_bound_preview_not_rebind(teacher, edit):
    work = reset(teacher)
    pid, bound = work["preview"]["id"], work["preview"]["revision"]
    expect(guided(teacher, pid))
    expect(teacher.patch("/api/sessions/s4", json=edit))
    info = expect(teacher.get(BASE))
    assert info["stale"] and info["reset_required"] and info["revision"] == bound and info["id"] == pid
    stale = expect(teacher.get("/api/sessions/s4/workspace"))
    assert stale["read_only"] and stale["read_only_reason"] == "preview_stale" and stale["messages"]
    expect(guided(teacher, pid, "because evidence", "changed"), 409)
    expect(guided(teacher, pid), 409)  # Even a completed retry cannot bypass current revision.
    expect(teacher.post(BASE + "/reset", json={"expected_revision": bound}), 409)
    assert reset(teacher)["preview"]["revision"] == info["current_revision"]


def test_revision_questions_membership_metadata_not_availability_or_storage_paths(teacher, app):
    work = reset(teacher)
    pid, bound = work["preview"]["id"], work["preview"]["revision"]
    expect(teacher.patch("/api/sessions/s4", json={"active": False, "starts_at": "2099-01-01T00:00:00+00:00", "ends_at": "2100-01-01T00:00:00+00:00"}))
    with app.state.database.connect() as conn:
        raw = json.loads(conn.execute("SELECT content_json FROM materials WHERE id='s4-public'").fetchone()[0])
        raw["extracted_at"] = "2099-02-03"
        raw["assets_dir"] = "C:/synthetic-relocated-assets"
        conn.execute("UPDATE materials SET content_json=?,file_path='C:/synthetic-relocated.txt' WHERE id='s4-public'", (json.dumps(raw),))
    assert expect(teacher.get(BASE))["current_revision"] == bound
    expect(guided(teacher, pid))  # Operational inactive does not disable the owned draft.
    detail = expect(teacher.get("/api/sessions/s4"))
    detail["questions"][0]["prompt"] += " Changed meaningful question."
    expect(teacher.patch("/api/sessions/s4", json={"questions": detail["questions"]}))
    assert expect(teacher.get(BASE))["stale"]
    reset(teacher)
    expect(teacher.patch("/api/sessions/s4/materials/s4-public", json={"title": "Changed material title"}))
    assert expect(teacher.get(BASE))["stale"]
    reset(teacher)
    with app.state.database.connect() as conn:
        raw["excerpt"] = "Changed real stored extraction."
        conn.execute("UPDATE materials SET content_json=? WHERE id='s4-public'", (json.dumps(raw),))
    assert expect(teacher.get(BASE))["stale"]
    reset(teacher)
    expect(teacher.delete("/api/sessions/s4/materials/s4-public"))
    assert expect(teacher.get(BASE))["stale"]


def test_managed_preview_cannot_be_bypassed_by_legacy_mutations(teacher):
    pid = reset(teacher)["preview"]["id"]
    expect(guided(teacher, pid))
    for path, data in [
        ("chat", {"message": "queued", "intent": "ask", "request_id": "legacy"}),
        ("answers/q1", {"answer": "queued"}), ("reading", {"group_id": "core"}),
        ("references/q1", {}), ("submit", {}),
    ]:
        expect(teacher.post("/api/sessions/s4/" + path, json=data), 409)
    assert teacher.get("/api/sessions/s4/export").status_code == 200


def test_reset_owner_session_student_and_historical_isolation(teacher, student, admin, app):
    vid = expect(student.get("/api/sessions/s4/workspace"))["version"]["id"]
    expect(student.post(f"/api/sessions/s4/answers/q1?version_id={vid}", json={"answer": "Protected student original"}))
    expect(teacher.get(f"/api/sessions/s4/workspace?version_id={vid}"))
    expect(teacher.post("/api/sessions/s2/tutor/start", json={}))
    expect(teacher.post("/api/sessions/s4/tutor/start", json={}))
    with app.state.database.connect() as conn:
        # Other staff draft rows are retained even if ownership was subsequently transferred.
        conn.execute("INSERT INTO workspaces(session_id,user_id,version_id) VALUES('s4','demo-admin','')")
        conn.execute("INSERT INTO messages(id,session_id,user_id,version_id,role,content,created_at,mode) VALUES('other-preview','s4','demo-admin','','user','Protected other staff',?,'demo')", (now(),))
        before = records(conn)
    expect(student.get(BASE), 403)
    expect(admin.get(BASE), 403)
    expect(admin.post(BASE + "/reset", json={"expected_revision": expect(teacher.get(BASE))["current_revision"]}), 403)
    reset(teacher)
    with app.state.database.connect() as conn:
        after = records(conn)
        for table in ("messages", "attempts", "revisions", "workspaces", "chat_requests", "tutor_runs", "tutor_requests"):
            cols = before[table]["columns"]
            protected = lambda rows: [r for r in rows if not (r[cols.index("session_id")] == "s4" and r[cols.index("user_id")] == "demo-teacher" and r[cols.index("version_id")] == "")]
            assert protected(after[table]["rows"]) == protected(before[table]["rows"]), table
        for table in ("users", "settings", "meta", "sessions", "materials", "course_versions", "enrollments"):
            assert after[table] == before[table], table
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
    historical = expect(teacher.get(f"/api/sessions/s4/workspace?version_id={vid}"))
    assert "preview" not in historical and historical["read_only_reason"] == "published_snapshot"
    assert "preview" not in expect(teacher.get(f"/api/teacher/sessions/s4/students/demo-student-1/workspace?version_id={vid}"))


@pytest.mark.parametrize("legacy", [False, True])
def test_reset_rejects_real_pending_guided_and_legacy_inference(teacher, app, legacy):
    pid = None if legacy else reset(teacher)["preview"]["id"]
    provider = ProtocolFixture()
    use_fixture(app, teacher, provider)
    entered, release = threading.Event(), threading.Event()
    if legacy:
        def block_feedback(*args, **kwargs):
            entered.set()
            assert release.wait(10)
            return "[Scripted legacy fixture] feedback", []
        app.state.tutor.feedback = block_feedback
        action = lambda: teacher.post("/api/sessions/s4/chat", json={"message": "Raw legacy clarification", "intent": "ask", "request_id": "pending-legacy"})
    else:
        def blocked(static, envelope):
            entered.set()
            assert release.wait(10)
            return {"schema_version": 1, "text": "[Scripted fixture] welcome", "intent": "none", "question_id": None, "outcome": "unknown"}
        provider.overrides.append(blocked)
        action = lambda: guided(teacher, pid)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(action)
        try:
            assert entered.wait(10)
            info = expect(teacher.get(BASE))
            assert info["pending"]
            expect(teacher.post(BASE + "/reset", json={"expected_revision": info["current_revision"]}), 409)
        finally:
            release.set()
        expect(future.result(timeout=10))
    assert not expect(teacher.get(BASE))["pending"]


@pytest.mark.parametrize("drift", ["instructions", "generation", "availability"])
def test_inference_commit_revision_generation_guard_and_raw_input(teacher, app, drift):
    configure(teacher, phases=["worksheet", "wrap_up"], count=1)
    pid = reset(teacher)["preview"]["id"]
    provider = ProtocolFixture()
    use_fixture(app, teacher, provider)
    opening = expect(guided(teacher, pid))
    def race(static, envelope):
        if drift == "instructions":
            expect(teacher.patch("/api/sessions/s4", json={"instructions": "Changed during inference"}))
        elif drift == "generation":
            with app.state.database.connect() as conn:
                conn.execute("UPDATE teacher_previews SET preview_id='synthetic-replacement' WHERE session_id='s4' AND user_id='demo-teacher'")
        else:
            expect(teacher.patch("/api/sessions/s4", json={"active": False}))
        return {"schema_version": 1, "text": "[Scripted fixture] sufficient", "intent": "answer", "question_id": "q1", "outcome": "sufficient"}
    provider.overrides.append(race)
    response = guided(teacher, pid, "Raw response because evidence.", "race")
    work = expect(teacher.get("/api/sessions/s4/workspace"))
    if drift == "availability":
        expect(response)
        assert work["attempts"]["q1"]["answer"] == "Raw response because evidence."
        assert work["messages"][-1]["metadata"]["formative_outcome"] == "sufficient"
    else:
        expect(response, 409)
        assert not work["attempts"] and work["tutor"]["phase"] == opening["tutor"]["phase"]
        assert work["messages"][-1]["role"] == "user" and work["messages"][-1]["content"] == "Raw response because evidence."
        assert len(work["messages"]) == len(opening["messages"]) + 1
        with app.state.database.connect() as conn:
            assert conn.execute("SELECT status FROM tutor_requests WHERE request_id='race'").fetchone()[0] == "failed"


def test_failed_managed_retry_keeps_idempotency_and_new_outcome_only(teacher, app):
    configure(teacher, phases=["worksheet", "wrap_up"], count=1)
    pid = reset(teacher)["preview"]["id"]
    provider = ProtocolFixture()
    use_fixture(app, teacher, provider)
    expect(guided(teacher, pid))
    provider.overrides.append(httpx.Response(503, text="Explicit fixture unavailable"))
    expect(guided(teacher, pid, "because evidence", "retry"), 502)
    before = expect(teacher.get("/api/sessions/s4/workspace"))
    assert "metadata" not in before["messages"][-1]
    after = expect(guided(teacher, pid, "because evidence", "retry"))
    assert len(after["attempts"]["q1"]["revisions"]) == 1
    assert sum(x["role"] == "user" for x in after["messages"]) == 1
    assert after["messages"][-2]["metadata"]["formative_outcome"] == "sufficient"
    count = len(provider.requests)
    assert expect(guided(teacher, pid, "because evidence", "retry"))["messages"] == after["messages"]
    assert len(provider.requests) == count
    assert all("preview_id" not in json.loads(r["messages"][1]["content"])["request"] for r in provider.requests)


def test_student_fingerprints_model_envelope_and_completed_retry_byte_compatibility(teacher, student, app):
    vid = configure(teacher, phases=["worksheet", "wrap_up"], count=1)
    provider = ProtocolFixture()
    use_fixture(app, student, provider)
    start(student, vid)
    message = "Byte compatible student evidence."
    expect(turn(student, vid, message, "byte-old"))
    with app.state.database.connect() as conn:
        expected_start = hashlib.sha256(json.dumps({"operation": "start"}, sort_keys=True).encode()).hexdigest()
        expected_turn = hashlib.sha256(json.dumps({"operation": "turn", "message": message, "web_search": False, "action": "message", "question_id": None}, sort_keys=True).encode()).hexdigest()
        assert conn.execute("SELECT fingerprint FROM tutor_requests WHERE request_id='opening'").fetchone()[0] == expected_start
        assert conn.execute("SELECT fingerprint FROM tutor_requests WHERE request_id='byte-old'").fetchone()[0] == expected_turn
    calls = len(provider.requests)
    expect(turn(student, vid, message, "byte-old", preview_id="irrelevant-client-teacher-token"))
    assert len(provider.requests) == calls
    assert all("preview_id" not in json.loads(r["messages"][1]["content"])["request"] for r in provider.requests)


def test_repeatable_additive_migration_preserves_original_19_tables_and_secret(teacher, student, app, catalog):
    expect(teacher.post("/api/sessions/s4/tutor/start", json={}))
    vid = expect(student.get("/api/sessions/s4/workspace"))["version"]["id"]
    expect(student.post(f"/api/sessions/s4/answers/q1?version_id={vid}", json={"answer": "Preserve old learning"}))
    with app.state.database.connect() as conn:
        conn.execute("INSERT OR REPLACE INTO settings VALUES('ai_api_key','SYNTHETIC_PRESERVE_ONLY')")
        conn.execute("INSERT OR REPLACE INTO meta VALUES('kv_scope_secret','SYNTHETIC_PRESERVE_NAMESPACE')")
        conn.execute("DROP TABLE teacher_previews")
        conn.execute("DROP TABLE course_trash")  # Genuine pre-Stage6 19-table fixture.
        conn.execute("DROP TABLE account_avatars")
        conn.execute("DROP TABLE feedback")
        # All19 original tables plus independently retained later additive tables.
        later = ('course_staff','account_imports','document_jobs','document_revisions')
        before = {k: v for k, v in records(conn).items() if k not in later}
        stage11_before = {k: v for k, v in records(conn).items() if k in later}
        assert len(before) == 19
    app.state.database.initialize(catalog, demo_enabled=False)
    app.state.database.initialize(catalog, demo_enabled=False)
    with app.state.database.connect() as conn:
        after = records(conn)
        assert all(after[name] == data for name, data in before.items())
        assert all(after[k] == v for k, v in stage11_before.items())
        assert after["teacher_previews"]["rows"] == [] and after["course_trash"]["rows"] == [] and len(after) == 27
        assert after["account_avatars"]["rows"] == [] and after["feedback"]["rows"] == []
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
    assert expect(teacher.get(BASE))["reset_required"]  # Original trial still available, not silently rebound.
    assert teacher.get("/api/sessions/s4/transcript?format=txt").status_code == 200


def test_real_backup_restore_preserves_preview_binding_and_no_false_stale(teacher, app, catalog, tmp_path):
    configure(teacher, phases=["worksheet", "wrap_up"], count=1)
    work = reset(teacher)
    pid = work["preview"]["id"]
    work = expect(guided(teacher, pid))
    before = expect(teacher.get(BASE))
    backup, restored = tmp_path / "stage6-backup", tmp_path / "stage6-restored"
    backup_tool.backup(app.state.database.path.parent, backup, catalog.parent / "materials")
    report = backup_tool.restore(backup, restored)
    assert report["records_match"] and report["files_match"]
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    assert "teacher_previews" in manifest["tables"]
    restored_app = create_app(data_dir=restored, catalog_path=catalog, demo_enabled=True, frontend_dir=tmp_path / "none")
    with TestClient(restored_app) as client:
        client.cookies.update(teacher.cookies)
        assert expect(client.get(BASE)) == before
        loaded = expect(client.get("/api/sessions/s4/workspace"))
        assert loaded["messages"] == work["messages"] and not loaded["read_only"]
        expect(guided(client, pid, "Because public evidence", "restored-turn"))
    (tmp_path / "stage6-backend-verification.json").write_text(json.dumps({"migration_old_tables": 19, "migration_new_tables": 27, "backup_records_match": report["records_match"], "backup_files_match": report["files_match"], "preview_binding_restored": True, "inference": "explicit demo/scripted protocol only"}, indent=2), encoding="utf-8")
