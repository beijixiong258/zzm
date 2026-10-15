import React from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { documentApi } from "../src/document-api";
import SourceCitations from "../src/SourceCitations";
import type { Message } from "../src/types";

const citation:NonNullable<Message["citations"]>[number]={kind:"document_supplement",material_id:"m",revision_id:"r",version_id:"v",supplement_id:"s1",source_kind:"speaker_notes",source_part:"ppt/notesSlides/notesSlide1.xml",source_label:"Synthetic slides",page:null,block_id:"s1",quote:"Exact source note.",url:"/api/materials/m/document/supplements/s1/text?version_id=v&revision_id=r"};

describe("supplementary source locators",()=>{
  it("builds revision and edition bound text URL",()=>{
    expect(documentApi.supplementUrl("m","s1","r","v")).toBe(citation.url);
  });
  it("shows source part without inventing a PDF page",()=>{
    const html=renderToStaticMarkup(<SourceCitations citations={[citation]}/>);
    expect(html).toContain("Open cited source note");expect(html).toContain("notesSlide1.xml");expect(html).not.toContain("PDF page");
  });
  it("rejects a different revision or material link",()=>{
    for(const url of [citation.url!.replace("revision_id=r","revision_id=other"),citation.url!.replace("/m/","/other/")]){
      const html=renderToStaticMarkup(<SourceCitations citations={[{...citation,url}]}/>);
      expect(html).toContain("Source-note link unavailable");expect(html).not.toContain("Open cited source note");
    }
  });
  it("does not reinterpret an external forged note link as web evidence",()=>{
    const html=renderToStaticMarkup(<SourceCitations citations={[{...citation,url:"https://invalid.example/",quote:"<script>source text only</script>"}]}/>);
    expect(html).not.toContain('href="https://invalid.example/"');expect(html).not.toContain("<script>");expect(html).toContain("&lt;script&gt;");
  });
});
