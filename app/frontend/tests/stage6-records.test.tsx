import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fixtureWorkspace } from "./fixtures";
import type { Workspace } from "../src/types";
import { api } from "../src/api";
import { sourceEvidenceUsage } from "../src/TeachingSourceReview";
import type { SourceReview } from "../src/types";
import { draftKey, readDraft, writeDraft } from "../src/drafts";
import {
  acknowledgePending,
  conversationScope,
  pendingKey,
  readPending,
  sameTurn,
  storePending,
} from "../src/guided-study";
import { processOverview, questionProcessFacts } from "../src/process-overview";
import TeacherProcessOverview from "../src/TeacherProcessOverview";
import { TutorMessage } from "../src/TutorMessage";
const timestamp = "2026-10-07T13:00:00Z";
function record(): Workspace {
  const w = fixtureWorkspace();
  w.version = {
    id: "edition-one",
    number: 1,
    is_current: false,
    is_draft: false,
  };
  w.submission.status = "submitted";
  w.read_only = true;
  w.read_only_reason = "historical_version";
  w.attempts.core = {
    question_id: "core",
    answer: "Final synthetic response",
    updated_at: timestamp,
    reference_revealed: false,
    revision_count: 2,
    revisions: [
      { answer: "First synthetic response", created_at: timestamp },
      { answer: "Second synthetic response", created_at: timestamp },
      { answer: "Final synthetic response", created_at: timestamp },
    ],
  };
  w.tutor = {
    phase: "complete",
    started_at: timestamp,
    updated_at: timestamp,
    elapsed_seconds: 0,
    current_question_id: null,
    completed_question_ids: ["core"],
    question_states: {
      core: {
        status: "discussed",
        answer_count: 3,
        hint_count: 2,
        last_outcome: "sufficient",
      },
      pong: {
        status: "not_started",
        answer_count: 0,
        hint_count: 0,
        last_outcome: "unknown",
      },
    },
    quiz: { status: "skipped", answered: 0, total: 0, correct: null },
    reading: { answered: 0, total: 0 },
    presentation: "full",
    idle_hint_seconds: 0,
  };
  w.messages = [
    {
      id: "raw-first",
      role: "user",
      content: "Original first response",
      question_id: "core",
      created_at: timestamp,
      mode: "demo",
      intent: "answer",
    },
    {
      id: "raw-help",
      role: "user",
      content: "Why does that distinction matter?",
      question_id: "core",
      created_at: timestamp,
      mode: "demo",
      intent: "ask",
    },
    {
      id: "raw-final",
      role: "user",
      content: "Final synthetic response",
      question_id: "core",
      created_at: timestamp,
      mode: "demo",
      intent: "answer",
    },
    {
      id: "raw-tutor",
      role: "assistant",
      content: "Feedback before the next question",
      question_id: "core",
      created_at: timestamp,
      mode: "demo",
      metadata: {
        presented_question: { ...w.session.questions[1] },
        phase: "worksheet",
      },
    },
  ];
  return w;
}
function storage() {
  const map = new Map<string, string>();
  return {
    getItem: (k: string) => map.get(k) ?? null,
    setItem: (k: string, v: string) => {
      map.set(k, v);
    },
    removeItem: (k: string) => {
      map.delete(k);
    },
  };
}
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("teacher process facts from stored workspace only", () => {
  it("keeps helped/discussed work separate from formal confirmation", () => {
    const w = record(),
      f = processOverview(w);
    expect(f.discussed).toBe(1);
    expect(f.savedResponses).toBe(3);
    expect(f.revisions).toBe(2);
    expect(f.guidedHelpTurns).toBe(2);
    expect(w.submission.status).toBe("submitted");
  });
  it("preserves original content and metadata", () => {
    const w = record(),
      before = JSON.stringify(w);
    processOverview(w);
    renderToStaticMarkup(
      <TeacherProcessOverview
        workspace={w}
        onMessage={() => {}}
        onResponse={() => {}}
      />,
    );
    expect(JSON.stringify(w)).toBe(before);
  });
  it("does not infer mastery or corrected-error history from final praise", () => {
    const w = record();
    delete w.tutor;
    w.messages[3].content = "Outstanding! You have mastered this.";
    const f = questionProcessFacts(w)[0];
    expect(f.latestOutcome).toBe("unknown");
    expect(f.discussion).toBe("in_progress");
    expect(f.guidedHelpTurns).toBeNull();
  });
  it("keeps unavailable legacy guided help unknown rather than inventing zero", () => {
    const w = record();
    delete w.tutor;
    expect(processOverview(w).guidedHelpTurns).toBeNull();
  });
  it("counts an existing response when old revisions are not present", () => {
    const w = record();
    w.attempts.core.revisions = [];
    w.attempts.core.revision_count = 0;
    expect(questionProcessFacts(w)[0].savedResponses).toBe(1);
  });
  it("uses the chosen reading path, not the other branch", () => {
    expect(questionProcessFacts(record()).map((r) => r.question.id)).toEqual([
      "core",
      "pong",
    ]);
  });
  it("locates the exact latest learner message, not a paraphrase", () => {
    const r = questionProcessFacts(record())[0];
    expect(r.latestResponseMessageId).toBe("raw-final");
    expect(r.relatedMessages.map((m) => m.id)).toEqual([
      "raw-first",
      "raw-help",
      "raw-final",
      "raw-tutor",
    ]);
  });
  it("retains both feedback-target and presented-question relations", () => {
    const rows = questionProcessFacts(record());
    expect(rows[0].relatedMessages.some((m) => m.id === "raw-tutor")).toBe(
      true,
    );
    expect(rows[1].relatedMessages.map((m) => m.id)).toEqual(["raw-tutor"]);
  });
  it("offers saved responses even when there is no conversation", () => {
    const w = record();
    w.messages = [];
    const html = renderToStaticMarkup(
      <TeacherProcessOverview
        workspace={w}
        onMessage={() => {}}
        onResponse={() => {}}
      />,
    );
    expect(html).toContain("Responses &amp; revisions");
    expect(html).not.toContain("Locate latest reply");
  });
  it("renders raw excerpts escaped, without interpreting markup", () => {
    const w = record();
    w.messages[0].content = '<script>alert("x")</script>';
    const html = renderToStaticMarkup(
      <TeacherProcessOverview
        workspace={w}
        onMessage={() => {}}
        onResponse={() => {}}
      />,
    );
    expect(html).toContain("&lt;script&gt;");
    expect(html).not.toContain("<script>");
  });
  it("labels the edition and latest outcome, never an engagement score", () => {
    const html = renderToStaticMarkup(
      <TeacherProcessOverview
        workspace={record()}
        onMessage={() => {}}
        onResponse={() => {}}
      />,
    );
    expect(html).toContain("Edition 1");
    expect(html).toContain("Sufficient to discuss");
    expect(html).toContain(
      "Discussion and formative outcomes are not teacher confirmation",
    );
    expect(html).not.toContain("High engagement");
  });
  it("supports a highlighted, keyboard-focusable original message", () => {
    const w = record();
    const html = renderToStaticMarkup(
      <TutorMessage
        message={w.messages[0]}
        workspace={w}
        latest={false}
        paced={false}
        highlighted
        onQuestion={() => {}}
      />,
    );
    expect(html).toContain('data-message-id="raw-first"');
    expect(html).toContain('tabindex="-1"');
    expect(html).toContain("is-located");
  });
});

describe("preview generation keeps other drafts and requests intact", () => {
  const preview = (id: string) => {
    const w = record();
    w.user.role = "teacher";
    w.version = { id: null, number: null, is_current: false, is_draft: true };
    w.preview = {
      id,
      revision: "r1",
      current_revision: "r1",
      stale: false,
      reset_required: false,
      pending: false,
      bound_at: timestamp,
    };
    return w;
  };
  it("retains the exact existing student draft-key format", () => {
    const w = record();
    const s = conversationScope(w, "teacher-viewer");
    expect(draftKey(s)).toBe(
      `aicademiya.draft.v1:${JSON.stringify(["teacher-viewer", "test-session", "edition-one", "learning", "phase:complete", "conversation"])}`,
    );
  });
  it("retains exact legacy teacher keys without a managed preview", () => {
    const w = preview("x");
    delete w.preview;
    const s = conversationScope(w, "teacher");
    expect(pendingKey(s)).toBe(
      `aicademiya.tutor-request.v1:${JSON.stringify(["teacher", "test-session", null, true])}`,
    );
  });
  it("separates both drafts and durable requests across resets", () => {
    const a = conversationScope(preview("run-a"), "teacher"),
      b = conversationScope(preview("run-b"), "teacher");
    expect(draftKey(a)).not.toBe(draftKey(b));
    expect(pendingKey(a)).not.toBe(pendingKey(b));
  });
  it("does not recover old preview text into the reset run", () => {
    const s = storage(),
      a = conversationScope(preview("run-a"), "teacher"),
      b = conversationScope(preview("run-b"), "teacher");
    writeDraft(a, "Old private trial", s);
    expect(readDraft(b, s)).toBeNull();
    expect(readDraft(a, s)).toBe("Old private trial");
  });
  it("does not acknowledge an old generation by coincident request ID", () => {
    const s = storage(),
      a = conversationScope(preview("run-a"), "teacher"),
      b = conversationScope(preview("run-b"), "teacher");
    const pending = {
      scope: a,
      turn: {
        request_id: "same-id",
        message: "Old trial",
        preview_id: "run-a",
      },
    };
    storePending(pending, s);
    expect(acknowledgePending(b, "same-id", s, pending)).toBeNull();
    expect(readPending(a, s)).not.toBeNull();
  });
  it("requires preview identity equality when reusing a pending turn", () => {
    const a = { request_id: "r", message: "A", preview_id: "old" };
    expect(sameTurn(a, { message: "A", preview_id: "new" })).toBe(false);
    expect(sameTurn(a, { message: "A", preview_id: "old" })).toBe(true);
  });
  it("does not accept a preview ID as a student namespace", () => {
    const w = record();
    w.preview = preview("private").preview;
    expect(conversationScope(w, "student").preview_run_id).toBeUndefined();
  });
});

describe("workbench transport contracts", () => {
  it("keeps snippet usage separate from capacity and counts Unicode code points", () => {
    const review = { public_evidence: [{ excerpt: "A😀中" }], private_evidence: [{ excerpt: "XY" }], budgets: {public_chars:32000,private_chars:8000,request_bytes:60000} } as SourceReview;
    expect(sourceEvidenceUsage(review)).toEqual({ publicChars: 3, privateChars: 2 });
  });
  it("carries preview identity on all synchronous full-preview actions", async () => {
    const urls: string[] = [];
    vi.stubGlobal("fetch",vi.fn(async (url:string) => {urls.push(url);return {ok:true,status:200,json:async()=>({})}}));
    await api.reading("s","g",undefined,"run/new");
    await api.answer("s","q","answer",undefined,"run/new");
    await api.reference("s","q",undefined,"run/new");
    await api.submit("s",undefined,"run/new");
    expect(urls).toEqual(["/api/sessions/s/reading?preview_id=run%2Fnew","/api/sessions/s/answers/q?preview_id=run%2Fnew","/api/sessions/s/references/q?preview_id=run%2Fnew","/api/sessions/s/submit?preview_id=run%2Fnew"]);
  });
  it("does not add preview fields to an ordinary learner start", async () => {
    const calls: RequestInit[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, options: RequestInit) => {
        calls.push(options);
        return { ok: true, status: 200, json: async () => ({}) };
      }),
    );
    await api.tutorStart("s", "request", "v");
    expect(JSON.parse(calls[0].body as string)).toEqual({
      request_id: "request",
    });
  });
  it("uses exact owner-only paths and explicit reset revision", async () => {
    const calls: { url: string; options: RequestInit }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, options: RequestInit) => {
        calls.push({ url, options });
        return { ok: true, status: 200, json: async () => ({}) };
      }),
    );
    await api.previewInfo("s/1");
    await api.resetPreview("s/1", "saved-revision");
    await api.sourceReview("s/1", {
      phase: "reading",
      instructions: "Unsaved synthetic instruction",
    });
    await api.instructionPreview(
      "s/1",
      new File(["Synthetic rule"], "rules.txt"),
    );
    await api.tutorStart("s/1", "request", null, "preview-1");
    expect(calls.map((c) => c.url)).toEqual([
      "/api/teacher/sessions/s%2F1/preview",
      "/api/teacher/sessions/s%2F1/preview/reset",
      "/api/teacher/sessions/s%2F1/source-review",
      "/api/teacher/sessions/s%2F1/instruction-import/preview",
      "/api/sessions/s%2F1/tutor/start",
    ]);
    expect(JSON.parse(calls[1].options.body as string)).toEqual({
      expected_revision: "saved-revision",
    });
    expect(calls[3].options.body).toBeInstanceOf(FormData);
    expect(JSON.parse(calls[4].options.body as string).preview_id).toBe(
      "preview-1",
    );
  });
});
