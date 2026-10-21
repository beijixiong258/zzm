"""Isolated course-library, protected figures and Chinese import regressions."""
import base64
import io
import json
import sqlite3
import pytest
from fastapi import HTTPException
from backend.aicademiya.db import SCHEMA
from backend.aicademiya.material_library import migrate_material_library, migrate_material_origin
from backend.aicademiya.roster import parse_rows
from .conftest import expect, publish, question
from .test_stage2_authoring import public_link_fixture


def test_empty_course_library_upload_edit_attach_and_publication(teacher, student, admin, app):
    course = expect(teacher.post("/api/courses", json={"title": "Synthetic empty course", "code": "EMPTY"}))
    cid = course["id"]
    url = f"/api/courses/{cid}/materials"
    assert expect(teacher.get(f"/api/courses/{cid}/sessions")) == []
    item = expect(teacher.post(url, data={"relative_path": "目录/章节/讲义.txt"}, files={"file": ("讲义.txt", "合成资料".encode())}))
    assert item["source_relative_path"] == "目录/章节/讲义.txt"
    assert expect(teacher.get(url))["materials"][0]["session_ids"] == []
    with app.state.database.connect() as conn:
        assert conn.execute("SELECT session_id FROM materials WHERE id=?", (item["id"],)).fetchone()[0] is None
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
    expect(student.get(url), 403)
    expect(admin.patch(url + "/" + item["id"], json={"title": "unauthorized"}), 403)
    expect(student.post(url, files={"file": ("no.txt", b"no")}), 403)
    sid = expect(teacher.post(f"/api/courses/{cid}/sessions", json={"title": "Synthetic session"}))["id"]
    expect(teacher.post(f"/api/sessions/{sid}/materials/attach", json={"material_id": item["id"]}))
    expect(teacher.patch(f"/api/sessions/{sid}", json={"status": "published"}))
    old = publish(teacher, cid)["id"]
    before = expect(teacher.get(f"/api/teacher/courses/{cid}/versions/{old}"))
    expect(teacher.patch(url + "/" + item["id"], json={"title": "Edited in library"}))
    assert expect(teacher.get(f"/api/sessions/{sid}"))["materials"][0]["title"] == "Edited in library"
    assert expect(teacher.get(f"/api/teacher/courses/{cid}/versions/{old}")) == before
    expect(teacher.delete(url + "/" + item["id"]), 409)
    expect(teacher.delete(f"/api/sessions/{sid}/materials/{item['id']}"))
    expect(teacher.delete(url + "/" + item["id"]))
    assert expect(teacher.get(url))["materials"] == []
    assert expect(teacher.get(f"/api/teacher/courses/{cid}/versions/{old}")) == before


def test_course_link_and_private_material_guards(teacher, public_link_fixture):
    url = "/api/courses/synthetic-course/materials"
    item = expect(teacher.post(url + "/link", json={"url": "https://example.org/synthetic", "title": "Course source"}))
    assert next(m for m in expect(teacher.get(url))["materials"] if m["id"] == item["id"])["session_ids"] == []
    expect(teacher.patch(url + "/" + item["id"], json={"title": "Renamed source"}))
    private = expect(teacher.post(url, files={"file": ("key.txt", b"synthetic answer")}, data={"kind": "answer_key", "visibility": "teacher"}))
    expect(teacher.patch(url + "/" + private["id"], json={"visibility": "student"}), 422)
    for bad in ("../escape.txt", "C:/local.txt", "/absolute.txt"):
        expect(teacher.post(url, files={"file": ("a.txt", b"x")}, data={"relative_path": bad}), 422)


def test_protected_uploaded_image_is_versioned_and_cannot_be_hidden(teacher, student):
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aH9sAAAAASUVORK5CYII=")
    item = expect(teacher.post("/api/sessions/s4/materials", files={"file": ("synthetic.png", png)}, data={"kind": "reference"}))
    q = question("image-match"); q.pop("teacher_internal")
    q.update(type="image_matching", images=[{"url": item["preview_url"], "label": "A", "alt": "Synthetic image"}], options=["First", "Second"])
    expect(teacher.patch("/api/sessions/s4", json={"questions": [q], "reference_answers": {}}))
    expect(teacher.delete(f"/api/sessions/s4/materials/{item['id']}"), 409)
    expect(teacher.patch(f"/api/courses/synthetic-course/materials/{item['id']}", json={"visibility": "teacher"}), 422)
    version = publish(teacher)["id"]
    image = expect(student.get(f"/api/sessions/s4?version_id={version}"))["questions"][0]["images"][0]
    assert "version_id=" in image["url"]
    response = student.get(image["url"])
    assert response.status_code == 200 and response.content == png
    hidden = expect(teacher.post("/api/sessions/s4/materials", files={"file": ("private.png", png)}, data={"visibility": "teacher"}))
    q["images"][0]["url"] = hidden["preview_url"]
    expect(teacher.patch("/api/sessions/s4", json={"questions": [q]}), 422)


@pytest.mark.parametrize("encoding", ["utf-8-sig", "gb18030"])
def test_chinese_csv_headers_and_encoding(encoding):
    rows = parse_rows("姓名,电子邮箱,临时密码\n合成学生,student@example.invalid,Abcd1234\n".encode(encoding), ".csv")
    assert rows == [(2, {"name": "合成学生", "email": "student@example.invalid", "temporary_password": "Abcd1234"})]


def test_chinese_xlsx_and_duplicate_aliases():
    from openpyxl import Workbook
    book = Workbook(); book.active.append(["姓名", "邮箱", "角色"])
    book.active.append(["合成教师", "teacher@example.invalid", "teacher"])
    out = io.BytesIO(); book.save(out); book.close()
    assert parse_rows(out.getvalue(), ".xlsx", global_accounts=True)[0][1]["role"] == "teacher"
    with pytest.raises(HTTPException):
        parse_rows("姓名,name,邮箱\n甲,乙,a@example.invalid".encode(), ".csv")


def test_legacy_material_origin_migration_preserves_references_and_detached_files():
    conn = sqlite3.connect(":memory:"); conn.row_factory = sqlite3.Row
    legacy = SCHEMA.replace("session_id TEXT REFERENCES sessions(id), content_json", "session_id TEXT NOT NULL REFERENCES sessions(id), content_json")
    conn.executescript(legacy)
    conn.execute("INSERT INTO courses VALUES('c','C','Course','',NULL,'JOIN')")
    conn.execute("INSERT INTO sessions VALUES('s','c','{}')")
    conn.execute("INSERT INTO materials VALUES('m','s','{}',NULL,0)")
    migrate_material_library(conn)
    conn.execute("DELETE FROM session_materials")
    conn.commit()
    migrate_material_origin(conn); migrate_material_library(conn); migrate_material_origin(conn)
    assert conn.execute("SELECT id,session_id FROM materials").fetchone()[:] == ('m','s')
    assert conn.execute("SELECT * FROM material_courses").fetchone()[:] == ('m','c')
    assert not conn.execute("SELECT * FROM session_materials").fetchall()
    conn.execute("INSERT INTO materials VALUES('new',NULL,'{}',NULL,0)")
    conn.execute("INSERT INTO material_courses VALUES('new','c')")
    assert not conn.execute("PRAGMA foreign_key_check").fetchall()
    conn.close()


def test_chinese_teaching_defaults_follow_content_language(teacher):
    item = expect(teacher.post("/api/courses/synthetic-course/sessions", json={"title": "合成课次", "teaching_language": "zh-CN"}))
    assert item["teaching_language"] == "zh-CN"
    assert item["groups"][0]["title"] == "核心任务"
    assert item["teaching_profile"]["tone"] == "耐心、具体、尊重学生，避免过度表扬。"
