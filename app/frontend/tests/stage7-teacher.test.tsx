import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import TeachingFramework from "../src/TeachingFramework";
import TeachingSourceReview, {
  sourceEvidenceUsage,
} from "../src/TeachingSourceReview";
import Availability, { AvailabilityBadge } from "../src/Availability";
import InstructionImport from "../src/InstructionImport";
import TeacherExtractionReport from "../src/TeacherExtractionReport";
import {
  defaultTeachingProfile,
  effectiveTeachingProfile,
} from "../src/teaching-profile";
import type {
  ExtractionReport,
  SessionDetail,
  SourceReview,
} from "../src/types";
// Synthetic frontend contract evidence; HTTP/Chrome interaction is in the companion harness.
const fixture = (): SessionDetail => ({
  id: "synthetic-session",
  course_id: "synthetic-course",
  number: 1,
  title: "Synthetic",
  subtitle: "",
  status: "draft",
  question_count: 0,
  estimated_minutes: 10,
  instructions: "Saved private instructions",
  learning_objectives: ["Explain reasoning"],
  reference_policy: "after_attempt",
  teaching_language: "en",
  teaching_profile: defaultTeachingProfile(),
  questions: [],
  groups: [],
  materials: [],
  reference_answers: { q1: "PRIVATE ANSWER NEVER IN DEFAULT REVIEW" },
  active: true,
  starts_at: null,
  ends_at: null,
});
const report: ExtractionReport = {
  schema_version: 1,
  method: "synthetic",
  units_processed: 1,
  units_total: 2,
  ocr_units: 1,
  images_detected: 2,
  chars_extracted: 42,
  excerpt_chars: 21,
  truncated: true,
  visual_review_required: true,
  failed_units: ["Part 2 failed"],
  notes: ["Exact extraction note"],
};
afterEach(() => vi.useRealTimers());
describe("Stage7 teacher hierarchy and disclosure", () => {
  it("keeps instructions, feedback and flow outside disclosure while context and advanced are closed", () => {
    const html = renderToStaticMarkup(
      <TeachingFramework
        session={fixture()}
        onChange={() => {}}
        instructionImport={<button>Import instructions</button>}
      />,
    );
    expect(html.indexOf("Instructions<textarea")).toBeLessThan(
      html.indexOf("Feedback strategy"),
    );
    expect(html.indexOf("Feedback strategy")).toBeLessThan(
      html.indexOf('id="tf-flow-title"'),
    );
    expect(html.indexOf('id="tf-flow-title"')).toBeLessThan(
      html.indexOf("<details"),
    );
    expect(html).toContain(
      '<details class="tf-details"><summary>Background &amp; learner context',
    );
    expect(html).toContain(
      '<details class="tf-details"><summary>Advanced delivery options',
    );
    expect(html).not.toContain("<details open");
    expect(html.indexOf("Import instructions")).toBeLessThan(
      html.indexOf("Feedback strategy"),
    );
  });
  it("retains separate eligibility and delivery controls and legacy on-request semantics", () => {
    const s = fixture();
    delete s.teaching_profile;
    const html = renderToStaticMarkup(
      <TeachingFramework session={s} onChange={() => {}} />,
    );
    expect(html).toContain("When examples become available");
    expect(html).toContain("How examples are offered");
    expect(html).toContain('<option value="after_attempt" selected="">');
    expect(html).toContain('<option value="on_request" selected="">');
    expect(effectiveTeachingProfile(s).reference_delivery).toBe("on_request");
  });
  it("exposes validation outside the closed advanced panel rather than hiding a blocker", () => {
    const s = fixture();
    s.teaching_profile!.idle_hint_seconds = 2;
    const html = renderToStaticMarkup(
      <TeachingFramework session={s} onChange={() => {}} />,
    );
    expect(html).toContain('role="alert"');
    expect(html).toContain("10–300");
    expect(html.indexOf('role="alert"')).toBeGreaterThan(
      html.indexOf("</fieldset>"),
    );
  });
  it("source review is one closed entry and never injects private answers or fake compilation", () => {
    const s = fixture();
    const html = renderToStaticMarkup(
      <TeachingSourceReview saved={s} draft={s} />,
    );
    expect(html).toContain(
      '<details class="tw-review-entry"><summary>Sources &amp; instructions',
    );
    expect(html).not.toContain("PRIVATE ANSWER");
    expect(html).not.toContain("Saved private instructions");
    expect(html).not.toContain("tw-source-result");
    expect(html).toContain("always use the saved draft");
  });
  it("counts actual Unicode code points separately from configured budgets", () => {
    const review = {
      public_evidence: [{ excerpt: "a😀" }, { excerpt: "bc" }],
      private_evidence: [{ excerpt: "é😀" }],
      budgets: { public_chars: 999, private_chars: 999 },
    } as SourceReview;
    expect(sourceEvidenceUsage(review)).toEqual({
      publicChars: 4,
      privateChars: 2,
    });
  });
  it("keeps extraction blockers visible but technical coverage closed and exact", () => {
    const html = renderToStaticMarkup(
      <TeacherExtractionReport report={report} />,
    );
    expect(html.indexOf("Extraction was truncated")).toBeLessThan(
      html.indexOf("<details"),
    );
    expect(html.indexOf("Visual review required")).toBeLessThan(
      html.indexOf("<details"),
    );
    expect(html).toContain("Processed 1 of 2 parts");
    expect(html).toContain("Part 2 failed");
    expect(html).toContain("Exact extraction note");
    expect(html).not.toContain("<details open");
  });
  it("import is a compact instruction-adjacent action, not a second configuration card", () => {
    const html = renderToStaticMarkup(
      <InstructionImport sid="s" instructions="private" onApply={() => {}} />,
    );
    expect(html).toContain("Import instructions");
    expect(html).not.toContain("<section");
    expect(html).not.toContain("<dialog");
    expect(html).not.toContain("private");
  });
  it.each([true, false])(
    "shows concise manual access for active=%s",
    (active) => {
      const html = renderToStaticMarkup(
        <AvailabilityBadge session={{ ...fixture(), active }} />,
      );
      expect(html).toContain(active ? "Open" : "Closed");
      expect(html).not.toContain("Inactive");
    },
  );
  it("distinguishes a future schedule from open-now access", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T00:00:00Z"));
    const html = renderToStaticMarkup(
      <AvailabilityBadge
        session={{ ...fixture(), starts_at: "2026-02-01T00:00:00Z" }}
      />,
    );
    expect(html).toContain("Scheduled · not started");
  });
  it("keeps schedule controls closed and immediate-apply semantics explicit", () => {
    const html = renderToStaticMarkup(
      <Availability session={fixture()} onSaved={() => {}} />,
    );
    expect(html).toContain("<details><summary>Schedule &amp; access");
    expect(html).not.toContain("<details open");
    expect(html).toContain("Apply availability now");
    expect(html).toContain("immediately");
    expect(html).toContain("Starts at (inclusive)");
    expect(html).toContain("Ends at (exclusive)");
  });
});
