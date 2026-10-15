import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {afterEach,describe,expect,it,vi} from "vitest";
import {Brand,AiBadge,connectionLabel} from "../src/ui";
import {readRoute,routeHash,canAccessRoute} from "../src/routes";
import {api} from "../src/api";
import HelpPopover from "../src/HelpPopover";
import Login from "../src/Login";
import type {AiStatus,ConnectionCheck} from "../src/types";
const ai:AiStatus={mode:"openai",configured:true,base_url:"",model:"Synthetic model"};
const checked:ConnectionCheck={status:"connected",checked_at:"2026-10-07T18:00:00Z",message:null};
afterEach(()=>vi.unstubAllGlobals());
describe("Stage7 global navigation and factual model state",()=>{
 it.each(["account","model","search","users"] as const)("roundtrips Settings section %s without a course id",section=>{
  const r={page:"settings" as const,section};expect(readRoute(`#${routeHash(r)}`)).toEqual(r);
 });
 it("keeps old settings and profile destinations valid",()=>{
  expect(readRoute("#/settings")).toEqual({page:"settings"});
  expect(readRoute("#/profile").page).toBe("profile");
  expect(readRoute("#/accounts").page).toBe("accounts");
  expect(readRoute("#/settings/unknown")).toEqual({page:"settings"});
 });
 it("allows account Settings shell for all roles without opening admin-only routes",()=>{
  for(const role of ["student","teacher","admin"] as const)expect(canAccessRoute(role,"settings")).toBe(true);
  expect(canAccessRoute("student","accounts")).toBe(false);expect(canAccessRoute("teacher","accounts")).toBe(true);
  expect(canAccessRoute("student","roster")).toBe(false);expect(canAccessRoute("admin","accounts")).toBe(true);
 });
 it("brand has real accessible home-link semantics",()=>{
  const html=renderToStaticMarkup(<Brand/>);expect(html).toContain('href="#/home"');expect(html).toContain('aria-label="AIcademiya · Course Home"');expect(html).toContain('aicademiya-mark.svg');
 });
 it("configured endpoint alone never appears connected",()=>{
  expect(connectionLabel(ai)).toEqual({status:"not_checked",text:"Not checked"});
  const html=renderToStaticMarkup(<AiBadge ai={ai} detail/>);expect(html).toContain("Active AI Model");expect(html).toContain("Not checked");expect(html).not.toContain("Last check passed");
 });
 it("a real stored check is explicitly historical and timestamped",()=>{
  const html=renderToStaticMarkup(<AiBadge ai={{...ai,connection:checked}} detail/>);
  expect(html).toContain("Last check passed");expect(html).toContain('dateTime="2026-10-07T18:00:00Z"');expect(html).toContain("Last checked");
 });
 it("unconfigured and later error override an old success indicator",()=>{
  expect(connectionLabel({...ai,configured:false,connection:checked}).status).toBe("not_configured");
  expect(connectionLabel({...ai,connection:checked,last_error:"Synthetic timeout"}).status).toBe("error");
  expect(connectionLabel({...ai,connection:{...checked,status:"error"}}).status).toBe("error");
 });
 it("keeps deterministic fixtures distinct rather than falsely displaying an active model",()=>{
  const html=renderToStaticMarkup(<AiBadge ai={{...ai,mode:"demo",connection:checked}} detail/>);
  expect(html).toContain("Test fixture");expect(html).not.toContain("Last check passed");expect(html).not.toContain("Active AI Model");
 });
 it("normal login has no product demo controls even on an explicit development backend",()=>{
  const html=renderToStaticMarkup(<Login bootstrap={{app_name:"Synthetic",demo_enabled:true,default_locale:"en",ai}} onAuthenticated={async()=>{}}/>);
  expect(html).not.toContain("demo-login");expect(html).not.toContain("Demo teacher");expect(html).not.toContain("Demo student");expect(html).toContain('type="password"');
 });
 it("short field help has a labelled keyboard button and is initially closed",()=>{
  const html=renderToStaticMarkup(<HelpPopover label="About saved drafts">Save before testing changes.</HelpPopover>);
  expect(html).toContain('type="button"');expect(html).toContain('aria-label="About saved drafts"');expect(html).toContain('aria-expanded="false"');expect(html).not.toContain('role="tooltip"');
 });
 it("search wrappers send explicit server fields and call tests only explicitly",async()=>{
  const fetch=vi.fn(async()=>new Response("{}",{headers:{"Content-Type":"application/json"}}));vi.stubGlobal("fetch",fetch);
  await api.searchSettings();expect(fetch).toHaveBeenCalledTimes(1);
  await api.saveSearchSettings({enabled:true,api_key:"synthetic-test-only"});
  await api.saveSearchSettings({clear_api_key:true});await api.testSearchSettings();
  expect(fetch.mock.calls.map(c=>(c as unknown[])[0])).toEqual(["/api/teacher/search-settings","/api/teacher/search-settings","/api/teacher/search-settings","/api/teacher/search-settings/test"]);
  const args=fetch.mock.calls as unknown as [string,RequestInit][];
  expect(JSON.parse(args[1][1].body as string)).toEqual({enabled:true,api_key:"synthetic-test-only"});
  expect(JSON.parse(args[2][1].body as string)).toEqual({clear_api_key:true});expect(args[3][1].method).toBe("POST");
 });
});
