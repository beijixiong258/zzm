import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../src/api";
import { fixtureWorkspace } from "./fixtures";
import { draftKey, readDraft, writeDraft } from "../src/drafts";
import {
  conversationScope,
  conversationQuestion,
  sameTurn,
  pendingKey,
  storePending,
  readPending,
  clearPending,
  acknowledgePending,
  paragraphChunks,
  recordedSpan,
  questionStatus,
  phaseLabels,
  canRevealExample,
  optionResponse,
} from "../src/guided-study";
import { QuestionPrompt, PacedText, TutorMessage } from "../src/TutorMessage";
import type { TutorState, TutorTurn } from "../src/types";
const tutor = (): TutorState => ({
  phase: "worksheet",
  started_at: "2026-10-06T00:00:00Z",
  updated_at: "2026-10-06T00:01:00Z",
  elapsed_seconds: 60,
  current_question_id: "core",
  completed_question_ids: [],
  question_states: {},
  quiz: { status: "not_offered", answered: 0, total: 0, correct: null },
  reading: { answered: 0, total: 0 },
  presentation: "full",
  idle_hint_seconds: 0,
});
const storage = () => {
  const map = new Map<string, string>();
  return {
    getItem: (key: string) => map.get(key) ?? null,
    setItem: (key: string, value: string) => {
      map.set(key, value);
    },
    removeItem: (key: string) => {
      map.delete(key);
    },
  };
};
afterEach(() => vi.unstubAllGlobals());
describe("guided conversation client contract (synthetic HTTP fixtures)", () => {
  it("sends one natural-language turn, not a compulsory answer/ask flag", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(
        new Response("{}", { headers: { "Content-Type": "application/json" } }),
      );
    vi.stubGlobal("fetch", fetcher);
    const body: TutorTurn = {
      message: "My response. Could you explain why?",
      request_id: "fixed-retry-id",
      web_search: false,
      action: "message",
    };
    await api.tutorTurn("s /1", body, "v&1");
    expect(fetcher.mock.calls[0][0]).toBe(
      "/api/sessions/s%20%2F1/tutor/turn?version_id=v%261",
    );
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual(body);
    expect(fetcher.mock.calls[0][1].body).not.toContain("intent");
  });
  it("pins opening and transcript downloads to the loaded edition", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(
        new Response("{}", { headers: { "Content-Type": "application/json" } }),
      );
    vi.stubGlobal("fetch", fetcher);
    await api.tutorStart("s", "opening-id", "v 1");
    expect(fetcher.mock.calls[0][0]).toBe(
      "/api/sessions/s/tutor/start?version_id=v%201",
    );
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({
      request_id: "opening-id",
    });
    expect(api.transcriptUrl("s /1", "html", "v 1")).toBe(
      "/api/sessions/s%20%2F1/transcript?version_id=v%201&format=html",
    );
    expect(api.transcriptUrl("s", "txt")).toBe(
      "/api/sessions/s/transcript?format=txt",
    );
  });
  it("keeps search and deliberate actions in retry identity", () => {
    const original: TutorTurn = {
      message: "Please help",
      request_id: "r",
      action: "hint",
      question_id: "q1",
      web_search: false,
    };
    expect(sameTurn(original, { ...original })).toBe(true);
    for (const change of [
      { message: "Different" },
      { action: "message" as const },
      { question_id: "q2" },
      { web_search: true },
    ])
      expect(sameTurn(original, { ...original, ...change })).toBe(false);
  });
});
describe("conversation draft and retry persistence", () => {
  it("retains an in-memory completed request when local storage is unavailable", () => {
    const scope = conversationScope(fixtureWorkspace(), "viewer");
    const unavailable = {
      getItem: () => {
        throw new Error("Unavailable");
      },
      removeItem: () => {
        throw new Error("Unavailable");
      },
    };
    const record = {
      scope,
      turn: { request_id: "memory-id", message: "Raw answer" },
      clear_draft: true,
    };
    expect(
      acknowledgePending(scope, "different", unavailable, record),
    ).toBeNull();
    expect(acknowledgePending(scope, "memory-id", unavailable, record)).toEqual(
      record,
    );
    expect(
      acknowledgePending(
        { ...scope, user: "other" },
        "memory-id",
        unavailable,
        record,
      ),
    ).toBeNull();
  });
  it("acknowledges only the completed request ID, not identical transcript text", () => {
    const scope = conversationScope(fixtureWorkspace(), "viewer");
    const store = storage();
    const record = {
      scope,
      turn: { request_id: "done-id", message: "Raw answer" },
      clear_draft: true,
    };
    storePending(record, store);
    writeDraft(scope, record.turn.message, store);
    for (const id of [undefined, null, "different-id"]) {
      expect(acknowledgePending(scope, id, store)).toBeNull();
      expect(readPending(scope, store)).toEqual(record);
      expect(readDraft(scope, store)).toBe("Raw answer");
    }
    expect(acknowledgePending(scope, "done-id", store)).toEqual(record);
    expect(readPending(scope, store)).toBeNull();
    expect(readDraft(scope, store)).toBeNull();
  });
  it("acknowledges a prior-context commit without erasing new current or edited drafts", () => {
    const w = fixtureWorkspace();
    w.tutor = tutor();
    const before = conversationScope(w, "viewer");
    const store = storage();
    const record = {
      scope: before,
      turn: { request_id: "done-id", message: "Raw answer" },
      clear_draft: true,
    };
    storePending(record, store);
    writeDraft(before, "A newer edit of the old draft", store);
    w.tutor.current_question_id = "quiz-persisted";
    const after = conversationScope(w, "viewer");
    writeDraft(after, "Unsent current question", store);
    expect(acknowledgePending(after, "done-id", store)).toEqual(record);
    expect(readPending(after, store)).toBeNull();
    expect(readDraft(before, store)).toBe("A newer edit of the old draft");
    expect(readDraft(after, store)).toBe("Unsent current question");
  });
  it("does not clear the composer draft after acknowledging a deliberate action", () => {
    const scope = conversationScope(fixtureWorkspace(), "viewer");
    const store = storage();
    storePending(
      {
        scope,
        turn: { request_id: "yes-id", message: "Yes" },
        clear_draft: false,
      },
      store,
    );
    writeDraft(scope, "Keep my unsent reflection", store);
    expect(acknowledgePending(scope, "yes-id", store)).not.toBeNull();
    expect(readDraft(scope, store)).toBe("Keep my unsent reflection");
  });
  it("uses the tutor's current question, not the first nonempty-answer progress pointer", () => {
    const w = fixtureWorkspace();
    w.tutor = tutor();
    w.progress.current_question_id = "other";
    expect(conversationQuestion(w)).toBe("core");
    expect(conversationScope(w, "viewer").intent).toBe("conversation");
  });
  it("separates warm-up, quiz and reading drafts when no worksheet question is active", () => {
    const w = fixtureWorkspace();
    w.tutor = { ...tutor(), phase: "warmup", current_question_id: null };
    const a = conversationScope(w, "viewer");
    w.tutor.phase = "quiz";
    const b = conversationScope(w, "viewer");
    expect(draftKey(a)).not.toBe(draftKey(b));
    const store = storage();
    writeDraft(a, "Unsent warm-up", store);
    expect(readDraft(b, store)).toBeNull();
  });
  it("retains the exact request ID and raw text through reload", () => {
    const w = fixtureWorkspace();
    w.tutor = tutor();
    const scope = conversationScope(w, "viewer");
    const store = storage();
    const record = {
      scope,
      turn: {
        request_id: "retry-exact",
        message: "  My raw text  ",
        action: "message" as const,
        web_search: false,
      },
      clear_draft: true,
    };
    expect(storePending(record, store)).toBe(true);
    expect(readPending(scope, store)).toEqual(record);
    expect(readPending({ ...scope, user: "other" }, store)).toBeNull();
    expect(readPending({ ...scope, version: "other" }, store)).toBeNull();
    expect(
      readPending({ ...scope, preview: !scope.preview }, store),
    ).toBeNull();
    clearPending(scope, store);
    expect(readPending(scope, store)).toBeNull();
  });
  it("does not import a forged different-account retry from the same storage slot", () => {
    const w = fixtureWorkspace();
    const scope = conversationScope(w, "viewer");
    const store = storage();
    store.setItem(
      pendingKey(scope),
      JSON.stringify({
        scope: { ...scope, user: "other" },
        turn: { message: "Other", request_id: "r" },
      }),
    );
    expect(readPending(scope, store)).toBeNull();
  });
  it("ignores broken local retry JSON without clearing other drafts", () => {
    const w = fixtureWorkspace();
    const scope = conversationScope(w, "viewer");
    const store = storage();
    writeDraft(scope, "Keep this", store);
    store.setItem(pendingKey(scope), "{bad");
    expect(readPending(scope, store)).toBeNull();
    expect(readDraft(scope, store)).toBe("Keep this");
  });
});
describe("question and message presentation", () => {
  it("submits canonical single-choice letters without discarding non-choice worksheet bank text", () => {
    const q = {
      id: "quiz",
      type: "single_choice" as const,
      prompt: "Choose",
      options: ["Reliability", "Validity"],
    };
    expect(optionResponse(q, 0)).toBe("A");
    expect(optionResponse(q, 1)).toBe("B");
    expect(optionResponse({ ...q, type: "fill_in_blank" }, 1)).toBe(
      "B. Validity",
    );
  });
  it("allows an explicit eligible after-submit reference while retaining historical/inactive/archived locks", () => {
    const w = fixtureWorkspace();
    w.session.reference_policy = "after_submit";
    w.attempts.core = {
      question_id: "core",
      answer: "Attempt",
      revision_count: 0,
      updated_at: "2026-10-06T00:00:00Z",
      reference_revealed: false,
    };
    expect(canRevealExample(w, "core")).toBe(false);
    w.submission.status = "submitted";
    w.read_only = true;
    w.read_only_reason = "submission_locked";
    expect(canRevealExample(w, "core")).toBe(true);
    w.read_only_reason = "historical_version";
    expect(canRevealExample(w, "core")).toBe(false);
    w.read_only_reason = "enrollment_archived";
    expect(canRevealExample(w, "core")).toBe(false);
    w.read_only_reason = "submission_locked";
    w.session.active = false;
    expect(canRevealExample(w, "core")).toBe(false);
  });
  it("renders optional metadata cards, safe options and all public reading sources without an invented ordinal", () => {
    const w = fixtureWorkspace();
    w.tutor = {
      ...tutor(),
      phase: "quiz",
      current_question_id: "quiz-persisted",
    };
    const message = {
      id: "optional",
      role: "assistant" as const,
      content: "Formative practice only",
      question_id: null,
      created_at: "2026-10-06T00:00:00Z",
      mode: "demo" as const,
      presented_question_id: "quiz-persisted",
      metadata: {
        phase: "quiz" as const,
        presented_question: {
          id: "quiz-persisted",
          type: "single_choice" as const,
          prompt: "What supports reliability?",
          options: ["Consistent evidence", "Automatic mastery"],
          images: [],
        },
      },
    };
    const html = renderToStaticMarkup(
      <TutorMessage
        message={message}
        workspace={w}
        latest
        paced={false}
        onQuestion={() => {}}
        onOption={() => {}}
      />,
    );
    expect(html).toContain('data-question-id="quiz-persisted"');
    expect(html).toContain("Consistent evidence");
    expect(html).toContain("Optional formative practice");
    expect(html).not.toContain("Question undefined");
    const reading = renderToStaticMarkup(
      <QuestionPrompt
        workspace={w}
        phase="reading"
        question={{
          id: "reading-persisted",
          type: "reading_response",
          prompt: "Discuss the public evidence.",
          images: [],
          source_labels: ["Public article one", "Public article two"],
        }}
      />,
    );
    expect(reading).toContain("Reading discussion");
    expect(reading).toContain("Public article one");
    expect(reading).toContain("Public article two");
    expect(reading).not.toContain("undefined");
  });
  it("preserves immutable metadata prompt/images instead of substituting session questions", () => {
    const w = fixtureWorkspace();
    const html = renderToStaticMarkup(
      <TutorMessage
        message={{
          id: "presented",
          role: "assistant",
          content: "Stored presentation",
          question_id: null,
          created_at: "2026-10-06T00:00:00Z",
          mode: "demo",
          presented_question_id: w.session.questions[0].id,
          metadata: {
            phase: "worksheet",
            presented_question: {
              ...w.session.questions[0],
              prompt: "Original stored graph prompt",
              images: [
                {
                  label: "A",
                  alt: "Original graph",
                  url: "/api/assets/original.png",
                },
              ],
            },
          },
        }}
        workspace={w}
        latest
        paced={false}
        onQuestion={() => {}}
      />,
    );
    expect(html).toContain("Original stored graph prompt");
    expect(html).toContain("/api/assets/original.png");
  });
  it("renders original figures, group context and all answer parts within the conversation", () => {
    const w = fixtureWorkspace();
    const q = {
      ...w.session.questions[0],
      answer_slots: 3,
      images: [{ label: "A", url: "/api/assets/a.png", alt: "Scatter plot A" }],
    };
    w.session.groups = [
      {
        id: q.group_id,
        title: "Practice",
        kind: "core",
        description: "Word bank: first; second; third",
      },
    ];
    const html = renderToStaticMarkup(
      <QuestionPrompt question={q} workspace={w} onOption={() => {}} />,
    );
    expect(html).toContain("Scatter plot A");
    expect(html).toContain("/api/assets/a.png");
    expect(html).toContain("Word bank");
    expect(html).toContain("3 answer parts");
  });
  it("keeps raw student markup as text rather than rendering it as teaching HTML", () => {
    const w = fixtureWorkspace();
    const html = renderToStaticMarkup(
      <TutorMessage
        message={{
          id: "m",
          role: "user",
          content: "<script>bad()</script> **my words**",
          question_id: null,
          created_at: "2026-10-06T00:00:00Z",
          mode: "openai",
        }}
        workspace={w}
        latest={false}
        paced={false}
        onQuestion={() => {}}
      />,
    );
    expect(html).toContain("&lt;script&gt;");
    expect(html).toContain("**my words**");
    expect(html).not.toContain("<script>");
  });
  it("labels deterministic demo feedback without claiming live-model output", () => {
    const w = fixtureWorkspace();
    const html = renderToStaticMarkup(
      <TutorMessage
        message={{
          id: "m",
          role: "assistant",
          content: "Synthetic preview",
          question_id: null,
          created_at: "2026-10-06T00:00:00Z",
          mode: "demo",
        }}
        workspace={w}
        latest={false}
        paced={false}
        onQuestion={() => {}}
      />,
    );
    expect(html).toContain("Recorded demo");
  });
  it("paces complete paragraphs with an explicit show-all action, not fake streaming", () => {
    const html = renderToStaticMarkup(
      <PacedText content={"First paragraph.\n\nSecond paragraph."} active />,
    );
    expect(html).toContain("First paragraph.");
    expect(html).not.toContain("Second paragraph.");
    expect(html).toContain("Show full response");
    expect(html).toContain("Paced reading");
  });
  it("renders history without re-hiding its paragraphs", () => {
    const html = renderToStaticMarkup(
      <PacedText content={"First.\n\nSecond."} active={false} />,
    );
    expect(html).toContain("Second.");
    expect(html).not.toContain("Continue reading");
  });
  it("does not split a code fence at internal blank lines", () => {
    expect(paragraphChunks("Intro\n\n```txt\na\n\nb\n```\n\nAfter")).toEqual([
      "Intro",
      "```txt\na\n\nb\n```",
      "After",
    ]);
  });
  it("does not label saved responses as correct or teacher-confirmed mastery", () => {
    const w = fixtureWorkspace();
    w.tutor = tutor();
    w.attempts.core = {
      question_id: "core",
      answer: "Attempt",
      revision_count: 1,
      updated_at: "2026-10-06T00:00:00Z",
      reference_revealed: false,
    };
    expect(questionStatus(w, "core")).toBe("Response saved");
    w.tutor.question_states.core = {
      status: "in_progress",
      answer_count: 1,
      hint_count: 1,
      last_outcome: "needs_retry",
    };
    expect(questionStatus(w, "core")).toBe("Keep exploring");
    w.tutor.question_states.core.status = "discussed";
    w.tutor.question_states.core.last_outcome = "sufficient";
    expect(questionStatus(w, "core")).toBe("Discussed");
  });
  it("formats recorded spans and unambiguous phase labels", () => {
    expect(recordedSpan(0)).toBe("Less than a minute");
    expect(recordedSpan(120)).toBe("2 min");
    expect(recordedSpan(3600)).toBe("1 hr 0 min");
    expect(phaseLabels.quiz_offer).toBe("Optional practice");
    expect(phaseLabels.complete).toBe("Session wrap-up");
  });
});
