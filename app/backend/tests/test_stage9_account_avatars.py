"""Synthetic image/account acceptance; no private images or external services."""
import hashlib
import io
import struct
import zlib

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, PngImagePlugin

from backend.aicademiya.account_avatars import MAX_UPLOAD_BYTES, MAX_PIXELS, MAX_PNG_BYTES
from backend.aicademiya.db import public_user
from .conftest import demo_client, expect
from .test_auth_change import forced_student, TEMP_PASSWORD, NEW_PASSWORD


def image_bytes(fmt="PNG", color="green", size=(600, 300), metadata=False):
    image = Image.new("RGB", size, color)
    output = io.BytesIO()
    kwargs = {}
    if metadata and fmt == "PNG":
        info = PngImagePlugin.PngInfo()
        info.add_text("private", "DO_NOT_RETAIN_RAW_METADATA")
        kwargs["pnginfo"] = info
    if metadata and fmt in ("JPEG", "WEBP"):
        exif = Image.Exif()
        exif[270] = "DO_NOT_RETAIN_RAW_METADATA"
        kwargs["exif"] = exif
    image.save(output, format=fmt, **kwargs)
    return output.getvalue()


def upload(client, content=None, filename="photo.png", mime="image/png"):
    return client.post("/api/auth/avatar", files={"file": (filename, content if content is not None else image_bytes(), mime)})


def image_row(app, uid="demo-student-1"):
    with app.state.database.connect() as conn:
        row = conn.execute("SELECT * FROM account_avatars WHERE user_id=?", (uid,)).fetchone()
        return dict(row) if row else None


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
def test_static_formats_pixel_only_blob_and_exact_me_readback(student, app, fmt):
    before = expect(student.get("/api/auth/me"))["user"]
    assert before["avatar_url"] is None
    with app.state.database.connect() as conn:
        users_before = [tuple(r) for r in conn.execute("SELECT * FROM users ORDER BY id")]
        sessions_before = [tuple(r) for r in conn.execute("SELECT * FROM auth_sessions ORDER BY token_hash")]
    source = image_bytes(fmt, metadata=True)
    saved = expect(upload(student, source, "../../untrusted.svg", "application/octet-stream"))["user"]
    assert {k: v for k, v in saved.items() if k != "avatar_url"} == {k: v for k, v in before.items() if k != "avatar_url"}
    assert expect(student.get("/api/auth/me"))["user"] == saved
    row = image_row(app)
    assert isinstance(row["content"], bytes) and len(row["content"]) <= MAX_PNG_BYTES
    assert row["sha256"] == hashlib.sha256(row["content"]).hexdigest()
    assert saved["avatar_url"] == f'/api/users/{saved["id"]}/avatar?v={row["sha256"]}'
    response = student.get(saved["avatar_url"])
    assert response.status_code == 200 and response.content == row["content"]
    assert response.headers["content-type"] == "image/png"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "private, no-cache"
    assert response.headers["etag"] == f'"{row["sha256"]}"'
    with Image.open(io.BytesIO(response.content)) as normalized:
        assert normalized.format == "PNG" and normalized.size == (256, 256)
        assert not normalized.info and not normalized.getexif()
    assert b"DO_NOT_RETAIN_RAW_METADATA" not in row["content"]
    assert source != row["content"]
    assert not list((app.state.database.path.parent / "uploads").iterdir())
    with app.state.database.connect() as conn:
        assert [tuple(r) for r in conn.execute("SELECT * FROM users ORDER BY id")] == users_before
        assert [tuple(r) for r in conn.execute("SELECT * FROM auth_sessions ORDER BY token_hash")] == sessions_before
        assert "avatar_url" not in public_user(conn.execute("SELECT * FROM users WHERE id=?", (saved["id"],)).fetchone())


def test_exif_orientation_before_centered_square(student):
    image = Image.new("RGB", (600, 300), "red")
    draw = ImageDraw.Draw(image)
    draw.rectangle((150, 0, 449, 149), fill="green")
    draw.rectangle((150, 150, 449, 299), fill="blue")
    output = io.BytesIO()
    exif = Image.Exif(); exif[274] = 6
    image.save(output, "JPEG", exif=exif, quality=100)
    url = expect(upload(student, output.getvalue()))["user"]["avatar_url"]
    with Image.open(io.BytesIO(student.get(url).content)) as result:
        left, right = result.getpixel((32, 128)), result.getpixel((224, 128))
        assert left[2] > 200 and left[0] < 10  # Rotated blue lower half now left.
        assert right[1] > 100 and right[0] < 10
        assert not result.getexif()


def png_header(width, height):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"")) + chunk(b"IEND", b"")


def animated(fmt):
    output = io.BytesIO()
    frames = [Image.new("RGB", (32, 32), color) for color in ("red", "blue")]
    frames[0].save(output, fmt, save_all=True, append_images=frames[1:], duration=100, loop=0)
    return output.getvalue()


@pytest.mark.parametrize("content,status", [
    (b"", 422), (b"not an image", 422), (b'<svg xmlns="http://www.w3.org/2000/svg"/>', 422),
    (image_bytes("GIF"), 422), (image_bytes("BMP"), 422), (image_bytes("TIFF"), 422),
    (animated("PNG"), 422), (animated("WEBP"), 422), (animated("GIF"), 422),
    (image_bytes()[:60], 422), (b"x" * (MAX_UPLOAD_BYTES + 1), 413),
    (png_header(4000, 4001), 413), (png_header(100000, 100000), 413),
], ids=["empty", "text", "svg", "gif", "bmp", "tiff", "apng", "animated-webp", "animated-gif",
        "truncated", "over-5MiB", "over-16M-pixels", "decompression-bomb"])
def test_invalid_upload_does_not_replace_saved_image(student, app, content, status):
    old = expect(upload(student))["user"]
    before = image_row(app)
    expect(upload(student, content), status)
    assert image_row(app) == before
    assert expect(student.get("/api/auth/me"))["user"] == old
    assert student.get(old["avatar_url"]).content == before["content"]


def test_inclusive_upload_and_pixel_limits(student):
    exact = image_bytes(size=(4000, 4000))
    assert 4000 * 4000 == MAX_PIXELS
    url = expect(upload(student, exact))["user"]["avatar_url"]
    assert student.get(url).status_code == 200
    # PNG trailing padding is not retained; the bounded input accepts exactly5MiB.
    content = image_bytes()
    assert len(content) < MAX_UPLOAD_BYTES
    exact = content + b"\0" * (MAX_UPLOAD_BYTES - len(content))
    expect(upload(student, exact))
    expect(upload(student, exact + b"\0"), 413)


def test_replace_remove_idempotency_signed_in_access_and_read_only(student, teacher, admin, app):
    uid = expect(student.get("/api/auth/me"))["user"]["id"]
    old = expect(upload(student))["user"]["avatar_url"]
    for reader in (teacher, admin):
        assert reader.get(old).status_code == 200
    with TestClient(app) as anonymous:
        expect(anonymous.get(old), 401)
        expect(upload(anonymous), 401)
        expect(anonymous.delete("/api/auth/avatar"), 401)
    expect(student.get(f"/api/users/{uid}/avatar"), 404)
    expect(student.get(f"/api/users/{uid}/avatar?v=wrong"), 404)
    expect(student.get("/api/users/missing/avatar?v=wrong"), 404)
    with app.state.database.connect() as conn:
        before = {t: [tuple(r) for r in conn.execute(f'SELECT * FROM "{t}" ORDER BY rowid')]
                  for t, in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for _ in range(3):
        assert student.get(old, headers={"If-None-Match": student.get(old).headers["etag"]}).status_code == 200
    with app.state.database.connect() as conn:
        assert {t: [tuple(r) for r in conn.execute(f'SELECT * FROM "{t}" ORDER BY rowid')] for t in before} == before
    new = expect(upload(student, image_bytes(color="blue")))["user"]["avatar_url"]
    assert new != old
    expect(student.get(old), 404)
    assert student.get(new).status_code == 200
    own_teacher = expect(upload(teacher, image_bytes(color="red")))["user"]["avatar_url"]
    assert own_teacher != new and student.get(new).status_code == 200
    for _ in range(2):
        removed = expect(student.delete("/api/auth/avatar"))["user"]
        assert removed["avatar_url"] is None
        assert expect(student.get("/api/auth/me"))["user"] == removed
        expect(student.get(new), 404)
    assert teacher.get(own_teacher).status_code == 200 and image_row(app) is None


def test_archived_target_and_archived_or_forced_viewer(student, teacher, app):
    url = expect(upload(student))["user"]["avatar_url"]
    with app.state.database.connect() as conn:
        conn.execute("UPDATE users SET archived_at='2099-01-01T00:00:00+00:00' WHERE id='demo-student-1'")
    expect(teacher.get(url), 404)
    expect(student.get(url), 401)
    expect(upload(student), 401)
    expect(student.delete("/api/auth/avatar"), 401)
    with app.state.database.connect() as conn:
        conn.execute("UPDATE users SET archived_at=NULL,must_change_password=1 WHERE id='demo-student-1'")
    assert expect(student.get("/api/auth/me"))["user"]["avatar_url"] == url
    expect(student.get(url), 403)
    expect(upload(student), 403)
    expect(student.delete("/api/auth/avatar"), 403)
    assert teacher.get(url).status_code == 200


def test_real_register_login_profile_password_projections_remain_exact(teacher, app):
    course = expect(teacher.get("/api/courses"))[0]
    with TestClient(app) as client:
        created = expect(client.post("/api/auth/register", json={"name": "Synthetic avatar learner", "email": "avatar@example.invalid",
                       "password": TEMP_PASSWORD, "join_code": course["join_code"]}))["user"]
        assert created["avatar_url"] is None
        saved = expect(upload(client))["user"]
        assert expect(client.post("/api/auth/login", json={"email": created["email"], "password": TEMP_PASSWORD}))["user"] == saved
        renamed = expect(client.patch("/api/auth/profile", json={"name": "New synthetic name"}))["user"]
        assert renamed["avatar_url"] == saved["avatar_url"]
        changed = expect(client.post("/api/auth/change-password", json={"current_password": TEMP_PASSWORD, "new_password": NEW_PASSWORD}))["user"]
        assert changed == renamed == expect(client.get("/api/auth/me"))["user"]
        assert expect(client.post("/api/auth/login", json={"email": created["email"], "password": NEW_PASSWORD}))["user"] == changed
        assert client.get(saved["avatar_url"]).status_code == 200
    with demo_client(app) as demo:
        url = expect(upload(demo))["user"]["avatar_url"]
        assert expect(demo.post("/api/auth/demo", json={"role": "student"}))["user"]["avatar_url"] == url


def test_forced_password_avatar_gate(forced_student):
    expect(upload(forced_student), 403)
    expect(forced_student.delete("/api/auth/avatar"), 403)
    expect(forced_student.get("/api/users/demo-teacher/avatar?v=none"), 403)
    assert expect(forced_student.get("/api/auth/me"))["user"]["avatar_url"] is None


def test_normalized_output_bound_is_enforced(student, monkeypatch):
    monkeypatch.setattr("backend.aicademiya.account_avatars.MAX_PNG_BYTES", 1)
    expect(upload(student), 413)
    assert expect(student.get("/api/auth/me"))["user"]["avatar_url"] is None


def test_multipart_or_query_identity_cannot_replace_another_account(student, teacher, app):
    target = expect(upload(teacher, image_bytes(color="red")))["user"]
    before = image_row(app, target["id"])
    result = expect(student.post("/api/auth/avatar?user_id=" + target["id"],
                    data={"user_id": target["id"], "avatar_url": "http://127.0.0.1/private"},
                    files={"file": ("../../target.png", image_bytes(color="blue"), "image/png")}))["user"]
    assert result["id"] == "demo-student-1" and result["avatar_url"] != target["avatar_url"]
    assert image_row(app, target["id"]) == before
    assert expect(student.get("/api/auth/me"))["user"] == result
    assert teacher.get(target["avatar_url"]).content == before["content"]
