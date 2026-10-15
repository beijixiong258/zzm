"""Signed-in profile images: decode static input and retain only normalized PNG."""
import hashlib
import io
import warnings
from urllib.parse import quote

from fastapi import Depends, File, HTTPException, Response, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from .db import now, public_user

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 16_000_000
MAX_PNG_BYTES = 512 * 1024
AVATAR_SIZE = (256, 256)


def avatar_url(conn, uid):
    row = conn.execute("""SELECT a.sha256 FROM account_avatars a JOIN users u ON u.id=a.user_id
        WHERE a.user_id=? AND u.archived_at IS NULL""", (uid,)).fetchone()
    return f"/api/users/{quote(uid, safe='')}/avatar?v={row[0]}" if row else None


def normalize_avatar(content):
    if not content:
        raise HTTPException(422, "Choose a static PNG, JPEG or WebP image")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Avatar must be at most 5 MiB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                if image.format not in ("PNG", "JPEG", "WEBP") or getattr(image, "n_frames", 1) != 1:
                    raise HTTPException(422, "Only static PNG, JPEG and WebP images are supported")
                if image.width * image.height > MAX_PIXELS:
                    raise HTTPException(413, "Avatar must contain at most 16 million pixels")
                image.load()
                oriented = ImageOps.exif_transpose(image)
                square = ImageOps.fit(oriented.convert("RGBA"), AVATAR_SIZE,
                                      method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
                # A fresh pixel-only image cannot inherit EXIF/ICC/text metadata.
                normalized = Image.frombytes("RGBA", AVATAR_SIZE, square.tobytes())
                output = io.BytesIO()
                normalized.save(output, format="PNG", optimize=True)
                result = output.getvalue()
    except (Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise HTTPException(413, "Avatar must contain at most 16 million pixels") from None
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        raise HTTPException(422, "Image could not be decoded; choose a static PNG, JPEG or WebP") from None
    if len(result) > MAX_PNG_BYTES:
        raise HTTPException(413, "Normalized avatar exceeds 512 KiB")
    return result


def register_account_avatar_routes(app, db, current_user):
    @app.post("/api/auth/avatar")
    async def upload_avatar(file: UploadFile = File(...), user=Depends(current_user)):
        try:
            content = await file.read(MAX_UPLOAD_BYTES + 1)
        finally:
            await file.close()
        normalized = normalize_avatar(content)
        digest = hashlib.sha256(normalized).hexdigest()
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("""INSERT INTO account_avatars(user_id,content,sha256,updated_at) VALUES(?,?,?,?)
                ON CONFLICT(user_id) DO UPDATE SET content=excluded.content,
                sha256=excluded.sha256,updated_at=excluded.updated_at""",
                         (user["id"], normalized, digest, now()))
            row = conn.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
            return {"user": public_user(row, conn)}

    @app.delete("/api/auth/avatar")
    def remove_avatar(user=Depends(current_user)):
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM account_avatars WHERE user_id=?", (user["id"],))
            row = conn.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
            return {"user": public_user(row, conn)}

    @app.get("/api/users/{user_id}/avatar")
    def get_avatar(user_id: str, v: str | None = None, user=Depends(current_user)):
        with db.connect() as conn:
            row = conn.execute("""SELECT a.content,a.sha256 FROM account_avatars a
                JOIN users u ON u.id=a.user_id WHERE a.user_id=? AND u.archived_at IS NULL
                AND a.sha256=?""", (user_id, v)).fetchone()
            if not row:
                raise HTTPException(404, "Avatar not found")
            return Response(content=bytes(row["content"]), media_type="image/png", headers={
                "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-cache",
                "ETag": f'"{row["sha256"]}"',
            })
