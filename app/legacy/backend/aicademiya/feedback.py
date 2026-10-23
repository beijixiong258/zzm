"""Own feedback and administrator human review, with durable retry identity."""
import re
from typing import Literal

from fastapi import Depends, HTTPException, Query
from pydantic import Field, StrictInt, field_validator

from .db import new_id, now
from .models import Payload
from .course_staff import live_actor

FeedbackCategory = Literal["bug", "idea", "general"]
FeedbackStatus = Literal["new", "reviewed"]


class FeedbackCreate(Payload):
    request_id: str = Field(min_length=1, max_length=80)
    category: FeedbackCategory
    subject: str = Field(min_length=1, max_length=160)
    message: str = Field(min_length=1, max_length=6000)

    @field_validator("request_id")
    @classmethod
    def safe_request_id(cls, value):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", value, flags=re.ASCII):
            raise ValueError("Use only ASCII letters, digits, underscores and hyphens for request_id")
        return value

    @field_validator("subject", "message")
    @classmethod
    def nonblank_text(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Subject and message must not be blank")
        return value


class FeedbackUpdate(Payload):
    status: FeedbackStatus
    reply: str = Field(max_length=6000)
    expected_revision: StrictInt = Field(ge=1)

    @field_validator("reply")
    @classmethod
    def trim_reply(cls, value):
        return value.strip()


FEEDBACK_SELECT = """SELECT f.*,u.id AS user_id,u.name AS user_name,u.email AS user_email,u.role AS user_role
    FROM feedback f LEFT JOIN users u ON u.id=f.author_id AND u.archived_at IS NULL"""
ITEM_FIELDS = ("id", "request_id", "category", "subject", "message", "status", "reply",
               "created_at", "updated_at", "revision")


def feedback_item(row):
    author = {"id": row["user_id"], "name": row["user_name"], "email": row["user_email"],
              "role": row["user_role"]} if row["user_id"] is not None else None
    return {**{key: row[key] for key in ITEM_FIELDS}, "author": author}


def get_item(conn, fid, uid=None):
    where, args = "f.id=?", [fid]
    if uid is not None:
        where += " AND f.author_id=?"
        args.append(uid)
    row = conn.execute(FEEDBACK_SELECT + " WHERE " + where, args).fetchone()
    if not row:
        raise HTTPException(404, "Feedback not found")
    return feedback_item(row)


def feedback_page(conn, offset, limit, category, status, uid=None, actor=None):
    clauses, args = [], []
    for column, value in (("author_id", uid), ("category", category), ("status", status)):
        if value is not None:
            clauses.append(f"f.{column}=?")
            args.append(value)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    # One read snapshot keeps filtered count and returned page mutually consistent.
    conn.execute("BEGIN")
    if actor is not None:
        live_actor(conn, actor, admin=uid is None)
    total = conn.execute("SELECT count(*) FROM feedback f" + where, args).fetchone()[0]
    rows = conn.execute(FEEDBACK_SELECT + where + " ORDER BY f.created_at DESC,f.id DESC LIMIT ? OFFSET ?",
                        [*args, limit, offset]).fetchall()
    return {"items": [feedback_item(row) for row in rows], "total": total, "offset": offset, "limit": limit}


def register_feedback_routes(app, db, current_user, admin_user):
    @app.post("/api/feedback")
    def create_feedback(payload: FeedbackCreate, user=Depends(current_user)):
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            old = conn.execute("SELECT * FROM feedback WHERE author_id=? AND request_id=?",
                               (user["id"], payload.request_id)).fetchone()
            if old:
                if any(old[key] != getattr(payload, key) for key in ("category", "subject", "message")):
                    raise HTTPException(409, "request_id was already used for different feedback")
                return get_item(conn, old["id"])
            fid, stamp = new_id(), now()
            conn.execute("""INSERT INTO feedback(id,author_id,request_id,category,subject,message,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?)""", (fid, user["id"], payload.request_id, payload.category,
                                           payload.subject, payload.message, stamp, stamp))
            return get_item(conn, fid)

    @app.get("/api/feedback")
    def own_feedback(offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100),
                     category: FeedbackCategory | None = None, status: FeedbackStatus | None = None,
                     user=Depends(current_user)):
        with db.connect() as conn:
            return feedback_page(conn, offset, limit, category, status, user["id"], actor=user)

    # The literal request lookup must precede the dynamic item route.
    @app.get("/api/feedback/requests/{request_id}")
    def by_request(request_id: str, user=Depends(current_user)):
        with db.connect() as conn:
            row = conn.execute("SELECT id FROM feedback WHERE author_id=? AND request_id=?",
                               (user["id"], request_id)).fetchone()
            if not row:
                raise HTTPException(404, "Feedback not found")
            return get_item(conn, row[0], user["id"])

    @app.get("/api/feedback/{feedback_id}")
    def own_item(feedback_id: str, user=Depends(current_user)):
        with db.connect() as conn:
            return get_item(conn, feedback_id, user["id"])

    @app.get("/api/admin/feedback")
    def inbox(offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100),
              category: FeedbackCategory | None = None, status: FeedbackStatus | None = None,
              user=Depends(admin_user)):
        with db.connect() as conn:
            return feedback_page(conn, offset, limit, category, status, actor=user)

    @app.get("/api/admin/feedback/{feedback_id}")
    def admin_item(feedback_id: str, user=Depends(admin_user)):
        with db.connect() as conn:
            conn.execute('BEGIN')
            live_actor(conn, user, admin=True)
            return get_item(conn, feedback_id)

    @app.patch("/api/admin/feedback/{feedback_id}")
    def review(feedback_id: str, payload: FeedbackUpdate, user=Depends(admin_user)):
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            live_actor(conn, user, admin=True)
            item = get_item(conn, feedback_id)
            if item["revision"] != payload.expected_revision:
                raise HTTPException(409, "Feedback changed; reload it before saving your reply")
            conn.execute("""UPDATE feedback SET status=?,reply=?,revision=revision+1,updated_at=?
                WHERE id=? AND revision=?""", (payload.status, payload.reply, now(), feedback_id,
                                             payload.expected_revision))
            return get_item(conn, feedback_id)
