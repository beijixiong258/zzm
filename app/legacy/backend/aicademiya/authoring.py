"""Draft authoring, safe private previews and pure helper integration."""
import copy
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from . import models as m
from .db import new_id, now
from .materials import MAX_UPLOAD_BYTES
from .material_library import (session_material_rows, member_material, course_material_rows,
                               linked_session_ids, attach_material, detach_material, course_material)
from .roster import staging, ensure_staging_capacity
from .services import public_detail, public_material
from .version_context import is_staff, course_access, session_access, material_rows
from . import versions


def link_helpers():
    try:
        from .link_materials import normalize_link, extract_link
        return normalize_link, extract_link
    except ImportError:
        raise HTTPException(503, "Link extraction helper is not installed") from None


def normalize(value):
    helper, _ = link_helpers()
    try:
        return helper(value)
    except ValueError:
        raise HTTPException(422, "Source must be a valid public HTTP(S) URL or exact DOI") from None


def link_data(value, title=None, visibility="student", *, managed=False):
    url = normalize(value)
    _, extraction = link_helpers()
    try:
        data = extraction(url)
    except Exception:
        data = {"title": title or url, "excerpt": "", "status": "needs_review", "warning": "Public link extraction failed; open the external URL to inspect it."}
    return {"id": new_id(), "title": title or data.get("title") or url, "kind": "link", "visibility": visibility,
            "url": url, "source_input": value, "source_label": value, "managed": managed,
            "status": data.get("status") or "needs_review", "excerpt": (data.get("excerpt") or "")[:50000],
            "warning": data.get("warning"), "extracted_at": now()}


def validate_content(detail):
    groups, questions = detail.get("groups", []), detail.get("questions", [])
    gids, qids = [g["id"] for g in groups], [q["id"] for q in questions]
    if len(groups) > 200 or len(questions) > 1000:
        raise HTTPException(413, "Limit: 200 groups and 1000 questions")
    if len(gids) != len(set(gids)) or any(not g["id"] or not g.get("title", "").strip() for g in groups):
        raise HTTPException(422, "Groups need unique IDs and meaningful titles")
    if len(qids) != len(set(qids)) or any(not q["id"] or not q.get("prompt", "").strip() for q in questions):
        raise HTTPException(422, "Questions need unique IDs and meaningful prompts")
    if any(q["group_id"] not in gids for q in questions):
        raise HTTPException(422, "Question group_id must refer to a current session group")
    if any(qid not in qids for qid in detail.get("reference_answers", {})):
        raise HTTPException(422, "References must refer to current question IDs")


def referenced_historically(conn, cid, mid):
    for row in conn.execute("SELECT snapshot_json FROM course_versions WHERE course_id=?", (cid,)):
        for s in json.loads(row[0])["sessions"]:
            if any(x["id"] == mid for x in s.get("_materials", [])):
                return True
    return False


def apply_session_update(conn, sid, user, update):
    detail = session_access(conn, sid, user)
    operational = {k: update.pop(k) for k in ("active", "starts_at", "ends_at") if k in update}
    row = conn.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
    start, end = operational.get("starts_at", row["starts_at"]), operational.get("ends_at", row["ends_at"])
    if start and end and datetime.fromisoformat(start.replace("Z", "+00:00")) >= datetime.fromisoformat(end.replace("Z", "+00:00")):
        raise HTTPException(422, "Session start must be before its end")
    if operational.get("active", True) is None:
        raise HTTPException(422, "Active must be a boolean")
    if any(v is None for k, v in update.items()):
        raise HTTPException(422, "Content fields cannot be null")
    candidate = {k: v for k, v in detail.items() if not k.startswith("_") and k not in versions.OPERATIONAL}
    candidate.update(update)
    if "questions" in update and "reference_answers" not in update:
        ids = {q["id"] for q in candidate["questions"]}
        candidate["reference_answers"] = {k: v for k, v in candidate.get("reference_answers", {}).items() if k in ids}
    validate_content(candidate)
    rows = {r["id"]: r for r in session_material_rows(conn, sid)}
    if "questions" in update:
        # Validate the whole batch before creating Links, including image ownership.
        normalized = {}
        known_images = {image.get("url") for q in detail.get("questions", []) for image in q.get("images", [])}
        for q in candidate["questions"]:
            if len(set(q.get("source_material_ids", []))) != len(q.get("source_material_ids", [])) or any(mid not in rows for mid in q.get("source_material_ids", [])):
                raise HTTPException(422, "Source materials must be active materials of this session")
            normalized[q["id"]] = [(raw, normalize(raw)) for raw in q.get("source_links", []) if raw.strip()]
            for image in q.get("images", []):
                url = image.get("url", "")
                if image.get("asset_key"):
                    raise HTTPException(422, "Asset keys must be resolved through reviewed worksheet import")
                if url not in known_images and not authorized_image_url(conn, sid, url):
                    raise HTTPException(422, "Question images must be authorized session assets")
        linked_ids = set()
        for q in candidate["questions"]:
            mids = list(q.get("source_material_ids", []))
            canonical = []
            for raw, url in normalized[q["id"]]:
                existing = next((r for r in rows.values() if json.loads(r["content_json"]).get("url") == url and json.loads(r["content_json"]).get("kind") == "link"), None)
                if existing:
                    mid = existing["id"]
                else:
                    library_link = next((r for r in course_material_rows(conn, detail["course_id"])
                                         if json.loads(r["content_json"]).get("url") == url
                                         and json.loads(r["content_json"]).get("kind") == "link"), None)
                    if library_link:
                        mid = library_link["id"]
                        attach_material(conn, sid, mid, detail["course_id"])
                    else:
                        data = link_data(raw, managed=True)
                        mid = data["id"]
                        conn.execute("INSERT INTO materials VALUES(?,?,?,?,0)", (mid, sid, json.dumps(data), None))
                    rows[mid] = conn.execute("SELECT * FROM materials WHERE id=?", (mid,)).fetchone()
                linked_ids.add(mid)
                if url not in canonical:
                    canonical.append(url)
            # Authored links and checkbox selections are separate user choices.
            # Adding a link must not silently check its material checkbox: otherwise
            # clearing that link after a readback would leave a hidden association.
            q["source_link_inputs"] = [raw for raw, _ in normalized[q["id"]]]
            q["source_links"], q["source_material_ids"] = canonical, mids
        selected = linked_ids | {mid for q in candidate["questions"] for mid in q.get("source_material_ids", [])}
        for mid, r in rows.items():
            raw = json.loads(r["content_json"])
            if raw.get("kind") == "link" and raw.get("managed") and mid not in selected and not referenced_historically(conn, detail["course_id"], mid):
                detach_material(conn, sid, mid)
    conn.execute("UPDATE sessions SET content_json=? WHERE id=?", (json.dumps(candidate, ensure_ascii=False), sid))
    for k, v in operational.items():
        conn.execute(f"UPDATE sessions SET {k}=? WHERE id=?", (v, sid))
    return public_detail(conn, session_access(conn, sid, user), True)


def safe_asset_path(raw, key):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,150}", key) or ".." in key:
        raise HTTPException(404, "Asset not found")
    if key not in {a.get("key") for a in raw.get("assets", [])}:
        raise HTTPException(404, "Asset not found")
    root = Path(raw.get("assets_dir", "")).resolve()
    path = (root / key).resolve()
    if not raw.get("assets_dir") or not path.is_relative_to(root) or not path.is_file() or path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
        raise HTTPException(404, "Asset not found")
    return path


def authorized_image_url(conn, sid, url):
    preview = re.fullmatch(r"/api/materials/([A-Za-z0-9-]+)/preview", url)
    if preview:
        row = next((r for r in session_material_rows(conn, sid) if r["id"] == preview[1]), None)
        if not row:
            return False
        raw = json.loads(row["content_json"])
        path = Path(row["file_path"]) if row["file_path"] else None
        return raw.get("visibility") == "student" and raw.get("kind") != "answer_key" and bool(path and path.is_file() and path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))
    match = re.fullmatch(r"/api/materials/([A-Za-z0-9-]+)/assets/([A-Za-z0-9_.-]+)", url)
    if not match:
        return False
    row = next((r for r in session_material_rows(conn, sid) if r["id"] == match[1]), None)
    if not row:
        return False
    try:
        safe_asset_path(json.loads(row["content_json"]), match[2])
        return True
    except HTTPException:
        return False


def resolve_material(conn, mid, user, version_id=None, asset_key=None):
    row = conn.execute("""SELECT m.*,c.course_id FROM materials m
        JOIN material_courses c ON c.material_id=m.id WHERE m.id=?""", (mid,)).fetchone()
    if not row:
        raise HTTPException(404, "Material not found")
    course = course_access(conn, row["course_id"], user)
    if version_id is not None and not version_id:
        raise HTTPException(422, "version_id must not be blank")
    if is_staff(user) and version_id is None:
        if row["archived"]:
            raise HTTPException(404, "Material is globally archived")
        # The owner can inspect retained course-library originals even without
        # any current membership, or after the origin session left the draft.
        return row, {"course_id": row["course_id"], "_version_id": ""}
    vid = version_id or course["published_version_id"]
    if not vid:
        raise HTTPException(404, "Course has no published version")
    _, content = versions.snapshot(conn, row["course_id"], vid)
    denied = None
    for saved in content["sessions"]:
        selected = next((r for r in saved.get("_materials", []) if r["id"] == mid), None)
        if not selected:
            continue
        try:
            # Try every snapshot membership: access to S2 must not depend on
            # the user's history in the file's origin S1.
            detail = session_access(conn, saved["id"], user, vid)
            if asset_key and not is_staff(user):
                wanted = f"/api/materials/{mid}/assets/{asset_key}"
                if not any(image.get("url", "").split("?", 1)[0] == wanted for q in detail.get("questions", []) for image in q.get("images", [])):
                    raise HTTPException(403, "Figure is not referenced by this published worksheet")
            elif not public_material(selected, is_staff(user), vid):
                raise HTTPException(403, "Teacher-only material")
            return selected, detail
        except HTTPException as exc:
            if exc.status_code not in (403, 404):
                raise
            if exc.status_code == 403:
                denied = exc
    if denied:
        raise denied
    raise HTTPException(404, "Material not found in this edition")


def selected_tutor_materials(conn, detail, question_id):
    question = next((q for q in detail.get("questions", []) if q["id"] == question_id), None)
    selected = set(question.get("source_material_ids", [])) if question else set()
    urls = set(question.get("source_links", [])) if question else set()
    public, private = [], []
    for row in material_rows(conn, detail):
        raw = json.loads(row["content_json"])
        if selected or urls:
            if row["id"] not in selected and raw.get("url") not in urls:
                continue
        # Never aggregate multi-question answer-key or private worksheet bodies.
        if raw.get("kind") == "answer_key" or (raw.get("visibility") == "teacher" and raw.get("kind") == "worksheet"):
            continue
        if raw.get("status") not in ("ready", "needs_review"):
            continue
        if not raw.get("excerpt") and not raw.get("document"):
            continue
        item = {k: raw.get(k) for k in ("id", "title", "source_label", "excerpt", "visibility", "kind", "status", "warning", "url")}
        item["id"] = row["id"]
        if raw.get("document"):
            from .document_storage import get_document_manifest
            manifest, root = get_document_manifest(conn, row)
            # Keep local asset resolution OUTSIDE the serializable document.
            # Only this already-authorized edition may supply model images.
            item['_document_asset_root'] = root
            item["_document"] = {"material_id":row["id"], "revision_id":raw["document"]["revision_id"],
                "title":raw.get("title", ""), "source_label":raw.get("source_label", ""),
                "visibility":raw.get("visibility"), "kind":raw.get("kind"), "manifest":manifest}
        (public if raw.get("visibility") == "student" else private).append(item)
    return public, private


def register_authoring_routes(app, db, tutor, uploads, teacher_user, current_user):
    from .worksheet_materials import register_worksheet_materials
    register_worksheet_materials(app, db, tutor, uploads, teacher_user)
    @app.get("/api/courses/{course_id}/materials")
    def course_materials(course_id: str, user=Depends(teacher_user)):
        with db.connect() as conn:
            course_access(conn, course_id, user)
            return {"materials": [{**public_material(r, True), "session_ids": linked_session_ids(conn, r["id"])}
                                  for r in course_material_rows(conn, course_id)]}

    @app.post("/api/sessions/{session_id}/materials/attach")
    def attach(session_id: str, payload: m.MaterialAttach, user=Depends(teacher_user)):
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            detail = session_access(conn, session_id, user)
            return public_material(attach_material(conn, session_id, payload.material_id, detail["course_id"]), True)

    @app.post("/api/sessions/{session_id}/materials/{material_id}/reprocess")
    def reprocess(session_id: str, material_id: str, user=Depends(teacher_user)):
        from .materials import extract_document
        with db.connect() as conn:
            session_access(conn, session_id, user)
            row = member_material(conn, session_id, material_id)
            if json.loads(row["content_json"]).get("document") or json.loads(row["content_json"]).get("processing") == "full_document":
                raise HTTPException(409, "Use the complete document processing workflow for this PDF")
            if json.loads(row["content_json"]).get("kind") == "link":
                raise HTTPException(422, "Use the Link edit/refetch workflow for links")
            path = Path(row["file_path"]) if row["file_path"] else None
            if not path or not path.is_file():
                raise HTTPException(404, "Original material file is unavailable")
        extraction = extract_document(path)
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            session_access(conn, session_id, user)
            current = member_material(conn, session_id, material_id)
            if current["file_path"] != row["file_path"]:
                raise HTTPException(409, "Material was restored while extracting; retry with its current original")
            raw = json.loads(current["content_json"])
            if raw.get("document") or raw.get("processing") == "full_document":
                raise HTTPException(409, "Complete document processing replaced the preview while extracting")
            raw.update({k: extraction[k] for k in ("status", "excerpt", "warning", "extraction_report")})
            raw["extracted_at"] = now()
            conn.execute("UPDATE materials SET content_json=? WHERE id=?", (json.dumps(raw), material_id))
            return public_material(conn.execute("SELECT * FROM materials WHERE id=?", (material_id,)).fetchone(), True)

    @app.post("/api/sessions/{session_id}/teaching-preview")
    def teaching_preview(session_id: str, payload: m.TeachingPreview, user=Depends(teacher_user)):
        from .teaching import compile_teaching
        with db.connect() as conn:
            detail = session_access(conn, session_id, user)
            edits = payload.model_dump(exclude_unset=True)
            if any(value is None for value in edits.values()):
                raise HTTPException(422, "Preview fields cannot be null")
            return compile_teaching({**detail, **edits})

    @app.get("/api/teacher/courses/{course_id}/versions")
    def version_list(course_id: str, user=Depends(teacher_user)):
        with db.connect() as conn:
            c = course_access(conn, course_id, user)
            return {"current_version_id": c["published_version_id"], "has_unpublished_changes": versions.changed(conn, course_id),
                    "versions": [versions.version_entry(r) for r in conn.execute("SELECT * FROM course_versions WHERE course_id=? ORDER BY number", (course_id,))]}

    @app.post("/api/teacher/courses/{course_id}/versions/publish")
    def publish(course_id: str, payload: m.Publish, user=Depends(teacher_user)):
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            course_access(conn, course_id, user)
            return versions.publish(conn, course_id, user["id"], payload.label)

    @app.get("/api/teacher/courses/{course_id}/versions/{version_id}")
    def get_version(course_id: str, version_id: str, user=Depends(teacher_user)):
        with db.connect() as conn:
            course_access(conn, course_id, user)
            row, content = versions.snapshot(conn, course_id, version_id)
            return {**versions.version_entry(row), "course": content["course"], "sessions": [public_detail(conn, {**s, "_version_id": version_id}, True) for s in content["sessions"]]}

    @app.get("/api/teacher/courses/{course_id}/versions/{version_id}/diff")
    def version_diff(course_id: str, version_id: str, user=Depends(teacher_user)):
        with db.connect() as conn:
            course_access(conn, course_id, user)
            _, saved = versions.snapshot(conn, course_id, version_id)
            # Private storage locations are not useful UI fields.
            changes = versions.diff(versions.comparison_snapshot(saved),
                                    versions.comparison_snapshot(versions.draft_snapshot(conn, course_id)))
            return {"changes": [r for r in changes if "file_path" not in r["path"] and "assets_dir" not in r["path"]]}

    @app.post("/api/teacher/courses/{course_id}/versions/{version_id}/restore")
    def version_restore(course_id: str, version_id: str, payload: m.Publish, user=Depends(teacher_user)):
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            course_access(conn, course_id, user)
            return versions.restore(conn, course_id, version_id, user["id"], payload.label)

    @app.post("/api/courses/{course_id}/materials/link")
    def create_course_link(course_id: str, payload: m.LinkCreate, user=Depends(teacher_user)):
        with db.connect() as conn:
            course_access(conn, course_id, user)
        item = link_data(payload.url, payload.title, payload.visibility)
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            course_access(conn, course_id, user)
            conn.execute("INSERT INTO materials VALUES(?,NULL,?,?,0)", (item["id"], json.dumps(item), None))
            conn.execute("INSERT INTO material_courses VALUES(?,?)", (item["id"], course_id))
            return public_material(conn.execute("SELECT * FROM materials WHERE id=?", (item["id"],)).fetchone(), True)

    @app.delete("/api/courses/{course_id}/materials/{material_id}")
    def archive_course_material(course_id: str, material_id: str, user=Depends(teacher_user)):
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            course_access(conn, course_id, user)
            course_material(conn, course_id, material_id)
            if linked_session_ids(conn, material_id):
                raise HTTPException(409, "Remove this material from its session drafts before removing it from the course library")
            conn.execute("UPDATE materials SET archived=1 WHERE id=?", (material_id,))
            return {"ok": True}

    @app.post("/api/sessions/{session_id}/materials/link")
    def create_link(session_id: str, payload: m.LinkCreate, user=Depends(teacher_user)):
        with db.connect() as conn:
            session_access(conn, session_id, user)
        item = link_data(payload.url, payload.title, payload.visibility)
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            session_access(conn, session_id, user)
            conn.execute("INSERT INTO materials VALUES(?,?,?,?,0)", (item["id"], session_id, json.dumps(item), None))
            return public_material(conn.execute("SELECT * FROM materials WHERE id=?", (item["id"],)).fetchone(), True)

    @app.patch("/api/courses/{course_id}/materials/{material_id}")
    def patch_course_material(course_id: str, material_id: str, payload: m.MaterialPatch, user=Depends(teacher_user)):
        return patch_material_record(None, course_id, material_id, payload, user)

    @app.patch("/api/sessions/{session_id}/materials/{material_id}")
    def patch_material(session_id: str, material_id: str, payload: m.MaterialPatch, user=Depends(teacher_user)):
        return patch_material_record(session_id, None, material_id, payload, user)

    def patch_material_record(session_id, course_id, material_id, payload, user):
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if session_id:
                session_access(conn, session_id, user)
                r = member_material(conn, session_id, material_id)
            else:
                course_access(conn, course_id, user)
                r = course_material(conn, course_id, material_id)
            raw = json.loads(r["content_json"])
            values = payload.model_dump(exclude_unset=True)
            if any(v is None for v in values.values()) or ("title" in values and not values["title"].strip()):
                raise HTTPException(422, "Material fields must not be blank or null")
            if raw.get("kind") == "answer_key" and values.get("visibility") == "student":
                raise HTTPException(422, "Answer keys must remain teacher-only")
            if "kind" in values and raw.get("kind") == "link":
                raise HTTPException(422, "Link materials cannot be changed into file materials")
            if values.get("kind") == "answer_key":
                if values.get("visibility") == "student":
                    raise HTTPException(422, "Answer keys must remain teacher-only")
                values["visibility"] = "teacher"
            if "url" in values:
                if raw.get("kind") != "link":
                    raise HTTPException(422, "Only Link materials have editable URLs")
                fresh = link_data(values["url"], values.get("title", raw["title"]), values.get("visibility", raw["visibility"]), managed=raw.get("managed", False))
                fresh["id"] = material_id
                raw.update(fresh)
                # Canonical relationships follow this edited material, never historical copies.
                old_url = json.loads(r["content_json"]).get("url")
                for sid in linked_session_ids(conn, material_id):
                    detail = json.loads(conn.execute("SELECT content_json FROM sessions WHERE id=?", (sid,)).fetchone()[0])
                    for q in detail.get("questions", []):
                        if old_url in q.get("source_links", []):
                            q["source_links"] = [raw["url"] if x == old_url else x for x in q.get("source_links", [])]
                    conn.execute("UPDATE sessions SET content_json=? WHERE id=?", (json.dumps(detail), sid))
            if values.get("visibility", raw.get("visibility")) != "student" or values.get("kind", raw.get("kind")) == "answer_key":
                image_url = f"/api/materials/{material_id}/preview"
                for sid in linked_session_ids(conn, material_id):
                    detail = json.loads(conn.execute("SELECT content_json FROM sessions WHERE id=?", (sid,)).fetchone()[0])
                    if any(image.get("url", "").split("?", 1)[0] == image_url for q in detail.get("questions", []) for image in q.get("images", [])):
                        raise HTTPException(422, "Student question images must remain student-visible")
            raw.update({k: v for k, v in values.items() if k != "url"})
            conn.execute("UPDATE materials SET content_json=? WHERE id=?", (json.dumps(raw), material_id))
            return public_material(conn.execute("SELECT * FROM materials WHERE id=?", (material_id,)).fetchone(), True)

    @app.get("/api/materials/{material_id}/preview")
    def preview_material(material_id: str, version_id: str | None = None, user=Depends(current_user)):
        with db.connect() as conn:
            row, _ = resolve_material(conn, material_id, user, version_id)
            raw = json.loads(row["content_json"])
            path = Path(row["file_path"]) if row["file_path"] else None
            if path and path.is_file() and path.suffix.lower() in (".pdf", ".png", ".jpg", ".jpeg", ".webp"):
                # Chromium/Edge's native PDF viewer cannot run under CSP sandbox.
                # Keep auth, the exact MIME and nosniff; the UI opens PDFs top-level.
                mime = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
                        ".jpeg": "image/jpeg", ".webp": "image/webp"}[path.suffix.lower()]
                headers = {"X-Content-Type-Options": "nosniff"}
                if path.suffix.lower() != ".pdf":
                    headers["Content-Security-Policy"] = "sandbox"
                return FileResponse(path, media_type=mime, filename=raw.get("title") or path.name,
                                    content_disposition_type="inline", headers=headers)
            return PlainTextResponse(raw.get("excerpt") or raw.get("warning") or "No extractable preview is available.", headers={"X-Content-Type-Options": "nosniff"})

    @app.get("/api/materials/{material_id}/assets/{asset_key}")
    def material_asset(material_id: str, asset_key: str, version_id: str | None = None, user=Depends(current_user)):
        with db.connect() as conn:
            row = conn.execute("SELECT * FROM materials WHERE id=?", (material_id,)).fetchone()
            if row:
                row, _ = resolve_material(conn, material_id, user, version_id, asset_key)
                raw = json.loads(row["content_json"])
            else:
                if not is_staff(user):
                    raise HTTPException(404, "Asset not found")
                raw = None
                for r in conn.execute("SELECT * FROM import_staging WHERE owner_id=? AND kind='worksheet'", (user["id"],)):
                    data = json.loads(r["payload_json"])
                    if data["material"]["id"] == material_id:
                        staging(conn, r["id"], user["id"], r["course_id"], "worksheet", r["session_id"])
                        course_access(conn, r["course_id"], user)
                        raw = data["material"]
                        break
                if raw is None:
                    raise HTTPException(404, "Asset not found")
            return FileResponse(safe_asset_path(raw, asset_key), headers={"X-Content-Type-Options": "nosniff"})

    @app.post("/api/sessions/{session_id}/worksheet-import/preview")
    def worksheet_preview(session_id: str, file: UploadFile = File(...), use_ai: bool = Form(False), user=Depends(teacher_user)):
        with db.connect() as conn:
            detail = session_access(conn, session_id, user)
            settings = tutor.settings(conn)
            ensure_staging_capacity(conn, user["id"], "worksheet")
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in {".docx", ".pdf", ".txt", ".md", ".pptx"}:
            raise HTTPException(415, "Supported worksheets: DOCX, PDF, TXT, MD, PPTX")
        data = file.file.read(MAX_UPLOAD_BYTES+1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Worksheet exceeds the 25 MiB limit")
        if use_ai and settings["mode"] == "demo":
            raise HTTPException(409, "Demo mode cannot perform AI extraction; use deterministic preview")
        try:
            from .worksheet_import import preview_worksheet
        except ImportError:
            raise HTTPException(503, "Worksheet extraction helper is not installed") from None
        iid, mid = new_id(), new_id()
        path, asset_dir = uploads / (mid+suffix), uploads / (mid+"-assets")
        path.write_bytes(data)
        asset_dir.mkdir(parents=True, exist_ok=True)
        llm = None
        provider_errors = []
        if use_ai:
            def llm(messages):
                with db.connect() as conn:
                    session_access(conn, session_id, user)
                if len(json.dumps(messages, ensure_ascii=False)) > 100000:
                    raise HTTPException(413, "AI worksheet extraction payload exceeds the bounded document limit")
                args = {"max_tokens": 8192}
                if tutor.uses_aicademiya_router(settings):
                    args["kv_scope"] = tutor.kv_scope(user, session_id+":"+mid, "worksheet-import")
                if tutor.uses_aicademiya_router(settings) or tutor.uses_siliconflow(settings):
                    args["response_format"] = {"type": "json_object"}
                try:
                    return tutor.complete(settings, messages, **args)
                except ModelFailure as exc:
                    provider_errors.append(str(exc))
                    raise
        from .ai import ModelFailure
        try:
            parsed = preview_worksheet(path, assets_dir=asset_dir, llm=llm)
        except ModelFailure as exc:
            raise HTTPException(502, str(exc)) from None
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(422, "Worksheet extraction failed; inspect the document and retry") from None
        if provider_errors:
            tutor.record_error(provider_errors[0])
            raise HTTPException(502, provider_errors[0])
        filename = (file.filename or "Worksheet").replace("\\", "/").split("/")[-1]
        material = {"id": mid, "title": filename, "kind": "worksheet", "visibility": "teacher", "source_label": filename,
                    "status": "needs_review" if parsed.get("needs_review") else "ready", "excerpt": parsed.get("source_text", "")[:50000],
                    "warning": "; ".join(parsed.get("warnings", [])) or None, "assets": parsed.get("assets", []), "assets_dir": str(asset_dir)}
        draft = {k: parsed[k] for k in ("title", "groups", "questions", "reference_answers")}
        stored = {"material": material, "file_path": str(path), "draft": draft}
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            session_access(conn, session_id, user)
            ensure_staging_capacity(conn, user["id"], "worksheet")
            deadline = (datetime.now(timezone.utc)+timedelta(minutes=30)).isoformat()
            conn.execute("INSERT INTO import_staging VALUES(?,?,?,?,?,?,?)", (iid, user["id"], detail["course_id"], session_id, "worksheet", deadline, json.dumps(stored)))
        response_material = public_material({"id": mid, "content_json": json.dumps(material), "file_path": str(path)}, True)
        response_material["download_url"], response_material["preview_url"] = None, None
        return {"import_id": iid, "material": response_material, "draft": draft, "warnings": parsed.get("warnings", []), "method": parsed.get("method"),
                "assets": [{"key": a["key"], "label": a.get("label", ""), "url": f"/api/materials/{mid}/assets/{a['key']}"} for a in parsed.get("assets", [])], "needs_review": bool(parsed.get("needs_review"))}

    @app.post("/api/sessions/{session_id}/worksheet-import/{import_id}/commit")
    def worksheet_commit(session_id: str, import_id: str, payload: m.WorksheetCommit, user=Depends(teacher_user)):
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            detail = session_access(conn, session_id, user)
            stored = staging(conn, import_id, user["id"], detail["course_id"], "worksheet", session_id)
            material = stored["material"]
            questions = [q.model_dump() for q in payload.questions]
            for q in questions:
                for image in q.get("images", []):
                    key = image.pop("asset_key", None)
                    if key:
                        safe_asset_path(material, key)
                        image["url"] = f"/api/materials/{material['id']}/assets/{key}"
                    elif image.get("url"):
                        raise HTTPException(422, "Imported figures must use this preview's asset_key")
            groups = [g.model_dump() for g in payload.groups]
            refs = dict(payload.reference_answers)
            if payload.mode == "append":
                existing_g = {g["id"]: g for g in detail.get("groups", [])}
                for g in groups:
                    if g["id"] in existing_g and g != existing_g[g["id"]]:
                        raise HTTPException(409, "Imported group ID conflicts with the current draft")
                    existing_g[g["id"]] = g
                groups = list(existing_g.values())
                questions = detail.get("questions", []) + questions
                refs = {**detail.get("reference_answers", {}), **refs}
            validate_content({"groups": groups, "questions": questions, "reference_answers": refs})
            if stored.get('existing_material_id'):
                from .worksheet_materials import reuse_on_commit
                reuse_on_commit(conn, detail, stored, questions, payload.reference_answers, uploads)
            else:
                conn.execute("INSERT INTO materials VALUES(?,?,?,?,0)", (material["id"], session_id, json.dumps(material), stored["file_path"]))
            update = {"groups": groups, "questions": questions, "reference_answers": refs}
            if stored.get('existing_material_id'):
                update['worksheet_import_sources'] = detail.get('worksheet_import_sources', []) + [
                    {**stored['provenance'], 'import_id': import_id, 'saved_at': now(),
                     'question_ids': [q.id for q in payload.questions]}]
            result = apply_session_update(conn, session_id, user, update)
            conn.execute("DELETE FROM import_staging WHERE id=?", (import_id,))
            return result
