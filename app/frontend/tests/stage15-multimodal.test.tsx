import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {describe,expect,it} from "vitest";
import DocumentBlockContent from "../src/DocumentBlockContent";
import SourceCitations from "../src/SourceCitations";
import {TutorMessage} from "../src/TutorMessage";
import {fixtureWorkspace} from "./fixtures";
import type {Message} from "../src/types";

describe("multimodal source presentation",()=>{
 it("preserves observed inline cell breaks without admitting arbitrary HTML",()=>{
  const text="| Activity | Class |\n| --- | --- |\n| First<br>Second | T → C<br>T ↔ Ss |";
  const html=renderToStaticMarkup(<DocumentBlockContent text={text} format="markdown"/>);
  expect(html).toMatch(/First<br\s*\/?>\s*Second/);expect(html).toMatch(/T → C<br\s*\/?>\s*T ↔ Ss/);
 });
 it("renders Markdown headings and source table cells with raw text retained",()=>{
  const text="# Source rubric\n\n| Band | Description |\n| --- | --- |\n| 3− | Limited range |";
  const html=renderToStaticMarkup(<DocumentBlockContent text={text} format="markdown"/>);
  expect(html).toContain("<h1>Source rubric</h1>");expect(html).toContain("<table>");expect(html).toContain("<td>3−</td>");expect(html).toContain("Raw transcription");
 });
 it("allows Markdown prose with a safe merged-cell HTML table",()=>{
  const text="## Comparison\n\n<table><tr><th colspan=\"2\">Trait</th></tr><tr><td>A</td><td>B</td></tr></table>\n\n**Source note**";
  const html=renderToStaticMarkup(<DocumentBlockContent text={text} format="markdown"/>);
  expect(html).toContain("<h2>Comparison</h2>");expect(html).toMatch(/col[Ss]pan="2"/);expect(html).toContain("<strong>Source note</strong>");
 });
 it("does not execute source HTML or load arbitrary Markdown images",()=>{
  const html=renderToStaticMarkup(<DocumentBlockContent format="markdown" text={'![source](https://example.invalid/image.png)\n<script>alert(1)</script>'}/>);
  expect(html).not.toContain("<img");expect(html).not.toContain("<script");expect(html).toContain("Raw transcription");
 });
 it("labels image evidence without inventing a verbatim quotation or block",()=>{
  const html=renderToStaticMarkup(<SourceCitations citations={[{kind:"document",evidence_kind:"source_image",source_label:"Original diagram",material_id:"m",revision_id:"r",version_id:"v",page:3,block_id:null,quote:"",url:"/api/materials/m/preview?version_id=v#page=3"}]}/>);
  expect(html).toContain("Original page image");expect(html).toContain("Open cited original page");expect(html).not.toContain("<blockquote");expect(html).not.toContain("block null");
 });
 it("distinguishes selected-view coverage from retained unresolved alternatives",()=>{
  const m:Message={id:"alternative-progress",role:"assistant",mode:"openai",created_at:"2026-10-12T00:00:00Z",content:"Source response",question_id:null,metadata:{document_read_coverage:[{material_id:"m",revision_id:"r",source_label:"Book",read_characters:1915,available_characters:1915,eligible_text_complete:true,unresolved_blocks:1,excluded_blocks:0,all_stored_regions_read:false,next_page:null,text_view_id:"synthetic-view",alternative_text_blocks:92,alternative_text_characters:1879,alternative_unresolved_blocks:8,alternative_excluded_blocks:2}]}};
  const html=renderToStaticMarkup(<TutorMessage message={m} workspace={fixtureWorkspace()} latest paced={false} onQuestion={()=>{}} onOption={()=>{}}/>);
  expect(html).toContain("selected-view characters supplied");expect(html).toContain("Selected text view supplied in full");expect(html).toContain("92 alternative text blocks retained outside this reading count");expect(html).toContain("8 alternative blocks need source review");expect(html).toContain("2 alternative blocks were explicitly excluded");expect(html).toContain("1 unresolved selected-view regions remain");expect(html).not.toContain("Available text supplied in full");expect(html).not.toContain("3,794");
 });
 it("keeps image coverage separate from completed text coverage",()=>{
  const m:Message={id:"image-progress",role:"assistant",mode:"openai",created_at:"2026-10-12T00:00:00Z",content:"Source response",question_id:null,metadata:{document_read_coverage:[{material_id:"m",revision_id:"r",source_label:"Book",read_characters:12,available_characters:12,eligible_text_complete:true,unresolved_blocks:1,excluded_blocks:0,all_stored_regions_read:false,next_page:null,visual_read_pages:2,available_image_pages:3,visual_read_complete:false}]}};
  const html=renderToStaticMarkup(<TutorMessage message={m} workspace={fixtureWorkspace()} latest paced={false} onQuestion={()=>{}} onOption={()=>{}}/>);
  expect(html).toContain("Available text supplied in full");expect(html).toContain("Original page images supplied: 2 / 3");expect(html).toContain("More images remain");
 });
});
