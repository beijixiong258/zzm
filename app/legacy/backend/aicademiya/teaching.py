"""Versioned teaching framework. Compilation is pure and makes no model calls."""
from .models import TeachingProfile


def effective_profile(detail):
    raw = detail.get("teaching_profile")
    if raw is not None:
        return TeachingProfile.model_validate(raw).model_dump()
    # Never rewrite existing catalog/session/snapshot JSON to install defaults.
    return TeachingProfile(reference_delivery="on_request").model_dump()


def compile_teaching(detail):
    p = effective_profile(detail)
    sections = []
    def add(key, title, text):
        sections.append({"id": key, "title": title, "text": text})
    add("role", "Teaching role", "You are AIcademiya's formative tutor. Discuss work, not formal mastery. Never submit, grade formally or confirm work for the learner or teacher.")
    add("goals", "Learning goals and language", "Language: " + detail.get("teaching_language", "en") + "\n" + "\n".join(detail.get("learning_objectives", [])))
    for key, title in (("background", "Background"), ("student_profile", "Student profile"), ("response_strategies", "Response strategies"), ("tone", "Tone")):
        add(key, title, p[key])
    add("feedback", "Progressive feedback", "Detail: " + p["response_detail"] + ". Identify a specific strength or misconception, give a focused next-step hint and invite revision. Adapt help to the actual response and prior assistance, never a fixed number of wrong attempts. Pure help requests and previous-question follow-ups are not new answers. For mixed answers and questions, address both. An existing attempt is evidence of work, not correctness.")
    add("phases", "Lesson sequence", " → ".join(p["phases"]) + ". Worksheet uses only stored questions and the selected reading branch. Quiz is optional: five persisted formative items after explicit opt-in. Reading discussion uses public materials and at most " + str(p["reading_question_count"]) + " questions. Empty worksheets and missing reading evidence must be acknowledged, not invented.")
    add("reading", "Reading focus", p["reading_focus"])
    add("references", "Reference rules", "Eligibility: " + detail.get("reference_policy", "after_attempt") + ". Delivery: " + p["reference_delivery"] + ". Never expose unrevealed private references or teacher sources. The application alone reveals an eligible reference; before reveal provide hints, not an exact option, token or paraphrased model answer.")
    add("additional", "Additional instructions", detail.get("instructions", ""))
    warnings = []
    if not detail.get("questions"):
        warnings.append("No configured worksheet questions; required questions will not be invented.")
    if "reading" in p["phases"]:
        warnings.append("Reading discussion requires accessible public material evidence; private worksheets and keys are excluded.")
    if not detail.get("teaching_profile"):
        warnings.append("Legacy effective profile: references remain on_request; existing reference eligibility is unchanged.")
    return {"text": "\n\n".join(s["title"] + "\n" + s["text"] for s in sections), "sections": sections, "warnings": warnings}
