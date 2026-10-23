"""Stable live evidence selection with real material identity for teacher review."""
import re

PUBLIC_CHARS = 32000
PRIVATE_CHARS = 8000
REQUEST_BYTES = 60000


def bounded_evidence_items(materials, question=None, *, private=False, budget=PUBLIC_CHARS):
    """Return (material, prompt item) pairs; IDs never come from display labels.

    Ranking, iteration order, slices and optional warning bytes are the original
    bounded_evidence algorithm. Keep the identity outside the model prompt.
    """
    eligible = [m for m in materials if m.get("kind") != "answer_key" and m.get("status") in ("ready", "needs_review")
                and m.get("excerpt") and (private or m.get("visibility") == "student")]
    words = set(re.findall(r"[A-Za-z]{3,}", (question or {}).get("prompt", "").lower()))
    if len(eligible) <= 8:
        ranked = [(0, i, m, m["excerpt"][:4000]) for i, m in enumerate(eligible)]
    else:
        ranked = []
        for index, material in enumerate(eligible):
            text = material["excerpt"][:50000]
            chunks = [text[n:n+2000] for n in range(0, len(text), 1500)]
            score, snippet = max(((len(words & set(re.findall(r"[A-Za-z]{3,}", chunk.lower()))), chunk) for chunk in chunks), key=lambda pair: pair[0])
            ranked.append((score, index, material, snippet))
        ranked.sort(key=lambda x: (-x[0], x[1]))
    context = []
    for _, _, material, snippet in ranked:
        if budget <= 0:
            break
        snippet = snippet[:min(4000, budget)]
        item = {"source_label": material.get("source_label", ""), "excerpt": snippet}
        if material.get("warning"):
            item["warning"] = material["warning"][:500]
        context.append((material, item))
        budget -= len(snippet)
    return context


def bounded_evidence(materials, question=None, *, private=False, budget=PUBLIC_CHARS):
    return [item for _, item in bounded_evidence_items(materials, question, private=private, budget=budget)]


def optional_evidence_phase(phase, task="turn"):
    return phase in ("quiz", "quiz_offer", "reading") or task.endswith("generate")
