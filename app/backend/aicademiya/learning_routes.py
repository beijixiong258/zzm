"""Version-pinned learning endpoints. Accepted inference keeps its original run."""
import hashlib
import json
from fastapi import Depends, HTTPException
from fastapi.responses import JSONResponse
from . import models as m
from .ai import ModelFailure
from .db import new_id, now, public_user
from .services import (active_question, editable, ensure_workspace, mark_active, reading_groups,
                       save_answer, save_message, workspace_response)
from .version_context import session_access, observed_detail, is_staff, availability
from .authoring import selected_tutor_materials
from .teacher_preview import legacy_write_guard
from .course_lifecycle import trash_timestamp, require_live_course


def register_learning_routes(app, db, tutor, current_user, teacher_user):
    def own(conn, detail, user):
        return workspace_response(conn, detail, user, tutor.status(conn, is_staff(user)), is_staff(user))

    def get_run(conn, sid, user, vid, write=True, preview_id=None):
        detail = session_access(conn, sid, user, vid, write=write)
        if write:
            legacy_write_guard(conn, detail, user, preview_id)
        state = ensure_workspace(conn, sid, user["id"], detail["_version_id"])
        if write:
            from .guided_state import ensure_no_guided_request
            ensure_no_guided_request(conn, sid, user["id"], detail["_version_id"])
        return detail, state

    @app.get("/api/history")
    def history(user=Depends(current_user)):
        from .versions import snapshot
        from .services import active_questions
        result = []
        with db.connect() as conn:
            conn.execute("BEGIN")  # Keep skip/authorization in one read snapshot.
            for run in conn.execute("SELECT * FROM workspaces WHERE user_id=? ORDER BY coalesce(last_active,'') DESC,rowid DESC", (user["id"],)).fetchall():
                row = conn.execute("SELECT * FROM sessions WHERE id=?", (run["session_id"],)).fetchone()
                if not row:
                    continue
                if trash_timestamp(conn, row["course_id"]) is not None:
                    continue  # Keep the rows and every unrelated historical run.
                # Authorize against enrollment/ownership, never other staff records.
                from .version_context import course_access
                try:
                    course_access(conn, row["course_id"], user)
                except HTTPException as exc:
                    if exc.status_code in (403, 404, 410):
                        continue
                    raise
                # A former staff member's draft is never student history. Keep
                # its bytes private while retaining their genuine learning runs.
                if not is_staff(user) and not run['version_id']:
                    continue
                if run["version_id"]:
                    version, saved = snapshot(conn, row["course_id"], run["version_id"])
                    detail = next((s for s in saved["sessions"] if s["id"] == run["session_id"]), None)
                    if not detail:
                        continue
                    course = saved["course"]
                    version_info = {k: version[k] for k in ("id", "number", "label")}
                else:
                    detail = json.loads(row["content_json"])
                    course = dict(conn.execute("SELECT * FROM courses WHERE id=?", (row["course_id"],)).fetchone())
                    version_info = {"id": None, "number": None, "label": "Draft preview"}
                qids = {q["id"] for q in active_questions(detail, run["selected_reading"])}
                answered = sum(bool(r["answer"].strip()) and r["question_id"] in qids for r in conn.execute("SELECT question_id,answer FROM attempts WHERE session_id=? AND user_id=? AND version_id=?", (run["session_id"], user["id"], run["version_id"])))
                result.append({"course": {k: course[k] for k in ("id", "code", "title")}, "session": {k: detail[k] for k in ("id", "title", "number")}, "version": version_info,
                               "status": run["status"], "answered": answered, "total": len(qids), "last_active": run["last_active"]})
        return result

    @app.get("/api/sessions/{session_id}/workspace")
    def workspace(session_id: str, version_id: str | None = None, user=Depends(current_user)):
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            return own(conn, session_access(conn, session_id, user, version_id), user)

    @app.post("/api/sessions/{session_id}/reading")
    def select_reading(session_id: str, payload: m.ReadingChoice, version_id: str | None = None, preview_id: str | None = None, user=Depends(current_user)):
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            detail, state = get_run(conn, session_id, user, version_id, preview_id=preview_id)
            editable(state)
            if payload.group_id not in reading_groups(detail):
                raise HTTPException(422, "This session does not offer the selected reading")
            vid = detail["_version_id"]
            conn.execute("UPDATE workspaces SET selected_reading=? WHERE session_id=? AND user_id=? AND version_id=?", (payload.group_id, session_id, user["id"], vid))
            from .guided_state import load_state, save_state, select_current
            guided = load_state(conn, detail, user)
            if guided["started_at"] and state["selected_reading"] != payload.group_id and guided["phase"] != "warmup":
                guided["phase"] = "worksheet"
                select_current(detail, guided, payload.group_id)
                guided["updated_at"] = now()
                save_state(conn, detail, user, guided)
            mark_active(conn, session_id, user["id"], version_id=vid)
            return own(conn, detail, user)

    @app.post("/api/sessions/{session_id}/answers/{question_id}")
    def answer(session_id: str, question_id: str, payload: m.Answer, version_id: str | None = None, preview_id: str | None = None, user=Depends(current_user)):
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            detail, state = get_run(conn, session_id, user, version_id, preview_id=preview_id)
            editable(state)
            active_question(detail, state, question_id)
            save_answer(conn, session_id, user["id"], question_id, payload.answer, detail["_version_id"])
            return own(conn, detail, user)

    @app.post("/api/sessions/{session_id}/chat")
    def chat(session_id: str, payload: m.Chat, version_id: str | None = None, user=Depends(current_user)):
        uid, rid = user["id"], payload.request_id or new_id()
        fingerprint_data = payload.model_dump(exclude={"request_id"})
        if not payload.web_search:
            fingerprint_data.pop("web_search")
        fingerprint = hashlib.sha256(json.dumps(fingerprint_data, sort_keys=True).encode()).hexdigest()
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            detail, state = get_run(conn, session_id, user, version_id)
            vid = detail["_version_id"]
            key = (session_id, uid, vid, rid)
            old = conn.execute("SELECT * FROM chat_requests WHERE session_id=? AND user_id=? AND version_id=? AND request_id=?", key).fetchone()
            if old:
                if old["fingerprint"] != fingerprint:
                    raise HTTPException(409, "request_id was already used with different content")
                if old["status"] == "done":
                    return own(conn, detail, user)
                if old["status"] == "pending":
                    raise HTTPException(409, "This chat request is still awaiting feedback")
            editable(state)
            if payload.question_id:
                active_question(detail, state, payload.question_id)
            if payload.intent == "answer" and not payload.question_id:
                raise HTTPException(422, "Answer intent requires an active question_id")
            settings = tutor.settings(conn)
            if not old:
                if payload.intent == "answer":
                    save_answer(conn, session_id, uid, payload.question_id, payload.message, vid)
                save_message(conn, session_id, uid, "user", payload.message, payload.question_id, settings["mode"], payload.intent, version_id=vid)
                mark_active(conn, session_id, uid, version_id=vid)
                conn.execute("INSERT INTO chat_requests(session_id,user_id,request_id,fingerprint,status,created_at,version_id) VALUES(?,?,?,?,?,?,?)", (session_id, uid, rid, fingerprint, "pending", now(), vid))
            else:
                conn.execute("UPDATE chat_requests SET status='pending' WHERE session_id=? AND user_id=? AND version_id=? AND request_id=?", key)
            context = own(conn, detail, user)
            from .guided_state import load_state
            context['_document_read_progress']=load_state(conn, detail, user).get('document_read_progress',{})
            public_materials, private_materials = selected_tutor_materials(conn, detail, payload.question_id)
            context["session"]["materials"] = public_materials
            # Teacher preview's UI includes answer keys; never send that projection.
            context["session"]["questions"] = own(conn, detail, user)["session"]["questions"]
            for q in context["session"]["questions"]:
                q.pop("source_material_ids", None)
                q.pop("source_links", None)
            private_reference = tutor.reference_context(conn, detail, payload.question_id)
            private_instructions = detail.get("instructions", "")
        try:
            feedback, citations = tutor.feedback(settings, context, payload, private_reference=private_reference,
                                                private_instructions=private_instructions, private_materials=private_materials)
        except ModelFailure as exc:
            with db.connect() as conn:
                conn.execute("UPDATE chat_requests SET status='failed' WHERE session_id=? AND user_id=? AND version_id=? AND request_id=?", key)
            tutor.record_error(str(exc))
            raise HTTPException(502, str(exc)) from None
        try:
            with db.connect() as conn:
                # Preserve accepted-run completion after closure/publication, but
                # never use revoked staff/account permission or recreate a run.
                conn.execute("BEGIN IMMEDIATE")
                require_live_course(conn, detail["course_id"])
                from .version_context import course_access
                course_access(conn, detail['course_id'], user)
                request = conn.execute("SELECT status FROM chat_requests WHERE session_id=? AND user_id=? AND version_id=? AND request_id=?", key).fetchone()
                if not request or request[0] != "pending":
                    raise HTTPException(409, "This accepted request no longer owns a pending learning run")
                if is_staff(user) and not vid:
                    legacy_write_guard(conn, session_access(conn, session_id, user), user)
                message_id=save_message(conn, session_id, uid, "assistant", feedback, payload.question_id, settings["mode"], payload.intent, citations, version_id=vid)
                updates=context.get('_document_read_updates',{})
                if updates:
                    from .guided_state import load_state,save_state
                    live=load_state(conn,detail,user)
                    progress=live.setdefault('document_read_progress',{})
                    expected=context.get('_document_read_progress',{})
                    for mid,value in updates.items():
                        # A concurrent accepted turn must not overwrite a newer
                        # cursor/restart. Its actual citations remain valid.
                        if progress.get(mid)==expected.get(mid):progress[mid]=value
                    save_state(conn,detail,user,live)
                    conn.execute('UPDATE messages SET metadata_json=? WHERE id=?',
                                 (json.dumps({'document_read_coverage':context.get('_document_read_coverage',[])},ensure_ascii=False),message_id))
                conn.execute("UPDATE chat_requests SET status='done' WHERE session_id=? AND user_id=? AND version_id=? AND request_id=?", key)
                conn.execute("DELETE FROM meta WHERE key='ai_last_error'")
                operational = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
                detail.update(availability(operational))
                detail["_current_version_id"] = conn.execute("SELECT published_version_id FROM courses WHERE id=?", (detail["course_id"],)).fetchone()[0]
                if not is_staff(user):
                    enrollment = conn.execute("SELECT archived_at FROM enrollments WHERE course_id=? AND user_id=?", (detail["course_id"], uid)).fetchone()
                    detail["_enrollment_archived"] = not enrollment or bool(enrollment[0])
                return own(conn, detail, user)
        except Exception:
            with db.connect() as conn:
                conn.execute("UPDATE chat_requests SET status='failed' WHERE session_id=? AND user_id=? AND version_id=? AND request_id=? AND status='pending'", key)
            raise

    def reference(conn, sid, qid, user, version_id, reveal, preview_id=None):
        detail, state = get_run(conn, sid, user, version_id, write=reveal, preview_id=preview_id)
        if reveal:
            question = active_question(detail, state, qid)
        else:
            question = next((q for q in detail.get("questions", []) if q["id"] == qid), None)
            if not question:
                raise HTTPException(404, "Question not found in this edition")
        key = (sid, user["id"], detail["_version_id"], qid)
        attempt = conn.execute("SELECT * FROM attempts WHERE session_id=? AND user_id=? AND version_id=? AND question_id=?", key).fetchone()
        if not attempt or not attempt["answer"].strip():
            raise HTTPException(409, "Try this question before explicitly requesting its reference")
        if not reveal and not attempt["reference_revealed"]:
            raise HTTPException(403, "This reference has not been revealed in your learning run")
        if reveal:
            policy = detail.get("reference_policy", "after_attempt")
            if policy == "after_submit" and not state["submitted_at"]:
                raise HTTPException(409, "Submit your work before requesting references")
            if policy == "after_feedback" and not conn.execute("SELECT 1 FROM messages WHERE session_id=? AND user_id=? AND version_id=? AND question_id=? AND role='assistant' AND mode IN ('demo','openai') AND created_at>=?", (*key, attempt["updated_at"])).fetchone():
                raise HTTPException(409, "Request feedback on this attempt before revealing its reference")
        value = detail.get("reference_answers", {}).get(qid)
        if not value:
            raise HTTPException(404, "No teacher reference is available for this question")
        if reveal:
            conn.execute("UPDATE attempts SET reference_revealed=1 WHERE session_id=? AND user_id=? AND version_id=? AND question_id=?", key)
        return {"question_id": qid, "reference": value, "source_label": question.get("source_label", "")}

    @app.post("/api/sessions/{session_id}/references/{question_id}")
    def reveal_reference(session_id: str, question_id: str, version_id: str | None = None, preview_id: str | None = None, user=Depends(current_user)):
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            return reference(conn, session_id, question_id, user, version_id, True, preview_id)

    @app.get("/api/sessions/{session_id}/references/{question_id}")
    def get_reference(session_id: str, question_id: str, version_id: str | None = None, user=Depends(current_user)):
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            return reference(conn, session_id, question_id, user, version_id, False)

    @app.post("/api/sessions/{session_id}/submit")
    def submit(session_id: str, payload: m.Empty, version_id: str | None = None, preview_id: str | None = None, user=Depends(current_user)):
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            detail, state = get_run(conn, session_id, user, version_id, preview_id=preview_id)
            if state["status"] in ("submitted", "confirmed"):
                return own(conn, detail, user)
            if reading_groups(detail) and not state["selected_reading"]:
                raise HTTPException(409, "Choose one reading before submitting")
            response = own(conn, detail, user)
            if response["progress"]["answered"] != response["progress"]["total"]:
                raise HTTPException(409, "Answer every question on your active path before submitting")
            conn.execute("UPDATE workspaces SET status='submitted',submitted_at=?,reviewed_at=NULL,last_active=? WHERE session_id=? AND user_id=? AND version_id=?", (now(), now(), session_id, user["id"], detail["_version_id"]))
            return own(conn, detail, user)

    def export_response(data):
        filename = f"aicademiya-{data['session']['id']}-{data['user']['id']}-v{data['version']['number'] or 'draft'}.json"
        filename = "".join(c for c in filename if c.isascii() and (c.isalnum() or c in "-_."))
        return JSONResponse(data, headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    @app.get("/api/sessions/{session_id}/export")
    def export_own(session_id: str, version_id: str | None = None, user=Depends(current_user)):
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            return export_response(own(conn, session_access(conn, session_id, user, version_id), user))

    @app.get("/api/teacher/sessions/{session_id}/students")
    def students(session_id: str, version_id: str | None = None, user=Depends(teacher_user)):
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            draft = session_access(conn, session_id, user, version_id)
            rows = conn.execute("SELECT u.* FROM users u JOIN enrollments e ON e.user_id=u.id WHERE e.course_id=? AND u.role='student' ORDER BY u.name,u.id", (draft["course_id"],)).fetchall()
            result = []
            for row in rows:
                try:
                    detail, target = observed_detail(conn, session_id, row["id"], user, version_id)
                except HTTPException as exc:
                    if exc.status_code == 404 and not version_id:
                        continue  # Entire session has never been published yet.
                    raise
                work = workspace_response(conn, detail, target, tutor.status(conn, True), True)
                state = ensure_workspace(conn, session_id, target["id"], detail["_version_id"])
                result.append({"user": target, "answered": work["progress"]["answered"], "total": work["progress"]["total"],
                               "selected_reading": work["selected_reading"], "status": work["submission"]["status"], "last_active": state["last_active"],
                               "submitted_at": work["submission"]["submitted_at"], "version": work["version"], "available_versions": work["available_versions"]})
            return result

    def observed(conn, sid, uid, user, vid):
        detail, target = observed_detail(conn, sid, uid, user, vid)
        return detail, workspace_response(conn, detail, target, tutor.status(conn, True), True)

    @app.get("/api/teacher/sessions/{session_id}/students/{user_id}/workspace")
    def observe(session_id: str, user_id: str, version_id: str | None = None, user=Depends(teacher_user)):
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            return observed(conn, session_id, user_id, user, version_id)[1]

    @app.post("/api/teacher/sessions/{session_id}/students/{user_id}/review")
    def review(session_id: str, user_id: str, payload: m.Review, version_id: str | None = None, user=Depends(teacher_user)):
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            detail, work = observed(conn, session_id, user_id, user, version_id)
            from .guided_state import ensure_no_guided_request
            ensure_no_guided_request(conn, session_id, user_id, detail["_version_id"])
            if work["submission"]["status"] not in ("submitted", "confirmed", "needs_revision"):
                raise HTTPException(409, "Student must submit work before teacher review")
            conn.execute("UPDATE workspaces SET status=?,reviewed_at=?,teacher_note=? WHERE session_id=? AND user_id=? AND version_id=?", (payload.status, now(), payload.note, session_id, user_id, detail["_version_id"]))
            return workspace_response(conn, detail, work["user"], tutor.status(conn, True), True)

    @app.get("/api/teacher/sessions/{session_id}/students/{user_id}/export")
    def export_student(session_id: str, user_id: str, version_id: str | None = None, user=Depends(teacher_user)):
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            return export_response(observed(conn, session_id, user_id, user, version_id)[1])
