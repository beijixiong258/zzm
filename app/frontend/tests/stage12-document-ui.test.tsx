import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { authorizedDocumentAsset } from "../src/document-state";
import {
  materialReadbackMatches,
  selectMaterialFiles,
  uploadMaterialQueue,
} from "../src/material-upload";
import SourceCitations from "../src/SourceCitations";
import Materials from "../src/Materials";
import type { Material } from "../src/types";
const material: Material = {
  id: "m1",
  title: "Synthetic PDF",
  kind: "reading",
  visibility: "student",
  source_label: "Synthetic",
  status: "processing",
  excerpt: "",
  preview_kind: "pdf",
  download_url: "/api/materials/m1/download",
  preview_url: "/api/materials/m1/preview",
  processing: "full_document",
};
describe("Stage12 complete document UI helpers/SSR (not backend acceptance)", () => {
  it("accepts completed/failed readbacks of saved full originals, not source identity changes", () => {
    for (const status of ["ready", "needs_review", "error"] as const)
      expect(
        materialReadbackMatches(material, {
          ...material,
          processing: undefined,
          status,
          excerpt: "Changed by the background job",
        }),
      ).toBe(true);
    expect(
      materialReadbackMatches(material, { ...material, id: "other" }),
    ).toBe(false);
    expect(
      materialReadbackMatches(material, {
        ...material,
        download_url: "/different",
      }),
    ).toBe(false);
    expect(
      materialReadbackMatches(material, { ...material, source_label: "other" }),
    ).toBe(false);
    expect(
      materialReadbackMatches(
        { ...material, processing: "preview" },
        { ...material, status: "ready" },
      ),
    ).toBe(false);
  });
  it("freezes full-PDF mode while other/unconfigured formats remain preview", () => {
    const files = [
      new File(["fixture"], "a.PDF"),
      new File(["fixture"], "b.txt"),
    ];
    expect(selectMaterialFiles(files, true).map((q) => q.processing)).toEqual([
      "full_document",
      "preview",
    ]);
    expect(
      selectMaterialFiles(files).every((q) => q.processing === "preview"),
    ).toBe(true);
  });
  it("retains failed queue mode on retry and never resubmits an accepted file", async () => {
    let rows = selectMaterialFiles([new File(["fixture"], "a.pdf")], true);
    const changed = (q: (typeof rows)[number]) => {
      rows = [q];
    };
    const upload = vi
      .fn()
      .mockRejectedValueOnce(new Error("fixture rejection"))
      .mockResolvedValue(material);
    await uploadMaterialQueue(
      "s",
      rows,
      { kind: "reading", visibility: "teacher" },
      changed,
      () => true,
      upload,
    );
    await uploadMaterialQueue(
      "s",
      rows,
      { kind: "slides", visibility: "student" },
      changed,
      () => true,
      upload,
    );
    expect(upload.mock.calls[1].slice(2,5)).toEqual([
      "teacher",
      "reading",
      "full_document",
    ]);
    await uploadMaterialQueue(
      "s",
      rows,
      { kind: "reading", visibility: "student" },
      changed,
      () => true,
      upload,
    );
    expect(upload).toHaveBeenCalledTimes(2);
  });
  it("keeps the complete-document 64MiB limit before posting", async () => {
    const upload = vi.fn();
    const q = selectMaterialFiles(
      [new File([new Uint8Array(64 * 1024 * 1024 + 1)], "large.pdf")],
      true,
    );
    let error = "";
    await uploadMaterialQueue(
      "s",
      q,
      { kind: "reading", visibility: "student" },
      (q) => {
        error = q.error || "";
      },
      () => true,
      upload,
    );
    expect(error).toContain("64 MiB");
    expect(upload).not.toHaveBeenCalled();
  });
  it("accepts only exact authorized source assets", () => {
    const url =
      "/api/materials/m1/document/assets/pages/p1.png?revision_id=r1&version_id=v1";
    expect(authorizedDocumentAsset(url, "m1", "r1", "v1")).toBe(url);
    expect(authorizedDocumentAsset(url, "m1", "r2", "v1")).toBe(null);
    expect(authorizedDocumentAsset(url, "m1", "r1", "v2")).toBe(null);
    expect(
      authorizedDocumentAsset("https://outside.test/image", "m1", "r1"),
    ).toBe(null);
    expect(authorizedDocumentAsset(url, "m2", "r1")).toBe(null);
  });
  it("keeps document quotes literal and edition-pinned while preserving legacy/web sources", () => {
    const html = renderToStaticMarkup(
      <SourceCitations
        citations={[
          {
            kind: "document",
            material_id: "m1",
            revision_id: "r1",
            block_id: "p269-b1",
            page: 269,
            printed_label: "A147",
            version_id: "old",
            source_label: "Synthetic",
            quote: "<script>alert(1)</script>",
            url: "/api/materials/m1/preview?version_id=old#page=269",
          },
          { source_label: "Legacy file", text: "Legacy quote" },
          {
            kind: "web",
            source_label: "Website",
            url: "https://example.test",
            text: "Retrieved",
          },
        ]}
      />,
    );
    expect(html).toContain("&lt;script&gt;");
    expect(html).not.toContain("<script>");
    expect(html).toContain("#page=269");
    expect(html).toContain("block p269-b1");
    expect(html).toContain("Legacy file");
    expect(html).toContain("Retrieved web sources");
  });
  it("offers the reader on existing material cards without leaking teacher-only files", () => {
    const html = renderToStaticMarkup(
      <Materials
        materials={[
          material,
          {
            ...material,
            id: "private",
            visibility: "teacher",
            title: "Private original",
          },
        ]}
        versionId="old"
      />,
    );
    expect(html).toContain("Full PDF / processing status");
    expect(html).not.toContain("Private original");
    expect(html).toContain("version_id=old");
  });
});
