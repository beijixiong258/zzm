// Real built UI + FastAPI + SQLite. No route mocking; all users/data are synthetic.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
const require=createRequire(new URL('../frontend/package.json',import.meta.url));
const {chromium,expect}=require('@playwright/test');
const base=process.env.AICADEMIYA_TEST_URL;
if(!base)throw new Error('Run on an isolated stage2 QA server');
const out=process.env.AICADEMIYA_TEST_ARTIFACT_DIR||path.resolve(import.meta.dirname,'../artifacts/stage2/browser');
await fs.mkdir(out,{recursive:true});
if(process.env.TMPDIR){process.env.TEMP=process.env.TMPDIR;process.env.TMP=process.env.TMPDIR;}
const checks=[],screenshots=[],errors=[],apiErrors=[];let browser;let result;
const check=async(name,fn)=>{await fn();checks.push(name);console.log('PASS',name);await fs.writeFile(path.join(out,'progress.json'),JSON.stringify({checks,screenshots},null,2));};
const shot=async(name,page,fullPage=true)=>{const target=path.join(out,name+'.png');await page.screenshot({path:target,fullPage});screenshots.push(target);};
const observe=page=>{page.on('pageerror',e=>errors.push(e.message));page.on('response',r=>{if(r.url().includes('/api/')&&r.status()>=400&&r.status()!==401)apiErrors.push({url:r.url(),status:r.status()});});};
const api=async(context,method,url,data,expected=200)=>{
 const response=await context.request.fetch(base+url,{method,...(data===undefined?{}:{data})});
 if(response.status()!==expected)throw new Error(`${method} ${url}: ${response.status()} ${await response.text()}`);
 return response.headers()['content-type']?.startsWith('application/json')?response.json():response;
};
const go=async(page,route)=>{await page.goto(base+'/#/'+route);};
const tab=async(page,label)=>{await page.locator('.teacher-page .tabs').getByRole('button',{name:label,exact:true}).click();};
try{
 browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const teacher=await browser.newContext({viewport:{width:1440,height:1050}});
 const student=await browser.newContext({viewport:{width:1440,height:1000}});
 const admin=await browser.newContext({viewport:{width:1440,height:1000}});
 await api(teacher,'POST','/api/auth/demo',{role:'teacher'});
 await api(student,'POST','/api/auth/demo',{role:'student',student_index:1});
 await api(admin,'POST','/api/auth/demo',{role:'admin'});
 const c=await api(teacher,'POST','/api/courses',{code:'BROWSER-QA',title:'Browser learning lab',description:'Synthetic integrated browser acceptance'});
 const lesson=await api(teacher,'POST',`/api/courses/${c.id}/sessions`,{title:'A versioned learning session',number:1,instructions:'Private synthetic teaching instruction'});
 const sid=lesson.id;const gid=lesson.groups[0].id;
 const questions=['q1','q2'].map((id,i)=>({id,group_id:gid,ordinal:i+1,type:'open_response',prompt:`Browser question ${i+1}: explain with evidence.`,options:[],answer_slots:1,images:[],source_label:'Synthetic worksheet',source_material_ids:[],source_links:[]}));
 await api(teacher,'PATCH',`/api/sessions/${sid}`,{status:'published',questions,reference_answers:{q1:'Synthetic reference one',q2:'Synthetic reference two'}});
 const v1=await api(teacher,'POST',`/api/teacher/courses/${c.id}/versions/publish`,{label:'Original classroom'});
 await api(student,'POST','/api/courses/join',{join_code:c.join_code});
 const page=await student.newPage();observe(page);
 await page.goto(base);
 await check('AIcademiya branding and source-provided application icon',async()=>{
  await expect(page.locator('.brand')).toContainText('AIcademiya');
  await expect(page.locator('link[rel=icon]')).toHaveAttribute('href','/favicon.svg');
  expect((await page.request.get(base+'/aicademiya-mark.svg')).status()).toBe(200);
  expect((await page.request.get(base+'/favicon.ico')).status()).toBe(200);
 });
 await go(page,`workspace/${sid}`);
 await expect(page.locator('#question-select')).toBeVisible();
 await check('Unsent chat and unsaved answer drafts survive refresh without becoming server answers',async()=>{
  await page.getByRole('textbox',{name:'Answer this question',exact:true}).fill('Unsent answer-intent draft');
  await page.getByRole('textbox',{name:'Revise saved answer',exact:true}).fill('Unsaved answer-pane draft');
  await page.getByRole('button',{name:'Ask a follow-up',exact:true}).click();
  await page.getByRole('textbox',{name:'Ask a follow-up',exact:true}).fill('Unsent follow-up draft');
  await page.reload();
  await expect(page.getByRole('textbox',{name:'Answer this question',exact:true})).toHaveValue('Unsent answer-intent draft');
  await expect(page.getByRole('textbox',{name:'Revise saved answer',exact:true})).toHaveValue('Unsaved answer-pane draft');
  await page.getByRole('button',{name:'Ask a follow-up',exact:true}).click();
  await expect(page.getByRole('textbox',{name:'Ask a follow-up',exact:true})).toHaveValue('Unsent follow-up draft');
  const w=await api(student,'GET',`/api/sessions/${sid}/workspace`);
  expect(w.attempts).toEqual({});expect(w.messages).toEqual([]);
 });
 await check('Drafts are isolated by question and account in the same browser',async()=>{
  await page.locator('#question-select').selectOption('q2');
  await expect(page.getByRole('textbox',{name:'Ask a follow-up',exact:true})).toHaveValue('');
  await page.locator('#question-select').selectOption('q1');
  await expect(page.getByRole('textbox',{name:'Ask a follow-up',exact:true})).toHaveValue('Unsent follow-up draft');
  await api(student,'POST','/api/auth/demo',{role:'student',student_index:2});
  await api(student,'POST','/api/courses/join',{join_code:c.join_code});
  await page.reload();
  await expect(page.getByRole('textbox',{name:'Answer this question',exact:true})).toHaveValue('');
  await api(student,'POST','/api/auth/demo',{role:'student',student_index:1});
  await page.reload();
  await expect(page.getByRole('textbox',{name:'Answer this question',exact:true})).toHaveValue('Unsent answer-intent draft');
 });
 await check('Saving/sending persists real work and only clears its matching local draft',async()=>{
  await page.getByRole('button',{name:'Save answer only',exact:true}).click();
  await expect(page.getByRole('button',{name:'Save answer only',exact:true})).toBeDisabled();
  await page.getByRole('button',{name:'Ask a follow-up',exact:true}).click();
  await page.getByRole('textbox',{name:'Ask a follow-up',exact:true}).fill('A saved synthetic follow-up');
  await page.getByRole('button',{name:'Send',exact:true}).click();
  await expect(page.getByRole('textbox',{name:'Ask a follow-up',exact:true})).toHaveValue('');
  await expect(page.locator('.message-assistant')).toContainText('Demo feedback');
  const w=await api(student,'GET',`/api/sessions/${sid}/workspace`);
  expect(w.attempts.q1.answer).toBe('Unsaved answer-pane draft');expect(w.messages).toHaveLength(2);
  await page.getByRole('button',{name:'Answer this question',exact:true}).click();
  await expect(page.getByRole('textbox',{name:'Answer this question',exact:true})).toHaveValue('Unsent answer-intent draft');
 });
 await check('Avatar profile changes only display name and student cannot open model settings',async()=>{
  await page.getByRole('button',{name:'User Profile',exact:true}).click();
  await page.getByLabel('Full name',{exact:true}).fill('Browser Renamed Learner');
  await page.locator('.profile-page').getByRole('button',{name:'Save changes',exact:true}).first().click();
  await expect(page.locator('.profile-entry')).toContainText('Browser Renamed Learner');
  const me=(await api(student,'GET','/api/auth/me')).user;
  expect(me.name).toBe('Browser Renamed Learner');expect(me.email).toBe('demo-student-1@example.invalid');
  await go(page,'settings');await expect(page.getByRole('alert')).toContainText('not available to your role');
  await expect(page.getByRole('button',{name:'Model settings',exact:true})).toHaveCount(0);
 });
 const tpage=await teacher.newPage();observe(tpage);await go(tpage,`teacher/${sid}`);
 await check('Teacher tab order and role-limited model navigation',async()=>{
  await expect(tpage.getByRole('heading',{name:'A versioned learning session',exact:true})).toBeVisible();
  expect((await tpage.locator('.teacher-page .tabs button').allTextContents()).slice(0,3)).toEqual(['Configuration','Materials','Questions & references']);
  await expect(tpage.getByRole('button',{name:'Model settings',exact:true})).toHaveCount(0);
 });
 await tab(tpage,'Materials');
 let uploaded;
 await check('Real file upload and authenticated basic preview',async()=>{
  await tpage.locator('.material-create-grid form').first().getByLabel('Choose a file',{exact:true}).setInputFiles({name:'browser-reading.txt',mimeType:'text/plain',buffer:Buffer.from('Real uploaded synthetic reading: stable marking supports reliability.')});
  await tpage.locator('.material-create-grid form').first().getByRole('button',{name:'Upload material',exact:true}).click();
  await expect(tpage.getByText('browser-reading.txt',{exact:true}).first()).toBeVisible();
  const detail=await api(teacher,'GET',`/api/sessions/${sid}`);uploaded=detail.materials.find(m=>m.title==='browser-reading.txt');expect(uploaded).toBeTruthy();
  await tpage.getByRole('button',{name:'Preview material',exact:true}).first().click();
  await expect(tpage.locator('.preview-text')).toContainText('Real uploaded synthetic reading');
  await tpage.getByRole('button',{name:'Close preview',exact:true}).click();
 });
 await check('Independent upload/Link visibility controls and real Link entry',async()=>{
  const forms=tpage.locator('.material-create-grid form');
  await forms.first().getByLabel('Material type',{exact:true}).selectOption('answer_key');
  await expect(forms.first().getByLabel('Who can view it?',{exact:true})).toHaveValue('teacher');
  await expect(forms.last().getByLabel('Who can view it?',{exact:true})).toHaveValue('student');
  await forms.last().getByLabel('URL / DOI',{exact:true}).fill('https://example.org/');
  await forms.last().getByLabel('Title',{exact:true}).fill('Public example Link');
  await forms.last().getByRole('button',{name:'Save Link',exact:true}).click();
  await expect(tpage.getByText('Public example Link',{exact:true}).first()).toBeVisible({timeout:35000});
  await expect(tpage.getByRole('link',{name:'Open source link',exact:true}).first()).toHaveAttribute('href','https://example.org/');
 });
 await tab(tpage,'Questions & references');
 await check('Source multi-select is real saved data and blank remains all materials',async()=>{
  const card=tpage.locator('.question-edit-card').first();
  await expect(card.getByText(/All materials · no selection/)).toBeVisible();
  await card.locator('.source-material-picker summary').click();
  await card.getByLabel('browser-reading.txt',{exact:false}).check();
  await card.getByPlaceholder('https://… / 10.1234/example').fill('https://example.org/');
  await card.getByRole('button',{name:'Add source',exact:true}).click();
  await tpage.getByRole('button',{name:'Save content draft',exact:true}).click();
  await expect(tpage.getByText(/Saved content draft/)).toBeVisible();
  const detail=await api(teacher,'GET',`/api/sessions/${sid}`);
  expect(detail.questions[0].source_material_ids).toEqual([uploaded.id]);expect(detail.questions[0].source_links).toEqual(['https://example.org/']);
  expect(detail.questions[1].source_material_ids).toEqual([]);
 });
 await check('Groups/questions can be added, edited, reordered and removed',async()=>{
  await tpage.getByRole('button',{name:'Add group',exact:true}).click();
  const group=tpage.locator('.group-editor').last();
  await group.getByLabel('Title',{exact:true}).fill('Optional reading group');await group.locator('select').selectOption('reading');
  const newGroup=await group.locator('code').textContent();
  await tpage.getByRole('button',{name:'Add question',exact:true}).click();
  const card=tpage.locator('.question-edit-card').last();
  await card.getByLabel('Question prompt',{exact:true}).fill('Added in the real editor');
  await card.getByLabel('Group',{exact:true}).selectOption(newGroup);
  await card.getByLabel('Teacher reference response',{exact:true}).fill('Synthetic teacher reference for new question');
  await card.getByRole('button',{name:/Move question up/}).click();
  await tpage.getByRole('button',{name:'Save content draft',exact:true}).click();
  await expect(tpage.getByText(/Saved content draft/)).toBeVisible();
  let d=await api(teacher,'GET',`/api/sessions/${sid}`);expect(d.questions.some(q=>q.prompt==='Added in the real editor')).toBe(true);
  await tpage.locator('.group-editor').last().getByRole('button',{name:'Delete group',exact:true}).click();
  await tpage.locator('.confirmation').getByRole('button',{name:'Delete',exact:true}).click();
  await tpage.getByRole('button',{name:'Save content draft',exact:true}).click();
  await expect(tpage.getByText(/Saved content draft/)).toBeVisible();
  d=await api(teacher,'GET',`/api/sessions/${sid}`);expect(d.questions).toHaveLength(2);
 });
 await check('Real original worksheet imports22 questions/three figures into a reviewed draft only',async()=>{
  const before=await api(teacher,'GET',`/api/sessions/${sid}`);
  await tpage.getByLabel('Worksheet file',{exact:true}).setInputFiles('D:/HermesProjects/EDUC7703/Course Materials - Session 4/EDUC7703 Session 4 Worksheet_student.docx');
  await tpage.getByRole('button',{name:'Extract preview',exact:true}).click();
  await expect(tpage.locator('.import-review')).toBeVisible({timeout:60000});
  await expect(tpage.locator('.import-review .question-edit-card')).toHaveCount(22);
  await expect(tpage.getByRole('button',{name:'Save reviewed content draft',exact:true})).toBeDisabled();
  await tpage.locator('.import-review').getByText('Extracted figures',{exact:false}).click();
  await expect(tpage.locator('.import-review .question-images').first().locator('img')).toHaveCount(3);
  await expect.poll(()=>tpage.locator('.import-review .question-images').first().locator('img').evaluateAll(xs=>xs.every(x=>x.complete&&x.naturalWidth>0))).toBe(true);
  await shot('worksheet-import-review',tpage,false);
  await tpage.getByLabel('I reviewed the extracted questions, references and figures.',{exact:true}).check();
  await tpage.getByRole('button',{name:'Save reviewed content draft',exact:true}).click();
  await expect(tpage.getByText(/Reviewed worksheet saved/)).toBeVisible();
  const after=await api(teacher,'GET',`/api/sessions/${sid}`);expect(after.questions).toHaveLength(before.questions.length+22);
  const sw=await api(student,'GET',`/api/sessions/${sid}/workspace`);expect(sw.session.questions).toHaveLength(2);
 });
 await tab(tpage,'Configuration');
 await check('Deactive closes student writes without losing drafts/history, schedule takes priority',async()=>{
  await tpage.getByLabel('Manually active (used only without a schedule)',{exact:true}).uncheck();
  await tpage.getByRole('button',{name:'Apply availability now',exact:true}).click();
  await expect(tpage.getByText('Availability saved and read back.',{exact:true})).toBeVisible();
  await go(page,`workspace/${sid}`);await expect(page.locator('.composer')).toHaveCount(0);
  await expect(page.getByRole('textbox',{name:'Revise saved answer',exact:true})).toHaveCount(0);
  await expect(page.getByRole('link',{name:'Export original record',exact:true}).first()).toBeVisible();
  await tpage.getByLabel('Starts at (inclusive)',{exact:true}).fill('2020-01-01T00:00');
  await tpage.getByLabel('Ends at (exclusive)',{exact:true}).fill('2099-01-01T00:00');
  await expect(tpage.getByLabel('Manually active (used only without a schedule)',{exact:true})).toBeDisabled();
  await tpage.getByRole('button',{name:'Apply availability now',exact:true}).click();
  await expect(tpage.getByText('Availability saved and read back.',{exact:true})).toBeVisible();
  const d=await api(teacher,'GET',`/api/sessions/${sid}`);expect(d.active).toBe(false);expect(d.effective_active).toBe(true);
  await page.reload();await page.locator('#question-select').selectOption('q1');await expect(page.getByRole('textbox',{name:'Answer this question',exact:true})).toHaveValue('Unsent answer-intent draft');
 });
 await tab(tpage,'Versions');let v2;
 await check('Publish exposes a new edition while original learning remains version-bound',async()=>{
  await tpage.getByLabel('Publication / restore label (optional)',{exact:true}).fill('Browser published edition');
  await tpage.getByRole('button',{name:'Publish complete course draft',exact:true}).click();
  await expect(tpage.getByText(/Course version 2 published/)).toBeVisible();
  const list=await api(teacher,'GET',`/api/teacher/courses/${c.id}/versions`);v2=list.versions.find(v=>v.id===list.current_version_id);
  await go(page,`workspace/${sid}`);await page.reload();await expect(page.getByLabel('Content edition',{exact:true})).toHaveValue(v2.id);await expect(page.getByRole('textbox',{name:'Answer this question',exact:true})).toHaveValue('');
  await page.getByLabel('Content edition',{exact:true}).selectOption(v1.id);
  await expect(page.locator('.composer')).toHaveCount(0);await expect(page.getByText('Historical · read-only',{exact:true})).toBeVisible();
  expect(page.url()).toContain('version_id='+v1.id);
  await page.locator('#question-select').selectOption('q1');
  await expect(page.locator('body')).toContainText('Unsaved answer-pane draft');
  await shot('student-historical-record',page);
 });
 await check('Version browser renders real differences and restore creates a new edition',async()=>{
  await tpage.getByRole('button',{name:'Browse & compare',exact:true}).first().click();
  await expect(tpage.locator('.diff-card').first()).toBeVisible();
  await expect(tpage.locator('.version-snapshot')).toContainText('Original classroom');
  await shot('version-diff',tpage,false);
  await tpage.getByRole('button',{name:'Restore as new edition',exact:true}).click();
  await tpage.getByRole('button',{name:'Confirm restore',exact:true}).click();
  await expect(tpage.getByText(/Course version 3 published/)).toBeVisible();
  const restored=await api(teacher,'GET',`/api/sessions/${sid}`);expect(restored.questions).toHaveLength(2);expect(restored.starts_at).toBeTruthy();
 });
 await tab(tpage,'Course roster');const rosterEmail='browser-import@example.invalid';
 await check('CSV import preview/commit actually creates a first-change account without displaying its password',async()=>{
  await tpage.getByText('Import CSV / XLSX roster',{exact:true}).click();
  await tpage.getByLabel('Choose a file',{exact:true}).setInputFiles({name:'students.csv',mimeType:'text/csv',buffer:Buffer.from(`name,email,temporary_password\nImported Browser Learner,${rosterEmail},SyntheticBrowser9\n`)});
  await tpage.getByRole('button',{name:'Validate and preview',exact:true}).click();
  await expect(tpage.getByRole('button',{name:'Commit reviewed import',exact:true})).toBeEnabled();
  expect(await tpage.locator('body').innerText()).not.toContain('SyntheticBrowser9');
  await tpage.getByRole('button',{name:'Commit reviewed import',exact:true}).click();
  await expect(tpage.getByText('Import committed · Created 1 · Enrolled 0 · Restored 0 · Skipped 0',{exact:true})).toBeVisible();
  await expect(tpage.getByText(rosterEmail,{exact:true})).toBeVisible();
  const list=await api(teacher,'GET',`/api/teacher/courses/${c.id}/students`);expect(list.find(r=>r.user.email===rosterEmail).user.must_change_password).toBe(true);
 });
 await check('Roster recycle bin shows retention and restore preserves shared students',async()=>{
  await tpage.getByRole('checkbox',{name:'demo-student-1@example.invalid',exact:true}).check();
  await tpage.getByRole('button',{name:'Archive selected (1)',exact:true}).click();
  await tpage.locator('.confirmation').getByRole('button',{name:'Confirm archive',exact:true}).click();
  await tpage.getByRole('button',{name:'Recycle bin',exact:true}).click();
  const archivedRow=tpage.getByRole('row').filter({hasText:'demo-student-1@example.invalid'});
  await expect(archivedRow.locator('.retention-countdown')).toContainText('30d');
  await shot('roster-recycle-bin',tpage);
  await tpage.getByRole('checkbox',{name:'demo-student-1@example.invalid',exact:true}).check();
  await tpage.getByRole('button',{name:'Restore selected (1)',exact:true}).click();
  await tpage.locator('.confirmation').getByRole('button',{name:'Confirm restore',exact:true}).click();
  await expect(tpage.getByText('No students in this list',{exact:true})).toBeVisible();
  const old=await api(student,'GET',`/api/sessions/${sid}/workspace?version_id=${v1.id}`);expect(old.attempts.q1.answer).toBe('Unsaved answer-pane draft');
 });
 // Real account UI; passwords are tested only via the synthetic HTTP client.
 const real=await browser.newContext({viewport:{width:1280,height:950}});
 await api(real,'POST','/api/auth/login',{email:rosterEmail,password:'SyntheticBrowser9'});
 const rp=await real.newPage();observe(rp);
 await check('New imported student remains gated; profile password API validates current password',async()=>{
  await go(rp,'profile');await expect(rp.getByRole('heading',{name:'Make this account yours.',exact:true})).toBeVisible();
  await api(real,'POST','/api/auth/change-password',{current_password:'SyntheticBrowser9',new_password:'SyntheticChanged9'});
  await rp.reload();await expect(rp.getByRole('heading',{name:'User Profile',exact:true})).toBeVisible();
  await expect(rp.getByLabel('Current password',{exact:true})).toBeVisible();
  await api(real,'POST','/api/auth/change-password',{current_password:'WrongSynthetic9',new_password:'SyntheticNewer9'},400);
  await api(real,'POST','/api/auth/change-password',{current_password:'SyntheticChanged9',new_password:'SyntheticNewer9'});
  await rp.reload();await expect(rp.getByRole('heading',{name:'User Profile',exact:true})).toBeVisible();
  await shot('real-student-profile',rp);
 });
 const ap=await admin.newPage();observe(ap);
 await check('Admin model settings and authorized promotion work in real UI',async()=>{
  await go(ap,'settings');await expect(ap.getByRole('heading',{name:'A clear view of your AI connection.',exact:true})).toBeVisible();
  await expect(ap.getByRole('button',{name:'Model settings',exact:true})).toBeVisible();
  await go(ap,'accounts');await ap.getByRole('button',{name:'Promote to admin',exact:true}).first().click();
  await ap.getByRole('button',{name:'Confirm promotion',exact:true}).click();
  await expect(ap.getByText('Teacher promoted to administrator.',{exact:true})).toBeVisible();
  await expect(ap.getByRole('heading',{name:'Global student accounts',exact:true})).toBeVisible();
  await shot('admin-accounts',ap);
 });
 await check('English-only profile and mobile course/workspace layouts are usable',async()=>{
  await go(rp,'profile');
  await expect(rp.getByRole('heading',{name:'User Profile',exact:true})).toBeVisible();
  await expect(rp.getByRole('button',{name:'中文界面',exact:true})).toHaveCount(0);
  await expect(rp.getByRole('button',{name:'English interface',exact:true})).toHaveCount(0);
  await expect(rp.locator('html')).toHaveAttribute('lang','en');
  await rp.setViewportSize({width:390,height:844});expect(await rp.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await shot('profile-mobile-en',rp);
  await page.setViewportSize({width:390,height:844});await go(page,`workspace/${sid}?version_id=${v1.id}`);
  await expect(page.locator('#question-select')).toBeAttached();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await shot('history-mobile',page);
 });
 if(errors.length)throw new Error('Page errors: '+errors.join('; '));
 result={status:'passed',checks,screenshots,page_errors:errors,observed_api_errors:apiErrors,real_backend:true,real_sqlite:true,synthetic_users:true,real_model:false,course_id:c.id,session_id:sid};
}catch(error){
 result={status:'failed',error:String(error),checks,screenshots,page_errors:errors,observed_api_errors:apiErrors};
 if(browser){let n=0;for(const context of browser.contexts())for(const p of context.pages()){n++;await p.screenshot({path:path.join(out,`failure-${n}.png`),fullPage:true}).catch(()=>{});await fs.writeFile(path.join(out,`failure-${n}.txt`),await p.locator('body').innerText().catch(()=>''));}}
 console.error(error);process.exitCode=1;
}finally{
 if(browser)await browser.close();
 await fs.writeFile(path.join(out,'result.json'),JSON.stringify(result,null,2));
 console.log(JSON.stringify({status:result.status,checks:checks.length,screenshots:screenshots.length,error:result.error}));
}
