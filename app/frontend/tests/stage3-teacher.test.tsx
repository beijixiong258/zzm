import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../src/api";
import TeachingFramework from "../src/TeachingFramework";
import type {
  SessionDetail,
  TeachingPhase,
  TeachingProfile,
} from "../src/types";
import {
  defaultTeachingProfile,
  effectiveTeachingProfile,
  moveTeachingPhase,
  saveTeachingDraft,
  teachingPreviewInput,
  teachingPreviewKey,
  teachingProfileErrors,
  teachingProfileKey,
  teachingTextLimits,
  toggleTeachingPhase,
} from "../src/teaching-profile";

// Synthetic fixtures for focused UI/API contract tests; not backend or model evidence.
function fixture(): SessionDetail {
  return {
    id: "synthetic-teacher-session",
    course_id: "synthetic-course",
    number: 1,
    title: "Synthetic teaching session",
    subtitle: "Explicit frontend fixture",
    status: "draft",
    question_count: 0,
    estimated_minutes: 10,
    instructions: "Existing private additional instructions",
    learning_objectives: ["Explain assessment purpose."],
    reference_policy: "after_attempt",
    teaching_language: "en",
    teaching_profile: defaultTeachingProfile(),
    groups: [],
    questions: [],
    materials: [],
    reference_answers: {
      "private-q": "PRIVATE REFERENCE MUST NOT BE IN EDITOR PREVIEW",
    },
  };
}
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("stage 3 teacher teaching profile", () => {
  it("uses exactly the frozen fields and new-session defaults", () => {
    const p = defaultTeachingProfile();
    expect(Object.keys(p).sort()).toEqual(
      [
        "schema_version",
        "background",
        "student_profile",
        "response_strategies",
        "tone",
        "response_detail",
        "phases",
        "reading_focus",
        "reading_question_count",
        "reference_delivery",
        "idle_hint_seconds",
        "presentation",
      ].sort(),
    );
    expect(p.phases).toEqual(["warmup", "worksheet", "quiz", "wrap_up"]);
    expect(p.reference_delivery).toBe("after_sufficient_answer");
    expect(p.response_detail).toBe("balanced");
    expect(p.reading_question_count).toBe(3);
    expect(p.idle_hint_seconds).toBe(0);
    expect(p.presentation).toBe("full");
    expect(teachingProfileErrors(p)).toEqual([]);
  });
  it("preserves legacy reference delivery instead of silently adopting the new default", () => {
    const session = fixture();
    delete session.teaching_profile;
    expect(effectiveTeachingProfile(session).reference_delivery).toBe(
      "on_request",
    );
    expect(session.instructions).toBe(
      "Existing private additional instructions",
    );
    expect(session.reference_policy).toBe("after_attempt");
  });
  it("never mutates stored profiles when toggling phases", () => {
    const p = defaultTeachingProfile();
    const enabled = toggleTeachingPhase(p.phases, "reading");
    expect(enabled).toEqual([
      "warmup",
      "worksheet",
      "quiz",
      "reading",
      "wrap_up",
    ]);
    expect(p.phases).toEqual(["warmup", "worksheet", "quiz", "wrap_up"]);
    expect(toggleTeachingPhase(enabled, "warmup")).toEqual([
      "worksheet",
      "quiz",
      "reading",
      "wrap_up",
    ]);
    expect(toggleTeachingPhase(["worksheet", "wrap_up"], "warmup")).toEqual([
      "warmup",
      "worksheet",
      "wrap_up",
    ]);
  });
  it("allows quiz/reading ordering but prevents crossing worksheet, warmup or wrap-up", () => {
    const phases: TeachingPhase[] = [
      "warmup",
      "worksheet",
      "quiz",
      "reading",
      "wrap_up",
    ];
    expect(moveTeachingPhase(phases, "reading", -1)).toEqual([
      "warmup",
      "worksheet",
      "reading",
      "quiz",
      "wrap_up",
    ]);
    expect(moveTeachingPhase(phases, "quiz", 1)).toEqual([
      "warmup",
      "worksheet",
      "reading",
      "quiz",
      "wrap_up",
    ]);
    expect(moveTeachingPhase(phases, "quiz", -1)).toEqual(phases);
    expect(moveTeachingPhase(phases, "reading", 1)).toEqual(phases);
    expect(moveTeachingPhase(phases, "worksheet", -1)).toEqual(phases);
    expect(moveTeachingPhase(phases, "wrap_up", -1)).toEqual(phases);
  });
  it.each([
    ["worksheet", "quiz", "quiz", "wrap_up"],
    ["worksheet", "warmup", "wrap_up"],
    ["quiz", "worksheet", "wrap_up"],
    ["reading", "worksheet", "wrap_up"],
    ["warmup", "wrap_up"],
    ["worksheet", "wrap_up", "reading"],
  ])("rejects invalid phase sequence %s", (...phases) => {
    expect(
      teachingProfileErrors({
        ...defaultTeachingProfile(),
        phases: phases as TeachingPhase[],
      }).length,
    ).toBeGreaterThan(0);
  });
  it.each([0, 10, 300])("accepts idle invitation boundary %i", (seconds) => {
    expect(
      teachingProfileErrors({
        ...defaultTeachingProfile(),
        idle_hint_seconds: seconds,
      }),
    ).toEqual([]);
  });
  it.each([-1, 1, 9, 301, 10.5, NaN])(
    "rejects invalid idle invitation %s",
    (seconds) => {
      expect(
        teachingProfileErrors({
          ...defaultTeachingProfile(),
          idle_hint_seconds: seconds,
        }).join(),
      ).toContain("Idle invitation");
    },
  );
  it("bounds reading questions and documents practical private-text limits", () => {
    for (const count of [0, 6, 1.5, NaN])
      expect(
        teachingProfileErrors({
          ...defaultTeachingProfile(),
          reading_question_count: count,
        }).join(),
      ).toContain("1–5");
    for (const count of [1, 5])
      expect(
        teachingProfileErrors({
          ...defaultTeachingProfile(),
          reading_question_count: count,
        }),
      ).toEqual([]);
    expect(
      teachingProfileErrors({
        ...defaultTeachingProfile(),
        tone: "x".repeat(teachingTextLimits.tone + 1),
      }).join(),
    ).toContain("1,000");
    expect(teachingTextLimits.instructions).toBe(30000);
  });
  it("preview body includes unsaved eligibility and existing source fields, not duplicate goals or references", async () => {
    const draft = fixture();
    draft.reference_policy = "after_submit";
    const input = teachingPreviewInput(draft);
    expect(Object.keys(input).sort()).toEqual(
      [
        "teaching_profile",
        "instructions",
        "learning_objectives",
        "teaching_language",
        "reference_policy",
      ].sort(),
    );
    expect(input.instructions).toBe(draft.instructions);
    expect(input.learning_objectives).toEqual(draft.learning_objectives);
    expect(input.reference_policy).toBe("after_submit");
    const fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          text: "Explicit HTTP fixture result",
          sections: [],
          warnings: [],
        }),
        { headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetch);
    await api.teachingPreview("session /1", input);
    expect(fetch.mock.calls[0][0]).toBe(
      "/api/sessions/session%20%2F1/teaching-preview",
    );
    expect(fetch.mock.calls[0][1].method).toBe("POST");
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual(input);
  });
  it("preview freshness covers profile, objectives, language, instructions and eligibility", () => {
    const s = fixture();
    const key = teachingPreviewKey(s);
    for (const patch of [
      { instructions: "Changed" },
      { learning_objectives: ["Changed"] },
      { teaching_language: "zh" },
      { reference_policy: "after_submit" as const },
      { teaching_profile: { ...s.teaching_profile!, tone: "Changed" } },
    ])
      expect(teachingPreviewKey({ ...s, ...patch })).not.toBe(key);
    const reordered = Object.fromEntries(
      Object.entries(s.teaching_profile!).reverse(),
    );
    expect(teachingProfileKey(reordered as TeachingProfile)).toBe(
      teachingProfileKey(s.teaching_profile!),
    );
  });
  it("saves the entire existing teacher draft and requires a separate successful GET read-back", async () => {
    const draft = fixture();
    const order: string[] = [];
    const patch = vi
      .spyOn(api, "updateSession")
      .mockImplementation(async () => {
        order.push("PATCH");
        return draft;
      });
    const get = vi.spyOn(api, "session").mockImplementation(async () => {
      order.push("GET");
      return structuredClone(draft);
    });
    const result = await saveTeachingDraft(draft.id, draft);
    expect(order).toEqual(["PATCH", "GET"]);
    expect(get).toHaveBeenCalledWith(draft.id);
    expect(patch.mock.calls[0][1]).toMatchObject({
      teaching_profile: draft.teaching_profile,
      instructions: draft.instructions,
      learning_objectives: draft.learning_objectives,
      teaching_language: "en",
      reference_policy: "after_attempt",
      reference_answers: draft.reference_answers,
      questions: [],
      groups: [],
      status: "draft",
    });
    expect(patch.mock.calls[0][1]).not.toHaveProperty("active");
    expect(patch.mock.calls[0][1]).not.toHaveProperty("published_version_id");
    expect(result).toEqual(draft);
  });
  it("rejects a saved profile mismatch without claiming save success", async () => {
    const draft = fixture();
    vi.spyOn(api, "updateSession").mockResolvedValue(draft);
    vi.spyOn(api, "session").mockResolvedValue({
      ...draft,
      teaching_profile: {
        ...draft.teaching_profile!,
        response_detail: "detailed",
      },
    });
    await expect(saveTeachingDraft(draft.id, draft)).rejects.toThrow(
      "could not be verified",
    );
    expect(draft.teaching_profile!.response_detail).toBe("balanced");
  });
  it("does not treat a missing legacy profile as verified persistence", async () => {
    const draft = fixture();
    const legacy = { ...draft, teaching_profile: undefined };
    vi.spyOn(api, "updateSession").mockResolvedValue(draft);
    vi.spyOn(api, "session").mockResolvedValue(legacy);
    await expect(saveTeachingDraft(draft.id, draft)).rejects.toThrow(
      "could not be verified",
    );
  });
  it("keeps edits on PATCH/GET errors and does not retry or publish implicitly", async () => {
    const draft = fixture();
    const patch = vi
      .spyOn(api, "updateSession")
      .mockRejectedValue(new Error("Explicit fixture PATCH failure"));
    const get = vi.spyOn(api, "session");
    await expect(saveTeachingDraft(draft.id, draft)).rejects.toThrow(
      "PATCH failure",
    );
    expect(get).not.toHaveBeenCalled();
    patch.mockResolvedValue(draft);
    get.mockRejectedValue(new Error("Explicit fixture GET failure"));
    await expect(saveTeachingDraft(draft.id, draft)).rejects.toThrow(
      "GET failure",
    );
    expect(patch).toHaveBeenCalledTimes(2);
    expect(draft.instructions).toBe("Existing private additional instructions");
  });
  it("rejects invalid numeric settings before writing", async () => {
    const draft = fixture();
    draft.teaching_profile!.idle_hint_seconds = 2;
    const patch = vi.spyOn(api, "updateSession");
    await expect(saveTeachingDraft(draft.id, draft)).rejects.toThrow("10–300");
    expect(patch).not.toHaveBeenCalled();
  });
});

describe("stage 3 teacher editor static accessibility and boundaries", () => {
  it("renders labelled controls, honest preview/reading semantics and no instructor answer keys", () => {
    const draft = fixture();
    draft.teaching_profile!.phases = [
      "worksheet",
      "reading",
      "quiz",
      "wrap_up",
    ];
    const html = renderToStaticMarkup(
      <TeachingFramework session={draft} onChange={() => {}} />,
    );
    for (const label of [
      "Background &amp; tutor role",
      "Student profile",
      "Feedback strategy",
      "Instructions",
      "How examples are offered",
      "Response detail",
      "Response presentation",
      "Reading focus",
      "Reading discussion questions",
      "Idle help invitation",
    ])
      expect(html).toContain(label);
    expect(html).toContain('aria-label="Teaching phase order"');
    expect(html).toContain("Move Reading discussion later");
    expect(html).toContain("Teaching approach"); // compilation moved to Sources & instructions
    expect(html).toContain("not an automatic AI request");
    expect(html).toContain("already-generated response");
    expect(html).toContain("No worksheet questions yet");
    expect(html).not.toContain("PRIVATE REFERENCE MUST NOT");
    expect(html).not.toMatch(/[\u3400-\u9fff]/);
  });
  it("disables the full fieldset while saving and does not compile a local fake preview", () => {
    const html = renderToStaticMarkup(
      <TeachingFramework session={fixture()} disabled onChange={() => {}} />,
    );
    expect(html).toContain('class="tf-fields" disabled=""');
    expect(html).toContain("Instructions");
    expect(html).not.toContain("tf-preview-result");
    expect(html).toContain("Advanced delivery options");
  });
});
