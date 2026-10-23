"""Eight independent synthetic learners and an actual bounded uvicorn process."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import httpx
from fastapi.testclient import TestClient
from .conftest import expect


def test_eight_concurrent_students_keep_independent_workspaces(app, teacher):
    invite = expect(teacher.get("/api/courses"))[0]["join_code"]

    def learner(index):
        # The teacher fixture owns lifespan; these clients only carry distinct cookies.
        client = TestClient(app)
        try:
            identity = expect(client.post("/api/auth/register", json={"name": f"Synthetic concurrency learner {index}", "email": f"concurrent-{index}@example.invalid", "password": "synthetic-concurrency-fixture1", "join_code": invite}))["user"]
            message = f"Independent synthetic response number {index}"
            work = expect(client.post("/api/sessions/s4/chat", json={"message": message, "question_id": "q1", "intent": "answer", "request_id": "shared-request-id"}))
            assert work["attempts"]["q1"]["answer"] == message
            assert len(work["messages"]) == 2
            reloaded = expect(client.get("/api/sessions/s4/workspace"))
            assert reloaded["user"]["id"] == identity["id"]
            assert reloaded["attempts"]["q1"]["answer"] == message
            return identity["id"], message
        finally:
            client.close()

    with ThreadPoolExecutor(max_workers=8) as workers:
        results = list(workers.map(learner, range(8)))
    assert len({uid for uid, _ in results}) == 8
    for uid, message in results:
        work = expect(teacher.get(f"/api/teacher/sessions/s4/students/{uid}/workspace"))
        assert work["attempts"]["q1"]["answer"] == message
    assert len(expect(teacher.get("/api/teacher/sessions/s4/students"))) == 10


def test_module_launch_with_actual_uvicorn_and_isolated_data_dir(tmp_path):
    root = Path(__file__).resolve().parents[2]
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env = dict(os.environ, AICADEMIYA_DATA_DIR=str(tmp_path / "uvicorn-data"), AICADEMIYA_DEMO_ENABLED="false", AICADEMIYA_AI_MODE="openai")
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.aicademiya.main:app", "--host", "127.0.0.1", "--port", str(port)], cwd=root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    reached = False
    try:
        deadline = time.monotonic() + 15
        with httpx.Client(timeout=1, trust_env=False) as client:
            while time.monotonic() < deadline and process.poll() is None:
                try:
                    health = client.get(f"http://127.0.0.1:{port}/api/health")
                    if health.status_code == 200:
                        assert health.json() == {"status": "ok"}
                        bootstrap = client.get(f"http://127.0.0.1:{port}/api/bootstrap").json()
                        assert bootstrap["app_name"] == "AIcademiya" and not bootstrap["demo_enabled"]
                        assert client.post(f"http://127.0.0.1:{port}/api/auth/demo", json={"role": "teacher"}).status_code == 403
                        reached = True
                        break
                except httpx.RequestError:
                    pass
                time.sleep(0.1)
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            _, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            _, stderr = process.communicate(timeout=10)
    assert reached, stderr.decode(errors="replace")
    assert (tmp_path / "uvicorn-data" / "aicademiya.sqlite3").is_file()
