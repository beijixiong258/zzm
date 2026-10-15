import React from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { TutorMessage } from "../src/TutorMessage";
import type { Message } from "../src/types";
import { fixtureWorkspace } from "./fixtures";
import { selectMaterialFiles } from "../src/material-upload";

const progress = { material_id:"m",revision_id:"r",source_label:"Synthetic source",read_characters:18000,available_characters:70000,eligible_text_complete:false,unresolved_blocks:2,excluded_blocks:0,all_stored_regions_read:false,next_page:5 };
const html = (coverage?: typeof progress[]) => {
  const message:Message={id:"s14-message",role:"assistant",content:"Synthetic source feedback.",question_id:null,created_at:"2026-10-11T00:00:00Z",mode:"openai",metadata:{document_read_coverage:coverage}};
  return renderToStaticMarkup(<TutorMessage message={message} workspace={fixtureWorkspace()} latest paced={false} onQuestion={()=>{}} onOption={()=>{}}/>);
};

describe("complete source and sequential read UI",()=>{
  it("uses configured full processing for every supported source suffix",()=>{
    const formats=["pdf","pptx","docx","doc","txt","md","png","jpg","jpeg","webp"];
    const files=formats.map(f=>new File(["synthetic"],`source.${f}`));
    const queue=selectMaterialFiles(files,{available:true,formats,max_upload_bytes:64*1024*1024,max_pages:1000});
    expect(queue).toHaveLength(formats.length);expect(queue.every(x=>x.processing==="full_document")).toBe(true);
  });
  it("shows actual partial progress and unresolved regions, not whole-file completion",()=>{
    const value=html([progress]);expect(value).toContain("AI source reading progress");expect(value).toContain("More remains from source page 5");expect(value).toContain("2 unresolved source regions remain");expect(value).not.toContain("Available text supplied in full");
  });
  it("distinguishes available-text completion from remaining visual uncertainty",()=>{
    const value=html([{...progress,read_characters:70000,eligible_text_complete:true,next_page:null}]);expect(value).toContain("Available text supplied in full");expect(value).toContain("2 unresolved source regions remain");expect(value).not.toContain("accurate");
  });
  it("does not invent progress on historical messages",()=>{
    expect(html()).not.toContain("AI source reading progress");
  });
});
