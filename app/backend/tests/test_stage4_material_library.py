"""Stage-4 synthetic SQLite/HTTP regressions; never live model/search calls."""
import io
import json
from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.aicademiya.authoring import selected_tutor_materials
from backend.aicademiya.material_library import migrate_material_library
from backend.aicademiya.main import create_app
from backend.aicademiya.version_context import session_access
from tools import backup_data
from .conftest import demo_client, expect, publish, question
from .test_materials import payload_for
from .test_stage2_authoring import public_link_fixture, worksheet_docx

CID = "synthetic-course"
LIBRARY = f"/api/courses/{CID}/materials"
VERSIONS = f"/api/teacher/courses/{CID}/versions"


def upload(client, sid, name, data=None, **metadata):
    return expect(client.post(f"/api/sessions/{sid}/materials", data=metadata,
                              files={"file": (name, data if data is not None else ("Synthetic " + name).encode())}))


def attach(client, sid, mid):
    return expect(client.post(f"/api/sessions/{sid}/materials/attach", json={"material_id": mid}))


def mids(client, sid):
    return {m["id"] for m in expect(client.get(f"/api/sessions/{sid}"))["materials"]}


def library(client, cid=CID):
    return {m["id"]: m for m in expect(client.get(f"/api/courses/{cid}/materials"))["materials"]}


def new_session(client, cid=CID, title="Synthetic library session"):
    result = expect(client.post(f"/api/courses/{cid}/sessions", json={"title": title}))
    sid = result["id"]
    expect(client.patch(f"/api/sessions/{sid}", json={"status": "published"}))
    return sid


def test_exact_abc_bde_no_copies_idempotency_detach_and_restart(app, teacher, catalog):
    s1, s2 = new_session(teacher), new_session(teacher)
    before = set(library(teacher))
    a, b, c = [upload(teacher, s1, name+".txt") for name in "ABC"]
    assert mids(teacher, s1) == {a["id"], b["id"], c["id"]}
    assert mids(teacher, s2) == set()
    assert set(library(teacher)) - before == mids(teacher, s1)
    d, e = [upload(teacher, s2, name+".txt") for name in "DE"]
    assert attach(teacher, s2, b["id"]) == attach(teacher, s2, b["id"])
    assert mids(teacher, s2) == {b["id"], d["id"], e["id"]}
    assert mids(teacher, s1) == {a["id"], b["id"], c["id"]}
    current = library(teacher)
    assert set(current) - before == {m["id"] for m in (a, b, c, d, e)}
    assert current[b["id"]]["session_ids"] == [s1, s2]
    with app.state.database.connect() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM materials") if r["id"] not in before]
        assert len(rows) == 5 and len({r["file_path"] for r in rows}) == 5
        b_row = next(r for r in rows if r["id"] == b["id"])
        assert b_row["session_id"] == s1
        assert conn.execute("SELECT count(*) FROM session_materials WHERE material_id=?", (b["id"],)).fetchone()[0] == 2
    expect(teacher.delete(f"/api/sessions/{s1}/materials/{b['id']}"))
    assert b["id"] not in mids(teacher, s1) and b["id"] in mids(teacher, s2)
    assert library(teacher)[b["id"]]["session_ids"] == [s2]
    expect(teacher.delete(f"/api/sessions/{s2}/materials/{b['id']}"))
    assert library(teacher)[b["id"]]["session_ids"] == []
    assert teacher.get(b["download_url"]).content == b"Synthetic B.txt"
    expect(teacher.post(f"/api/sessions/{s1}/materials/{b['id']}/reprocess"), 404)
    for _ in range(2):
        app.state.database.initialize(catalog, True)
    assert b["id"] not in mids(teacher, s1) | mids(teacher, s2)
    assert library(teacher)[b["id"]]["session_ids"] == []
    assert Path(b_row["file_path"]).read_bytes() == b"Synthetic B.txt"
    assert attach(teacher, s2, b["id"])["id"] == b["id"]


def test_owner_course_role_and_private_guards(app, teacher, student, admin):
    item = upload(teacher, "s4", "private.txt", b"PRIVATE_LIBRARY_SENTINEL", visibility="teacher", kind="answer_key")
    attach(teacher, "s2", item["id"])
    expect(teacher.patch(f"/api/sessions/s2/materials/{item['id']}", json={"visibility": "student"}), 422)
    v = publish(teacher)["id"]
    for sid in ("s4", "s2"):
        assert item["id"] not in mids(student, sid)
        assert "PRIVATE_LIBRARY_SENTINEL" not in student.get(f"/api/sessions/{sid}/workspace?version_id={v}").text
    for path in (LIBRARY, item["download_url"], item["preview_url"]):
        expect(student.get(path), 403)
        expect(admin.get(path), 403)  # Admin is not the teaching course owner.
    expect(student.post("/api/sessions/s2/materials/attach", json={"material_id": item["id"]}), 403)
    expect(student.post(f"/api/sessions/s2/materials/{item['id']}/reprocess"), 403)
    expect(admin.post("/api/sessions/s2/materials/attach", json={"material_id": item["id"]}), 403)
    other = expect(teacher.post("/api/courses", json={"title": "Other owned course", "code": "OTHER"}))["id"]
    sid = new_session(teacher, other)
    expect(teacher.post(f"/api/sessions/{sid}/materials/attach", json={"material_id": item["id"]}), 422)
    expect(teacher.post("/api/sessions/s4/materials/attach", json={"material_id": "missing"}), 404)
    expect(teacher.post("/api/sessions/s4/materials/attach", json={}), 422)
    expect(teacher.get(item["preview_url"]+"?version_id="), 422)
    with TestClient(app) as anonymous:
        expect(anonymous.get(LIBRARY), 401)
        expect(anonymous.get(item["download_url"]), 401)
        expect(anonymous.get(item["preview_url"]), 401)
    foreign_course = expect(admin.post("/api/courses", json={"title": "Another owner", "code": "ADMIN"}))["id"]
    foreign_sid = new_session(admin, foreign_course)
    expect(teacher.post(f"/api/sessions/{foreign_sid}/materials/attach", json={"material_id": item["id"]}), 403)
    expect(teacher.get(f"/api/courses/{foreign_course}/materials"), 403)


def test_shared_metadata_reprocess_and_immutable_snapshot(app, teacher, student):
    item = upload(teacher, "s4", "shared.txt", b"Original synthetic reading")
    attach(teacher, "s2", item["id"])
    old = publish(teacher)["id"]
    expect(student.get(f"/api/sessions/s2/workspace?version_id={old}"))
    before = expect(teacher.get(VERSIONS+"/"+old))
    expect(teacher.patch(f"/api/sessions/s2/materials/{item['id']}", json={"title": "Shared title", "visibility": "teacher"}))
    assert library(teacher)[item["id"]]["title"] == "Shared title"
    for sid in ("s4", "s2"):
        assert next(m for m in expect(teacher.get(f"/api/sessions/{sid}"))["materials"] if m["id"] == item["id"])["visibility"] == "teacher"
    with app.state.database.connect() as conn:
        row = conn.execute("SELECT * FROM materials WHERE id=?", (item["id"],)).fetchone()
        original = row["file_path"]
    Path(original).write_text("Reprocessed synthetic text with different coverage", encoding="utf-8")
    result = expect(teacher.post(f"/api/sessions/s2/materials/{item['id']}/reprocess"))
    assert result["excerpt"] == "Reprocessed synthetic text with different coverage"
    assert result["extraction_report"]["schema_version"] == 1
    assert result["extraction_report"]["chars_extracted"] == len(result["excerpt"])
    assert result["title"] == "Shared title" and result["visibility"] == "teacher"
    assert expect(teacher.get(VERSIONS+"/"+old)) == before
    assert "Original synthetic reading" in student.get(f"/api/materials/{item['id']}/preview?version_id={old}").text
    new = publish(teacher)["id"]
    expect(student.get(f"/api/materials/{item['id']}/preview?version_id={new}"), 403)
    with app.state.database.connect() as conn:
        assert conn.execute("SELECT file_path,session_id FROM materials WHERE id=?", (item["id"],)).fetchone()[:] == (original, "s4")
    Path(original).unlink()
    expect(teacher.post(f"/api/sessions/s2/materials/{item['id']}/reprocess"), 404)


def test_reprocess_rejects_links_unassigned_and_preserves_error_report(teacher, public_link_fixture):
    item = upload(teacher, "s4", "bad.pdf", b"Synthetic invalid PDF")
    result = expect(teacher.post(f"/api/sessions/s4/materials/{item['id']}/reprocess"))
    assert result["status"] == "error" and result["warning"] and result["extraction_report"]["failed_units"]
    expect(teacher.post(f"/api/sessions/s2/materials/{item['id']}/reprocess"), 404)
    link = expect(teacher.post("/api/sessions/s4/materials/link", json={"url": "https://example.org/refetch"}))
    expect(teacher.post(f"/api/sessions/s4/materials/{link['id']}/reprocess"), 422)
    assert public_link_fixture == ["https://example.org/refetch"]


def test_shared_link_relationships_reuse_cleanup_and_frozen_history(app, teacher, public_link_fixture):
    q = question("link-q"); q.pop("teacher_internal")
    q["source_links"] = ["https://example.org/shared-source"]
    s1 = expect(teacher.patch("/api/sessions/s4", json={"questions": [q]}))
    item = next(m for m in s1["materials"] if m["kind"] == "link")
    s2 = expect(teacher.patch("/api/sessions/s2", json={"groups": [{"id": "core", "title": "Core", "kind": "core"}], "questions": [q]}))
    assert next(m for m in s2["materials"] if m["kind"] == "link")["id"] == item["id"]
    assert len(public_link_fixture) == 1
    old = publish(teacher)["id"]
    expect(teacher.patch(f"/api/sessions/s2/materials/{item['id']}", json={"url": "https://example.org/changed-source"}))
    for sid in ("s4", "s2"):
        draft = expect(teacher.get(f"/api/sessions/{sid}"))
        assert draft["questions"][0]["source_links"] == ["https://example.org/changed-source"]
        expect(teacher.delete(f"/api/sessions/{sid}/materials/{item['id']}"), 409)
    saved = expect(teacher.get(VERSIONS+"/"+old))
    assert all(s["questions"][0]["source_links"] == ["https://example.org/shared-source"] for s in saved["sessions"])
    # Cleanup of an unpublished managed link in S1 must not remove S2's membership.
    q["source_links"] = ["https://example.org/unpublished-shared"]
    draft = expect(teacher.patch("/api/sessions/s4", json={"questions": [q]}))
    fresh = next(m for m in draft["materials"] if m.get("url") == q["source_links"][0])
    expect(teacher.patch("/api/sessions/s2", json={"questions": [q]}))
    q["source_links"] = []
    expect(teacher.patch("/api/sessions/s4", json={"questions": [q]}))
    assert fresh["id"] not in mids(teacher, "s4") and fresh["id"] in mids(teacher, "s2")
    assert library(teacher)[fresh["id"]]["session_ids"] == ["s2"]


def test_selected_tutor_sources_follow_membership_visibility_and_versions(app, teacher):
    a = upload(teacher, "s4", "A.txt", b"PUBLIC_SELECTED_A")
    b = upload(teacher, "s4", "B.txt", b"PUBLIC_SELECTED_B")
    c = upload(teacher, "s4", "C.txt", b"PRIVATE_SELECTED_C", visibility="teacher")
    key = upload(teacher, "s4", "key.txt", b"NEVER_AGGREGATE_KEY", visibility="teacher", kind="answer_key")
    for item in (b, c, key):
        attach(teacher, "s2", item["id"])
    q = question("source-q"); q.pop("teacher_internal")
    q["source_material_ids"] = [b["id"], c["id"], key["id"]]
    expect(teacher.patch("/api/sessions/s2", json={"groups": [{"id": "core", "title": "Core", "kind": "core"}], "questions": [q]}))
    version = publish(teacher)["id"]
    owner = expect(teacher.get("/api/auth/me"))["user"]
    with app.state.database.connect() as conn:
        public, private = selected_tutor_materials(conn, session_access(conn, "s2", owner), "source-q")
        assert {x["id"] for x in public} == {b["id"]}
        assert {x["id"] for x in private} == {c["id"]}
    q["source_material_ids"] = []
    expect(teacher.patch("/api/sessions/s2", json={"questions": [q]}))
    expect(teacher.delete(f"/api/sessions/s2/materials/{b['id']}"))
    with app.state.database.connect() as conn:
        public, private = selected_tutor_materials(conn, session_access(conn, "s2", owner), "source-q")
        assert {x["id"] for x in public} == {"s2-public"}
        assert {x["id"] for x in private} == {c["id"]}
        historical, _ = selected_tutor_materials(conn, session_access(conn, "s2", owner, version), "source-q")
        assert {x["id"] for x in historical} == {b["id"]} and a["id"] not in {x["id"] for x in historical}


def test_restore_exact_memberships_retained_new_library_and_origin_history(app, teacher, student):
    s1, s2 = new_session(teacher), new_session(teacher)
    a, b, c = [upload(teacher, s1, name+".txt") for name in "ABC"]
    d, e = [upload(teacher, s2, name+".txt") for name in "DE"]
    attach(teacher, s2, b["id"])
    old = publish(teacher)["id"]
    expect(student.get(f"/api/sessions/{s2}/workspace?version_id={old}"))  # History only in S2.
    old_snapshot = expect(teacher.get(VERSIONS+"/"+old))
    expect(teacher.delete(f"/api/sessions/{s1}/materials/{b['id']}"))
    expect(teacher.delete(f"/api/sessions/{s2}/materials/{d['id']}"))
    f = upload(teacher, s2, "F.txt")
    expect(teacher.patch(f"/api/sessions/{s2}/materials/{b['id']}", json={"title": "Changed shared B"}))
    newer = publish(teacher)["id"]
    # Historical download finds the allowed S2 membership after S1 history denial.
    assert student.get(b["download_url"]+"?version_id="+old).content == b"Synthetic B.txt"
    with demo_client(app, index=2) as no_history:
        expect(no_history.get(b["download_url"]+"?version_id="+old), 403)
    restored = expect(teacher.post(VERSIONS+"/"+old+"/restore", json={}))
    assert restored["id"] not in (old, newer)
    assert mids(teacher, s1) == {a["id"], b["id"], c["id"]}
    assert mids(teacher, s2) == {b["id"], d["id"], e["id"]}
    assert library(teacher)[f["id"]]["session_ids"] == []
    assert library(teacher)[b["id"]]["title"] == "B.txt"
    assert teacher.get(f["download_url"]).content == b"Synthetic F.txt"
    assert expect(teacher.get(VERSIONS+"/"+old)) == old_snapshot
    with app.state.database.connect() as conn:
        assert conn.execute("SELECT session_id FROM materials WHERE id=?", (b["id"],)).fetchone()[0] == s1
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        assert conn.execute("SELECT count(*) FROM materials WHERE id=?", (b["id"],)).fetchone()[0] == 1
    assert not expect(teacher.get(VERSIONS))["has_unpublished_changes"]


def test_removed_origin_session_keeps_library_and_attached_student_access(teacher, student):
    baseline = publish(teacher)["id"]
    sid = new_session(teacher)
    item = upload(teacher, sid, "removed-origin.txt")
    attach(teacher, "s2", item["id"])
    edition = publish(teacher)["id"]
    expect(student.get(f"/api/sessions/{sid}/workspace?version_id={edition}"))
    expect(teacher.post(VERSIONS+"/"+baseline+"/restore", json={}))
    expect(teacher.get(f"/api/sessions/{sid}"), 404)
    assert library(teacher)[item["id"]]["session_ids"] == []
    assert teacher.get(item["download_url"]).content == b"Synthetic removed-origin.txt"
    attach(teacher, "s2", item["id"])
    latest = publish(teacher)["id"]
    assert student.get(item["download_url"]+"?version_id="+latest).content == b"Synthetic removed-origin.txt"
    assert student.get(item["download_url"]+"?version_id="+edition).status_code == 200
    expect(teacher.post(f"/api/sessions/{sid}/materials/attach", json={"material_id": item["id"]}), 404)


def test_shared_worksheet_assets_and_original_history_authorization(app, teacher, student):
    preview = expect(teacher.post("/api/sessions/s4/worksheet-import/preview", files={"file": ("synthetic-figure.docx", worksheet_docx())}))
    payload = {k: preview["draft"][k] for k in ("groups", "questions", "reference_answers")}
    payload["mode"] = "replace"
    expect(teacher.post(f"/api/sessions/s4/worksheet-import/{preview['import_id']}/commit", json=payload))
    mid, asset = preview["material"]["id"], preview["assets"][0]
    attach(teacher, "s2", mid)
    q = question("shared-figure-q"); q.pop("teacher_internal")
    q["images"] = [{"url": asset["url"], "label": "Shared", "alt": "Synthetic figure"}]
    expect(teacher.patch("/api/sessions/s2", json={"groups": [{"id": "core", "title": "Core", "kind": "core"}], "questions": [q]}))
    expect(teacher.patch("/api/sessions/s4", json={"status": "draft"}))
    old = publish(teacher)["id"]
    expect(student.get("/api/sessions/s2/workspace?version_id="+old))
    assert student.get(asset["url"]+"?version_id="+old).content.startswith(b"\x89PNG")
    expect(student.get(f"/api/materials/{mid}/download?version_id={old}"), 403)
    expect(student.get(f"/api/materials/{mid}/preview?version_id={old}"), 403)
    expect(teacher.delete(f"/api/sessions/s2/materials/{mid}"), 409)
    q["images"] = []
    expect(teacher.patch("/api/sessions/s2", json={"questions": [q]}))
    new = publish(teacher)["id"]
    expect(student.get(asset["url"]+"?version_id="+new), 403)
    assert student.get(asset["url"]+"?version_id="+old).status_code == 200
    expect(teacher.delete(f"/api/sessions/s2/materials/{mid}"))
    expect(teacher.delete(f"/api/sessions/s4/materials/{mid}"), 409)
    assert library(teacher)[mid]["session_ids"] == ["s4"]
    with app.state.database.connect() as conn:
        assert conn.execute("SELECT count(*) FROM material_courses WHERE material_id=?", (mid,)).fetchone()[0] == 1


def test_pdf_preview_no_sandbox_exact_mime_authenticated(teacher, student, app):
    data = payload_for("pdf")
    item = upload(teacher, "s4", "native.pdf", data)
    publish(teacher)
    for client in (teacher, student):
        response = client.get(item["preview_url"])
        assert response.status_code == 200 and response.content == data
        assert response.headers["content-type"] == "application/pdf"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["content-disposition"].startswith("inline")
        assert "sandbox" not in response.headers.get("content-security-policy", "")
    with TestClient(app) as anonymous:
        expect(anonymous.get(item["preview_url"]), 401)
    expect(teacher.patch(f"/api/sessions/s4/materials/{item['id']}", json={"title": "Title without extension"}))
    assert teacher.get(item["download_url"]).headers["content-type"] == "application/pdf"
    expect(teacher.delete(f"/api/sessions/s4/materials/{item['id']}"))
    assert teacher.get(item["preview_url"]).status_code == 200


def test_image_upload_is_not_worksheet_format(teacher):
    from PIL import Image
    out = io.BytesIO()
    Image.new("RGB", (16, 16), "white").save(out, format="PNG")
    item = upload(teacher, "s4", "synthetic.png", out.getvalue())
    assert item["preview_kind"] == "image" and item["extraction_report"]["schema_version"] == 1
    assert teacher.get(item["preview_url"]).headers["content-type"] == "image/png"
    expect(teacher.post("/api/sessions/s4/worksheet-import/preview", files={"file": ("synthetic.png", out.getvalue())}), 415)


def test_stage3_migration_preserves_all_rows_backfills_once_and_legacy_inserts(app, teacher, student, catalog):
    old = expect(student.get("/api/sessions/s4/workspace"))["version"]["id"]
    expect(student.post("/api/sessions/s4/answers/q1?version_id="+old, json={"answer": "Preserved synthetic learning"}))
    db = app.state.database
    with db.connect() as conn:
        conn.execute("INSERT INTO materials VALUES(?,?,?,?,1)", ("global-archive", "s4", json.dumps({"id": "global-archive", "title": "Archived file", "visibility": "student"}), None))
        conn.execute("INSERT INTO settings VALUES('synthetic-preserved','opaque-setting')")
        conn.execute("DROP TRIGGER material_library_insert")
        conn.execute("DROP TRIGGER material_membership_same_course")
        conn.execute("DROP TABLE session_materials")
        conn.execute("DROP TABLE material_courses")
        conn.execute("DELETE FROM meta WHERE key='stage4_material_library'")
        conn.execute("PRAGMA user_version=3")
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        before = {t: [tuple(r) for r in conn.execute(f'SELECT * FROM "{t}" ORDER BY rowid')] for t in tables}
        schema = {r[0]: r[1] for r in conn.execute("SELECT name,sql FROM sqlite_master WHERE type IN ('table','trigger')")}
    for _ in range(3):
        db.initialize(catalog, True)
    with db.connect() as conn:
        after = {t: [tuple(r) for r in conn.execute(f'SELECT * FROM "{t}" ORDER BY rowid')] for t in tables}
        # Only the additive migration marker is new in an original table.
        after['meta'] = [r for r in after['meta'] if r[0] != 'stage4_material_library']
        assert after == before
        for name, sql in schema.items():
            assert conn.execute("SELECT sql FROM sqlite_master WHERE name=?", (name,)).fetchone()[0] == sql
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 9
        assert conn.execute("SELECT count(*) FROM session_materials").fetchone()[0] == 4
        assert not conn.execute("SELECT 1 FROM session_materials WHERE material_id='global-archive'").fetchone()
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        conn.execute("INSERT INTO materials VALUES(?,?,?,?,0)", ("legacy-insert", "s2", json.dumps({"id": "legacy-insert", "title": "Legacy positional caller", "visibility": "student"}), None))
        assert conn.execute("SELECT course_id FROM material_courses WHERE material_id='legacy-insert'").fetchone()[0] == CID
        assert conn.execute("SELECT session_id FROM session_materials WHERE material_id='legacy-insert'").fetchone()[0] == "s2"
    assert 'global-archive' not in library(teacher)
    expect(teacher.get("/api/materials/global-archive/preview"), 404)
    expect(teacher.delete("/api/sessions/s2/materials/legacy-insert"))
    expect(teacher.delete("/api/sessions/s4/materials/s4-public"))
    db.initialize(catalog, True)
    assert 'legacy-insert' not in mids(teacher, 's2') and 's4-public' not in mids(teacher, 's4')
    assert library(teacher)['legacy-insert']['session_ids'] == []
    assert expect(student.get("/api/sessions/s4/workspace?version_id="+old))["attempts"]["q1"]["answer"] == "Preserved synthetic learning"


def test_membership_database_cross_course_constraint(app, teacher):
    other = expect(teacher.post("/api/courses", json={"title": "Constraint course", "code": "CHECK"}))["id"]
    sid = new_session(teacher, other)
    with app.state.database.connect() as conn:
        with pytest.raises(sqlite3.IntegrityError, match="same course|in its course"):
            conn.execute("INSERT INTO session_materials VALUES(?,?)", (sid, "s4-public"))
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()


def test_material_migration_failure_rolls_back_additions_and_keeps_original_rows(app, teacher):
    with app.state.database.connect() as conn:
        conn.execute("DROP TRIGGER material_library_insert")
        conn.execute("DROP TRIGGER material_membership_same_course")
        conn.execute("DROP TABLE session_materials")
        conn.execute("DROP TABLE material_courses")
        conn.execute("DELETE FROM meta WHERE key='stage4_material_library'")
    # Deliberately invalid data belongs only to this synthetic failure fixture.
    conn = sqlite3.connect(app.state.database.path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("INSERT INTO materials VALUES('orphan-original','absent-session','{}',NULL,0)")
        conn.commit()
        original = [tuple(r) for r in conn.execute("SELECT * FROM materials ORDER BY rowid")]
        with pytest.raises(sqlite3.IntegrityError, match="in its course"):
            migrate_material_library(conn)
        assert [tuple(r) for r in conn.execute("SELECT * FROM materials ORDER BY rowid")] == original
        assert not conn.execute("SELECT 1 FROM meta WHERE key='stage4_material_library'").fetchone()
        assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name IN ('material_courses','session_materials','material_library_insert','material_membership_same_course')").fetchone()
    finally:
        conn.close()


def test_archived_enrollment_keeps_only_saved_session_membership_history(app, teacher, student):
    item = upload(teacher, "s4", "archived-history.txt")
    unseen = upload(teacher, "s4", "unseen-history.txt")
    attach(teacher, "s2", item["id"])
    old = publish(teacher)["id"]
    expect(student.get("/api/sessions/s2/workspace?version_id="+old))
    expect(teacher.post(f"/api/teacher/courses/{CID}/students/archive", json={"user_ids": ["demo-student-1"]}))
    assert student.get(item["download_url"]+"?version_id="+old).status_code == 200
    expect(student.get(unseen["download_url"]+"?version_id="+old), 403)
    assert "Only your existing learning history" in student.get(unseen["preview_url"]+"?version_id="+old).text
    expect(student.get(LIBRARY), 403)
    with app.state.database.connect() as conn:
        conn.execute("UPDATE enrollments SET purge_at='2000-01-01T00:00:00+00:00' WHERE user_id='demo-student-1'")
    expect(student.get(item["download_url"]+"?version_id="+old), 410)


def test_reprocess_does_not_overwrite_material_restored_during_extraction(app, teacher, monkeypatch):
    from backend.aicademiya import materials
    item = upload(teacher, "s4", "race-original.txt")
    original_extract = materials.extract_document
    with app.state.database.connect() as conn:
        original = conn.execute("SELECT file_path FROM materials WHERE id=?", (item["id"],)).fetchone()[0]
    replacement = Path(original).with_name("synthetic-restored-original.txt")
    replacement.write_text("Synthetic alternate restored edition", encoding="utf-8")
    def extraction_with_restore(path):
        result = original_extract(path)
        with app.state.database.connect() as conn:
            conn.execute("UPDATE materials SET file_path=? WHERE id=?", (str(replacement), item["id"]))
        return result
    monkeypatch.setattr(materials, "extract_document", extraction_with_restore)
    expect(teacher.post(f"/api/sessions/s4/materials/{item['id']}/reprocess"), 409)
    assert teacher.get(item["download_url"]).content == b"Synthetic alternate restored edition"
    assert library(teacher)[item["id"]]["excerpt"] == item["excerpt"]


def test_backup_relocation_preserves_membership_unassigned_historic_and_http(app, teacher, student, catalog, tmp_path):
    item = upload(teacher, "s4", "backup-shared.txt")
    attach(teacher, "s2", item["id"])
    preview = expect(teacher.post("/api/sessions/s4/worksheet-import/preview", files={"file": ("shared-backup-figure.docx", worksheet_docx())}))
    payload = {k: preview["draft"][k] for k in ("groups", "questions", "reference_answers")}
    payload["mode"] = "replace"
    expect(teacher.post(f"/api/sessions/s4/worksheet-import/{preview['import_id']}/commit", json=payload))
    worksheet_id, asset_url = preview["material"]["id"], preview["assets"][0]["url"]
    attach(teacher, "s2", worksheet_id)
    q = question("backup-figure-q"); q.pop("teacher_internal")
    q["images"] = [{"url": asset_url, "label": "Shared backup figure"}]
    expect(teacher.patch("/api/sessions/s2", json={"groups": [{"id": "core", "title": "Core", "kind": "core"}], "questions": [q]}))
    old = publish(teacher)["id"]
    expect(student.get("/api/sessions/s2/workspace?version_id="+old))
    retained = upload(teacher, "s4", "backup-retained.txt")
    expect(teacher.delete(f"/api/sessions/s4/materials/{retained['id']}"))
    expect(teacher.delete(f"/api/sessions/s4/materials/{item['id']}"))
    publish(teacher)
    source = app.state.database.path.parent
    saved = tmp_path / "stage4-backup"
    restored = tmp_path / "stage4-restored"
    result = backup_data.backup(source, saved, catalog.parent / "materials")
    assert result["integrity"] == "ok"
    outcome = backup_data.restore(saved, restored)
    assert outcome["records_match"] and outcome["files_match"] and outcome["integrity"] == "ok"
    hidden_source = source.with_name(source.name+"-unavailable")
    hidden_materials = catalog.parent / "materials-unavailable"
    source.rename(hidden_source)
    (catalog.parent / "materials").rename(hidden_materials)
    try:
        restored_app = create_app(data_dir=restored, catalog_path=catalog, demo_enabled=True, frontend_dir=tmp_path / "none")
        with demo_client(restored_app, "teacher") as owner, demo_client(restored_app) as learner:
            entries = library(owner)
            assert entries[item["id"]]["session_ids"] == ["s2"]
            assert entries[retained["id"]]["session_ids"] == []
            assert entries[worksheet_id]["session_ids"] == ["s4", "s2"]
            assert owner.get(retained["download_url"]).content == b"Synthetic backup-retained.txt"
            assert learner.get(item["download_url"]+"?version_id="+old).content == b"Synthetic backup-shared.txt"
            assert learner.get(asset_url+"?version_id="+old).content.startswith(b"\x89PNG")
            expect(learner.get(f"/api/materials/{worksheet_id}/download?version_id={old}"), 403)
            with restored_app.state.database.connect() as conn:
                for row in conn.execute("SELECT file_path FROM materials WHERE file_path IS NOT NULL"):
                    assert Path(row[0]).resolve().is_relative_to(restored.resolve()) and Path(row[0]).is_file()
                raw = json.loads(conn.execute("SELECT content_json FROM materials WHERE id=?", (worksheet_id,)).fetchone()[0])
                assert Path(raw["assets_dir"]).resolve().is_relative_to(restored.resolve())
                assert not conn.execute("PRAGMA foreign_key_check").fetchall()
                assert conn.execute("PRAGMA user_version").fetchone()[0] == 9
    finally:
        hidden_source.rename(source)
        hidden_materials.rename(catalog.parent / "materials")
