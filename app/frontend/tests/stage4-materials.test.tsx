import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../src/api";
import Materials from "../src/Materials";
import MaterialManager from "../src/MaterialManager";
import {
  materialReadbackMatches,
  selectMaterialFiles,
  uploadMaterialQueue,
  type MaterialUpload,
} from "../src/material-upload";
import type { Material, SessionDetail } from "../src/types";
const material = (name = "A.txt"): Material => ({
  id: name,
  title: name,
  kind: "reading",
  visibility: "student",
  source_label: name,
  status: "ready",
  excerpt: "Synthetic reading text",
  download_url: `/api/materials/${name}/download`,
});
const files = () =>
  ["A.txt", "B.txt", "C.txt"].map(
    (name) => new File([`Synthetic ${name}`], name, { type: "text/plain" }),
  );
const session = (): SessionDetail => ({
  id: "s1",
  course_id: "c1",
  title: "Synthetic",
  subtitle: "",
  number: 1,
  status: "draft",
  question_count: 0,
  estimated_minutes: 10,
  learning_objectives: [],
  instructions: "",
  teaching_language: "en",
  reference_policy: "after_attempt",
  questions: [],
  groups: [],
  materials: [],
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("stage4 bounded multi-file queue", () => {
  it("uploads all selected files once with the same session scope", async () => {
    const items = selectMaterialFiles(files()),
      changes: MaterialUpload[] = [];
    const upload = vi.fn(async (_sid, f) => material(f.name));
    const accepted = await uploadMaterialQueue(
      "s1",
      items,
      { visibility: "teacher", kind: "slides" },
      (i) => changes.push(i),
      () => true,
      upload,
    );
    expect(accepted.map((m) => m.id)).toEqual(["A.txt", "B.txt", "C.txt"]);
    expect(upload).toHaveBeenCalledTimes(3);
    expect(upload.mock.calls.every((args) => args[0] === "s1")).toBe(true);
    expect(changes.map((i) => i.status)).toEqual([
      "uploading",
      "uploaded",
      "uploading",
      "uploaded",
      "uploading",
      "uploaded",
    ]);
  });
  it("continues after one failure and retries only that file with its original metadata", async () => {
    let rows = selectMaterialFiles(files());
    const changed = (item: MaterialUpload) => {
      rows = rows.map((r) => (r.key === item.key ? item : r));
    };
    const upload = vi.fn(async (_sid, f) => {
      if (f.name === "B.txt") throw new Error("Synthetic upload rejection");
      return material(f.name);
    });
    await uploadMaterialQueue(
      "s1",
      rows,
      { visibility: "teacher", kind: "slides" },
      changed,
      () => true,
      upload,
    );
    expect(rows.map((r) => r.status)).toEqual([
      "uploaded",
      "failed",
      "uploaded",
    ]);
    const retry = vi.fn(async (_sid, f) => material(f.name));
    await uploadMaterialQueue(
      "s1",
      rows,
      { visibility: "student", kind: "reading" },
      changed,
      () => true,
      retry,
    );
    expect(retry).toHaveBeenCalledTimes(1);
    expect(retry).toHaveBeenCalledWith("s1", rows[1].file, "teacher", "slides", "preview", expect.any(Function));
    expect(rows.every((r) => r.status === "uploaded")).toBe(true);
  });
  it("retains accepted uploads even when extraction needs review instead of uploading duplicates", async () => {
    const rows = selectMaterialFiles(files().slice(0, 1));
    const changes: MaterialUpload[] = [];
    const result = await uploadMaterialQueue(
      "s1",
      rows,
      { visibility: "student", kind: "reading" },
      (i) => changes.push(i),
      () => true,
      async () => ({
        ...material(),
        status: "error",
        warning: "Synthetic extraction failure",
      }),
    );
    expect(result).toHaveLength(1);
    expect(changes.at(-1)?.status).toBe("uploaded");
    expect(changes.at(-1)?.material?.status).toBe("error");
  });
  it("does not resubmit successful rows after a refresh failure", async () => {
    const item = {
      ...selectMaterialFiles(files())[0],
      status: "uploaded" as const,
      material: material(),
    };
    const upload = vi.fn();
    await uploadMaterialQueue(
      "s1",
      [item],
      { visibility: "student", kind: "reading" },
      () => {},
      () => true,
      upload,
    );
    expect(upload).not.toHaveBeenCalled();
  });
  it("stops pending files and suppresses old-session UI callbacks after navigation", async () => {
    let active = true;
    const changed = vi.fn();
    const upload = vi.fn(async () => {
      active = false;
      return material();
    });
    const result = await uploadMaterialQueue(
      "old",
      selectMaterialFiles(files()),
      { visibility: "student", kind: "reading" },
      changed,
      () => active,
      upload,
    );
    expect(upload).toHaveBeenCalledTimes(1);
    expect(changed).toHaveBeenCalledTimes(1);
    expect(result).toHaveLength(1);
  });
  it("does not collapse distinct same-named files in a selection", () => {
    const items = selectMaterialFiles([
      new File(["one"], "same.txt"),
      new File(["two"], "same.txt"),
    ]);
    expect(new Set(items.map((x) => x.key)).size).toBe(2);
  });
  it("checks actual readback metadata, not just response status", () => {
    const m = material();
    expect(materialReadbackMatches(m, { ...m })).toBe(true);
    expect(materialReadbackMatches(m)).toBe(false);
    expect(materialReadbackMatches(m, { ...m, visibility: "teacher" })).toBe(
      false,
    );
    expect(materialReadbackMatches(m, { ...m, excerpt: "stale" })).toBe(false);
  });
});

describe("stage4 materials controls and authenticated previews", () => {
  it("offers multiple supported uploads and separate Session/Course controls", () => {
    const html = renderToStaticMarkup(
      <MaterialManager session={session()} onChanged={() => {}} />,
    );
    expect(html).toContain("Session materials");
    expect(html).toContain("Reuse a course material");
    expect(html).toContain('multiple=""');
    expect(html).toContain(".png,.jpg,.jpeg,.webp");
    expect(html).toContain("Upload selected files");
  });
  it("opens PDFs as authenticated top-level links, without a sandboxed iframe", () => {
    const m = {
      ...material("file.pdf"),
      preview_kind: "pdf" as const,
      preview_url: "/api/materials/m1/preview?version_id=old",
    };
    const html = renderToStaticMarkup(
      <Materials materials={[m]} versionId="v2" />,
    );
    expect(html).toContain('href="/api/materials/m1/preview?version_id=v2"');
    expect(html).toContain('target="_blank"');
    expect(html).toContain('rel="noopener noreferrer"');
    expect(html).toContain("Open PDF preview");
    expect(html).not.toContain("iframe");
  });
  it("retains a pre-pinned preview version when there is no parent override", () => {
    const html = renderToStaticMarkup(
      <Materials
        materials={[
          {
            ...material(),
            preview_kind: "pdf",
            preview_url: "/api/materials/m1/preview?version_id=historic",
          },
        ]}
      />,
    );
    expect(html).toContain("version_id=historic");
  });
  it("labels session removal separately from file deletion", () => {
    const html = renderToStaticMarkup(
      <Materials
        materials={[material()]}
        teacher
        onArchive={async () => {}}
        onReprocess={async () => {}}
      />,
    );
    expect(html).toContain("Remove from this session");
    expect(html).not.toContain("Archive material");
    expect(html).toContain("Re-extract text / OCR");
  });
  it("shows coverage, limits and visual-review information rather than claiming full understanding", () => {
    const m: Material = {
      ...material(),
      extraction_report: {
        schema_version: 1,
        method: "native+cpu_ocr",
        units_total: 10,
        units_processed: 9,
        ocr_units: 4,
        images_detected: 5,
        chars_extracted: 53000,
        excerpt_chars: 50000,
        truncated: true,
        visual_review_required: true,
        failed_units: ["Page 10 could not be read"],
        notes: ["Skipped: page 201-210 (native-unit limit)."],
      },
    };
    const html = renderToStaticMarkup(<Materials materials={[m]} teacher />);
    expect(html).toContain("Processed 9 of 10 parts");
    expect(html).toContain("OCR used on 4");
    expect(html).toContain("Page 10 could not be read");
    expect(html).toContain("not all visual meaning");
    expect(html).toContain(
      "selected excerpts, not the full text of every file",
    );
    expect(html).toContain("Coverage notes &amp; limits");
    expect(html).toContain("Skipped: page 201-210");
  });
  it("does not leak teacher-only material from the shared list to students", () => {
    const html = renderToStaticMarkup(
      <Materials
        materials={[{ ...material("PRIVATE_KEY"), visibility: "teacher" }]}
      />,
    );
    expect(html).not.toContain("PRIVATE_KEY");
  });
  it("sends course list, attach and reprocess to exactly scoped endpoints", async () => {
    const fetcher = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ materials: [] }),
    }));
    vi.stubGlobal("fetch", fetcher);
    await api.courseMaterials("course/one");
    await api.attachMaterial("s2", "m1");
    await api.reprocessMaterial("s2", "m1");
    expect(fetcher.mock.calls.map((r: unknown[]) => r[0])).toEqual([
      "/api/courses/course%2Fone/materials",
      "/api/sessions/s2/materials/attach",
      "/api/sessions/s2/materials/m1/reprocess",
    ]);
    expect(fetcher.mock.calls[1][1].body).toBe(
      JSON.stringify({ material_id: "m1" }),
    );
  });
});
