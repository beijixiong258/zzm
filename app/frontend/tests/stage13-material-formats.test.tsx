import React from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { selectMaterialFiles, uploadMaterialQueue } from "../src/material-upload";
import { documentApi } from "../src/document-api";
import SourceCitations from "../src/SourceCitations";

const capability = { available: true, formats: ["pdf", "pptx", "docx", "doc"], max_upload_bytes: 64 * 1024 * 1024, max_pages: 1000 };
describe("Stage13 complete material routing", () => {
  it("freezes explicit format/limit capability per selected file", () => {
    const files = ["deck.PPTX", "paper.docx", "legacy.doc", "reading.pdf", "note.txt", "photo.png"].map(n => new File(["synthetic"], n));
    const queue = selectMaterialFiles(files, capability);
    expect(queue.map(x => x.processing)).toEqual(["full_document", "full_document", "full_document", "full_document", "preview", "preview"]);
    expect(queue.map(x => x.maxBytes)).toEqual([64,64,64,64,25,25].map(x => x * 1024 * 1024));
    expect(selectMaterialFiles(files, { ...capability, available: false }).every(x => x.processing === "preview")).toBe(true);
  });
  it("allows a real-size slide deck only on complete processing", async () => {
    const file = new File([new Uint8Array(33 * 1024 * 1024)], "deck.pptx");
    let called = 0;
    const upload = async () => { called++; return { id: "m", status: "processing" } as any; };
    const queue = selectMaterialFiles([file], capability);
    expect((await uploadMaterialQueue("s", queue, { visibility: "student", kind: "slides" }, () => {}, () => true, upload)).length).toBe(1);
    expect(called).toBe(1);
    expect((await uploadMaterialQueue("s", selectMaterialFiles([file], false), { visibility: "student", kind: "slides" }, () => {}, () => true, upload)).length).toBe(0);
    expect(called).toBe(1);
  });
  it("generates a revision and edition bound rendered URL", () => {
    expect(documentApi.renderedUrl("material", "revision", "edition")).toBe("/api/materials/material/document/pdf?version_id=edition&revision_id=revision");
  });
  it("renders only matching rendered citation identity", () => {
    const citation: any = { kind: "document", source_label: "Slides", quote: "Literal", material_id: "m", revision_id: "r", version_id: "v", page: 2, printed_label: "Slide2", block_id: "p2-b0", url: "/api/materials/m/document/pdf?version_id=v&revision_id=r#page=2" };
    const html = renderToStaticMarkup(<SourceCitations citations={[citation]} />);
    expect(html).toContain("Open cited rendered page");
    expect(html).toContain("revision_id=r");
    const invalid = renderToStaticMarkup(<SourceCitations citations={[{...citation, url: citation.url.replace("revision_id=r", "revision_id=other")}]} />);
    expect(invalid).not.toContain("Open cited rendered page");
    expect(invalid).toContain("link unavailable");
  });
});
