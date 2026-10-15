"""Re-runnable CPU/browser Stage16 QA. Run with app/.venv/Scripts/python.exe.
Only synthetic artifacts are written; source is served through an owned Vite dev
server. No production database, real account, GPU or generation endpoint is used.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from browser_fixture import prepare

BROWSER_JS = r'''
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
const [base, backend, out, inputDir, chrome, root, lane='all'] = process.argv.slice(2);
const require=createRequire(path.join(root,'frontend/package.json'));
const {chromium,expect}=require('@playwright/test');
const result={status:'running',synthetic_only:true,groups:[],checks:[],issues:[],page_errors:[],api_trace:[],layout:[],limitations:[],browser_closed:false};
let browser,context,page,cdp,uploaded,version,original,originalBytes;
const sid='s16-session',cid='s16-course';
const api=async(url,options={})=>{const r=await context.request.fetch(base+'/api'+url,options);assert.equal(r.status(),200,url+' '+await r.text());return r.json();};
const control=async(url)=>{const r=await context.request.post(backend+url);assert.equal(r.status(),200);return r.json();};
const metrics=async()=>{const r=await context.request.get(backend+'/__qa/metrics');assert.equal(r.status(),200);return r.json();};
const hash=(b)=>createHash('sha256').update(b).digest('hex');
const shot=async(name)=>{const f=path.join(out,name+'.png');await page.screenshot({path:f,fullPage:true});return f;};
const save=()=>fs.writeFile(path.join(out,'browser-result.json'),JSON.stringify(result,null,2));
function check(name,evidence={}){result.checks.push({name,...evidence});}
async function group(name,fn){if(lane==='ai'&&name!=='ai-periodic-unreachable-visibility-expiry-unmount'){result.groups.push({name,status:'skipped',reason:'--only-ai focused lane'});return;}const rec={name,status:'failed',started_at:new Date().toISOString()};result.groups.push(rec);try{await fn();rec.status='passed';}catch(e){rec.error=String(e);rec.stack=e.stack;const file=await shot('failure-'+name).catch(()=>null);result.issues.push({group:name,error:String(e),screenshot:file,url:page?.url(),body:await page?.locator('body').innerText().catch(()=>null)});}finally{rec.finished_at=new Date().toISOString();await save();console.log(JSON.stringify({group:name,status:rec.status,error:rec.error}));}}
async function home(){await page.goto(base+'/#/home');await expect(page.getByRole('heading',{name:'Course Home',exact:true})).toBeVisible();await expect(page.locator('.session-card').first()).toBeVisible();}
async function materials(){await page.goto(base+'/#/teacher/'+sid);await page.getByRole('navigation',{name:'Teaching session sections'}).getByRole('button',{name:'Materials',exact:true}).click();await expect(page.getByLabel('Choose a folder',{exact:true})).toBeEnabled();}
async function qa(){await page.goto(base+'/#/teacher/'+sid);const nav=page.getByRole('navigation',{name:'Teaching session sections'});result.teaching_tabs=await nav.getByRole('button').allTextContents();const btn=nav.getByRole('button').filter({hasText:/Q\s*&\s*A|Questions?\s*&\s*answers?/i});assert.equal(await btn.count(),1,'Q&A tab '+JSON.stringify(result.teaching_tabs));await btn.click();await expect(page.getByRole('heading',{name:'Select worksheet from the materials',exact:true})).toBeVisible();}
async function layout(name,width,height){await page.setViewportSize({width,height});await page.evaluate(()=>scrollTo(0,0));await page.waitForTimeout(180);const e=await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,bodyWidth:document.body.scrollWidth,offscreen:[...document.querySelectorAll('button,input,select,textarea,dialog[open]')].filter(x=>{const r=x.getBoundingClientRect();return r.width>0&&r.height>0&&(r.left<-2||r.right>innerWidth+2)}).map(x=>({tag:x.tagName,text:(x.innerText||x.getAttribute('aria-label')||'').slice(0,90),left:x.getBoundingClientRect().left,right:x.getBoundingClientRect().right}))}));e.name=name;e.screenshot=await shot(name);result.layout.push(e);assert.ok(e.scrollWidth<=width+2&&e.bodyWidth<=width+2,JSON.stringify(e));assert.equal(e.offscreen.length,0,JSON.stringify(e.offscreen));check(name+' bounds',e);}
try{
 browser=await chromium.launch({headless:false,executablePath:chrome,args:['--no-first-run','--disable-default-apps','--window-size=1440,1000']});
 context=await browser.newContext({viewport:{width:1440,height:1000}});
 await context.addInitScript(()=>{
   window.__qaProgress=[];window.__qaDomProgress=[];window.__qaVisibility=[];
   document.addEventListener('visibilitychange',()=>window.__qaVisibility.push({state:document.visibilityState,at:Date.now()}));
   const open=XMLHttpRequest.prototype.open;
   XMLHttpRequest.prototype.open=function(method,url,...args){this.__qaUrl=String(url);return open.call(this,method,url,...args);};
   const send=XMLHttpRequest.prototype.send;
   XMLHttpRequest.prototype.send=function(body){if(this.__qaUrl?.includes('/materials')){for(const event of ['progress','load'])this.upload.addEventListener(event,e=>window.__qaProgress.push({url:this.__qaUrl,event,loaded:e.loaded,total:e.total,lengthComputable:e.lengthComputable,at:Date.now()}));}return send.call(this,body);};
   document.addEventListener('DOMContentLoaded',()=>new MutationObserver(()=>{for(const e of document.querySelectorAll('progress'))window.__qaDomProgress.push({label:e.getAttribute('aria-label'),value:e.value,text:e.parentElement.innerText,at:Date.now()});}).observe(document.body,{childList:true,subtree:true,attributes:true,characterData:true}));
 });
 await api('/auth/demo',{method:'POST',data:{role:'teacher'}});
 page=await context.newPage();
 page.on('pageerror',e=>result.page_errors.push(String(e)));
 page.on('dialog',async d=>{(result.dialogs??=[]).push({type:d.type(),message:d.message()});await d.accept();});
 page.on('request',r=>{const u=new URL(r.url());if(u.pathname.startsWith('/api/')){const row={path:u.pathname+u.search,method:r.method(),at:Date.now()};if(u.pathname.includes('worksheet-import')&&r.method()==='POST'){try{row.body=r.postDataJSON();}catch{}}result.api_trace.push(row);}});
 page.on('response',r=>{const row=result.api_trace.findLast(x=>x.path===new URL(r.url()).pathname+new URL(r.url()).search&&!x.status);if(row)row.status=r.status();});
 cdp=await context.newCDPSession(page);
 await group('home-session-lifecycle',async()=>{
   original=await api('/sessions/'+sid);
   await api('/sessions/s16-other/materials/attach',{method:'POST',data:{material_id:'s16-shared'}});
   const p=await api('/teacher/courses/'+cid+'/versions/publish',{method:'POST',data:{label:'Synthetic historical baseline'}});version=p.id||p.version_id;assert.ok(version,'version ID '+JSON.stringify(p));result.version_id=version;
   const r=await context.request.get(base+original.materials[0].download_url);assert.equal(r.status(),200);originalBytes=hash(await r.body());
   const historical=await api('/teacher/courses/'+cid+'/versions/'+version);result.historical_before=historical;
   await home();await page.getByRole('button',{name:'Edit session Synthetic Stage16 session',exact:true}).click();
   const dialog=page.getByRole('dialog',{name:'Edit session',exact:true});await expect(dialog.getByLabel('Session title',{exact:true})).toBeEnabled();
   await dialog.getByLabel('Session title',{exact:true}).fill('Stage16 edited title');await dialog.getByLabel('Session number',{exact:true}).fill('16');await dialog.getByLabel('Description',{exact:true}).fill('Stage16 edited subtitle\nSecond synthetic line.');
   await shot('desktop-session-edit');await dialog.getByRole('button',{name:'Save changes',exact:true}).click();await expect(dialog).not.toBeVisible();
   const edited=await api('/sessions/'+sid);assert.equal(edited.number,16);assert.equal(edited.title,'Stage16 edited title');assert.equal(edited.subtitle,'Stage16 edited subtitle\nSecond synthetic line.');check('Home edits persisted through real PATCH/readback',{fields:{number:edited.number,title:edited.title,subtitle:edited.subtitle}});
   await page.getByRole('button',{name:'Delete session Stage16 edited title',exact:true}).click();const deletion=page.getByRole('dialog',{name:'Delete session from draft?',exact:true});await expect(deletion).toBeVisible();await expect(deletion.getByRole('button',{name:'Delete session',exact:true})).toBeEnabled();await deletion.getByRole('button',{name:'Cancel',exact:true}).click();assert.ok((await api('/courses/'+cid+'/sessions')).some(s=>s.id===sid));check('Delete confirmation Cancel keeps the session');
   await page.getByRole('button',{name:'Delete session Stage16 edited title',exact:true}).click();await expect(deletion.getByRole('button',{name:'Delete session',exact:true})).toBeEnabled();await deletion.getByRole('button',{name:'Delete session',exact:true}).click();await expect(deletion).not.toBeVisible();await expect(page.getByRole('button',{name:'Edit session Stage16 edited title',exact:true})).toHaveCount(0);
   assert.ok(!(await api('/courses/'+cid+'/sessions')).some(s=>s.id===sid));assert.ok((await api('/courses/'+cid+'/sessions/trash')).sessions.some(s=>s.id===sid));
   await page.getByText('Deleted sessions',{exact:true}).click();await expect(page.getByRole('button',{name:'Restore session',exact:true})).toBeVisible();await shot('desktop-deleted-session');
   const after=await api('/teacher/courses/'+cid+'/versions/'+version);assert.deepEqual(after,historical);assert.ok((await api('/sessions/s16-other')).materials.some(m=>m.id==='s16-shared'));
   const dr=await context.request.get(base+original.materials[0].download_url+'?version_id='+version);assert.equal(dr.status(),200);assert.equal(hash(await dr.body()),originalBytes);check('Deleted draft preserves historical edition, shared ID and original SHA256',{sha256:originalBytes,version_id:version});
   await page.getByRole('button',{name:'Restore session',exact:true}).click();await expect(page.getByRole('button',{name:'Edit session Stage16 edited title',exact:true})).toBeVisible();const restored=await api('/sessions/'+sid);assert.deepEqual(restored.materials.map(m=>m.id),edited.materials.map(m=>m.id));assert.equal(restored.title,edited.title);assert.equal(restored.number,16);assert.equal(restored.subtitle,edited.subtitle);assert.ok(!(await api('/courses/'+cid+'/sessions/trash')).sessions.some(s=>s.id===sid));check('Deleted sessions restore retains edited fields/material IDs');await layout('desktop-home',1440,1000);await layout('mobile-home',390,844);await page.setViewportSize({width:1440,height:1000});
 });
 await group('materials-folder-progress-edit-remove',async()=>{
   await materials();const before=await api('/courses/'+cid+'/materials');result.material_before_ids=before.materials.map(m=>m.id);
   await page.getByLabel('Choose a folder',{exact:true}).setInputFiles(inputDir);
   await expect(page.getByRole('heading',{name:'Selected files (4)',exact:true})).toBeVisible();
   const selected=await page.getByLabel('Choose a folder',{exact:true}).evaluate(e=>[...e.files].map(f=>({name:f.name,path:f.webkitRelativePath,size:f.size})));
   assert.equal(selected.length,4);assert.ok(selected.every(f=>f.path.startsWith('Stage16Folder/')&&f.size>0));result.selected_files=selected;
   for(const f of selected){assert.equal(f.size,(await fs.stat(path.join(inputDir,f.path.replace(/^Stage16Folder\//,'')))).size);await expect(page.locator('.upload-results li').filter({hasText:f.path})).toContainText(f.size<1024?`${f.size} B`:`${(f.size/1024).toFixed(1)} KiB`);}
   await page.getByRole('button',{name:'Remove selected Stage16Folder/remove-me.txt',exact:true}).click();await expect(page.getByRole('heading',{name:'Selected files (3)',exact:true})).toBeVisible();
   await page.getByLabel('Material type for Stage16Folder/worksheet.docx',{exact:true}).selectOption('worksheet');await page.getByLabel('Material type for Stage16Folder/nested/key.txt',{exact:true}).selectOption('answer_key');await page.getByLabel('Material type for Stage16Folder/nested/reading.txt',{exact:true}).selectOption('reading');
   await shot('desktop-folder-selected');await layout('mobile-folder-selected',390,844);await page.setViewportSize({width:1440,height:1000});
   await cdp.send('Network.enable');await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:20,downloadThroughput:1024*1024,uploadThroughput:128*1024});
   await page.getByRole('button',{name:'Upload selected files',exact:true}).click();await expect(page.locator('progress').first()).toBeVisible();await shot('desktop-upload-progress');await page.waitForFunction(()=>document.querySelectorAll('[data-upload-state="uploaded"]').length===3,{},{timeout:90000});
   await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1});
   await expect(page.locator('.materials-editor > .section-heading button')).toBeEnabled();uploaded=(await api('/courses/'+cid+'/materials')).materials.filter(m=>!result.material_before_ids.includes(m.id));assert.equal(uploaded.length,3);
   const worksheet=uploaded.find(m=>m.title==='worksheet.docx'),key=uploaded.find(m=>m.title==='key.txt'),reading=uploaded.find(m=>m.title==='reading.txt');assert.ok(worksheet&&key&&reading,JSON.stringify(uploaded));assert.equal(worksheet.kind,'worksheet');assert.equal(key.kind,'answer_key');assert.equal(key.visibility,'teacher');assert.equal(reading.kind,'reading');assert.ok(uploaded.every(m=>m.processing!=='full_document'));result.uploaded=uploaded;
   await expect(page.locator('.materials-editor > .notice')).toHaveText('3 files saved. Text/OCR preview only; check each file’s status below.');
   check('Preview-only success notice accurately describes accepted uploads without inventing document jobs');
   const progress=await page.evaluate(()=>({xhr:window.__qaProgress,dom:window.__qaDomProgress}));result.upload_progress=progress;assert.ok(progress.xhr.some(e=>e.event==='progress'&&e.loaded>0&&e.total>0));assert.ok(progress.dom.some(e=>e.value>0));check('Real folder input paths/sizes, per-file types and native XHR upload progress',{files:selected,xhr_events:progress.xhr.length,dom_progress_samples:progress.dom.length,preview_only:true});
   const card=()=>page.locator('.material-card').filter({has:page.getByRole('heading',{name:'worksheet.docx',exact:true})});
   for(const kind of ['slides','worksheet']){await card().getByRole('button',{name:'Edit',exact:true}).click();const form=page.locator('form').filter({has:page.getByRole('heading',{name:'Edit shared material',exact:true})});await form.getByLabel('Edit material type',{exact:true}).selectOption(kind);await form.locator('button.primary').click();await expect(form).toHaveCount(0);assert.equal((await api('/sessions/'+sid)).materials.find(m=>m.id===worksheet.id).kind,kind);assert.equal((await api('/courses/'+cid+'/materials')).materials.length,before.materials.length+3);}
   check('Uploaded type edited and read back without new original IDs');await api('/sessions/s16-other/materials/attach',{method:'POST',data:{material_id:reading.id}});
   const readingCard=page.locator('.material-card').filter({has:page.getByRole('heading',{name:'reading.txt',exact:true})});await expect(readingCard.getByRole('button',{name:'Remove from this session',exact:true})).toBeVisible();await readingCard.getByRole('button',{name:'Remove from this session',exact:true}).click();await expect(page.getByRole('button',{name:'Confirm removal',exact:true})).toBeVisible();await page.getByRole('button',{name:'Confirm removal',exact:true}).click();await expect(readingCard).toHaveCount(0);
   assert.ok(!(await api('/sessions/'+sid)).materials.some(m=>m.id===reading.id));assert.ok((await api('/courses/'+cid+'/materials')).materials.some(m=>m.id===reading.id));assert.ok((await api('/sessions/s16-other')).materials.some(m=>m.id===reading.id));const rb=await context.request.get(base+reading.download_url);assert.equal(rb.status(),200);check('Direct Remove with confirmation only removes this session link; shared original still downloads');await layout('desktop-materials',1440,1000);await layout('mobile-materials',390,844);await page.setViewportSize({width:1440,height:1000});
 });
 await group('qa-from-material-review-commit',async()=>{
   assert.ok(uploaded,'Materials upload prerequisite');const worksheet=uploaded.find(m=>m.title==='worksheet.docx'),key=uploaded.find(m=>m.title==='key.txt');const before=await api('/courses/'+cid+'/materials');const sessionBefore=await api('/sessions/'+sid);
   await qa();const section=page.locator('.worksheet-import');assert.equal(await section.locator('input[type=file]').count(),0);assert.equal(await page.locator('input[type=file]').count(),0);await expect(section.getByRole('checkbox',{name:/AI detection/})).toBeChecked();await section.getByLabel('Worksheet material',{exact:true}).selectOption(worksheet.id);await section.getByLabel('Answer key material',{exact:true}).selectOption(key.id);await section.getByRole('checkbox',{name:/AI detection/}).uncheck();await section.getByRole('button',{name:'Detect questions & answers',exact:true}).click();await expect(section.getByRole('heading',{name:/Review extracted worksheet/})).toBeVisible();
   const previewRequest=result.api_trace.findLast(x=>x.path.endsWith('/worksheet-import/from-material'));assert.deepEqual(previewRequest.body,{material_id:worksheet.id,answer_material_id:key.id,use_ai:false});await expect(section.getByRole('button',{name:'Save reviewed draft',exact:true})).toBeDisabled();
   const prompt=section.locator('.question-edit-body > .form-grid textarea').first();await expect(prompt).toBeVisible();await prompt.fill('Stage16 reviewed prompt: explain the supplied violet source.');await section.getByLabel('Private answer / example',{exact:true}).first().fill('violet');await section.getByRole('checkbox',{name:'I reviewed the extracted questions, references and figures.',exact:true}).check();await shot('desktop-worksheet-review');await layout('mobile-worksheet-review',390,844);await page.setViewportSize({width:1440,height:1000});await section.getByRole('button',{name:'Save reviewed draft',exact:true}).click();await expect(section.getByText('Reviewed worksheet saved to content draft, not published.',{exact:true})).toBeVisible();
   const after=await api('/sessions/'+sid),afterLibrary=await api('/courses/'+cid+'/materials');assert.deepEqual(afterLibrary.materials.map(m=>m.id).sort(),before.materials.map(m=>m.id).sort());assert.deepEqual(after.materials.map(m=>m.id).sort(),sessionBefore.materials.map(m=>m.id).sort());const q=after.questions.find(q=>q.prompt==='Stage16 reviewed prompt: explain the supplied violet source.');assert.ok(q);assert.deepEqual(q.source_material_ids,[worksheet.id]);assert.equal(after.reference_answers[q.id],'violet');result.committed_question=q;check('Q&A defaults AI on, has no upload input, selected source/key parsed locally then edited/reviewed/committed with exact IDs/counts preserved',{material_id:worksheet.id,answer_material_id:key.id,question_id:q.id,material_count:afterLibrary.materials.length});
   await qa();const fresh=page.locator('.worksheet-import');await fresh.getByLabel('Worksheet material',{exact:true}).selectOption(worksheet.id);await fresh.getByLabel('Answer key material',{exact:true}).selectOption('');await fresh.getByRole('checkbox',{name:/AI detection/}).uncheck();await fresh.getByRole('button',{name:'Detect questions & answers',exact:true}).click();await expect(fresh.getByRole('heading',{name:/Review extracted worksheet/})).toBeVisible();assert.deepEqual(result.api_trace.findLast(x=>x.path.endsWith('/worksheet-import/from-material')).body,{material_id:worksheet.id,answer_material_id:null,use_ai:false});await fresh.getByRole('button',{name:'Discard preview',exact:true}).click();assert.deepEqual((await api('/sessions/'+sid)).questions,after.questions);check('Optional no-key local parse uses null, Discard leaves committed content unchanged');await layout('desktop-qa',1440,1000);await layout('mobile-qa',390,844);await page.setViewportSize({width:1440,height:1000});
 });
 await group('ai-periodic-unreachable-visibility-expiry-unmount',async()=>{
   await home();await expect(page.locator('.ai-connection-state').first()).toHaveText('Endpoint reachable',{timeout:10000});
   const conn=()=>result.api_trace.filter(x=>x.path==='/api/ai/connection');const start=conn().length;await page.waitForTimeout(32000);assert.ok(conn().length>start,'30s API refresh missing');const times=conn().map(x=>x.at);result.connection_poll_times=times;const health=await metrics();assert.ok(health.model_protocol_requests.length>=1);check('Real 30s browser refresh reaches localhost /models protocol fixture',{api_poll_times:times,model_gets:health.model_protocol_requests});
   const off=await control('/__qa/model/off');assert.equal(off.fixture_listening,false);const offRead=await metrics();assert.equal(offRead.fixture_listening,false);await expect(page.locator('.ai-connection-state').first()).toHaveText('Connection issue',{timeout:65000});await shot('desktop-ai-unreachable');check('Actual closed localhost model socket updates badge to Connection issue');
   await control('/__qa/model/on');assert.equal((await metrics()).fixture_listening,true);await expect(page.locator('.ai-connection-state').first()).toHaveText('Endpoint reachable',{timeout:65000});
   await control('/__qa/connection-delay/2500');assert.equal((await metrics()).connection_delay_ms,2500);
   const {windowId}=await cdp.send('Browser.getWindowForTarget');await cdp.send('Emulation.setFocusEmulationEnabled',{enabled:false});await cdp.send('Browser.setWindowBounds',{windowId,bounds:{windowState:'minimized'}});await page.waitForTimeout(500);result.native_visibility_after_minimize=await page.evaluate(()=>document.visibilityState);result.visibility_mode=result.native_visibility_after_minimize==='hidden'?'native':'emulated-document-event';
   if(result.visibility_mode!=='native'){result.limitations.push('This Windows automation browser stayed document.visibilityState=visible after real minimize and tab-switch probes. Native OS visibility is unverified; hidden/visible Document events below are explicitly emulated in the real app DOM.');await page.evaluate(()=>{window.__qaVisibilityOverride='hidden';Object.defineProperty(document,'visibilityState',{configurable:true,get:()=>window.__qaVisibilityOverride});document.dispatchEvent(new Event('visibilitychange'));});}
   await page.waitForFunction(()=>document.visibilityState==='hidden',{},{timeout:5000});const hiddenStart=conn().length;await page.waitForTimeout(65000);assert.equal(conn().length,hiddenStart,'Polling continued while document visibility is hidden');
   await cdp.send('Browser.setWindowBounds',{windowId,bounds:{windowState:'normal'}});if(result.visibility_mode!=='native')await page.evaluate(()=>{delete document.visibilityState;document.dispatchEvent(new Event('visibilitychange'));});await page.waitForFunction(()=>document.visibilityState==='visible',{},{timeout:5000});await expect(page.locator('.ai-connection-state').first()).toHaveText('Check expired',{timeout:1500});await shot('desktop-ai-expired');await expect(page.locator('.ai-connection-state').first()).toHaveText('Endpoint reachable',{timeout:8000});assert.ok(conn().length>hiddenStart);result.visibility_events=await page.evaluate(()=>window.__qaVisibility);check('65s hidden Document state skips polling; real TTL expires and visible event refreshes pending expired badge',{visibility_mode:result.visibility_mode,visibility_events:result.visibility_events});
   await control('/__qa/connection-delay/0');const logout=page.getByRole('button',{name:/log out|logout|sign out/i});assert.equal(await logout.count(),1);await logout.click();await expect(page.locator('.ai-connection-state')).toHaveCount(0);const unmountStart=conn().length;await page.waitForTimeout(32000);assert.equal(conn().length,unmountStart,'Authenticated polling continued after logout');check('Logout identity/unmount cleanup cancels subsequent 30s polling');
 });
 const final=await metrics();result.provider_metrics=final;assert.equal(final.blocked_model_requests.length,0);assert.ok(final.model_protocol_requests.every(r=>r.method==='GET'&&r.path==='/v1/models'));check('No model generation/search/network provider calls; only explicit localhost model-list protocol GETs');
 result.limitations.push('CPU preview uploads only; full-document worker/GPU processing deliberately unavailable. AI extraction itself is not invoked. Parent owns full frontend/backend test gates. Current-source Vite lane, not deployment/dist acceptance.');
 if(result.page_errors.length)result.issues.push({group:'console',error:JSON.stringify(result.page_errors)});
 result.scope=lane;result.status=result.groups.every(g=>g.status==='passed'||g.status==='skipped')&&result.issues.length===0?'passed':'failed';
}catch(e){result.status='failed';result.fatal=String(e);result.stack=e.stack;}finally{if(browser){await browser.close();result.browser_closed=true;}await save();console.log(JSON.stringify({status:result.status,checks:result.checks.length,issues:result.issues.map(x=>({group:x.group,error:x.error})),result:path.join(out,'browser-result.json')}));}
process.exitCode=result.status==='passed'?0:1;
'''


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def closed(port):
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(('127.0.0.1', port)) != 0


def ready(proc, url, timeout=40):
    import httpx
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if proc.poll() is not None:
            raise RuntimeError('Owned process exited during readiness: ' + str(proc.returncode))
        try:
            if httpx.get(url, trust_env=False, timeout=2).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(.15)
    raise RuntimeError('Readiness timed out: ' + url)


def stop(proc):
    if not proc or proc.poll() is not None:
        return
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True, timeout=15)
    else:
        proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


def manifest():
    return {str(f.relative_to(ROOT)): hashlib.sha256(f.read_bytes()).hexdigest()
            for f in sorted((ROOT / 'frontend' / 'src').rglob('*')) if f.is_file()}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--artifact-dir')
    p.add_argument('--only-ai', action='store_true', help='Focused real AI badge protocol lane; skips material/home mutation groups')
    p.add_argument('--chrome', default='C:/Users/17193/AppData/Local/hermes/tools/chromium-1208/chrome-win64/chrome.exe')
    a = p.parse_args()
    folder = Path(a.artifact_dir).resolve() if a.artifact_dir else ROOT / 'artifacts' / 'stage16' / 'browser' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
    assert folder.is_relative_to(ROOT / 'artifacts' / 'stage16' / 'browser')
    folder.mkdir(parents=True, exist_ok=False)
    assert Path(a.chrome).is_file(), a.chrome
    node = shutil.which('node')
    assert node, 'Installed Node required'
    _, inputs = prepare(folder)
    before = manifest()
    (folder / 'source-before.json').write_text(json.dumps(before, indent=2), encoding='utf-8')
    ports = [free_port() for _ in range(3)]
    assert len(set(ports)) == 3
    backend_port, frontend_port, model_port = ports
    backend = f'http://127.0.0.1:{backend_port}'
    base = f'http://127.0.0.1:{frontend_port}'
    env = os.environ.copy()
    for key in list(env):
        if key.upper() in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY') or key.startswith('AICADEMIYA_') or key == 'TAVILY_API_KEY':
            env.pop(key, None)
    env.update(AICADEMIYA_DEMO_ENABLED='true', AICADEMIYA_AI_MODE='openai',
               AICADEMIYA_AI_BASE_URL=f'http://127.0.0.1:{model_port}/v1', AICADEMIYA_AI_MODEL='stage16-protocol-fixture',
               AICADEMIYA_AI_API_KEY='', AICADEMIYA_AI_PROVIDER='', AICADEMIYA_WEB_SEARCH_ENABLED='false',
               AICADEMIYA_DOCUMENT_WORKER_COMMAND='', AICADEMIYA_COOKIE_SECURE='false',
               AICADEMIYA_ALLOWED_ORIGINS=base, NO_PROXY='127.0.0.1,localhost,::1', no_proxy='127.0.0.1,localhost,::1',
               PYTHONDONTWRITEBYTECODE='1')
    server_js = folder / 'vite-owned.mjs'
    server_js.write_text("import {createServer} from " + json.dumps((ROOT / 'frontend/node_modules/vite/dist/node/index.js').as_uri()) + ";\nimport react from " + json.dumps((ROOT / 'frontend/node_modules/@vitejs/plugin-react/dist/index.js').as_uri()) + ";\nconst s=await createServer({configFile:false,root:" + json.dumps(str(ROOT / 'frontend')) + ",plugins:[react()],server:{host:'127.0.0.1',port:" + str(frontend_port) + ",strictPort:true,watch:null,proxy:{'/api':{target:" + json.dumps(backend) + ",changeOrigin:true}}}});await s.listen();console.log('OWNED_VITE_READY');\n", encoding='utf-8')
    jsfile = folder / 'browser-harness.mjs'
    jsfile.write_text(BROWSER_JS, encoding='utf-8')
    procs, logs = [], []
    summary = {'status': 'failed', 'artifact_dir': str(folder), 'ports': ports, 'synthetic_only': True, 'owned_processes': []}
    try:
        for name, command, health in [('backend', [sys.executable, str(Path(__file__).with_name('browser_fixture.py')), '--folder', str(folder), '--port', str(backend_port), '--model-port', str(model_port)], backend + '/__qa/metrics'), ('frontend', [node, str(server_js)], base)]:
            log = (folder / (name + '.log')).open('w', encoding='utf-8')
            logs.append(log)
            proc = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
            procs.append(proc)
            summary['owned_processes'].append({'name': name, 'pid': proc.pid})
            ready(proc, health)
        summary['base_url'] = base
        print(json.dumps({'artifact_dir': str(folder), 'base_url': base}), flush=True)
        done = subprocess.run([node, str(jsfile), base, backend, str(folder), str(inputs), a.chrome, str(ROOT), 'ai' if a.only_ai else 'all'], cwd=ROOT, env=env, capture_output=True, text=True, timeout=420)
        (folder / 'harness.log').write_text(done.stdout + '\n' + done.stderr, encoding='utf-8')
        print(done.stdout, flush=True)
        summary['browser_returncode'] = done.returncode
        browser = json.loads((folder / 'browser-result.json').read_text(encoding='utf-8'))
        summary['status'] = browser['status']
        summary['checks'] = len(browser['checks'])
        summary['issues'] = [{'group': x['group'], 'error': x['error']} for x in browser['issues']]
        summary['browser_closed'] = browser['browser_closed']
    except Exception as exc:
        summary['error'] = str(exc)
    finally:
        for proc in reversed(procs):
            stop(proc)
        for log in logs:
            log.close()
        summary['owned_servers_stopped'] = all(proc.poll() is not None for proc in procs)
        summary['owned_ports_closed'] = {str(port): closed(port) for port in ports}
        after = manifest()
        summary['source_changed_during_run'] = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
        (folder / 'source-after.json').write_text(json.dumps(after, indent=2), encoding='utf-8')
        if not summary['owned_servers_stopped'] or not all(summary['owned_ports_closed'].values()) or summary.get('source_changed_during_run'):
            summary['status'] = 'failed'
        (folder / 'result.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0 if summary['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
