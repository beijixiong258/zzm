"""Server-owned transitions. Inference returns advice, never database mutations."""
import copy
import re
from .ai import ModelFailure
from .guided_director import direct, opt_in, pure_help
from .guided_state import select_current, public_question, presentation, presentation_text
from .services import active_questions, reading_groups
from .teaching import effective_profile
from .db import new_id
from .guided_reading import has_document_text


def run_lesson(tutor, settings, workspace, detail, accepted, payload, *, opening=False):
    state = copy.deepcopy(accepted)
    state.pop("_last_document_read_coverage",None)
    selected = workspace["selected_reading"]
    texts, citations = [], []
    answer_event, intent, target = None, "ask", None
    p = effective_profile(detail)
    public = workspace.get("_public_materials", workspace["session"]["materials"])
    # Optional phases always use public evidence only; private sources selected
    # for the current worksheet question are supplied separately by the route.
    public = [m for m in public if m.get("visibility") == "student" and m.get("kind") != "answer_key" and m.get("status") in ("ready", "needs_review") and (m.get("excerpt") or m.get("_document"))]

    def generate(task):
        result, refs = direct(tutor, settings, workspace, detail, state, {}, None, public, task=task)
        citations.extend(refs)
        texts.append(result.text)
        return result

    def enter(phase):
        state["phase"] = "quiz_offer" if phase == "quiz" else phase
        state["current_question_id"] = None
        if phase == "quiz":
            if state["quiz"]["status"] in ("completed", "skipped"):
                advance()
            elif state["quiz"]["status"] == "active":
                state["phase"] = "quiz"
            else:
                state["quiz"]["status"] = "offered"
        elif phase == "reading":
            if state["reading_items"]:
                if state["reading"]["answered"] == state["reading"]["total"]:
                    advance()
                return
            if not any((m.get("excerpt") or has_document_text([m])) and m.get("source_label") for m in public):
                texts.append("Reading discussion is unavailable: no accessible public reading evidence was configured. No reading questions have been invented.")
                advance()
            else:
                result = generate("reading_generate")
                state["reading_items"] = [{"id": "reading-" + new_id(), **item.model_dump()} for item in result.items]
                state["reading"] = {"answered": 0, "total": len(result.items)}

    def advance():
        current = "quiz" if state["phase"] in ("quiz_offer", "quiz") else state["phase"]
        index = p["phases"].index(current)
        if index + 1 < len(p["phases"]):
            enter(p["phases"][index + 1])
        else:
            state["phase"] = "complete"
            state["current_question_id"] = None

    def settle_worksheet():
        if state["phase"] == "worksheet" and not select_current(detail, state, selected) and not (reading_groups(detail) and not selected):
            if not active_questions(detail, selected):
                texts.append("There are no configured required worksheet questions on this path. No required questions have been invented.")
            advance()

    if opening:
        state["phase"] = p["phases"][0]
        if state["phase"] == "worksheet":
            select_current(detail, state, selected)
        question = public_question(detail, state["current_question_id"])
        result, refs = direct(tutor, settings, workspace, detail, state, {}, question, public, task="start")
        if result.intent != "none" or result.question_id is not None or result.outcome != "unknown" or result.reading_group_id:
            raise ModelFailure("Model returned an invalid guided opening transition. Retry this opening request.")
        texts.append(result.text)
        citations.extend(refs)
        settle_worksheet()
    else:
        phase = state["phase"]
        if phase == "worksheet":
            select_current(detail, state, selected)
        target = payload.get("question_id") or state["current_question_id"]
        question = public_question(detail, target)
        review = bool(question and target != state["current_question_id"] or payload.get("action") == "review_question")
        if phase in ("quiz", "reading") and not question:
            item = next((x for x in state["quiz_items" if phase == "quiz" else "reading_items"] if x["id"] == target), None)
            question = {k: item[k] for k in ("id", "prompt", "options", "source_labels") if k in item} if item else None
        bypass = payload.get("action") == "skip_quiz"
        if bypass:
            texts.append("Optional quiz skipped. Required worksheet submission is unchanged.")
            state["quiz"]["status"] = "skipped"
            advance()
        else:
            eval_state = {**state, "phase": "worksheet"} if review else state
            result, refs = direct(tutor, settings, workspace, detail, eval_state, payload, question,
                                  workspace.get("_question_materials", public) if question and "group_id" in question else public,
                                  private_reference=workspace.get("_private_reference"), private_materials=workspace.get("_private_materials"))
            if eval_state is not state and "document_read_progress" in eval_state:
                state["document_read_progress"]=eval_state["document_read_progress"]
                state["_last_document_read_coverage"]=eval_state.get("_last_document_read_coverage",[])
            texts.append(result.text)
            citations.extend(refs)
            intent, target = result.intent, result.question_id
            # A completed conversation remains open for clarification until
            # explicit submission. Only an actually recorded prior question
            # can receive a revision; generic follow-ups create no answers.
            if phase == "complete" and target in workspace["attempts"]:
                review = True
            if payload.get("action") in ("hint", "review_question") or pure_help(payload["message"]):
                # A pure ask cannot overwrite an answer even if the provider
                # erroneously classified it as an answer. Ignore its outcome.
                intent = "ask"
                result.outcome = "unknown"
                target = payload.get("question_id") or target or state["current_question_id"]
            if payload.get("question_id") and target != payload["question_id"]:
                raise ModelFailure("Model associated the response with the wrong configured question. Your raw message remains saved; retry.")
            if result.reading_group_id is not None and intent != "choice":
                raise ModelFailure("Model returned a reading selection without a choice intent. Retry this request.")
            if phase == "worksheet" or review:
                allowed = {q["id"] for q in active_questions(detail, selected)}
                if target is not None and (target not in allowed or target != state["current_question_id"] and target not in workspace["attempts"]):
                    raise ModelFailure("Model used an unknown or unattempted question ID. Your raw message remains saved; retry.")
                if intent == "choice":
                    if review or selected or state["current_question_id"] is not None:
                        raise ModelFailure("Model attempted to change the reading branch at the wrong point. Retry this request.")
                    choice = result.reading_group_id
                    groups = {g["id"]: g for g in detail.get("groups", []) if g.get("kind") == "reading"}
                    if choice not in groups or result.outcome != "unknown" or target is not None:
                        raise ModelFailure("Model returned an invalid reading path. Retry this request.")
                    # The model cannot opt the learner into a branch without a
                    # recognizable user selection of its real ID/title/number.
                    value = payload["message"].strip().casefold()
                    recognized = {choice.casefold(), groups[choice]["title"].casefold(), str(list(groups).index(choice)+1)}
                    if value not in recognized and not any(re.search(r"(?<!\w)" + re.escape(v) + r"(?!\w)", value) for v in recognized if len(v) > 1):
                        raise ModelFailure("Reading selection was not explicit in the learner message. Choose a displayed reading path.")
                    selected = choice
                    select_current(detail, state, selected)
                elif intent in ("answer", "mixed"):
                    if not target or result.outcome not in ("needs_retry", "sufficient") or payload.get("action") == "review_question":
                        raise ModelFailure("Model returned an invalid answer transition. Your raw message remains saved; retry.")
                    answer_event = {"question_id": target, "answer": payload["message"], "outcome": result.outcome}
                    qs = state["question_states"][target]
                    qs["answer_count"] += 1
                    qs["last_outcome"] = result.outcome
                    qs["status"] = "discussed" if result.outcome == "sufficient" else "in_progress"
                    if review and result.outcome == "needs_retry" and phase != "worksheet":
                        state["phase"] = "worksheet"
                        select_current(detail, state, selected)
                elif intent in ("ask", "none"):
                    if intent == "none" and target is not None:
                        raise ModelFailure("Model did not classify the question-associated learner turn. Retry this request.")
                    if result.outcome != "unknown":
                        raise ModelFailure("A help request cannot be marked sufficient. Retry this request.")
                    if target:
                        qs = state["question_states"][target]
                        qs["hint_count"] += 1
                        if qs["status"] == "not_started":
                            qs["status"] = "in_progress"
                else:
                    raise ModelFailure("Model returned an intent not valid for the worksheet. Retry this request.")
                if not review:
                    settle_worksheet()
            elif phase == "quiz_offer":
                if target is not None or result.outcome != "unknown":
                    raise ModelFailure("Quiz invitation cannot assess a worksheet response. Retry this request.")
                explicit = opt_in(payload["message"])
                if intent == "accept_quiz" and explicit is not False and not pure_help(payload["message"]):
                    # Natural explicit opt-in may be classified by the model;
                    # a question or a decline is never consent.
                    if explicit is not True and not re.search(r"\b(?:try|take|start|want|yes)\b.*\bquiz\b|\bquiz\b.*\b(?:please|yes)\b", payload["message"], re.I):
                        raise ModelFailure("Quiz opt-in must be explicit. Reply yes to start or no to skip.")
                    generated = generate("quiz_generate")
                    state["quiz_items"] = [{"id": "quiz-" + new_id(), **item.model_dump()} for item in generated.items]
                    state["quiz"] = {"status": "active", "answered": 0, "total": 5, "correct": 0}
                    state["phase"] = "quiz"
                elif intent == "decline_quiz" and explicit is not True:
                    state["quiz"]["status"] = "skipped"
                    advance()
                elif intent not in ("ask", "none"):
                    raise ModelFailure("Model returned an invalid quiz invitation response. Retry this request.")
            elif phase in ("quiz", "reading"):
                if target != state["current_question_id"] or result.reading_group_id is not None:
                    raise ModelFailure("Model associated optional practice with the wrong item. Retry this request.")
                if intent in ("answer", "mixed"):
                    if result.outcome not in ("sufficient", "needs_retry"):
                        raise ModelFailure("Optional answer has no usable formative outcome. Retry this request.")
                    index = state[phase]["answered"]
                    state["optional_answers"].append({"phase": phase, "question_id": target, "answer": payload["message"], "outcome": result.outcome})
                    # Quiz records one scored practice response per item.
                    # Reading is a discussion: a partial attempt remains on
                    # the same prompt so the requested fuller response matters.
                    if phase == "quiz" or result.outcome == "sufficient":
                        state[phase]["answered"] += 1
                    if phase == "quiz":
                        item = state["quiz_items"][index]
                        raw = payload["message"].strip()
                        number = (int(raw)-1 if len(raw) <= 3 else -1) if raw.isascii() and raw.isdigit() else ord(raw.upper())-65 if len(raw) == 1 and raw.upper() in "ABCDEF" else None
                        correct = number == item["correct_index"] if number is not None else result.outcome == "sufficient"
                        state["quiz"]["correct"] += int(correct)
                        state["optional_answers"][-1]["outcome"] = "sufficient" if correct else "needs_retry"
                        texts.append("Formative practice: " + ("correct" if correct else "not yet correct") + ". " + item["explanation"])
                    if state[phase]["answered"] == state[phase]["total"]:
                        if phase == "quiz":
                            state["quiz"]["status"] = "completed"
                        advance()
                elif intent != "ask" or result.outcome != "unknown":
                    raise ModelFailure("Model returned an invalid optional-phase response. Retry this request.")
            elif phase == "complete":
                if intent not in ("none", "ask") or target is not None or result.outcome != "unknown":
                    raise ModelFailure("A completed-session follow-up cannot create new required work. Retry this request.")
            elif phase in ("warmup", "wrap_up"):
                if intent not in ("none", "ask") or target is not None or result.outcome != "unknown":
                    raise ModelFailure("Model returned an invalid lesson-phase transition. Retry this request.")
                if payload.get("action") != "hint" and not pure_help(payload["message"]):
                    advance()
                    settle_worksheet()
            else:
                raise ModelFailure("This lesson phase does not accept a new transition.")
    metadata = presentation(detail, state, selected)
    if not opening and target and target != state["current_question_id"] and intent == "ask" and public_question(detail, target):
        metadata = {"phase": state["phase"], "kind": "review", "presented_question": public_question(detail, target)}
    if opening:
        metadata["opening"] = True
    # Preserve the complete raw transcript/export while exposing explicit display
    # parts. The card replaces only the appended presentation, never feedback.
    narrative = "\n\n".join(texts)
    appended = presentation_text(metadata)
    metadata.update(narrative_text=narrative, presentation_text=appended)
    coverage=state.pop("_last_document_read_coverage",[])
    if coverage:metadata["document_read_coverage"]=coverage
    return {"state": state, "selected": selected, "text": narrative + appended,
            "metadata": metadata, "citations": citations, "answer": answer_event, "intent": intent, "target": target}
