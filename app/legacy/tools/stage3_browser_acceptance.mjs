// Real built frontend -> actual FastAPI HTTP -> SQLite. NO app route interception.
// Model evidence is labelled deterministic demo only, NOT LLM teaching quality.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {parseArgs} from 'node:util';
const require=createRequire(new URL('../frontend/package.json',import.meta.url));
const {chromium,expect}=require('@playwright/test');
const {values:args}=parseArgs({options:{'base-url':{type:'string'},'confirm-test-data':{type:'boolean'},'artifact-dir':{type:'string'}}});
const base=(args['base-url']||process.env.AICADEMIYA_TEST_URL||'').replace(/\/$/,'');
const out=args['artifact-dir']||process.env.AICADEMIYA_TEST_ARTIFACT_DIR;
if(!base||!out||!args['confirm-test-data'])throw new Error('Require explicit --confirm-test-data, isolated QA URL and output directory.');
await fs.mkdir(out,{recursive:true});
if(process.env.TMPDIR){process.env.TEMP=process.env.TMPDIR;process.env.TMP=process.env.TMPDIR;}
const checks=[],failures=[],screenshots=[],events=[],pageErrors=[];let browser;let ids={};
const persist=async(status='running')=>fs.writeFile(path.join(out,'result.json'),JSON.stringify({status,checks,failures,screenshots,requests:events,request_count:events.length,page_errors:pageErrors,ids,real_backend:true,real_sqlite:true,synthetic_only:true,real_model:false,intercepted_application_routes:0},null,2));
const shot=async(name,page)=>{const file=path.join(out,name+'.png');await page.screenshot({path:file,fullPage:true});screenshots.push(file);};
const check=async(name,fn,page)=>{try{await fn();checks.push(name);console.log('PASS',name);await persist();return true;}catch(e){failures.push({name,error:String(e),url:page?.url()});console.log('FAIL',name,String(e));if(page){const n=failures.length;await shot('failure-'+n,page).catch(()=>{});await fs.writeFile(path.join(out,'failure-'+n+'.txt'),await page.locator('body').innerText().catch(()=>''));}await persist();return false;}};
const observe=page=>{page.on('pageerror',e=>pageErrors.push({url:page.url(),error:e.message}));page.on('response',r=>{if(r.url().includes('/api/'))events.push({url:r.url(),status:r.status(),method:r.request().method()});});};
const api=async(context,method,url,data,expected=200,extra={})=>{const r=await context.request.fetch(base+url,{method,...(data===undefined?{}:{data}),...extra});events.push({method,url,status:r.status(),expected});if(r.status()!==expected)throw new Error(`${method} ${url}: expected ${expected}, got ${r.status()}: ${(await r.text()).slice(0,500)}`);return r.headers()['content-type']?.startsWith('application/json')?r.json():r;};
const vp=(sid,route,vid)=>`/api/sessions/${sid}/${route}?version_id=${encodeURIComponent(vid)}`;
const go=async(page,route)=>{await page.goto(base+'/#/'+route);};
const tab=async(page,label)=>page.locator('.teacher-page .tabs').getByRole('button',{name:label,exact:true}).click();
const profile={schema_version:1,background:'PRIVATE_BROWSER_BACKGROUND',student_profile:'PRIVATE_BROWSER_STUDENT_PROFILE',response_strategies:'Invite reasoned revision, distinguish mixed follow-ups, and target misconceptions.',tone:'Supportive but direct.',response_detail:'balanced',phases:['warmup','worksheet','quiz','reading','wrap_up'],reading_focus:'Reliability and validity in the public reading.',reading_question_count:2,reference_delivery:'after_sufficient_answer',idle_hint_seconds:0,presentation:'full'};
const q=(id,i,prompt,extra={})=>({id,group_id:'core',ordinal:i,type:'open_response',prompt,options:[],answer_slots:1,images:[],source_label:'Synthetic browser worksheet',source_material_ids:[],source_links:[],...extra});
const draftScope=(w,question=w.tutor.current_question_id||`phase:${w.tutor.phase}`)=>({user:w.user.id,session:w.session.id,version:w.version.id,preview:false,question,intent:'conversation'});
const retryKeys=scope=>({pending:`aicademiya.tutor-request.v1:${JSON.stringify([scope.user,scope.session,scope.version,!!scope.preview])}`,draft:`aicademiya.draft.v1:${JSON.stringify([scope.user,scope.session,scope.version,scope.preview?'teacher-draft':'learning',scope.question,scope.intent])}`});
try{
 const chrome=process.env.AICADEMIYA_CHROME_PATH||(process.platform==='win32'?'C:/Program Files/Google/Chrome/Application/chrome.exe':undefined);
 browser=await chromium.launch({headless:true,...(chrome?{executablePath:chrome}:{})});
 const teacher=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true});
 const student=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true});
 const second=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true});
 const boot=await api(teacher,'GET','/api/bootstrap');
 if(!boot.demo_enabled||boot.ai.mode!=='demo')throw new Error('Target must be isolated explicit demo QA.');
 await api(teacher,'POST','/api/auth/demo',{role:'teacher'});
 const studentUser=(await api(student,'POST','/api/auth/demo',{role:'student',student_index:1})).user;
 await api(second,'POST','/api/auth/demo',{role:'student',student_index:2});
 const created=await api(teacher,'POST','/api/courses',{code:'S3-BROWSER-'+Date.now(),title:'Synthetic stage-three browser lab',description:'Isolated actual SQLite acceptance only.'});
 const lesson=await api(teacher,'POST',`/api/courses/${created.id}/sessions`,{title:'Reference eligibility browser lab',number:1,teaching_profile:{...profile,phases:['worksheet','quiz','wrap_up']}});
 const gate=lesson.id;
 await api(teacher,'PATCH',`/api/sessions/${gate}`,{status:'published',reference_policy:'after_submit',groups:[{id:'core',title:'Core reasoning',kind:'core'}],questions:[q('gate-q',1,'Explain why consistent marking supports reliability.')],reference_answers:{'gate-q':'Synthetic gated comparison: consistent marking improves reliability.'}});
 await api(second,'POST','/api/courses/join',{join_code:created.join_code});
 const gateVersion=(await api(teacher,'POST',`/api/teacher/courses/${created.id}/versions/publish`,{label:'Synthetic gate edition'})).id;
 // Seed figures are session-owned; only edit the isolated QA copy, not source files.
 const seed=(await api(teacher,'GET','/api/courses')).find(c=>c.code==='EDUC7703');
 const sid='session-4';
 const seedDetail=await api(teacher,'GET',`/api/sessions/${sid}`);
 const originalFigures=seedDetail.questions.find(x=>x.images.length===3).images;
 const material=await api(teacher,'POST',`/api/sessions/${sid}/materials`,undefined,200,{multipart:{file:{name:'synthetic-stage3-public.txt',mimeType:'text/plain',buffer:Buffer.from('Reliability means consistent results. Validity concerns supported interpretations for a purpose. Negative scatter plots slope down.')},visibility:'student',kind:'reading'}});
 await api(teacher,'POST',`/api/sessions/${sid}/materials`,undefined,200,{multipart:{file:{name:'synthetic-stage3-private.txt',mimeType:'text/plain',buffer:Buffer.from('PRIVATE_BROWSER_MATERIAL')},visibility:'teacher',kind:'answer_key'}});
 const questions=[q('browser-reliability',1,'Explain why consistent marking supports reliability.'),q('browser-graph',2,'Identify the negative relationship in the original scatter plots and explain it.',{type:'image_matching',images:originalFigures}),q('browser-validity',3,'Explain why validity requires evidence for a purpose.',{options:['Supported interpretation','Automatic teacher confirmation']})].map(x=>({...x,source_material_ids:[material.id]}));
 await api(teacher,'PATCH',`/api/sessions/${sid}`,{title:'Synthetic guided browser reasoning',status:'published',teaching_profile:profile,instructions:'PRIVATE_BROWSER_ADDITIONAL',learning_objectives:['Support assessment claims with reasons.'],reference_policy:'after_attempt',groups:[{id:'core',kind:'core',title:'Assessment word bank',description:'Word bank: reliability; validity; evidence; negative correlation.'}],questions,reference_answers:Object.fromEntries(questions.map(x=>[x.id,'Synthetic comparison for '+x.id]))});
 const tpage=await teacher.newPage();observe(tpage);await go(tpage,`teacher/${sid}`);
 await check('Actual teacher framework and private design editor visible',async()=>{await expect(tpage.getByRole('heading',{name:'Teaching framework',exact:true})).toBeVisible();await expect(tpage.getByLabel('Background & tutor role',{exact:false})).toHaveValue(profile.background);},tpage);
 await check('Unsaved compiled preview is real server output; stale results disappear on edit',async()=>{
  await tpage.getByLabel('Background & tutor role',{exact:false}).fill('PRIVATE_BROWSER_EDITED_BACKGROUND');
  await tpage.getByRole('button',{name:'Compile preview',exact:true}).click();
  await expect(tpage.locator('.tf-preview-result')).toContainText('PRIVATE_BROWSER_EDITED_BACKGROUND');
  expect((await api(teacher,'GET',`/api/sessions/${sid}`)).teaching_profile.background).toBe(profile.background);
  await tpage.getByLabel('Additional instructions',{exact:false}).fill('PRIVATE_BROWSER_EDITED_ADDITIONAL');
  await expect(tpage.locator('.tf-preview-result')).toHaveCount(0);
  await tpage.getByRole('button',{name:'Refresh preview',exact:true}).click();
  await expect(tpage.locator('.tf-preview-result')).toContainText('PRIVATE_BROWSER_EDITED_ADDITIONAL');
  await shot('teacher-compiled-preview',tpage);
 },tpage);
 await check('Teacher UI save has actual GET profile/instruction readback, separate from publication',async()=>{
  await tpage.getByRole('button',{name:'Save content draft',exact:true}).click();
  await expect(tpage.getByText('Saved content draft. Students keep their published edition until the course is published.',{exact:true})).toBeVisible();
  const d=await api(teacher,'GET',`/api/sessions/${sid}`);
  expect(d.teaching_profile.background).toBe('PRIVATE_BROWSER_EDITED_BACKGROUND');expect(d.instructions).toBe('PRIVATE_BROWSER_EDITED_ADDITIONAL');
  await tpage.reload();await expect(tpage.getByLabel('Background & tutor role',{exact:false})).toHaveValue('PRIVATE_BROWSER_EDITED_BACKGROUND');
 },tpage);
 await tab(tpage,'Versions');
 await tpage.getByLabel('Publication / restore label (optional)',{exact:true}).fill('Synthetic guided browser edition');
 await tpage.getByRole('button',{name:'Publish complete course draft',exact:true}).click();
 await expect(tpage.getByText(/Course version .* published/)).toBeVisible();
 const versions=await api(teacher,'GET',`/api/teacher/courses/${seed.id}/versions`);const vid=versions.current_version_id;
 ids={session:sid,version:vid,course:seed.id,gate_session:gate,gate_version:gateVersion,student:studentUser.id};
 await api(student,'POST','/api/courses/join',{join_code:seed.join_code});
 const page=await student.newPage();observe(page);await go(page,`workspace/${sid}?version_id=${vid}`);
 const work=()=>api(student,'GET',vp(sid,'workspace',vid));
 const composer=()=>page.getByRole('textbox',{name:'Message your tutor',exact:true});
 const send=async(message)=>{if(message!==undefined)await composer().fill(message);const response=page.waitForResponse(r=>new URL(r.url()).pathname===`/api/sessions/${sid}/tutor/turn`&&r.request().method()==='POST');await page.getByRole('button',{name:'Send',exact:true}).click();const r=await response;await expect(composer()).toBeEnabled();if(r.status()!==200)throw new Error(`Natural composer ${JSON.stringify(message)} returned ${r.status()}: ${await r.text()}`);return work();};
 await check('Proactive opening is demo labelled, timestamped and refreshed without duplication',async()=>{
  await expect(page.locator('.guided-message-assistant').first()).toContainText('Deterministic demo');
  const w=await work();expect(w.tutor.phase).toBe('warmup');expect(w.messages).toHaveLength(1);
  await page.reload();await expect(composer()).toBeEnabled();expect((await work()).messages).toHaveLength(1);
  expect(JSON.stringify(w)).not.toContain('PRIVATE_BROWSER');expect(w.session.teaching_profile).toBeUndefined();
 },page);
 await send('I am ready to reason about assessment.');
 await check('Single conversation composer with actual word bank/source and no compulsory answer form',async()=>{
  await expect(page.locator('.guided-question[data-question-id="browser-reliability"]')).toContainText('Word bank: reliability');
  await expect(page.locator('.guided-question').first()).toContainText('Synthetic browser worksheet');
  await expect(page.getByRole('textbox',{name:'Edit saved response',exact:true})).toHaveCount(0);
  await expect(page.locator('.guided-composer')).toHaveCount(1);
 },page);
 await check('Scoped unsent conversation survives refresh without becoming a server answer',async()=>{
  await composer().fill('Unsent synthetic conversation draft');await page.reload();await expect(composer()).toHaveValue('Unsent synthetic conversation draft');expect((await work()).attempts).toEqual({});
 },page);
 await check('Lost-response retry is acknowledged from real completed ID on reload without resending',async()=>{
  const before=await work(),scope=draftScope(before),keys=retryKeys(scope);
  const turn={message:'How should I think about consistency?',request_id:'browser-committed-'+Date.now(),action:'message',web_search:false};
  // Real HTTP commits; keep the pre-ack browser state as after a lost response.
  await api(student,'POST',vp(sid,'tutor/turn',vid),turn);const committed=await work();expect(committed.tutor.last_completed_request_id).toBe(turn.request_id);
  await page.evaluate(({scope,keys,turn})=>{localStorage.setItem(keys.pending,JSON.stringify({scope,turn,clear_draft:true}));localStorage.setItem(keys.draft,turn.message);},{scope,keys,turn});
  const postCount=events.filter(x=>x.method==='POST'&&x.url.includes('/tutor/turn')).length;
  await page.reload();await expect(composer()).toHaveValue('');await expect(page.getByRole('button',{name:'Retry previous message',exact:true})).toHaveCount(0);
  expect(await page.evaluate(keys=>[localStorage.getItem(keys.pending),localStorage.getItem(keys.draft)],keys)).toEqual([null,null]);
  expect((await work()).messages).toEqual(committed.messages);expect(events.filter(x=>x.method==='POST'&&x.url.includes('/tutor/turn')).length).toBe(postCount);
 },page);
 await check('Different saved request ID is not inferred complete from matching message text',async()=>{
  const w=await work(),scope=draftScope(w),keys=retryKeys(scope),message=w.messages.findLast(x=>x.role==='user').content;
  await page.evaluate(({scope,keys,message})=>{localStorage.setItem(keys.pending,JSON.stringify({scope,turn:{message,request_id:'not-the-completed-request'},clear_draft:true}));localStorage.setItem(keys.draft,message);},{scope,keys,message});
  await page.reload();await expect(composer()).toHaveValue(message);await expect(page.getByRole('button',{name:'Retry previous message',exact:true})).toBeVisible();
  expect(await page.evaluate(keys=>localStorage.getItem(keys.pending),keys)).not.toBeNull();
  // Remove only this deliberately unsubmitted QA request, never send another answer.
  await page.evaluate(keys=>{localStorage.removeItem(keys.pending);localStorage.removeItem(keys.draft);},keys);await page.reload();await expect(composer()).toHaveValue('');
 },page);
 await check('Two real wrong attempts and two hints remain on first question with original revisions',async()=>{
  const before=await work(),state=before.tutor.question_states['browser-reliability'];
  for(let i=0;i<2;i++){await send('wrong: a reliable test makes everyone pass.');const response=page.waitForResponse(r=>new URL(r.url()).pathname===`/api/sessions/${sid}/tutor/turn`);await page.getByRole('button',{name:'Hint',exact:true}).click();expect((await response).status()).toBe(200);await expect(composer()).toBeEnabled();}
  const w=await work();expect(w.tutor.current_question_id).toBe('browser-reliability');expect(w.tutor.question_states['browser-reliability'].answer_count).toBe(state.answer_count+2);expect(w.tutor.question_states['browser-reliability'].hint_count).toBe(state.hint_count+2);expect(w.attempts['browser-reliability'].revisions.slice(-2).map(x=>x.answer)).toEqual(['wrong: a reliable test makes everyone pass.','wrong: a reliable test makes everyone pass.']);expect(w.attempts['browser-reliability'].reference_revealed).toBe(false);await shot('student-multiple-retries',page);
 },page);
 const mixed='Consistent marking supports reliability because evidence is stable. Why might reliability not guarantee validity?';
 await check('Natural mixed answer/follow-up advances and auto-delivers legitimate instructor comparison',async()=>{
  const w=await send(mixed);expect(w.attempts['browser-reliability'].answer).toBe(mixed);expect(w.tutor.current_question_id).toBe('browser-graph');expect(w.attempts['browser-reliability'].reference_revealed).toBe(true);
  await expect(page.locator('.guided-message-assistant').last()).toContainText('Instructor reference');
 },page);
 await check('Previous-question acknowledgment preserves current and newer old-context drafts',async()=>{
  const w=await work(),current=draftScope(w),old=draftScope(w,'browser-reliability'),keys=retryKeys(old),currentKeys=retryKeys(current);
  const turn={message:mixed,request_id:w.tutor.last_completed_request_id,action:'message',web_search:false};
  await page.evaluate(({old,keys,currentKeys,turn})=>{localStorage.setItem(keys.pending,JSON.stringify({scope:old,turn,clear_draft:true}));localStorage.setItem(keys.draft,'New unsent edit of the previous answer');localStorage.setItem(currentKeys.draft,'Unsent graph reflection');},{old,keys,currentKeys,turn});
  await page.reload();await expect(composer()).toHaveValue('Unsent graph reflection');await expect(page.getByRole('button',{name:'Retry previous message',exact:true})).toHaveCount(0);
  expect(await page.evaluate(keys=>localStorage.getItem(keys.draft),keys)).toBe('New unsent edit of the previous answer');expect((await work()).messages).toEqual(w.messages);
 },page);
 await check('Original three graph images load from backend; canonical question source and word bank visible',async()=>{
  const card=page.locator('.guided-question[data-question-id="browser-graph"]').last();await expect(card.locator('img')).toHaveCount(3);
  await expect.poll(()=>card.locator('img').evaluateAll(xs=>xs.every(x=>x.complete&&x.naturalWidth>0))).toBe(true);
  for(let i=0;i<3;i++)expect(await card.locator('img').nth(i).getAttribute('src')).toContain(originalFigures[i].url);
  await shot('student-original-graphs',page);
 },page);
 await check('Mobile composer, graph and source are reachable without document overflow',async()=>{
  await page.setViewportSize({width:390,height:844});const card=page.locator('.guided-question[data-question-id="browser-graph"]').last();await card.scrollIntoViewIfNeeded();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await card.locator('a').first().click({trial:true});await composer().scrollIntoViewIfNeeded();await expect(composer()).toBeInViewport();await shot('student-mobile-graphs-composer',page);await page.setViewportSize({width:1440,height:1000});
 },page);
 await check('Earlier-question clarification via real progress panel preserves current question/answer',async()=>{
  await page.getByRole('button',{name:'Progress & responses',exact:true}).click();await page.getByLabel('Browse questions',{exact:true}).selectOption('browser-reliability');
  await page.getByRole('button',{name:'Discuss this question',exact:true}).click();await expect(composer()).toBeEnabled();
  await expect.poll(async()=>(await work()).messages.at(-1).presented_question_id).toBe('browser-reliability');
  const w=await work();expect(w.tutor.current_question_id).toBe('browser-graph');expect(w.attempts['browser-reliability'].answer).toBe(mixed);expect(w.attempts['browser-graph']).toBeUndefined();
 },page);
 await check('Pure follow-up alone does not overwrite or answer current worksheet',async()=>{const w=await send('How can I read the direction of these plots?');expect(w.attempts['browser-graph']).toBeUndefined();expect(w.tutor.current_question_id).toBe('browser-graph');},page);
 await send('The downward plot is negative because the paired values move in opposite directions.');
 await send('Validity requires evidence supporting the interpretation for a stated purpose.');
 await check('Required discussion reaches optional invitation, not automatic submission',async()=>{const w=await work();expect(w.tutor.phase).toBe('quiz_offer');expect(w.progress.answered).toBe(3);expect(w.submission.status).toBe('in_progress');await expect(page.getByRole('button',{name:'Try the practice quiz',exact:true})).toBeVisible();},page);
 await check('Try the practice quiz button actually opts into five-item quiz',async()=>{
  const response=page.waitForResponse(r=>new URL(r.url()).pathname===`/api/sessions/${sid}/tutor/turn`);await page.getByRole('button',{name:'Try the practice quiz',exact:true}).click();expect((await response).status()).toBe(200);await expect(composer()).toBeEnabled();expect((await work()).tutor.phase).toBe('quiz');
 },page);
 // If the button is broken, continue with the contract's exact opt-in, recording failure above.
 if((await work()).tutor.phase==='quiz_offer')await send('Yes');
 await check('Optional quiz canonical item/options render in actual conversation, with no private key',async()=>{
  const w=await work(), presented=w.messages.at(-1).metadata.presented_question;
  expect(presented.id).toMatch(/^quiz-/);expect(presented.options.length).toBeGreaterThan(1);expect(JSON.stringify(w)).not.toContain('correct_index');
  const card=page.locator(`[data-question-id="${presented.id}"]`);await expect(card).toBeVisible({timeout:3000});await expect(card).toContainText(presented.prompt);await expect(card.locator('.guided-options button')).toHaveCount(presented.options.length);await shot('student-optional-quiz',page);
 },page);
 await check('Option button submits canonical letter with full visible text and exact backend scoring',async()=>{
  const w=await work(),p=w.messages.at(-1).metadata.presented_question,card=page.locator(`[data-question-id="${p.id}"]`);
  await card.locator('.guided-options button').first().click();await expect(composer()).toHaveValue('A');
  const answered=await send();expect(answered.messages.findLast(x=>x.role==='user').content).toBe('A');expect(answered.tutor.quiz.answered).toBe(1);expect(answered.tutor.quiz.correct).toBe(1);
  await expect(card.locator('.guided-options button').first()).toBeDisabled();
 },page);
 for(const response of ['B','A','2','1'])await send(response);
 await check('Five formative responses independent of three required worksheet records',async()=>{const w=await work();expect(w.tutor.quiz).toEqual({status:'completed',answered:5,total:5,correct:3});expect(Object.keys(w.attempts)).toHaveLength(3);expect(w.tutor.phase).toBe('reading');},page);
 await check('Generated finite public-reading item/source labels render in actual conversation',async()=>{
  const w=await work(),p=w.messages.at(-1).metadata.presented_question;expect(p.id).toMatch(/^reading-/);expect(p.source_labels.length).toBeGreaterThan(0);
  const card=page.locator(`[data-question-id="${p.id}"]`);await expect(card).toBeVisible({timeout:3000});await expect(card).toContainText(p.prompt);for(const source of p.source_labels)await expect(card).toContainText(source);await expect(card).not.toContainText('Question undefined');
 },page);
 for(let i=0;i<2;i++)await send('The public reading gives evidence that reliability concerns consistent results.');
 await send('Finish this discussion.');
 await check('Wrap-up statistics/recorded span, explicit completion without teacher mastery claim',async()=>{const w=await work();expect(w.tutor.phase).toBe('complete');expect(w.submission.status).toBe('in_progress');await expect(page.locator('.guided-time')).toContainText('Recorded span');await expect(page.getByText('Your conversation is saved',{exact:true})).toBeVisible();await shot('student-completed',page);},page);
 await check('Completed-phase composer permits the follow-up promised by UI',async()=>{await send('Why is evidence important?');},page);
 await check('Raw transcript UI download includes real messages/version/timestamps and survives refresh',async()=>{
  // A failed completed follow-up must not prevent download/readback.
  await page.locator('.guided-export summary').click();const dl=page.waitForEvent('download');await page.getByRole('link',{name:'Conversation · text',exact:true}).click();const download=await dl;const file=path.join(out,'downloaded-transcript.txt');await download.saveAs(file);
  const text=await fs.readFile(file,'utf8');const w=await work();expect(text).toContain(mixed);expect(text).toContain(vid);expect(text).toContain(w.messages[0].created_at);expect(text).toContain('| formative=');
  const n=w.messages.length;await page.reload();await expect(page.locator('.guided-message')).toHaveCount(n);expect((await work()).messages).toEqual(w.messages);
 },page);
 await check('Actual explicit learner submission uses confirmation dialog and locks UI',async()=>{
  await page.getByRole('button',{name:'Submit for teacher review',exact:true}).click();await page.getByRole('dialog').getByRole('button',{name:'Submit worksheet',exact:true}).click();await expect(page.locator('.guided-locked')).toBeVisible();expect((await work()).submission.status).toBe('submitted');
 },page);
 await go(tpage,`record/${sid}/${studentUser.id}?version_id=${vid}`);
 await check('Real teacher observation/review confirms target learner without changing preview scope',async()=>{
  await tpage.getByRole('button',{name:'Teacher review',exact:true}).click();await tpage.getByLabel('Teacher note',{exact:true}).fill('Synthetic browser teacher explicitly reviewed this work.');await tpage.getByRole('button',{name:'Confirm completion',exact:true}).click();await expect(tpage.getByText('Teacher confirmation saved.',{exact:true})).toBeVisible();expect((await work()).submission.status).toBe('confirmed');await shot('teacher-confirmed-record',tpage);
 },tpage);
 // Independent gate/decline workflow in second learner context.
 const gp=await second.newPage();observe(gp);await go(gp,`workspace/${gate}?version_id=${gateVersion}`);
 await expect(gp.getByRole('textbox',{name:'Message your tutor',exact:true})).toBeEnabled();
 await check('After-submit reference button genuinely locked before/after sufficient answer',async()=>{
  await gp.getByRole('button',{name:'Progress & responses',exact:true}).click();await expect(gp.getByRole('button',{name:'Request instructor example',exact:true})).toBeDisabled();await gp.getByRole('button',{name:'Close learning panel',exact:true}).click();
  await gp.getByRole('textbox',{name:'Message your tutor',exact:true}).fill('Because evidence supports consistency.');await gp.getByRole('button',{name:'Send',exact:true}).click();await expect(gp.getByRole('button',{name:'Skip the quiz',exact:true})).toBeVisible();
  await gp.getByRole('button',{name:'Progress & responses',exact:true}).click();await expect(gp.getByRole('button',{name:'Request instructor example',exact:true})).toBeDisabled();expect((await api(second,'GET',vp(gate,'workspace',gateVersion))).attempts['gate-q'].reference_revealed).toBe(false);await gp.getByRole('button',{name:'Close learning panel',exact:true}).click();
 },gp);
 await check('Optional quiz decline UI skips without generating questions or blocking submission',async()=>{await gp.getByRole('button',{name:'Skip the quiz',exact:true}).click();await expect(gp.getByRole('textbox',{name:'Message your tutor',exact:true})).toBeEnabled();await expect.poll(async()=>(await api(second,'GET',vp(gate,'workspace',gateVersion))).tutor.quiz.status).toBe('skipped');const w=await api(second,'GET',vp(gate,'workspace',gateVersion));expect(w.tutor.quiz.total).toBe(0);},gp);
 await check('Optional quiz is not required for explicit submission; reference gate opens afterward',async()=>{
  await gp.getByRole('button',{name:'Progress & responses',exact:true}).click();await gp.getByRole('button',{name:'Submit for teacher review',exact:true}).click();await gp.getByRole('dialog').getByRole('button',{name:'Submit worksheet',exact:true}).click();await expect(gp.locator('.guided-locked')).toBeVisible();await gp.getByRole('button',{name:'Request instructor example',exact:true}).click();await expect(gp.locator('.guided-reference')).toContainText('Synthetic gated comparison');
 },gp);
 await check('Publish new edition retains original record/history and historical UI locks writes',async()=>{
  await api(teacher,'PATCH',`/api/sessions/${sid}`,{teaching_profile:{...profile,presentation:'paced'},questions:questions.map((x,i)=>({...x,prompt:i===0?'A newly published reliability prompt.':x.prompt}))});
  const old=await work();expect(old.session.questions[0].prompt).toBe(questions[0].prompt);
  const newer=await api(teacher,'POST',`/api/teacher/courses/${seed.id}/versions/publish`,{label:'Synthetic follow-up edition'});
  await page.reload();await expect(page.getByText('Historical · read-only',{exact:true})).toBeVisible();await expect(composer()).toHaveCount(0);expect((await work()).messages).toEqual(old.messages);expect(page.url()).toContain('version_id='+vid);
  await page.getByLabel('Content edition',{exact:true}).selectOption(newer.id);await expect(composer()).toBeEnabled();expect((await api(student,'GET',vp(sid,'workspace',newer.id))).attempts).toEqual({});
  await page.getByLabel('Content edition',{exact:true}).selectOption(vid);await expect(page.getByText('Historical · read-only',{exact:true})).toBeVisible();await shot('student-historical-edition',page);
 },page);
 await check('English mobile historical record retains download and progress reachability',async()=>{
  await page.setViewportSize({width:390,height:844});await page.getByRole('button',{name:'Progress & responses',exact:true}).click();await expect(page.getByLabel('Browse questions',{exact:true})).toBeVisible();await page.getByLabel('Browse questions',{exact:true}).selectOption('browser-reliability');await expect(page.locator('.guided-saved-answer')).toContainText(mixed);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await expect(page.locator('html')).toHaveAttribute('lang','en');await shot('student-mobile-history',page);
 },page);
 await check('No browser JavaScript exceptions across actual teacher/student workflows',async()=>expect(pageErrors).toEqual([]));
}catch(e){failures.push({name:'Browser scenario interrupted',error:String(e),stack:e.stack});console.error(e);if(browser){let n=0;for(const c of browser.contexts())for(const page of c.pages()){n++;await shot('interrupted-'+n,page).catch(()=>{});await fs.writeFile(path.join(out,'interrupted-'+n+'.txt'),await page.locator('body').innerText().catch(()=>''));}}}
finally{if(browser)await browser.close();await persist(failures.length?'failed':'passed');console.log(JSON.stringify({status:failures.length?'failed':'passed',checks:checks.length,failures:failures.length,requests:events.length,screenshots:screenshots.length}));if(failures.length)process.exitCode=1;}
