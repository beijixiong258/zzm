"""Synthetic catalog, isolated databases, and cookie-aware independent clients."""
import json
from contextlib import contextmanager
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from backend.aicademiya.main import create_app


def question(qid, group="core", ordinal=1):
    return {"id": qid, "group_id": group, "ordinal": ordinal, "type": "open_response",
            "prompt": f"Synthetic teaching question {qid}: explain with evidence.", "options": [],
            "answer_slots": 1, "images": [], "source_label": f"Synthetic worksheet {qid}",
            "hint": "Identify the concept, then give an example.", "teacher_internal": "DO_NOT_LEAK_NESTED"}


def session(sid, questions, groups=None):
    return {"id": sid, "course_id": "synthetic-course", "number": 4 if sid == "s4" else 2,
            "title": "Synthetic learning fixture", "subtitle": "Explicit test content, not real course data",
            "status": "published", "estimated_minutes": 40, "learning_objectives": ["Explain with evidence"],
            "instructions": "Give concise formative hints.", "reference_policy": "after_attempt", "teaching_language": "en",
            "groups": groups or [{"id": "core", "title": "Core", "kind": "core"}], "questions": questions,
            "reference_answers": {q["id"]: "TEACHER_REFERENCE_ONLY_" + q["id"] for q in questions},
            "materials": [
                {"id": sid + "-public", "title": "Student reading", "kind": "reading", "visibility": "student",
                 "source_label": "Synthetic student reading", "status": "ready", "excerpt": "Conceptual evidence available to students.", "file_path": "materials/reading.txt"},
                {"id": sid + "-private", "title": "Teacher key", "kind": "answer_key", "visibility": "teacher",
                 "source_label": "Private synthetic key", "status": "ready", "excerpt": "TEACHER_MATERIAL_DO_NOT_LEAK", "file_path": "materials/key.txt"},
            ], "research_notes": ["TEACHER_RESEARCH_DO_NOT_LEAK"]}


@pytest.fixture
def catalog(tmp_path):
    seed = tmp_path / "sample_data"
    (seed / "materials").mkdir(parents=True)
    (seed / "assets").mkdir()
    (seed / "materials" / "reading.txt").write_text("Synthetic reading", encoding="utf-8")
    (seed / "materials" / "key.txt").write_text("Private synthetic key", encoding="utf-8")
    (seed / "assets" / "plot.png").write_bytes(b"\x89PNG\r\n\x1a\nSynthetic fixture")
    s4 = session("s4", [question(f"q{i}", ordinal=i) for i in range(1, 23)])
    s4["questions"][0]["images"] = [{"label": "A", "url": "/api/assets/plot.png", "alt": "Scatter plot A", "secret": "IMAGE_METADATA_DO_NOT_LEAK"}]
    groups = [{"id": "I", "title": "Core", "kind": "core"}, {"id": "II-Pong", "title": "Pong", "kind": "reading"}, {"id": "II-Bray", "title": "Bray", "kind": "reading"}]
    questions = [question(f"core{i}", "I", i) for i in range(1, 10)]
    questions += [question(f"pong{i}", "II-Pong", i) for i in range(1, 6)]
    questions += [question(f"bray{i}", "II-Bray", i) for i in range(1, 6)]
    content = {"schema_version": 1, "course": {"id": "synthetic-course", "code": "TEST", "title": "Explicit synthetic test course", "description": "No real student data"}, "sessions": [s4, session("s2", questions, groups)]}
    path = seed / "catalog.json"
    path.write_text(json.dumps(content), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def no_live_search_environment(monkeypatch):
    monkeypatch.setenv("AICADEMIYA_WEB_SEARCH_ENABLED", "false")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)


@pytest.fixture
def app(tmp_path, catalog, monkeypatch):
    monkeypatch.setenv("AICADEMIYA_AI_MODE", "demo")
    monkeypatch.delenv("AICADEMIYA_AI_API_KEY", raising=False)
    return create_app(data_dir=tmp_path / "data", catalog_path=catalog, demo_enabled=True, frontend_dir=tmp_path / "dist")


@contextmanager
def demo_client(app, role="student", index=1):
    with TestClient(app) as client:
        response = client.post("/api/auth/demo", json={"role": role, "student_index": index})
        assert response.status_code == 200, response.text
        yield client


@pytest.fixture
def student(app):
    with demo_client(app) as client:
        yield client


@pytest.fixture
def teacher(app):
    with demo_client(app, "teacher") as client:
        yield client


@pytest.fixture
def admin(app):
    with demo_client(app, "admin") as client:
        yield client


def admin_request(client, method, url, **kwargs):
    """Configure protocol fixtures via the independent synthetic administrator."""
    with demo_client(client.app, "admin") as admin:
        return admin.request(method, url, **kwargs)


def publish(client, cid="synthetic-course"):
    return expect(client.post(f"/api/teacher/courses/{cid}/versions/publish", json={}))


def expect(response, status=200):
    assert response.status_code == status, response.text
    return response.json()
