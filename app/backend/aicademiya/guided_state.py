"""Persistent lesson state and public projections (quiz keys never leave this module)."""
import json
from datetime import datetime
from fastapi import HTTPException
from .teaching import effective_profile
from .services import active_questions, reading_groups


def key(detail, user):
    return (detail["id"], user["id"], detail.get("_version_id", ""))


def load_state(conn, detail, user):
    row = conn.execute("SELECT state_json FROM tutor_runs WHERE session_id=? AND user_id=? AND version_id=?", key(detail, user)).fetchone()
    if row:
        state = json.loads(row[0])
    else:
        state = {"phase": "not_started", "started_at": None, "updated_at": None, "current_question_id": None,
                 "question_states": {}, "quiz": {"status": "not_offered", "answered": 0, "total": 0, "correct": None},
                 "reading": {"answered": 0, "total": 0}, "quiz_items": [], "reading_items": [], "optional_answers": []}
    for q in detail.get("questions", []):
        if q["id"] not in state["question_states"]:
            count = conn.execute("SELECT count(*) FROM revisions WHERE session_id=? AND user_id=? AND version_id=? AND question_id=?", (*key(detail, user), q["id"])).fetchone()[0]
            existing = conn.execute("SELECT answer FROM attempts WHERE session_id=? AND user_id=? AND version_id=? AND question_id=?", (*key(detail, user), q["id"])).fetchone()
            if existing and existing[0].strip():
                count = max(1, count)
            state["question_states"][q["id"]] = {"status": "in_progress" if count else "not_started", "answer_count": count, "hint_count": 0, "last_outcome": "unknown"}
    return state


def save_state(conn, detail, user, state):
    conn.execute("INSERT INTO tutor_runs VALUES(?,?,?,?) ON CONFLICT(session_id,user_id,version_id) DO UPDATE SET state_json=excluded.state_json", (*key(detail, user), json.dumps(state, ensure_ascii=False)))


def public_state(conn, detail, user, workspace):
    state = load_state(conn, detail, user)
    p = effective_profile(detail)
    qids = [q["id"] for q in active_questions(detail, workspace["selected_reading"])]
    questions = {qid: state["question_states"][qid] for qid in qids}
    if state["phase"] == "worksheet":
        select_current(detail, state, workspace["selected_reading"])
    pending = conn.execute("SELECT request_id FROM tutor_requests WHERE session_id=? AND user_id=? AND version_id=? AND status='pending' ORDER BY rowid LIMIT 1", key(detail, user)).fetchone()
    completed = conn.execute("SELECT request_id FROM tutor_requests WHERE session_id=? AND user_id=? AND version_id=? AND status='done' ORDER BY rowid DESC LIMIT 1", key(detail, user)).fetchone()
    start, end = state["started_at"], state["updated_at"]
    span = max(0, int((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds())) if start and end else 0
    return {**{k: state[k] for k in ("phase", "started_at", "updated_at", "current_question_id", "quiz", "reading")},
            "elapsed_seconds": span, "completed_question_ids": [qid for qid in qids if questions[qid]["status"] == "discussed"],
            "question_states": questions, "presentation": p["presentation"], "idle_hint_seconds": p["idle_hint_seconds"],
            "pending_request_id": pending[0] if pending else None, "last_completed_request_id": completed[0] if completed else None}


def ensure_no_guided_request(conn, sid, uid, vid):
    if conn.execute("SELECT 1 FROM tutor_requests WHERE session_id=? AND user_id=? AND version_id=? AND status='pending'", (sid, uid, vid)).fetchone():
        raise HTTPException(409, "Wait for the pending guided request before changing this run")
    # A new explicit mutation may replace a failed request. Keep its raw
    # message, but never replay its older state over subsequently saved work.
    conn.execute("UPDATE tutor_requests SET status='superseded' WHERE session_id=? AND user_id=? AND version_id=? AND status='failed'", (sid, uid, vid))


def select_current(detail, state, selected):
    groups = {g["id"]: i for i, g in enumerate(detail.get("groups", []))}
    questions = sorted(active_questions(detail, selected), key=lambda q: (groups.get(q["group_id"], len(groups)), q.get("ordinal", 1)))
    state["current_question_id"] = next((q["id"] for q in questions if state["question_states"][q["id"]]["status"] != "discussed"), None)
    return state["current_question_id"]


def public_question(detail, qid):
    from .services import QUESTION_FIELDS
    from urllib.parse import urlencode
    raw = next((q for q in detail.get("questions", []) if q["id"] == qid), None)
    if not raw:
        return None
    q = {k: raw[k] for k in QUESTION_FIELDS if k in raw}
    q["images"] = [{k: img.get(k, "") for k in ("label", "url", "alt")} for img in raw.get("images", [])]
    for img in q["images"]:
        if detail.get("_version_id") and img["url"].startswith("/api/materials/"):
            img["url"] = img["url"].split("?", 1)[0] + "?" + urlencode({"version_id": detail["_version_id"]})
    return q


def presentation(detail, state, selected):
    """Public metadata describes the question PRESENTED, not just the feedback target."""
    phase = state["phase"]
    data = {"phase": phase, "kind": "question"}
    if phase == "worksheet":
        qid = select_current(detail, state, selected)
        if qid:
            data["presented_question"] = public_question(detail, qid)
        elif reading_groups(detail) and not selected:
            data["kind"] = "reading_choice"
            data["reading_choices"] = [{k: g[k] for k in ("id", "title", "description") if k in g} for g in detail.get("groups", []) if g.get("kind") == "reading"]
    elif phase in ("quiz", "reading"):
        items = state["quiz_items" if phase == "quiz" else "reading_items"]
        index = state[phase]["answered"]
        if index < len(items):
            item = items[index]
            state["current_question_id"] = item["id"]
            data["presented_question"] = {k: item[k] for k in ("id", "prompt", "options", "source_labels") if k in item}
            data["presented_question"].update(type="single_choice" if phase == "quiz" else "reading_response", images=[])
    else:
        state["current_question_id"] = None
        data["kind"] = phase
        if phase == "wrap_up":
            ids = [q["id"] for q in active_questions(detail, selected)]
            data["summary"] = {"worksheet_total": len(ids), "worksheet_discussed": sum(state["question_states"][qid]["status"] == "discussed" for qid in ids),
                               "recorded_answer_turns": sum(state["question_states"][qid]["answer_count"] for qid in ids),
                               "help_turns": sum(state["question_states"][qid]["hint_count"] for qid in ids),
                               "quiz": dict(state["quiz"]), "reading": dict(state["reading"])}
    return data


def presentation_text(data):
    q = data.get("presented_question")
    if q:
        text = "\n\n" + ("Optional formative practice" if data["phase"] == "quiz" else "Reading discussion" if data["phase"] == "reading" else "Worksheet question") + ":\n" + q["prompt"]
        if q.get("options"):
            text += "\n" + "\n".join(f"{i+1}. {v}" for i, v in enumerate(q["options"]))
        if q.get("images"):
            text += "\nRefer to the configured figures shown with this question."
        return text
    if data.get("kind") == "reading_choice":
        return "\n\nChoose one worksheet reading path: " + "; ".join(g["title"] + " (" + g["id"] + ")" for g in data["reading_choices"]) + "."
    if data["phase"] == "quiz_offer":
        return "\n\nWould you like an optional five-question formative quiz? Reply yes to try it or no to skip it. This does not affect required submission."
    if data["phase"] == "wrap_up":
        summary = data["summary"]
        quiz, reading = summary["quiz"], summary["reading"]
        text = f"\n\nDiscussion summary: {summary['worksheet_discussed']} of {summary['worksheet_total']} configured worksheet questions discussed; {summary['recorded_answer_turns']} recorded answer turns and {summary['help_turns']} help turns."
        text += f"\nOptional formative quiz: {quiz['status']}, {quiz['answered']} of {quiz['total']} items answered."
        if quiz["correct"] is not None:
            text += f" Formative correct responses: {quiz['correct']} (not a formal grade)."
        text += f"\nPublic reading discussion: {reading['answered']} of {reading['total']} questions answered."
        return text + "\nThis is a discussion summary, not a formal grade or teacher confirmation. Review your saved worksheet responses; final submission is your explicit action. Reply when you are ready to finish this conversation."
    if data["phase"] == "complete":
        return "\n\nConversation complete. Your work has not been submitted or teacher-confirmed automatically."
    return ""
