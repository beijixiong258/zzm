import { afterEach, describe, expect, it, vi } from "vitest";
import { documentApi, documentQuery } from "../src/document-api";
import {
  processingLabel,
  uncertainDocumentWrite,
  reviewReadbackMatches,
  reviewChangeError,
} from "../src/document-state";
import { ApiError } from "../src/api";
import type {
  DocumentInfo,
  DocumentJob,
  DocumentPage,
} from "../src/document-types";
const info: DocumentInfo = {
  revision_id: "r1",
  source_sha256: "a".repeat(64),
  page_count: 317,
  block_count: 10,
  quality: "needs_review",
  review_count: 1,
  parser: { name: "synthetic", version: "1", recipe: "test-only" },
  created_at: "2026-01-01T00:00:00Z",
  warnings: [],
};
const page: DocumentPage = {
  number: 269,
  printed_label: "A147",
  status: "text",
  rotation: 0,
  image_url: "/api/fixture",
  width: 100,
  height: 100,
  issues: [],
  blocks: [
    {
      id: "p269-b1",
      type: "text",
      bbox: [0, 0, 1, 1],
      text: "Checked source",
      quality: "approved",
      issues: [],
      assets: [],
      parent_id: null,
      review: {
        by: "synthetic",
        at: "2026-01-01",
        reason: "Compared source image",
      },
    },
  ],
};
afterEach(() => vi.unstubAllGlobals());
describe("Stage12 document client primitives — not backend/visual acceptance", () => {
  it("binds edition and exact revision without silently dropping blank values", () => {
    expect(documentQuery("v1", "r1")).toBe("?version_id=v1&revision_id=r1");
    expect(documentQuery(null, "r1")).toBe("?revision_id=r1");
    expect(documentQuery("", "r1")).toBe("?version_id=&revision_id=r1");
  });
  it("uses authorized page route with version/revision and credentials", async () => {
    const fetch = vi.fn(async () => new Response(JSON.stringify(page)));
    vi.stubGlobal("fetch", fetch);
    await documentApi.page("material/1", 269, "r1", "v1");
    expect(fetch.mock.calls[0][0]).toBe(
      "/api/materials/material%2F1/document/pages/269?version_id=v1&revision_id=r1",
    );
    expect(fetch.mock.calls[0][1]).toMatchObject({ credentials: "include" });
  });
  it("has GET-only scoped recovery when a job or review acknowledgement is lost", async () => {
    const fetch = vi.fn(async () => new Response("{}"));
    vi.stubGlobal("fetch", fetch);
    await documentApi.jobByRequest("m1", "request-1");
    await documentApi.reviewByRequest("m1", "request-2");
    expect(fetch.mock.calls.map((x) => x[0])).toEqual([
      "/api/materials/m1/document/jobs/requests/request-1",
      "/api/materials/m1/document/reviews/request-2",
    ]);
    expect(fetch.mock.calls.every((x) => !x[1]?.method)).toBe(true);
  });
  it("does not call a server conflict an unknown successful write", () => {
    expect(uncertainDocumentWrite(new ApiError("stale", 409))).toBe(false);
    expect(uncertainDocumentWrite(new Error("connection lost"))).toBe(true);
    expect(uncertainDocumentWrite(new ApiError("upstream lost", 502))).toBe(
      true,
    );
  });
  it("does not fabricate a progress percentage", () => {
    const job = {
      status: "running",
      page_count: 317,
      processed_pages: 0,
    } as DocumentJob;
    expect(processingLabel(job)).toBe("Processing complete document…");
    expect(processingLabel({ ...job, processed_pages: 12 })).toContain(
      "12 of 317",
    );
    expect(processingLabel({ ...job, status: "failed" })).toContain(
      "original is retained",
    );
  });
  it("only verifies the new exact revision and source-checked block mutation", () => {
    const next = { ...info, revision_id: "r2" };
    const change = {
      block_id: "p269-b1",
      text: "Checked source",
      quality: "approved" as const,
      reason: "Compared source image",
    };
    expect(reviewReadbackMatches(info, next, next, page, [change])).toBe(true);
    expect(
      reviewReadbackMatches(info, next, { ...next, revision_id: "r3" }, page, [
        change,
      ]),
    ).toBe(false);
    expect(
      reviewReadbackMatches(
        info,
        next,
        { ...next, source_sha256: "b".repeat(64) },
        page,
        [change],
      ),
    ).toBe(false);
    expect(
      reviewReadbackMatches(info, next, next, page, [
        { ...change, text: "Fabricated source" },
      ]),
    ).toBe(false);
    expect(
      reviewReadbackMatches(info, next, next, page, [
        { ...change, reason: "Different reason" },
      ]),
    ).toBe(false);
  });
  it("requires a source-review reason without truncating supplied text", () => {
    expect(reviewChangeError("Retain source typo", "")).toContain("original");
    expect(reviewChangeError("🧑".repeat(100000), "Checked")).toBe("");
    expect(reviewChangeError("x".repeat(100001), "Checked")).toContain(
      "100,000",
    );
  });
});
