import { describe, it, expect } from "vitest";
import {
  activeQuestions,
  canReveal,
  canSubmit,
  isLocked,
  dateLabel,
} from "../src/study";
import { fixtureWorkspace } from "./fixtures";
describe("explicit fixture: study rules", () => {
  it("counts only the active reading branch, even with retained answers", () => {
    const w = fixtureWorkspace();
    w.attempts.bray = {
      question_id: "bray",
      answer: "Retained alternate answer",
      revision_count: 1,
      updated_at: "2026-01-01T00:00:00Z",
      reference_revealed: false,
    };
    expect(activeQuestions(w).map((q) => q.id)).toEqual(["core", "pong"]);
  });
  it("does not reveal references before an actual attempt", () => {
    const w = fixtureWorkspace();
    expect(canReveal(w, "core")).toBe(false);
    w.attempts.core = {
      question_id: "core",
      answer: "   ",
      revision_count: 1,
      updated_at: "",
      reference_revealed: false,
    };
    expect(canReveal(w, "core")).toBe(false);
    w.attempts.core.answer = "My attempt";
    expect(canReveal(w, "core")).toBe(true);
  });
  it("honours feedback and submission reveal policies", () => {
    const w = fixtureWorkspace();
    w.attempts.core = {
      question_id: "core",
      answer: "Attempt",
      revision_count: 1,
      updated_at: "2026-10-03T08:00:00Z",
      reference_revealed: false,
    };
    w.session.reference_policy = "after_feedback";
    expect(canReveal(w, "core")).toBe(false);
    w.messages.push({
      id: "feedback",
      role: "assistant",
      content: "Fixture feedback",
      question_id: "core",
      created_at: "2026-10-03T08:01:00Z",
      mode: "demo",
    });
    expect(canReveal(w, "core")).toBe(true);
    w.attempts.core.updated_at = "2026-10-03T08:02:00Z";
    expect(canReveal(w, "core")).toBe(false);
    w.session.reference_policy = "after_submit";
    expect(canReveal(w, "core")).toBe(false);
    w.submission.status = "submitted";
    expect(canReveal(w, "core")).toBe(true);
  });
  it("requires all active units and a reading selection to submit", () => {
    const w = fixtureWorkspace();
    expect(canSubmit(w)).toBe(false);
    w.progress.answered = 2;
    w.selected_reading = null;
    expect(canSubmit(w)).toBe(false);
    w.selected_reading = "II-Pong";
    expect(canSubmit(w)).toBe(true);
  });
  it("locks submitted and confirmed records but allows requested revisions", () => {
    const w = fixtureWorkspace();
    w.progress.answered = 2;
    w.submission.status = "submitted";
    expect(isLocked(w)).toBe(true);
    expect(canSubmit(w)).toBe(false);
    w.submission.status = "confirmed";
    expect(isLocked(w)).toBe(true);
    expect(canSubmit(w)).toBe(false);
    w.submission.status = "needs_revision";
    expect(isLocked(w)).toBe(false);
    expect(canSubmit(w)).toBe(true);
  });
  it("handles missing and invalid dates without throwing", () => {
    expect(dateLabel(null)).toBe("—");
    expect(dateLabel("invalid")).toBe("invalid");
  });
  it("formats dates in English without consulting the browser locale", () => {
    const value = "2026-10-01T00:00:00Z";
    expect(dateLabel(value)).toBe(
      new Date(value).toLocaleString("en-GB", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }),
    );
    expect(dateLabel(value)).toContain("Oct");
  });
});
