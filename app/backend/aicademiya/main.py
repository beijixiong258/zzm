"""AIcademiya API. Run from app root: python -m uvicorn backend.aicademiya.main:app."""
from contextlib import asynccontextmanager
import asyncio
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import secrets
import sqlite3
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import models as m
from .access_control import registration_enabled, require_registration, register_access_settings_routes
from .auth import PasswordVerifier, RateLimiter, session_user
from .course_staff import AuthenticatedUser, live_actor, establish_assignment, register_staff_routes
from .global_accounts import change_role, register_global_account_routes
from .config import SecurityConfig
from .deployment_config import DEFAULTS
from .http_security import HttpSecurityMiddleware
from .version_context import is_staff, published_detail
from .roster import maintenance, register_roster_routes
from .course_lifecycle import register_course_lifecycle_routes
from .account_avatars import register_account_avatar_routes
from .feedback import register_feedback_routes
from .authoring import register_authoring_routes, resolve_material
from .ai import ModelFailure, Tutor
from .web_search import SearchFailure
from .service_settings import (
    MODEL_CHECK_OK, MODEL_CHECK_ERROR, SEARCH_CHECK_OK, SEARCH_CHECK_ERROR, SEARCH_TEST_QUERY,
    check_snapshot, effective_search_settings, fingerprint, put_value, record_check, search_projection, update_search_settings,
)
from .db import Database, issue_session, new_id, now, password_hash, password_matches, public_user
from .materials import MAX_UPLOAD_BYTES, SUPPORTED
from .document_bundle import FULL_FORMATS, MAX_FULL_UPLOAD_BYTES
from .material_library import member_material, detach_material
from .services import (
    active_question, active_questions, course_access, editable, ensure_teacher, ensure_workspace,
    mark_active, public_course, public_detail, public_material, reading_groups, save_answer,
    save_message, session_access, student_access, summary, workspace_response,
)

APP_ROOT = Path(__file__).resolve().parents[2]
COOKIE_NAME = "aicademiya_session"


def create_app(*, data_dir=None, db_path=None, catalog_path=None, upload_dir=None, demo_enabled=None,
               frontend_dir=None, ai_transport=None, document_worker_command=None,
               document_processor=None, document_worker_timeout=None):
    data_root = Path(data_dir or os.getenv("AICADEMIYA_DATA_DIR", str(APP_ROOT / "data-v2"))).resolve()
    database = Database(db_path or data_root / "aicademiya.sqlite3")
    catalog = Path(catalog_path or os.getenv("AICADEMIYA_CATALOG_PATH", str(APP_ROOT / "sample_data" / "catalog.json"))).resolve()
    uploads = Path(upload_dir or os.getenv("AICADEMIYA_UPLOAD_DIR", str(data_root / "uploads"))).resolve()
    frontend = Path(frontend_dir or os.getenv("AICADEMIYA_FRONTEND_DIR", str(APP_ROOT / "frontend" / "dist"))).resolve()
    demo = demo_enabled if demo_enabled is not None else os.getenv("AICADEMIYA_DEMO_ENABLED", "").lower() in ("1", "true", "yes")
    tutor = Tutor(database, transport=ai_transport, demo_enabled=demo)
    security = SecurityConfig.from_environment()
    limiter = RateLimiter()
    verifier = PasswordVerifier()
    from .document_jobs import DocumentQueue
    document_queue = DocumentQueue(database, uploads, command=document_worker_command,
                                   processor=document_processor, timeout=document_worker_timeout)

    @asynccontextmanager
    async def lifespan(application):
        database.initialize(catalog, demo)
        uploads.mkdir(parents=True, exist_ok=True)
        document_queue.start()
        # A crash must not leave an idempotent chat retry permanently pending.
        with database.connect() as conn:
            conn.execute("UPDATE chat_requests SET status='failed' WHERE status='pending'")
            conn.execute("UPDATE tutor_requests SET status='failed' WHERE status='pending'")
        def maintain():
            with database.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                maintenance(conn)
        maintain()
        async def periodic():
            while True:
                await asyncio.sleep(60)
                await asyncio.to_thread(maintain)
        task = asyncio.create_task(periodic())
        try:
            yield
        finally:
            await asyncio.to_thread(document_queue.close)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    application = FastAPI(title="AIcademiya", version="0.11.0", lifespan=lifespan)
    application.state.database = database
    application.state.tutor = tutor
    application.state.demo_enabled = demo
    application.state.catalog_path = catalog
    application.state.document_queue = document_queue
    application.state.security_limiter = limiter
    application.add_middleware(HttpSecurityMiddleware, config=security, limiter=limiter)

    @application.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Never return pydantic 'input' values: login/settings payloads contain secrets.
        if (request.url.path.startswith(('/api/auth/', '/api/admin/users'))
                or request.url.path == '/api/admin/access-settings'
                or (request.url.path.startswith('/api/teacher/courses/') and request.url.path.endswith('/students'))):
            return JSONResponse(status_code=422, content={"detail": "Invalid request; check the required fields and values"})
        errors = [".".join(str(p) for p in err["loc"]) + ": " + err["msg"] for err in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": "; ".join(errors)})

    @application.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc.detail)}, headers=exc.headers)

    @application.exception_handler(sqlite3.IntegrityError)
    async def integrity_error(request, exc):
        return JSONResponse(status_code=409, content={"detail": "This record already exists or conflicts with related data"})

    @application.exception_handler(Exception)
    async def unexpected_error(request, exc):
        # Preserve the contract and never expose private paths, document content,
        # provider details, or credentials in unexpected error responses.
        return JSONResponse(status_code=500, content={"detail": "An internal error occurred; your previously saved work is retained"},
                            headers={"X-Content-Type-Options": "nosniff", "X-Frame-Options": "SAMEORIGIN",
                                     "Content-Security-Policy": "frame-ancestors 'self'", "Referrer-Policy": "same-origin",
                                     "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
                                     "Cache-Control": "private, no-store"})

    def authenticated_user(request: Request):
        with database.connect() as conn:
            row = session_user(conn, request.cookies.get(COOKIE_NAME), demo_enabled=demo)
            return AuthenticatedUser(public_user(row, conn), hashlib.sha256(request.cookies[COOKIE_NAME].encode()).hexdigest())

    def current_user(user=Depends(authenticated_user)):
        if user["must_change_password"]:
            raise HTTPException(403, "Password change required")
        return user

    def teacher_user(user=Depends(current_user)):
        ensure_teacher(user)
        return user

    def admin_user(user=Depends(current_user)):
        if user["role"] != "admin":
            raise HTTPException(403, "Administrator access required")
        return user

    register_roster_routes(application, database, teacher_user, admin_user)
    register_authoring_routes(application, database, tutor, uploads, teacher_user, current_user)
    register_course_lifecycle_routes(application, database, teacher_user)
    register_account_avatar_routes(application, database, current_user)
    register_feedback_routes(application, database, current_user, admin_user)
    register_access_settings_routes(application, database, admin_user, COOKIE_NAME, demo)
    register_staff_routes(application, database, current_user, admin_user)
    register_global_account_routes(application, database, admin_user, demo_enabled=demo)
    from .document_api import register_document_routes
    register_document_routes(application, database, document_queue, current_user, teacher_user)

    @application.patch("/api/auth/profile")
    def profile(payload: m.Profile, user=Depends(current_user)):
        with database.connect() as conn:
            conn.execute("UPDATE users SET name=? WHERE id=?", (payload.name, user["id"]))
            return {"user": public_user(conn.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone(), conn)}

    @application.get("/api/admin/teachers")
    def list_teachers(user=Depends(admin_user)):
        with database.connect() as conn:
            conn.execute('BEGIN')
            live_actor(conn, user, admin=True)
            return [public_user(r, conn) for r in conn.execute("SELECT * FROM users WHERE role='teacher' AND archived_at IS NULL ORDER BY name,id")]

    @application.post("/api/admin/teachers/{user_id}/promote")
    def promote_teacher(user_id: str, payload: m.Empty, user=Depends(admin_user)):
        with database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            live_actor(conn, user, admin=True)
            target = conn.execute("SELECT * FROM users WHERE id=? AND role='teacher' AND archived_at IS NULL", (user_id,)).fetchone()
            if not target:
                raise HTTPException(422, "Only an active teacher can be promoted")
            row = change_role(conn, user, user_id, 'admin', demo_enabled=demo)
            return {"user": public_user(row, conn)}

    def set_cookie(response, token, request):
        secure = security.secure_cookie(request)
        response.set_cookie(COOKIE_NAME, token, httponly=True, secure=secure, samesite="lax", max_age=30 * 24 * 60 * 60, path="/")

    def own_workspace(conn, detail, user):
        return workspace_response(conn, detail, user, tutor.status(conn, is_staff(user)), is_staff(user))

    def validate_account_identity(name, email):
        if not name.strip() or "@" not in email or " " in email:
            raise HTTPException(422, "Provide a name and valid email address")

    @application.get("/api/health")
    def health():
        return {"status": "ok"}

    @application.get("/api/bootstrap")
    def bootstrap():
        with database.connect() as conn:
            return {"app_name": "AIcademiya", "demo_enabled": demo, "default_locale": os.getenv("AICADEMIYA_UI_LOCALE", DEFAULTS["frontend"]["locale"]), "ai": tutor.status(conn),
                    "registration_enabled": registration_enabled(conn)}

    @application.post("/api/auth/demo")
    def demo_login(payload: m.DemoLogin, response: Response, request: Request):
        if not demo:
            raise HTTPException(403, "Demo authentication is disabled")
        uid = "demo-admin" if payload.role == "admin" else "demo-teacher" if payload.role == "teacher" else f"demo-student-{payload.student_index}"
        with database.connect() as conn:
            user = conn.execute("SELECT * FROM users WHERE id=? AND is_demo=1", (uid,)).fetchone()
            if not user or user["archived_at"]:
                raise HTTPException(401, "Demo account is archived or unavailable")
            token = issue_session(conn, uid)
            set_cookie(response, token, request)
            return {"user": public_user(user, conn)}

    @application.post("/api/auth/login")
    def login(payload: m.Login, response: Response, request: Request):
        limiter.check('login-account', payload.email.strip().lower(), 10, 300)
        with database.connect() as conn:
            # Serialize password verification/session issuance with password changes.
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM users WHERE email=? AND is_demo=0", (payload.email.strip().lower(),)).fetchone()
            if not verifier.matches(payload.password, row):
                raise HTTPException(401, "Email or password is incorrect")
            set_cookie(response, issue_session(conn, row["id"]), request)
            return {"user": public_user(row, conn)}

    @application.post("/api/auth/register")
    def register(payload: m.Register, response: Response, request: Request):
        validate_account_identity(payload.name, payload.email)
        with database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            require_registration(conn)
            course = conn.execute("SELECT * FROM courses c WHERE join_code=? AND NOT EXISTS (SELECT 1 FROM course_trash t WHERE t.course_id=c.id)", (payload.join_code.strip(),)).fetchone()
            if not course:
                raise HTTPException(404, "Invitation code not found")
            uid = new_id()
            conn.execute("INSERT INTO users(id,name,email,role,password_hash) VALUES(?,?,?,'student',?)", (uid, payload.name.strip(), payload.email.strip().lower(), password_hash(payload.password)))
            conn.execute("INSERT INTO enrollments(course_id,user_id) VALUES(?,?)", (course["id"], uid))
            set_cookie(response, issue_session(conn, uid), request)
            return {"user": public_user(conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone(), conn)}

    @application.get("/api/auth/me")
    def me(user=Depends(authenticated_user)):
        return {"user": user}

    @application.post("/api/auth/change-password")
    def change_password(payload: m.ChangePassword, response: Response, request: Request,
                        user=Depends(authenticated_user)):
        limiter.check('password-account', user['id'], 10, 300)
        with database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = session_user(conn, request.cookies.get(COOKIE_NAME), demo_enabled=demo)
            if row["is_demo"]:
                raise HTTPException(400, "Demo accounts cannot change passwords")
            if not password_matches(payload.current_password, row["password_hash"]):
                raise HTTPException(400, "Current password is incorrect")
            if payload.new_password == payload.current_password:
                raise HTTPException(400, "New password must differ from the current password")
            conn.execute("UPDATE users SET password_hash=?,must_change_password=0 WHERE id=?",
                         (password_hash(payload.new_password), user["id"]))
            conn.execute("DELETE FROM auth_sessions WHERE user_id=?", (user["id"],))
            set_cookie(response, issue_session(conn, user["id"]), request)
            return {"user": public_user(conn.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone(), conn)}

    @application.post("/api/auth/logout")
    def logout(request: Request, response: Response):
        token = request.cookies.get(COOKIE_NAME)
        if token:
            with database.connect() as conn:
                conn.execute("DELETE FROM auth_sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))
        response.delete_cookie(COOKIE_NAME, path="/", secure=security.secure_cookie(request), httponly=True, samesite="lax")
        return {"ok": True}

    @application.get("/api/courses")
    def courses(user=Depends(current_user)):
        with database.connect() as conn:
            conn.execute("BEGIN")
            live_actor(conn, user)
            if is_staff(user):
                rows = conn.execute("SELECT * FROM courses c WHERE EXISTS (SELECT 1 FROM course_staff cs WHERE cs.course_id=c.id AND cs.user_id=?) AND NOT EXISTS (SELECT 1 FROM course_trash t WHERE t.course_id=c.id) ORDER BY rowid", (user["id"],))
            else:
                rows = conn.execute("SELECT c.* FROM courses c JOIN enrollments e ON e.course_id=c.id WHERE e.user_id=? AND (e.purge_at IS NULL OR e.purge_at>?) AND NOT EXISTS (SELECT 1 FROM course_trash t WHERE t.course_id=c.id) ORDER BY c.rowid", (user["id"], now()))
            return [public_course(conn, row, is_staff(user)) for row in rows]

    @application.post("/api/courses")
    def create_course(payload: m.CourseCreate, user=Depends(teacher_user)):
        if not payload.title.strip() or not payload.code.strip():
            raise HTTPException(422, "Course title and code must not be blank")
        with database.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            live_actor(conn, user, staff=True)
            cid = new_id()
            conn.execute("INSERT INTO courses(id,code,title,description,owner_id,join_code) VALUES(?,?,?,?,?,?)", (cid, payload.code, payload.title, payload.description, user["id"], secrets.token_urlsafe(8)))
            establish_assignment(conn, cid, user['id'])
            return public_course(conn, conn.execute("SELECT * FROM courses WHERE id=?", (cid,)).fetchone(), True)

    @application.post("/api/courses/join")
    def join_course(payload: m.JoinCourse, user=Depends(current_user)):
        limiter.check('join-account', user['id'], 20, 300)
        if user["role"] != "student":
            raise HTTPException(403, "Only students join courses by invitation")
        with database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            actor = live_actor(conn, user)
            if actor['role'] != 'student':
                raise HTTPException(403, 'Only students join courses by invitation')
            row = conn.execute("SELECT * FROM courses c WHERE join_code=? AND NOT EXISTS (SELECT 1 FROM course_trash t WHERE t.course_id=c.id)", (payload.join_code.strip(),)).fetchone()
            if not row:
                raise HTTPException(404, "Invitation code not found")
            previous = conn.execute("SELECT archived_at FROM enrollments WHERE course_id=? AND user_id=?", (row["id"], user["id"])).fetchone()
            if previous and previous[0]:
                raise HTTPException(403, "Enrollment is archived; ask the course owner to restore it")
            conn.execute("INSERT OR IGNORE INTO enrollments(course_id,user_id) VALUES(?,?)", (row["id"], user["id"]))
            return public_course(conn, row)

    @application.post("/api/teacher/courses/{course_id}/students")
    def provision_student(course_id: str, payload: m.ProvisionStudent, user=Depends(teacher_user)):
        validate_account_identity(payload.name, payload.email)
        with database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            course_access(conn, course_id, user)
            existing = conn.execute('SELECT * FROM users WHERE email=?', (payload.email.strip().lower(),)).fetchone()
            if existing:
                if existing['role'] != 'student' or existing['archived_at']:
                    raise HTTPException(409, 'Email belongs to staff or a disabled account; no account was changed')
                uid = existing['id']
                relation = conn.execute('SELECT archived_at,purge_at FROM enrollments WHERE course_id=? AND user_id=?', (course_id, uid)).fetchone()
                if relation and relation['archived_at']:
                    from .roster import expired
                    if expired(relation['purge_at']):
                        raise HTTPException(410, 'Archived enrollment has expired')
                    raise HTTPException(409, 'Enrollment is archived; restore it explicitly through Course Students')
            else:
                try:
                    m.validate_new_password(payload.temporary_password or '')
                except ValueError:
                    raise HTTPException(422, 'New accounts require 8–512 characters including an ASCII letter and digit') from None
                uid = new_id()
                conn.execute("INSERT INTO users(id,name,email,role,password_hash,is_demo,must_change_password) VALUES(?,?,?,'student',?,0,1)",
                             (uid, payload.name.strip(), payload.email.strip().lower(), password_hash(payload.temporary_password)))
            conn.execute("INSERT OR IGNORE INTO enrollments(course_id,user_id) VALUES(?,?)", (course_id, uid))
            return {"user": public_user(conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone(), conn),
                    "course_id": course_id}

    @application.get("/api/courses/{course_id}/sessions")
    def sessions(course_id: str, version_id: str | None = None, user=Depends(current_user)):
        with database.connect() as conn:
            course_access(conn, course_id, user)
            result = []
            for row in conn.execute("SELECT * FROM sessions WHERE course_id=? ORDER BY rowid", (course_id,)):
                try:
                    detail = session_access(conn, row["id"], user, version_id)
                except HTTPException as exc:
                    if exc.status_code in (403, 404):
                        continue
                    raise
                state = conn.execute("SELECT status FROM workspaces WHERE session_id=? AND user_id=? AND version_id=?", (detail["id"], user["id"], detail["_version_id"])).fetchone()
                result.append(summary(detail, state[0] if state else "not_started"))
            return sorted(result, key=lambda item: item["number"])

    @application.post("/api/courses/{course_id}/sessions")
    def create_session(course_id: str, payload: m.SessionCreate, user=Depends(teacher_user)):
        with database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            course_access(conn, course_id, user)
            from .models import TeachingProfile
            values = payload.model_dump()
            values["teaching_profile"] = values.get("teaching_profile") or TeachingProfile().model_dump()
            detail = {"id": new_id(), "course_id": course_id, **values, "status": "draft", "estimated_minutes": 40,
                      "reference_policy": "after_attempt", "teaching_language": "en", "groups": [{"id": "core", "title": "Core tasks", "kind": "core"}],
                      "questions": [], "reference_answers": {}}
            conn.execute("INSERT INTO sessions(id,course_id,content_json) VALUES(?,?,?)", (detail["id"], course_id, json.dumps(detail)))
            return public_detail(conn, detail, True)

    @application.get("/api/sessions/{session_id}")
    def get_session(session_id: str, version_id: str | None = None, user=Depends(current_user)):
        with database.connect() as conn:
            detail = session_access(conn, session_id, user, version_id)
            state = conn.execute("SELECT status FROM workspaces WHERE session_id=? AND user_id=? AND version_id=?", (session_id, user["id"], detail["_version_id"])).fetchone()
            return public_detail(conn, detail, is_staff(user), state[0] if state else "not_started")

    @application.patch("/api/sessions/{session_id}")
    def patch_session(session_id: str, payload: m.SessionPatch, user=Depends(teacher_user)):
        with database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            from .authoring import apply_session_update
            return apply_session_update(conn, session_id, user, payload.model_dump(exclude_unset=True))

    from .learning_routes import register_learning_routes
    from .session_lifecycle import register_session_lifecycle
    register_session_lifecycle(application, database, teacher_user)
    from .model_connection import register_model_connection
    register_model_connection(application, database, tutor, current_user)
    register_learning_routes(application, database, tutor, current_user, teacher_user)
    from .guided_routes import register_guided_routes
    register_guided_routes(application, database, tutor, current_user, teacher_user)
    from .teacher_workbench_routes import register_teacher_workbench_routes
    register_teacher_workbench_routes(application, database, tutor, teacher_user)

    @application.post("/api/sessions/{session_id}/materials")
    def upload_material(session_id: str, file: UploadFile = File(...), visibility: str = Form("student"),
                        kind: str = Form("reading"), processing: str = Form("preview"), user=Depends(teacher_user)):
        if processing not in ("preview", "full_document"):
            raise HTTPException(422, "Invalid material processing mode")
        if visibility not in ("student", "teacher") or kind not in ("reading", "worksheet", "answer_key", "slides", "reference"):
            raise HTTPException(422, "Invalid material visibility or kind")
        if kind == "answer_key" and visibility != "teacher":
            raise HTTPException(422, "Answer keys must have teacher visibility")
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in SUPPORTED and not (processing == 'full_document' and suffix.lstrip('.') in FULL_FORMATS):
            raise HTTPException(415, "Supported formats: txt, md, pdf, docx, pptx, png, jpg, jpeg, webp")
        with database.connect() as conn:
            session_access(conn, session_id, user)
        if processing == "full_document":
            if suffix.lstrip('.') not in document_queue.formats:
                raise HTTPException(415, "This source format is not enabled for complete processing")
            if not document_queue.available:
                raise HTTPException(503, "Complete document processing is not configured")
        upload_limit = MAX_FULL_UPLOAD_BYTES if processing == 'full_document' else MAX_UPLOAD_BYTES
        data = file.file.read(upload_limit + 1)
        if len(data) > upload_limit:
            raise HTTPException(413, "Upload exceeds the 64 MiB complete-document limit" if processing == 'full_document' else "Upload exceeds the 25 MiB preview limit")
        mid = new_id()
        destination = uploads / (mid + suffix)
        destination.write_bytes(data)
        from .materials import extract_document
        extraction = extract_document(destination) if processing == "preview" else {
            "status": "processing", "excerpt": "", "warning": None, "extraction_report": None}
        filename = (file.filename or "Uploaded material").replace("\\", "/").split("/")[-1]
        item = {"id": mid, "title": filename, "kind": kind, "visibility": visibility,
                "source_label": filename, "extracted_at": now(),
                **{k: extraction[k] for k in ("status", "excerpt", "warning", "extraction_report")}}
        if processing == "full_document":
            item["processing"] = "full_document"
        with database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            session_access(conn, session_id, user)
            conn.execute("INSERT INTO materials VALUES(?,?,?,?,0)", (mid, session_id, json.dumps(item), str(destination)))
            if processing == "full_document":
                from .document_storage import enqueue_job
                enqueue_job(conn, mid, user, "upload:" + mid, None)
            result = public_material(conn.execute("SELECT * FROM materials WHERE id=?", (mid,)).fetchone(), True)
        document_queue.notify()
        return result

    @application.delete("/api/sessions/{session_id}/materials/{material_id}")
    def detach_session_material(session_id: str, material_id: str, user=Depends(teacher_user)):
        with database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            session_access(conn, session_id, user)
            row = member_material(conn, session_id, material_id)
            detail = session_access(conn, session_id, user)
            material_url = json.loads(row["content_json"]).get("url")
            if any(material_id in q.get("source_material_ids", []) or (material_url and material_url in q.get("source_links", [])) or any(image.get("url", "").startswith(f"/api/materials/{material_id}/assets/") for image in q.get("images", [])) for q in detail.get("questions", [])):
                raise HTTPException(409, "Material is referenced by current questions; remove those relationships first")
            detach_material(conn, session_id, material_id)
            return {"ok": True}

    @application.get("/api/materials/{material_id}/download")
    def download(material_id: str, version_id: str | None = None, user=Depends(current_user)):
        with database.connect() as conn:
            row, detail = resolve_material(conn, material_id, user, version_id)
            material = public_material(row, is_staff(user), detail.get("_version_id"))
            path = Path(row["file_path"]) if row["file_path"] else None
            if not path or not path.is_file():
                raise HTTPException(404, "Original material file is unavailable")
            return FileResponse(path, filename=material["title"],
                                media_type=mimetypes.guess_type(str(path))[0] or "application/octet-stream",
                                headers={"X-Content-Type-Options": "nosniff"})

    @application.get("/api/assets/{asset_path:path}")
    def asset(asset_path: str, version_id: str | None = None, user=Depends(current_user)):
        from .material_security import resolve_catalog_asset
        with database.connect() as conn:
            path = resolve_catalog_asset(conn, catalog.parent / "assets", asset_path, user, version_id)
        return FileResponse(path, headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})

    def teacher_settings_response(conn):
        return {"ai": tutor.status(conn, True), "api_key_set": bool(tutor.settings(conn)["api_key"])}

    @application.get("/api/teacher/settings")
    def get_settings(user=Depends(admin_user)):
        with database.connect() as conn:
            conn.execute('BEGIN')
            live_actor(conn, user, admin=True)
            return teacher_settings_response(conn)

    @application.put("/api/teacher/settings")
    def update_settings(payload: m.Settings, user=Depends(admin_user)):
        with database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            live_actor(conn, user, admin=True)
            tutor.update(conn, payload)
            return teacher_settings_response(conn)

    @application.post("/api/teacher/settings/test")
    def test_settings(user=Depends(admin_user)):
        with database.connect() as conn:
            conn.execute("BEGIN")
            live_actor(conn, user, admin=True)
            settings = tutor.settings(conn)
            snapshot = check_snapshot(conn, "ai", tutor.check_config(settings))
        if settings["mode"] == "demo":
            # Explicit isolated fixtures are not evidence of connectivity.
            with database.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                live_actor(conn, user, admin=True)
                if check_snapshot(conn, "ai", tutor.check_config(tutor.settings(conn))) != snapshot:
                    raise HTTPException(409, "Service settings changed during the connection check; test the saved settings again")
                connection = tutor.status(conn, True)["connection"]
            return {"ok": True, "message": "Demo preview is enabled; no model connectivity was tested.", "model": settings["model"], "mode": "demo", "connection": connection}
        try:
            scope_args = ({"kv_scope": tutor.kv_scope(user, "settings-test", "probe")}
                          if tutor.uses_aicademiya_router(settings) else {})
            tutor.complete(settings, [{"role": "user", "content": "Reply with OK only; this is an AIcademiya connectivity test."}], max_tokens=32, **scope_args)
            ok = True
        except ModelFailure:
            ok = False
        with database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            live_actor(conn, user, admin=True)
            current = tutor.check_config(tutor.settings(conn))
            record_check(conn, "ai", snapshot, current, ok=ok)
            put_value(conn, "meta", "ai_last_error", "" if ok else MODEL_CHECK_ERROR)
            put_value(conn, "meta", "ai_last_error_binding", fingerprint(current))
            connection = tutor.status(conn, True)["connection"]
        return {"ok": ok, "message": MODEL_CHECK_OK if ok else MODEL_CHECK_ERROR,
                "model": settings["model"], "mode": "openai", "connection": connection}

    @application.get("/api/teacher/search-settings")
    def get_search_settings(user=Depends(admin_user)):
        with database.connect() as conn:
            conn.execute('BEGIN')
            live_actor(conn, user, admin=True)
            return search_projection(conn)

    @application.put("/api/teacher/search-settings")
    def save_search_settings(payload: m.SearchSettings, user=Depends(admin_user)):
        with database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            live_actor(conn, user, admin=True)
            return update_search_settings(conn, payload)

    @application.post("/api/teacher/search-settings/test")
    def test_search_settings(user=Depends(admin_user)):
        with database.connect() as conn:
            conn.execute("BEGIN")
            live_actor(conn, user, admin=True)
            settings = effective_search_settings(conn)
            snapshot = check_snapshot(conn, "search", settings)
        if not settings["enabled"] or not settings["api_key"]:
            raise HTTPException(409, "Enable web search and configure its API key before testing saved settings")
        try:
            result = tutor.search.search(SEARCH_TEST_QUERY, api_key=settings["api_key"])
            result_count, ok = len(result["results"]), True
        except SearchFailure:
            result_count, ok = 0, False
        with database.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            live_actor(conn, user, admin=True)
            record_check(conn, "search", snapshot, effective_search_settings(conn), ok=ok)
            connection = search_projection(conn)["connection"]
        if not ok:
            raise HTTPException(502, SEARCH_CHECK_ERROR)
        return {"ok": True, "message": SEARCH_CHECK_OK, "connection": connection, "result_count": result_count}

    @application.get("/{path:path}", include_in_schema=False)
    def serve_frontend(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "API route not found")
        target = (frontend / path).resolve()
        if not target.is_relative_to(frontend) or "\\" in path:
            raise HTTPException(404, "Not found")
        if target.is_file():
            return FileResponse(target)
        if (frontend / "index.html").is_file():
            return FileResponse(frontend / "index.html")
        raise HTTPException(404, "Frontend build missing; build frontend/dist before serving the UI")

    return application


app = create_app()
