"""Synthetic own/admin feedback API boundaries, validation and concurrent writes."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from .conftest import demo_client, expect
from .test_auth_change import forced_student


ITEM_KEYS = {"id", "request_id", "category", "subject", "message", "status", "reply", "created_at", "updated_at", "revision", "author"}


def create(client, request_id="synthetic-request", **changes):
    return client.post("/api/feedback", json={"request_id": request_id, "category": "general",
                      "subject": "Synthetic subject", "message": "Synthetic message", **changes})


def patch(client, fid, revision=1, **changes):
    return client.patch("/api/admin/feedback/" + fid, json={"status": "reviewed", "reply": "Human synthetic reply",
                       "expected_revision": revision, **changes})


@pytest.mark.parametrize("role", ["student", "teacher", "admin"])
def test_all_roles_create_own_history_exact_requests_and_detail(app, role):
    with demo_client(app, role) as client:
        user = expect(client.get("/api/auth/me"))["user"]
        item = expect(create(client, subject='  <script>alert("literal")</script>  ', message="  First line\n\n  内部原文 & <b>text</b>  "))
        assert set(item) == ITEM_KEYS
        assert item["subject"] == '<script>alert("literal")</script>'
        assert item["message"] == "First line\n\n  内部原文 & <b>text</b>"
        assert item["status"] == "new" and item["reply"] == "" and item["revision"] == 1
        assert item["created_at"] == item["updated_at"]
        assert datetime.fromisoformat(item["created_at"]).utcoffset().total_seconds() == 0
        assert item["author"] == {k: user[k] for k in ("id", "name", "email", "role")}
        assert expect(client.get("/api/feedback/" + item["id"])) == item
        assert expect(client.get("/api/feedback/requests/" + item["request_id"])) == item
        assert expect(client.get("/api/feedback")) == {"items": [item], "total": 1, "offset": 0, "limit": 25}
        expect(client.get("/api/feedback/requests/not-saved"), 404)
        expect(client.get("/api/feedback/not-saved"), 404)
        if role == "admin":
            assert expect(client.get("/api/admin/feedback/" + item["id"])) == item


@pytest.mark.parametrize("override", [
    {"request_id": ""}, {"request_id": "x" * 81}, {"request_id": "with space"}, {"request_id": "ß"},
    {"request_id": "a\n"}, {"request_id": " slash/"}, {"request_id": "a.b"}, {"request_id": "a?b"},
    {"request_id": None}, {"request_id": True}, {"request_id": 1},
    {"category": "other"}, {"category": None}, {"category": "Bug"},
    {"subject": ""}, {"subject": " \n\t"}, {"subject": "x" * 161}, {"subject": " " * 160 + "a"},
    {"subject": None}, {"subject": False}, {"subject": 12},
    {"message": ""}, {"message": " \n\t"}, {"message": "x" * 6001}, {"message": " " * 6000 + "a"},
    {"message": None}, {"message": []},
    {"status": "reviewed"}, {"reply": "spoof"}, {"author": {"id": "demo-admin"}},
    {"author_id": "demo-admin"}, {"email": "spoof@example.invalid"}, {"role": "admin"},
    {"revision": 99}, {"created_at": "2026-01-01"}, {"id": "spoof"}, {"unknown": "ignored?"},
])
def test_create_invalid_payloads_and_spoofed_identity_rejected(student, app, override):
    expect(create(student, **override), 422)
    with app.state.database.connect() as conn:
        assert conn.execute("SELECT count(*) FROM feedback").fetchone()[0] == 0


@pytest.mark.parametrize("subject,message,request_id", [("a", "a", "a"), ("s" * 160, "m" * 6000, "A_0-" * 20)])
def test_create_inclusive_limits(student, subject, message, request_id):
    item = expect(create(student, request_id, subject=subject, message=message))
    assert item["subject"] == subject and item["message"] == message and item["request_id"] == request_id


def test_durable_request_identity_normalization_collision_and_per_account_scope(student, teacher, admin, app):
    item = expect(create(student, category="bug", subject="  A  subject  ", message="  A\n message  "))
    assert expect(create(student, category="bug", subject="A  subject", message="A\n message")) == item
    other = expect(create(teacher))
    assert other["id"] != item["id"] and other["request_id"] == item["request_id"]
    for change in ({"category": "idea"}, {"subject": "A subject"}, {"message": "A message"}):
        expect(create(student, **{"category": "bug", "subject": "A  subject", "message": "A\n message", **change}), 409)
    updated = expect(patch(admin, item["id"]))
    # POST retry returns the saved current human review, never resets it.
    assert expect(create(student, category="bug", subject="A  subject", message="A\n message")) == updated
    assert expect(student.get("/api/feedback/requests/" + item["request_id"])) == updated
    with app.state.database.connect() as conn:
        assert conn.execute("SELECT count(*) FROM feedback").fetchone()[0] == 2


def test_own_cross_identity_hidden_admin_inbox_separate(student, teacher, admin, app):
    mine, theirs = expect(create(student)), expect(create(teacher))
    for reader, hidden in ((student, theirs), (teacher, mine), (admin, mine)):
        expect(reader.get("/api/feedback/" + hidden["id"]), 404)
    for reader in (student, teacher):
        expect(reader.get("/api/admin/feedback"), 403)
        expect(reader.get("/api/admin/feedback/" + mine["id"]), 403)
        expect(patch(reader, mine["id"]), 403)
    assert expect(admin.get("/api/feedback"))["total"] == 0
    expect(admin.get("/api/feedback/requests/" + mine["request_id"]), 404)
    assert expect(admin.get("/api/admin/feedback"))["total"] == 2
    assert expect(admin.get("/api/admin/feedback/" + mine["id"])) == mine
    expect(admin.get("/api/admin/feedback/absent"), 404)
    expect(patch(admin, "absent"), 404)
    # No user editing/deleting or administrator public deletion endpoints.
    for path in ("/api/feedback/" + mine["id"], "/api/admin/feedback/" + mine["id"]):
        expect(admin.delete(path), 405)
    expect(student.patch("/api/feedback/" + mine["id"], json={"message": "rewrite"}), 405)
    assert expect(student.get("/api/feedback/" + mine["id"])) == mine


@pytest.mark.parametrize("query", ["offset=-1", "offset=1.5", "offset=no", "limit=0", "limit=101", "limit=-1", "limit=abc",
                                   "category=other", "category=BUG", "status=done", "status=Reviewed"])
@pytest.mark.parametrize("is_admin", [False, True])
def test_pagination_filters_validation(student, admin, is_admin, query):
    client = admin if is_admin else student
    expect(client.get(("/api/admin/feedback?" if is_admin else "/api/feedback?") + query), 422)


def test_real_total_stable_order_large_history_and_combined_filters(student, teacher, admin, app):
    created = []
    for i in range(107):
        created.append(expect(create(student, f"page_{i:03d}", category=("bug" if i % 2 == 0 else "idea"))))
    other = expect(create(teacher, "page_000", category="bug"))
    for item in created[::4]:
        expect(patch(admin, item["id"]))
    # Force timestamp ties to exercise secondary ID order, not insertion order.
    with app.state.database.connect() as conn:
        conn.execute("UPDATE feedback SET created_at='2026-01-01T00:00:00+00:00'")
        own_ids = [r[0] for r in conn.execute("SELECT id FROM feedback WHERE author_id='demo-student-1' ORDER BY created_at DESC,id DESC")]
    all_items = []
    for offset in (0, 25, 50, 75, 100):
        page = expect(student.get(f"/api/feedback?offset={offset}&limit=25"))
        assert page["total"] == 107 and page["offset"] == offset and page["limit"] == 25
        all_items.extend(page["items"])
    assert [item["id"] for item in all_items] == own_ids
    assert len({item["id"] for item in all_items}) == 107
    assert expect(student.get("/api/feedback?limit=100"))["items"] == all_items[:100]
    empty = expect(student.get("/api/feedback?offset=999&limit=1"))
    assert empty == {"items": [], "total": 107, "offset": 999, "limit": 1}
    for category in (None, "bug", "idea", "general"):
        for status in (None, "new", "reviewed"):
            filtered = [item for item in all_items if (category is None or item["category"] == category)
                        and (status is None or item["status"] == status)]
            query = "offset=2&limit=7" + (f"&category={category}" if category else "") + (f"&status={status}" if status else "")
            page = expect(student.get("/api/feedback?" + query))
            assert page == {"items": filtered[2:9], "total": len(filtered), "offset": 2, "limit": 7}
            inbox = expect(admin.get("/api/admin/feedback?" + query))
            extra = int((category is None or category == "bug") and (status is None or status == "new"))
            assert inbox["total"] == len(filtered) + extra
            assert len(inbox["items"]) == min(7, max(0, inbox["total"] - 2))
    assert expect(admin.get("/api/feedback"))["total"] == 0


@pytest.mark.parametrize("override", [
    {"expected_revision": True}, {"expected_revision": False}, {"expected_revision": "1"},
    {"expected_revision": 1.0}, {"expected_revision": 0}, {"expected_revision": -1}, {"expected_revision": None},
    {"reply": "x" * 6001}, {"reply": " " * 6000 + "a"}, {"reply": None}, {"reply": True},
    {"status": "resolved"}, {"status": None}, {"status": "Reviewed"},
    {"author_id": "demo-admin"}, {"category": "idea"}, {"subject": "rewrite"}, {"message": "rewrite"},
    {"request_id": "rewrite"}, {"revision": 9}, {"author": None},
])
def test_admin_update_validation_immutable_author_and_no_side_effects(student, admin, override):
    item = expect(create(student))
    expect(admin.patch("/api/admin/feedback/" + item["id"], json={"status": "reviewed", "reply": "Human synthetic reply",
                       "expected_revision": 1, **override}), 422)
    assert expect(student.get("/api/feedback/" + item["id"])) == item


@pytest.mark.parametrize("missing", ["status", "reply", "expected_revision"])
def test_admin_update_requires_complete_dto(student, admin, missing):
    item = expect(create(student))
    payload = {"status": "new", "reply": "", "expected_revision": 1}; payload.pop(missing)
    expect(admin.patch("/api/admin/feedback/" + item["id"], json=payload), 422)


def test_human_reply_trim_revision_stale_reject_and_exact_utc(student, admin):
    initial = expect(create(student))
    reply = '  <script>literal</script>\n  human & "reply"  '
    before = datetime.now(timezone.utc)
    reviewed = expect(patch(admin, initial["id"], reply=reply))
    after = datetime.now(timezone.utc)
    assert reviewed["revision"] == 2 and reviewed["status"] == "reviewed"
    assert reviewed["reply"] == '<script>literal</script>\n  human & "reply"'
    assert before <= datetime.fromisoformat(reviewed["updated_at"]) <= after
    for key in ("id", "request_id", "category", "subject", "message", "created_at", "author"):
        assert reviewed[key] == initial[key]
    assert expect(admin.get("/api/admin/feedback/" + initial["id"])) == reviewed
    assert expect(student.get("/api/feedback/" + initial["id"])) == reviewed
    expect(patch(admin, initial["id"], reply="stale human draft"), 409)
    assert expect(student.get("/api/feedback/requests/" + initial["request_id"])) == reviewed
    maximum = expect(patch(admin, initial["id"], revision=2, status="new", reply="r" * 6000))
    assert maximum["revision"] == 3 and len(maximum["reply"]) == 6000
    cleared = expect(patch(admin, initial["id"], revision=3, reply=" \n "))
    assert cleared["reply"] == "" and cleared["revision"] == 4
    repeated = expect(patch(admin, initial["id"], revision=4, reply=""))
    assert repeated["revision"] == 5


def test_concurrent_same_request_single_item_and_revision_single_winner(student, admin, app):
    barrier = Barrier(4)
    def submit(_):
        barrier.wait(timeout=10)
        return create(student)
    with ThreadPoolExecutor(max_workers=4) as pool:
        saved = [expect(response) for response in pool.map(submit, range(4))]
    assert all(item == saved[0] for item in saved)
    fid = saved[0]["id"]
    barrier = Barrier(4)
    def review(i):
        barrier.wait(timeout=10)
        return patch(admin, fid, reply=f"human-{i}")
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(review, range(4)))
    assert sorted(r.status_code for r in responses) == [200, 409, 409, 409]
    winner = next(r.json() for r in responses if r.status_code == 200)
    assert winner["revision"] == 2 and expect(student.get("/api/feedback/" + fid)) == winner
    with app.state.database.connect() as conn:
        assert conn.execute("SELECT count(*) FROM feedback").fetchone()[0] == 1


def test_author_current_server_details_and_archived_projection(student, admin, app):
    item = expect(create(student))
    expect(student.patch("/api/auth/profile", json={"name": "Changed server-derived name"}))
    current = expect(admin.get("/api/admin/feedback/" + item["id"]))
    assert current["author"]["name"] == "Changed server-derived name"
    with app.state.database.connect() as conn:
        conn.execute("UPDATE users SET archived_at='2026-01-01T00:00:00+00:00',purge_at='2099-01-01T00:00:00+00:00' WHERE id='demo-student-1'")
    assert expect(admin.get("/api/admin/feedback/" + item["id"]))["author"] is None
    expect(create(student), 401)
    expect(student.get("/api/feedback"), 401)
    with app.state.database.connect() as conn:
        conn.execute("UPDATE users SET archived_at=NULL,purge_at=NULL WHERE id='demo-student-1'")
    assert expect(student.get("/api/feedback/" + item["id"])) == current


def test_concurrent_conflicting_payload_request_has_one_winner(student, app):
    barrier = Barrier(2)
    def submit(i):
        barrier.wait(timeout=10)
        return create(student, "same-conflicting-id", subject=f"distinct-{i}")
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(submit, range(2)))
    assert sorted(r.status_code for r in responses) == [200, 409]
    winner = next(r.json() for r in responses if r.status_code == 200)
    assert expect(student.get("/api/feedback/requests/same-conflicting-id")) == winner
    with app.state.database.connect() as conn:
        assert conn.execute("SELECT count(*) FROM feedback").fetchone()[0] == 1


def test_anonymous_and_must_change_password_routes_have_no_side_effects(app, student, forced_student):
    item = expect(create(student))
    requests = [("POST", "/api/feedback", {"json": {"request_id": "new", "subject": "s", "message": "m", "category": "bug"}}),
                ("GET", "/api/feedback", {}), ("GET", "/api/feedback/" + item["id"], {}),
                ("GET", "/api/feedback/requests/" + item["request_id"], {}),
                ("GET", "/api/admin/feedback", {}), ("GET", "/api/admin/feedback/" + item["id"], {}),
                ("PATCH", "/api/admin/feedback/" + item["id"], {"json": {"status": "reviewed", "reply": "reply", "expected_revision": 1}})]
    with TestClient(app) as anonymous:
        for method, url, kwargs in requests:
            expect(anonymous.request(method, url, **kwargs), 401)
            expect(forced_student.request(method, url, **kwargs), 403)
    assert expect(student.get("/api/feedback"))["total"] == 1
