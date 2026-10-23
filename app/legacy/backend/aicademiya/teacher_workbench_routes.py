"""Stage6 owner-only preview/review/import endpoints; explicit reset is the only write."""
from pathlib import Path
import tempfile
from fastapi import Depends, File, HTTPException, UploadFile
from . import models as m
from .materials import MAX_UPLOAD_BYTES, SUPPORTED, extract_document
from .services import workspace_response
from .source_review import source_review
from .teacher_preview import preview_info, reset_preview
from .version_context import session_access


def register_teacher_workbench_routes(app, db, tutor, teacher_user):
    @app.get("/api/teacher/sessions/{session_id}/preview")
    def preview(session_id: str, user=Depends(teacher_user)):
        with db.connect() as conn:
            return preview_info(conn, session_access(conn, session_id, user), user)

    @app.post("/api/teacher/sessions/{session_id}/preview/reset")
    def reset(session_id: str, payload: m.PreviewReset, user=Depends(teacher_user)):
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            detail = session_access(conn, session_id, user)
            reset_preview(conn, detail, user, payload.expected_revision)
            return workspace_response(conn, detail, user, tutor.status(conn, True), True)

    @app.post("/api/teacher/sessions/{session_id}/source-review")
    def review(session_id: str, payload: m.SourceReviewInput, user=Depends(teacher_user)):
        with db.connect() as conn:
            return source_review(conn, session_access(conn, session_id, user), payload)

    @app.post("/api/teacher/sessions/{session_id}/instruction-import/preview")
    def instruction_import(session_id: str, file: UploadFile = File(...), user=Depends(teacher_user)):
        with db.connect() as conn:
            session_access(conn, session_id, user)
        filename = (file.filename or "instruction.txt").replace("\\", "/").rsplit("/", 1)[-1]
        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED:
            raise HTTPException(422, "Unsupported instruction file format; use TXT, MD, PDF, DOCX, PPTX, PNG, JPG, JPEG or WebP")
        data = file.file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Upload exceeds the 25 MiB preview limit")
        # Only an owned random temporary input is written, never a material row or
        # persistent original. Parsers do not fetch external Office resources.
        with tempfile.TemporaryDirectory(prefix="instruction-preview-", dir=db.path.parent) as temp:
            path = Path(temp) / ("input" + suffix)
            path.write_bytes(data)
            extracted = extract_document(path)
        with db.connect() as conn:
            session_access(conn, session_id, user)
        text, warning, status = extracted["excerpt"], extracted["warning"], extracted["status"]
        report = extracted["extraction_report"]
        report["notes"].append("Instruction preview only: the temporary uploaded copy was removed; no material, instruction, draft save or publication was created. Keep your original file for inspection.")
        if len(text) > 30000:
            limit_warning = "Extracted text exceeds the 30,000-character instruction field limit. Edit/trim before explicitly applying; this preview has not silently truncated it to that field limit."
            warning = ((warning + " ") if warning else "") + limit_warning
            report["notes"].append(limit_warning)
            if status == "ready":
                status = "needs_review"
        return {"filename": filename, "text": text, "status": status, "warning": warning,
                "extraction_report": report, "max_instruction_chars": 30000}
