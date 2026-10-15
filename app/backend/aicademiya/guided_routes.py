"""Authenticated guided API; reserve → infer outside SQLite → atomic commit."""
import hashlib
import html
import json
from typing import Literal
from fastapi import Depends, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from . import models as m
from .ai import ModelFailure
from .db import now, new_id
from .services import ensure_workspace, editable, workspace_response, save_message, save_answer, mark_active, active_questions
from .version_context import session_access, ensure_learning_write, availability, is_staff, published_detail
from .teaching import effective_profile
from .authoring import selected_tutor_materials
from .guided_state import key, load_state, save_state, select_current, ensure_no_guided_request, public_question, presentation_text
from .guided_engine import run_lesson
from .teacher_preview import reserve_guard, commit_guard
from .course_lifecycle import require_live_course


def register_guided_routes(app, db, tutor, current_user, teacher_user):
    def own(conn, detail, user):
        return workspace_response(conn, detail, user, tutor.status(conn, is_staff(user)), is_staff(user))

    def reserve(sid, user, version_id, payload, opening):
        # preview_id is application identity, never learner/model content. Ordinary
        # student and legacy fingerprints remain byte-compatible with Stage3.
        data = payload.model_dump(exclude={"request_id", "preview_id"})
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            detail = session_access(conn, sid, user, version_id)
            accepted_preview = reserve_guard(conn, detail, user, payload.preview_id)
            fingerprint_data = {"operation": "start" if opening else "turn", **data}
            if accepted_preview:
                fingerprint_data["preview_id"] = accepted_preview["id"]
            fingerprint = hashlib.sha256(json.dumps(fingerprint_data, sort_keys=True).encode()).hexdigest()
            runkey = key(detail, user)
            workspace = ensure_workspace(conn, *runkey[:2], runkey[2])
            state = load_state(conn, detail, user)
            rid = payload.request_id
            if opening and not rid and state["started_at"]:
                return own(conn, detail, user), None
            if opening and not rid:
                existing = conn.execute("SELECT request_id FROM tutor_requests WHERE session_id=? AND user_id=? AND version_id=? AND status IN ('pending','failed') ORDER BY rowid LIMIT 1", runkey).fetchone()
                rid = existing[0] if existing else new_id()
            requestkey = (*runkey, rid)
            old = conn.execute("SELECT * FROM tutor_requests WHERE session_id=? AND user_id=? AND version_id=? AND request_id=?", requestkey).fetchone()
            if old:
                if old["fingerprint"] != fingerprint:
                    raise HTTPException(409, "request_id was already used with different content or action")
                if old["status"] == "done":
                    return own(conn, detail, user), None
                if old["status"] == "pending":
                    raise HTTPException(409, "This guided request is still pending")
                if old["status"] == "superseded":
                    raise HTTPException(409, "This failed request was replaced by newer saved work; its raw message is retained")
            if opening and state["started_at"]:
                return own(conn, detail, user), None
            ensure_learning_write(detail, user)
            # The normal unversioned-write stale-edition protection also applies.
            session_access(conn, sid, user, version_id, write=True)
            editable(workspace)
            if not old:
                ensure_no_guided_request(conn, *runkey)
            if conn.execute("SELECT 1 FROM chat_requests WHERE session_id=? AND user_id=? AND version_id=? AND status='pending'", runkey).fetchone():
                raise HTTPException(409, "Wait for the existing chat feedback before starting a guided request")
            if not opening:
                if state["phase"] == "not_started":
                    raise HTTPException(409, "Start this guided conversation before sending a turn")
                if state["phase"] == "worksheet":
                    select_current(detail, state, workspace["selected_reading"])
                if data["action"] == "skip_quiz" and state["phase"] not in ("quiz_offer", "quiz"):
                    raise HTTPException(409, "There is no optional quiz to skip")
                qid = data.get("question_id")
                allowed = {q["id"] for q in active_questions(detail, workspace["selected_reading"])}
                attempted = conn.execute("SELECT 1 FROM attempts WHERE session_id=? AND user_id=? AND version_id=? AND question_id=?", (*runkey, qid)).fetchone() if qid else None
                if qid and not (qid == state["current_question_id"] or qid in allowed and attempted):
                    raise HTTPException(409, "Question must be current or previously attempted on the selected path")
                if data["action"] == "review_question" and (not qid or not attempted):
                    raise HTTPException(422, "review_question requires an attempted worksheet question_id")
            settings = tutor.settings(conn)
            if not old:
                mid = None
                if not opening:
                    mid = save_message(conn, sid, user["id"], "user", data["message"], data.get("question_id"), settings["mode"], None, version_id=runkey[2])
                    mark_active(conn, sid, user["id"], version_id=runkey[2])
                    state["updated_at"] = conn.execute("SELECT created_at FROM messages WHERE id=?", (mid,)).fetchone()[0]
                    # Failed turns are still real recorded activity; record their
                    # timestamp without accepting an answer or advancing a phase.
                    save_state(conn, detail, user, state)
                plan = {"detail": detail, "state": state, "payload": data, "opening": opening, "message_id": mid}
                if accepted_preview:
                    plan["preview"] = accepted_preview
                conn.execute("INSERT INTO tutor_requests(session_id,user_id,version_id,request_id,fingerprint,status,created_at,plan_json) VALUES(?,?,?,?,?,?,?,?)", (*requestkey, fingerprint, "pending", now(), json.dumps({**plan, "detail": {k: v for k, v in detail.items() if k != "_materials"}}, ensure_ascii=False)))
            else:
                plan = json.loads(old["plan_json"])
                detail, state, data = plan["detail"], plan["state"], plan["payload"]
                if detail.get("_version_id"):
                    # File bindings are maintained by the immutable-edition
                    # backup/restore layer, not copied into request plans.
                    detail["_materials"] = published_detail(conn, sid, detail["_version_id"])["_materials"]
                conn.execute("UPDATE tutor_requests SET status='pending' WHERE session_id=? AND user_id=? AND version_id=? AND request_id=?", requestkey)
            context = own(conn, detail, user)
            qid = data.get("question_id") or state["current_question_id"]
            public, private = selected_tutor_materials(conn, detail, qid)
            context["_question_materials"], context["_private_materials"] = public, private
            context["_public_materials"], _ = selected_tutor_materials(conn, detail, None)
            context["_private_reference"] = tutor.reference_context(conn, detail, qid)
            created = conn.execute("SELECT created_at FROM tutor_requests WHERE session_id=? AND user_id=? AND version_id=? AND request_id=?", requestkey).fetchone()[0]
            return None, (requestkey, plan, settings, context, created)

    def execute(sid, user, version_id, payload, opening=False):
        resumed, job = reserve(sid, user, version_id, payload, opening)
        if resumed is not None:
            return resumed
        requestkey, plan, settings, context, created = job
        detail = plan["detail"]
        try:
            result = run_lesson(tutor, settings, context, detail, plan["state"], plan["payload"], opening=opening)
            with db.connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                require_live_course(conn, detail["course_id"])
                from .version_context import course_access
                course_access(conn, detail['course_id'], user)
                # Retention can remove the authorized run while inference is in
                # flight. Do not recreate expired work or commit an orphan.
                request = conn.execute("SELECT status FROM tutor_requests WHERE session_id=? AND user_id=? AND version_id=? AND request_id=?", requestkey).fetchone()
                if not request or request[0] != "pending":
                    raise HTTPException(409, "This accepted request no longer owns a pending learning run")
                if is_staff(user) and not requestkey[2] and not plan.get("preview"):
                    from .teacher_preview import legacy_write_guard
                    legacy_write_guard(conn, session_access(conn, sid, user), user)
                commit_guard(conn, sid, user, plan.get("preview"))
                stamp = now()
                state = result["state"]
                state["started_at"] = state["started_at"] or created
                state["updated_at"] = stamp
                for answer in state["optional_answers"]:
                    answer.setdefault("created_at", stamp)
                event = result["answer"]
                if event:
                    save_answer(conn, sid, user["id"], event["question_id"], event["answer"], requestkey[2])
                if plan["message_id"]:
                    learner_metadata = {"kind": "learner_turn", "phase": plan["state"]["phase"], "detected_intent": result["intent"]}
                    if event:
                        learner_metadata["formative_outcome"] = event["outcome"]
                    conn.execute("UPDATE messages SET question_id=?,intent=?,metadata_json=? WHERE id=?", (result["target"], "answer" if result["intent"] in ("answer", "mixed") else "ask", json.dumps(learner_metadata), plan["message_id"]))
                conn.execute("UPDATE workspaces SET selected_reading=? WHERE session_id=? AND user_id=? AND version_id=?", (result["selected"], *requestkey[:3]))
                mid = save_message(conn, sid, user["id"], "assistant", result["text"], result["target"], settings["mode"], "answer" if event else "ask", result["citations"], version_id=requestkey[2])
                # Automatic delivery is a distinct server action after sufficient
                # feedback, not permission for a model to reveal private keys.
                if event and event["outcome"] == "sufficient" and effective_profile(detail)["reference_delivery"] == "after_sufficient_answer":
                    workspace = ensure_workspace(conn, sid, user["id"], requestkey[2])
                    policy = detail.get("reference_policy", "after_attempt")
                    value = detail.get("reference_answers", {}).get(event["question_id"])
                    operational = conn.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
                    current_version = conn.execute("SELECT published_version_id FROM courses WHERE id=?", (detail["course_id"],)).fetchone()[0]
                    enrollment = conn.execute("SELECT archived_at FROM enrollments WHERE course_id=? AND user_id=?", (detail["course_id"], user["id"])).fetchone()
                    eligible_run = is_staff(user) or (requestkey[2] == current_version and availability(operational)["effective_active"] and enrollment and not enrollment[0] and workspace["status"] not in ("submitted", "confirmed"))
                    if value and eligible_run and (policy != "after_submit" or workspace["submitted_at"]):
                        conn.execute("UPDATE attempts SET reference_revealed=1 WHERE session_id=? AND user_id=? AND version_id=? AND question_id=?", (*requestkey[:3], event["question_id"]))
                        # Put the comparison before the next question, and keep
                        # message.question_id on the feedback target.
                        tail = "\n\nInstructor reference comparison (not a formal grade):\n" + value
                        next_prompt = presentation_text(result["metadata"])
                        base = result["text"][:-len(next_prompt)] if next_prompt and result["text"].endswith(next_prompt) else result["text"]
                        conn.execute("UPDATE messages SET content=? WHERE id=?", (base + tail + next_prompt, mid))
                        result["metadata"]["reference_question_id"] = event["question_id"]
                if event:
                    result["metadata"]["formative_outcome"] = event["outcome"]
                elif plan["message_id"] and result["state"]["optional_answers"]:
                    latest = result["state"]["optional_answers"][-1]
                    if latest["question_id"] == result["target"] and latest["answer"] == plan["payload"].get("message") and result["intent"] in ("answer", "mixed"):
                        result["metadata"]["formative_outcome"] = latest["outcome"]
                        learner_metadata["formative_outcome"] = latest["outcome"]
                        conn.execute("UPDATE messages SET metadata_json=? WHERE id=?", (json.dumps(learner_metadata), plan["message_id"]))
                conn.execute("UPDATE messages SET metadata_json=? WHERE id=?", (json.dumps(result["metadata"], ensure_ascii=False), mid))
                mark_active(conn, sid, user["id"], version_id=requestkey[2])
                save_state(conn, detail, user, state)
                conn.execute("UPDATE tutor_requests SET status='done' WHERE session_id=? AND user_id=? AND version_id=? AND request_id=?", requestkey)
                conn.execute("DELETE FROM meta WHERE key='ai_last_error'")
                operational = conn.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
                detail.update(availability(operational))
                detail["_current_version_id"] = conn.execute("SELECT published_version_id FROM courses WHERE id=?", (detail["course_id"],)).fetchone()[0]
                if not is_staff(user):
                    enrollment = conn.execute("SELECT archived_at FROM enrollments WHERE course_id=? AND user_id=?", (detail["course_id"], user["id"])).fetchone()
                    detail["_enrollment_archived"] = not enrollment or bool(enrollment[0])
                return own(conn, detail, user)
        except ModelFailure as exc:
            with db.connect() as conn:
                conn.execute("UPDATE tutor_requests SET status='failed' WHERE session_id=? AND user_id=? AND version_id=? AND request_id=?", requestkey)
            tutor.record_error(str(exc))
            raise HTTPException(502, str(exc)) from None
        except Exception:
            with db.connect() as conn:
                conn.execute("UPDATE tutor_requests SET status='failed' WHERE session_id=? AND user_id=? AND version_id=? AND request_id=?", requestkey)
            raise

    @app.post("/api/sessions/{session_id}/tutor/start")
    def start(session_id: str, payload: m.TutorStart, version_id: str | None = None, user=Depends(current_user)):
        return execute(session_id, user, version_id, payload, opening=True)

    @app.post("/api/sessions/{session_id}/tutor/turn")
    def turn(session_id: str, payload: m.TutorTurn, version_id: str | None = None, user=Depends(current_user)):
        return execute(session_id, user, version_id, payload)

    @app.get("/api/sessions/{session_id}/transcript")
    def transcript(session_id: str, version_id: str | None = None, format: Literal["html", "txt"] = "html", user=Depends(current_user)):
        with db.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            detail = session_access(conn, session_id, user, version_id)
            work = own(conn, detail, user)
            state = load_state(conn, detail, user)
        title = "AIcademiya raw transcript — " + detail["title"]
        lines = [title, "Session ID: " + session_id, "Version ID: " + (work["version"]["id"] or "draft"),
                 "Version number: " + str(work["version"]["number"]), "Learner: " + user["name"] + " (" + user["id"] + ")",
                 "Guided start: " + str(work["tutor"]["started_at"]), "Last guided update: " + str(work["tutor"]["updated_at"]),
                 "Timestamp span (not active study time): " + str(work["tutor"]["elapsed_seconds"]) + " seconds", "", "RAW MESSAGES"]
        for message in work["messages"]:
            lines.extend([f"[{message['created_at']}] {message['role']} | question={message['question_id']} | mode={message['mode']}", message["content"], ""])
        lines.append("RECORDED WORKSHEET RESPONSES")
        for qid, attempt in work["attempts"].items():
            lines.extend([f"{qid} [{attempt['updated_at']}]", attempt["answer"], "Recorded revisions:"])
            for rev in attempt["revisions"]:
                lines.extend(["[" + rev["created_at"] + "]", rev["answer"]])
        lines.append("RECORDED OPTIONAL RESPONSES (formative, not required worksheet work)")
        for answer in state["optional_answers"]:
            lines.extend([f"[{answer['created_at']}] {answer['phase']} | question={answer['question_id']} | formative={answer['outcome']}", answer["answer"]])
        text = "\n".join(lines)
        filename = "aicademiya-transcript-" + "".join(c for c in session_id if c.isascii() and (c.isalnum() or c in "-_.")) + "." + format
        headers = {"Content-Disposition": f'attachment; filename="{filename}"', "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"}
        if format == "txt":
            return PlainTextResponse(text, headers=headers)
        headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
        return HTMLResponse("<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>" + html.escape(title) + "</title><style>body{font:16px system-ui;max-width:960px;margin:2rem auto;padding:1rem}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>" + html.escape(title) + "</h1><pre>" + html.escape(text) + "</pre></html>", headers=headers)
