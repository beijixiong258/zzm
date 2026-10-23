// Real built frontend + live FastAPI + SQLite. No route interception or fixture API.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
const require=createRequire(new URL('../frontend/package.json',import.meta.url));
const {chromium,expect}=require('@playwright/test');
const base=process.env.AICADEMIYA_TEST_URL||'http://127.0.0.1:18773';
const root=path.resolve(import.meta.dirname,'..');
const out=process.env.AICADEMIYA_TEST_ARTIFACT_DIR||path.join(root,'artifacts','browser-integration');
await fs.mkdir(out,{recursive:true});
if(process.env.TMPDIR){process.env.TEMP=process.env.TMPDIR;process.env.TMP=process.env.TMPDIR;}
let browser,page;
const checks=[],screenshots=[],errors=[],apiErrors=[];
const expectedApiErrors=[];
let expectModelFailure=false;
const check=async(name,fn)=>{await fn();checks.push(name);console.log('PASS',name);};
const shot=async(name,p=page)=>{const f=path.join(out,name+'.png');await p.screenshot({path:f,fullPage:true});screenshots.push(f);};
const observe=p=>{p.on('pageerror',e=>errors.push(e.message));p.on('response',r=>{if(r.url().includes('/api/')&&r.status()>=400&&r.status()!==401){const entry={url:r.url(),status:r.status()};if(expectModelFailure&&r.status()===502&&new URL(r.url()).pathname.endsWith('/chat'))expectedApiErrors.push(entry);else apiErrors.push(entry);}});};
let result;
try{
 browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const studentContext=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true});
 page=await studentContext.newPage();observe(page);
 await page.goto(base);await expect(page.getByRole('button',{name:'Student 2',exact:true})).toBeVisible();
 await shot('01-login');
 await check('Sign-in stays English despite stale browser language preferences',async()=>{
  await page.evaluate(()=>{localStorage.setItem('akademiya.locale','zh');localStorage.setItem('aicademiya.locale','zh');});
  await page.reload();await expect(page.getByRole('button',{name:'Student 2',exact:true})).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('lang','en');
  await expect(page.locator('.locale-button')).toHaveCount(0);
 });
 await page.getByRole('button',{name:'Student 2',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Language Testing & Assessment',exact:true})).toBeVisible();
 await shot('02-student-courses');
 await page.goto(base+'/#/workspace/session-4');
 await expect(page.locator('#question-select')).toBeVisible();
 await page.locator('#question-select').selectOption('S4-T1-Q01');
 await check('Original word bank and task instructions are visible',async()=>{await expect(page.locator('.group-context')).toContainText('Word bank: practicality, reliability, authenticity');});
 await check('Reference gated before first attempt',async()=>{await expect(page.getByRole('button',{name:'Request reference',exact:true})).toBeDisabled();await expect(page.getByRole('button',{name:'Submit worksheet',exact:true})).toBeDisabled();});
 await check('UI answer -> real DB -> explicit reference',async()=>{
  await page.getByRole('textbox',{name:'Answer this question',exact:true}).fill('Practicality. The test can run with the available time and resources. [Synthetic QA]');
  await page.getByRole('button',{name:'Send',exact:true}).click();
  await expect(page.getByRole('button',{name:'Request reference',exact:true})).toBeEnabled();
  await expect(page.locator('.message-assistant').last()).toContainText('Demo feedback preview');
  await page.getByRole('button',{name:'Request reference',exact:true}).click();
  await expect(page.locator('.reference-answer')).toContainText('practicality');
 });
 await check('Follow-up does not replace saved answer',async()=>{
  await page.getByRole('button',{name:'Ask a follow-up',exact:true}).click();
  await page.getByRole('textbox',{name:'Ask a follow-up',exact:true}).fill('What kind of classroom resource should I consider? [Synthetic QA]');
  await page.getByRole('button',{name:'Send',exact:true}).click();
  await expect(page.getByRole('textbox',{name:'Revise saved answer',exact:true})).toHaveValue('Practicality. The test can run with the available time and resources. [Synthetic QA]');
  await expect(page.locator('.message-user')).toHaveCount(2);
 });
 const revision='Practicality concerns available time, cost and staff. This is a revised synthetic QA answer.';
 await check('Revision survives real page reload',async()=>{
  await page.getByRole('textbox',{name:'Revise saved answer',exact:true}).fill(revision);
  await page.getByRole('button',{name:'Save answer only',exact:true}).click();
  await expect(page.getByText('Saved',{exact:true}).first()).toBeVisible();
  await page.reload();await page.locator('#question-select').selectOption('S4-T1-Q01');
  await expect(page.getByRole('textbox',{name:'Revise saved answer',exact:true})).toHaveValue(revision);
 });
 await shot('03-student-dialogue');
 await check('Model error preserves the saved answer and retry is idempotent',async()=>{
  const control=await browser.newContext();
  await control.request.post(base+'/api/auth/demo',{data:{role:'admin'}});
  let response=await control.request.put(base+'/api/teacher/settings',{data:{mode:'openai',base_url:'http://127.0.0.1:1/v1',model:'qa-unavailable',api_key:''}});
  if(!response.ok())throw new Error('Could not arrange explicit model failure');
  const text='Synthetic QA retry test: my answer remains saved when the provider is unavailable.';
  await page.getByRole('button',{name:'Answer this question',exact:true}).click();
  await page.getByRole('textbox',{name:'Answer this question',exact:true}).fill(text);
  expectModelFailure=true;
  await page.getByRole('button',{name:'Send',exact:true}).click();
  await expect(page.getByRole('alert').first()).toContainText(/Cannot reach the model endpoint|Model provider returned HTTP 502/);
  await expect(page.getByRole('textbox',{name:'Answer this question',exact:true})).toHaveValue(text);
  await expect(page.getByRole('textbox',{name:'Revise saved answer',exact:true})).toHaveValue(text);
  const failed=await (await page.request.get(base+'/api/sessions/session-4/workspace')).json();
  const versions=failed.attempts['S4-T1-Q01'].revision_count;
  response=await control.request.put(base+'/api/teacher/settings',{data:{mode:'demo',base_url:'',model:'',api_key:''}});
  if(!response.ok())throw new Error('Could not restore explicit demo mode');
  expectModelFailure=false;
  await page.getByRole('button',{name:'Send',exact:true}).click();
  await expect(page.getByRole('textbox',{name:'Answer this question',exact:true})).toHaveValue('');
  const retried=await (await page.request.get(base+'/api/sessions/session-4/workspace')).json();
  if(retried.messages.filter(m=>m.role==='user'&&m.content===text).length!==1||retried.attempts['S4-T1-Q01'].revision_count!==versions)throw new Error('Retry duplicated saved work');
  // Restore the recognizable edited answer used by the teacher readback check.
  await page.getByRole('textbox',{name:'Revise saved answer',exact:true}).fill(revision);
  await page.getByRole('button',{name:'Save answer only',exact:true}).click();
  await expect(page.getByText('Saved',{exact:true}).first()).toBeVisible();
  await control.close();
 });
 await check('Three real worksheet diagrams visible',async()=>{
  await page.locator('#question-select').selectOption('S4-T3-Q01');
  await expect(page.locator('.question-images img')).toHaveCount(3);
  await expect.poll(()=>page.locator('.question-images img').evaluateAll(imgs=>imgs.every(i=>i.complete&&i.naturalWidth>200))).toBe(true);
 });
 await shot('04-real-scatter-plots');
 await check('All 22 real task units can be saved and submitted',async()=>{
  const ids=await page.locator('#question-select option').evaluateAll(os=>os.map(o=>o.value));
  if(ids.length!==22)throw new Error('Expected 22 tasks, got '+ids.length);
  for(const id of ids){
   if(id==='S4-T1-Q01')continue;
   await page.locator('#question-select').selectOption(id);
   await page.getByRole('textbox',{name:'Revise saved answer',exact:true}).fill('Synthetic browser QA response for '+id+'. Not a real learner or AI-produced answer.');
   await page.getByRole('button',{name:'Save answer only',exact:true}).click();
   await expect(page.locator('#question-select')).toBeEnabled();
   await expect(page.getByText('Saved',{exact:true}).first()).toBeVisible();
  }
  await expect(page.getByRole('button',{name:'Submit worksheet',exact:true})).toBeEnabled();
  await page.getByRole('button',{name:'Submit worksheet',exact:true}).click();
  await page.locator('.submit-confirm').getByRole('button',{name:'Submit worksheet',exact:true}).click();
  await expect(page.locator('.workspace-heading-meta')).toContainText('Submitted');
  await expect(page.locator('.composer')).toHaveCount(0);
 });
 await shot('05-submitted');
 await check('Browser export downloads real persisted work',async()=>{
  const event=page.waitForEvent('download');
  await page.getByRole('link',{name:'Export original record',exact:true}).first().click();
  const download=await event;const target=path.join(out,'student-export.json');await download.saveAs(target);
  const data=JSON.parse(await fs.readFile(target,'utf8'));
  if(data.user.id!=='demo-student-2'||Object.keys(data.attempts).length!==22||data.session.reference_answers)throw new Error('Invalid student export projection');
 });
 await page.goto(base+'/#/workspace/session-2');await expect(page.locator('#question-select')).toBeVisible();
 await check('One selected reading gives 14 active units',async()=>{
  const detail=page.locator('.reading-selector details');if(await detail.getAttribute('open')===null)await detail.locator('summary').click();
  await page.getByRole('button',{name:/^Part II · Pong/}).click();
  await expect(page.locator('.reading-option').filter({hasText:/Part II · Pong/})).toHaveClass(/selected/);
  await expect(page.locator('#question-select')).toBeEnabled();
  await expect(page.locator('#question-select option')).toHaveCount(14);
  const ids=await page.locator('#question-select option').evaluateAll(os=>os.map(o=>o.value));
  if(ids.some(id=>id.includes('II-Bray')))throw new Error('Unselected reading counted');
 });
 await check('390px layout has no horizontal overflow and task tab works',async()=>{
  await page.setViewportSize({width:390,height:844});
  await page.locator('.mobile-workspace-tabs button').nth(1).click();
  await expect(page.locator('#question-select')).toBeVisible();
  const metrics=await page.evaluate(()=>({w:innerWidth,scroll:document.documentElement.scrollWidth}));
  if(metrics.scroll>metrics.w)throw new Error('Horizontal overflow '+JSON.stringify(metrics));
 });
 await shot('06-mobile-reading');
 const teacherContext=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true});
 const teacher=await teacherContext.newPage();observe(teacher);await teacher.goto(base);
 await teacher.getByRole('button',{name:'Try as teacher',exact:true}).click();
 await expect(teacher.getByRole('heading',{name:'Language Testing & Assessment',exact:true})).toBeVisible();
 await teacher.goto(base+'/#/teacher/session-4');
 await expect(teacher.getByRole('heading',{name:'What makes a good test?',exact:true})).toBeVisible();
 await shot('07-teacher-configuration',teacher);
 await check('Teacher instruction edits persist and remain private to students',async()=>{
  const field=teacher.getByRole('textbox',{name:'Teaching instructions',exact:true});
  const original=await field.inputValue();
  const changed=original+'\nSynthetic teacher configuration round-trip check.';
  await field.fill(changed);
  await teacher.getByRole('button',{name:'Save content draft',exact:true}).click();
  await expect(teacher.getByText(/Saved content draft/)).toBeVisible();
  const saved=await (await teacher.request.get(base+'/api/sessions/session-4')).json();
  if(saved.instructions!==changed)throw new Error('Teacher edit did not persist');
  const studentView=await (await page.request.get(base+'/api/sessions/session-4')).json();
  if(studentView.instructions)throw new Error('Teacher instructions exposed to student');
  await teacher.reload();await expect(teacher.getByRole('textbox',{name:'Teaching instructions',exact:true})).toHaveValue(changed);
  await teacher.getByRole('textbox',{name:'Teaching instructions',exact:true}).fill(original);
  await teacher.getByRole('button',{name:'Save content draft',exact:true}).click();
  await expect(teacher.getByText(/Saved content draft/)).toBeVisible();
 });
 await check('Teacher upload is parsed, downloadable, and hidden from students',async()=>{
  await teacher.locator('.teacher-page .tabs').getByRole('button',{name:'Materials',exact:true}).click();
  const form=teacher.locator('.material-create-grid form').first();
  await form.getByLabel('Material type',{exact:true}).selectOption('answer_key');
  await expect(form.getByLabel('Who can view it?',{exact:true})).toHaveValue('teacher');
  const marker='SYNTHETIC_TEACHER_ONLY_UPLOAD_FOR_REAL_BROWSER_QA';
  await form.getByLabel('Choose a file',{exact:true}).setInputFiles({name:'qa-teacher-notes.txt',mimeType:'text/plain',buffer:Buffer.from(marker)});
  await form.getByRole('button',{name:'Upload material',exact:true}).click();
  await expect(teacher.getByText('qa-teacher-notes.txt',{exact:true}).first()).toBeVisible();
  const detail=await (await teacher.request.get(base+'/api/sessions/session-4')).json();
  const material=detail.materials.find(m=>m.title==='qa-teacher-notes.txt');
  if(!material||material.status!=='ready'||material.visibility!=='teacher'||!material.excerpt.includes(marker))throw new Error('Upload extraction/projection incorrect');
  const downloaded=await teacher.request.get(base+material.download_url);if((await downloaded.text())!==marker)throw new Error('Uploaded original mismatch');
  // Unpublished material is absent from the student's immutable edition (404).
  const forbidden=await page.request.get(base+material.download_url);
  if(forbidden.status()!==404)throw new Error('Unpublished teacher material must be unavailable to students: '+forbidden.status());
  const studentView=await (await page.request.get(base+'/api/sessions/session-4')).json();if(studentView.materials.some(m=>m.id===material.id))throw new Error('Teacher upload exposed in student payload');
 });
 await shot('07b-teacher-upload',teacher);
 await teacher.goto(base+'/#/record/session-4/demo-student-2');
 await check('Teacher sees exact revision and confirms submitted work',async()=>{
  await expect(teacher.locator('.review-card')).toBeVisible();
  await teacher.locator('#question-select').selectOption('S4-T1-Q01');
  await expect(teacher.locator('.saved-answer > p')).toHaveText(revision);
  await teacher.locator('.review-card textarea').fill('Synthetic QA: reviewed original answers and conversation. No formal grade.');
  await teacher.getByRole('button',{name:'Confirm completion',exact:true}).click();
  await expect(teacher.locator('.workspace-heading-meta')).toContainText('Teacher confirmed');
 });
 await shot('08-teacher-review',teacher);
 await page.setViewportSize({width:1440,height:1000});await page.goto(base+'/#/workspace/session-4');
 await check('Teacher confirmation visible to same student after reload',async()=>{await expect(page.locator('.workspace-heading-meta')).toContainText('Teacher confirmed');await expect(page.locator('.composer')).toHaveCount(0);});
 const adminContext=await browser.newContext();
 await adminContext.request.post(base+'/api/auth/demo',{data:{role:'admin'}});
 const adminPage=await adminContext.newPage();observe(adminPage);
 await adminPage.goto(base+'/#/settings');await expect(adminPage.getByRole('heading',{name:'A clear view of your AI connection.',exact:true})).toBeVisible();
 await shot('09-model-settings-demo',adminPage);
 if(errors.length)throw new Error('Page errors: '+errors.join('; '));
 if(apiErrors.length)throw new Error('Unexpected API errors: '+JSON.stringify(apiErrors));
 result={status:'passed',evidence_mode:'Real integrated backend and SQLite with explicit synthetic test identities/responses; no mocked API',ai_mode:'demo',real_llm_tested:false,checks,screenshots,page_errors:errors,unexpected_api_errors:apiErrors,expected_api_errors:expectedApiErrors};
}catch(e){
 result={status:'failed',error:String(e),checks,screenshots,page_errors:errors,api_errors:apiErrors};
 if(page){await shot('failure').catch(()=>{});await fs.writeFile(path.join(out,'failure-body.txt'),await page.locator('body').innerText().catch(()=>''));}
 console.error(e);process.exitCode=1;
}finally{
 await fs.writeFile(path.join(out,'browser-result.json'),JSON.stringify(result,null,2));
 if(browser)await browser.close();
 console.log(JSON.stringify({status:result.status,checks:checks.length,screenshots:screenshots.length,error:result.error}));
}
