// Owned Stage7 additive browser gates. Real HTTP only; never intercepts routes.
export async function stage7ShellGates(h) {
 const {browser,teacher,student,api,go,check,shot,observe,expect,notes,legacy}=h;
 const page=await teacher.newPage();observe(page);
 await check('Global Settings Account is available to all roles; direct admin sections never fetch for non-admin',async()=>{
  for(const role of ['teacher','student']){
   const ctx=await browser.newContext();await api(ctx,'POST','/api/auth/demo',{role});const p=await ctx.newPage();observe(p);const privileged=[];
   p.on('request',r=>{if(/\/api\/teacher\/(settings|search-settings)|\/api\/admin\//.test(r.url()))privileged.push(r.url())});
   for(const section of ['account','model','search','users']){await go(p,'settings/'+section);const courseScope=['0.9.0','0.10.0'].includes(process.env.AICADEMIYA_QA_TARGET_API)&&role==='teacher'&&section==='users';await expect(p.getByRole('heading',{name:courseScope?'Course Students':'Account',exact:true}).first()).toBeVisible();await expect(p.getByRole('button',{name:'AI Model',exact:true})).toHaveCount(0);await expect(p.getByRole('button',{name:'Global User Accounts',exact:true})).toHaveCount(0);}
   expect(privileged).toEqual([]);await ctx.close();
  }
 });
 const admin=await browser.newContext({viewport:{width:1440,height:1000}});const settings=await admin.newPage();observe(settings);await api(admin,'POST','/api/auth/demo',{role:'admin'});
 const priorModel=await api(admin,'GET','/api/teacher/settings');await api(admin,'PUT','/api/teacher/settings',{mode:'openai',base_url:'http://127.0.0.1:9/v1',model:'Synthetic Stage7 shell model'});
 await check('Settings natural AI Model shell has no mode choices or automatic test POST',async()=>{
  const tests=[];settings.on('request',r=>{if(r.method()==='POST'&&/\/api\/teacher\/(settings|search-settings)\/test$/.test(r.url()))tests.push(r.url())});
  await go(settings,'settings/model');await expect(settings.getByRole('heading',{name:'AI Model',exact:true})).toBeVisible();await expect(settings.locator('.mode-choices')).toHaveCount(0);
  await expect(settings.locator('.sidebar')).toContainText('Active AI Model');expect(tests).toEqual([]);await shot('stage7-settings-shell',settings);
 },settings);
 await check('Help focus/Enter/Escape and mobile tap stay accessible inside viewport',async()=>{
  await go(settings,'settings/search');await expect(settings.getByRole('heading',{name:'Web Search',exact:true})).toBeVisible();const help=settings.getByRole('button',{name:'Help with Tavily API key',exact:true});await expect(help).toBeVisible();await help.focus();await expect(help).toBeFocused();await expect(settings.getByRole('tooltip')).toBeVisible();await settings.keyboard.press('Enter');await expect(settings.getByRole('tooltip')).toBeVisible();await settings.keyboard.press('Escape');await expect(settings.getByRole('tooltip')).toHaveCount(0);
  await settings.setViewportSize({width:390,height:844});await help.click();await expect(settings.getByRole('tooltip')).toBeVisible();const b=await settings.getByRole('tooltip').boundingBox();expect(b.x).toBeGreaterThanOrEqual(0);expect(b.x+b.width).toBeLessThanOrEqual(390);expect(await settings.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await shot('stage7-mobile-help',settings);await settings.keyboard.press('Escape');
 },settings);
 await check('Brand real link keyboard returns Course Home and Settings unsaved cancellation retains draft',async()=>{
  await settings.setViewportSize({width:1440,height:1000});await settings.getByLabel('API key',{exact:true}).fill('SYNTHETIC_UNSAVED_KEY_NEVER_STORE');const brand=settings.getByRole('link',{name:'AIcademiya · Course Home',exact:true});await expect(brand).toHaveAttribute('href','#/home');settings.once('dialog',d=>d.dismiss());await brand.focus();await settings.keyboard.press('Enter');await expect(settings.getByLabel('API key',{exact:true})).toHaveValue('SYNTHETIC_UNSAVED_KEY_NEVER_STORE');settings.once('dialog',d=>d.accept());await brand.click();await expect(settings).toHaveURL(/#\/home$/);expect(await settings.evaluate(()=>JSON.stringify({local:{...localStorage},session:{...sessionStorage}}))).not.toContain('SYNTHETIC_UNSAVED_KEY_NEVER_STORE');
 },settings);
 await api(admin,'PUT','/api/teacher/settings',{mode:priorModel.ai.mode,base_url:priorModel.ai.base_url,model:priorModel.ai.model});await admin.close();await page.close();
 if(legacy)notes.push({pending_final_gate:'Stage7 CourseLibrary route/membership navigation and natural teacher collapsed/Advanced gates intentionally NOT run against explicitly stale Stage6-labelled dist. Strict final run must exercise them.'});
}

export async function stage7TeacherGates(h) {
 const {page,expect,check,shot,legacy}=h;
 if(legacy)return;
 await check('Natural teacher task scope excludes course roster/version tabs and hides technical details by default',async()=>{
  const nav=page.getByRole('navigation',{name:'Teaching session sections',exact:true});for(const name of ['Teaching setup','Materials','Questions & answers','Student work'])await expect(nav.getByRole('button',{name,exact:true})).toBeVisible();
  await expect(nav.getByRole('button',{name:'Course roster',exact:true})).toHaveCount(0);await expect(nav.getByRole('button',{name:'Versions',exact:true})).toHaveCount(0);await expect(page.getByRole('button',{name:'Import instructions',exact:true})).toBeVisible();
  const sources=page.locator('details').filter({has:page.locator('summary').filter({hasText:/^Sources & instructions/})});await expect(sources).toHaveCount(1);expect(await sources.evaluate(el=>el.open)).toBe(false);
  const technical=page.locator('.tw-preview summary').filter({hasText:/^Technical details$/}).locator('..');await expect(technical).toHaveCount(1);expect(await technical.evaluate(el=>el.open)).toBe(false);await shot('stage7-natural-teacher-collapsed',page);
 },page);
 await check('Advanced low-frequency controls begin collapsed and keyboard expand without hiding core objectives/instructions',async()=>{
  const advanced=page.locator('details').filter({has:page.locator('summary').filter({hasText:/Advanced|Timing|Schedule/})});expect(await advanced.count()).toBeGreaterThan(0);
  for(let i=0;i<await advanced.count();i++)expect(await advanced.nth(i).evaluate(el=>el.open)).toBe(false);
  const first=advanced.first(),summary=first.locator(':scope > summary');await summary.focus();await page.keyboard.press('Enter');expect(await first.evaluate(el=>el.open)).toBe(true);await page.keyboard.press('Enter');expect(await first.evaluate(el=>el.open)).toBe(false);await expect(page.locator('.tf-additional textarea')).toBeVisible();await shot('stage7-advanced-keyboard',page);
 },page);
}

export async function openSources(page,legacy) {
 if(legacy)return;
 const details=page.locator('details').filter({has:page.locator('summary').filter({hasText:/^Sources & instructions/})});
 if(!await details.evaluate(el=>el.open))await details.locator('summary').click();
}

export async function openSourceTechnical(page,legacy) {
 if(legacy)return;
 const details=page.locator('.tw-source-result details');
 for(let i=0;i<await details.count();i++){const d=details.nth(i);if(!await d.evaluate(el=>el.open))await d.locator(':scope > summary').click();}
}

export async function teacherBrandCancel(h) {
 const {page,editor,expect,check,api,teacher,sid}=h;
 await check('Brand and raw hash navigation cancel cannot silently discard unsaved teaching draft',async()=>{
  const raw=await editor.inputValue(),before=(await api(teacher,'GET',`/api/sessions/${sid}`)).instructions;
  page.once('dialog',d=>d.dismiss());await page.getByRole('link',{name:'AIcademiya · Course Home',exact:true}).click();await expect(page).toHaveURL(new RegExp('#/teacher/'+sid+'$'));await expect(editor).toHaveValue(raw);
  page.once('dialog',d=>d.dismiss());await page.evaluate(()=>{location.hash='/home'});await expect(page).toHaveURL(new RegExp('#/teacher/'+sid+'$'));await expect(editor).toHaveValue(raw);expect((await api(teacher,'GET',`/api/sessions/${sid}`)).instructions).toBe(before);
 },page);
}

export async function courseLibraryGate(h) {
 const {page,teacher,api,go,expect,check,shot,legacy,course,sid,publicMaterial}=h;
 if(legacy)return;
 await check('CourseLibrary uses canonical same-ID memberships and actual navigation to linked session',async()=>{
  const s2=(await api(teacher,'POST',`/api/courses/${course.id}/sessions`,{title:'Synthetic library destination'})).id;
  await api(teacher,'POST',`/api/sessions/${s2}/materials/attach`,{material_id:publicMaterial.id});const library=await api(teacher,'GET',`/api/courses/${course.id}/materials`);const row=library.materials.find(m=>m.id===publicMaterial.id);expect(row.session_ids.sort()).toEqual([sid,s2].sort());
  await page.reload();await expect(page.getByRole('button',{name:'Course materials',exact:true})).toBeVisible();await page.getByRole('button',{name:'Course materials',exact:true}).click();await expect(page).toHaveURL(new RegExp('#/course-materials/'+course.id+'$'));
  // A row must expose both memberships, not fabricate a course-wide copy/action.
  const card=page.locator(`[data-library-material="${publicMaterial.id}"]`);await expect(card).toBeVisible();const savedSession=await api(teacher,'GET',`/api/sessions/${sid}`);await expect(card).toContainText(savedSession.title);await expect(card).toContainText('Synthetic library destination');await shot('stage7-course-library-memberships',page);
  const open=card.getByRole('button',{name:/Synthetic library destination/});await expect(open).toBeVisible();await open.click();await expect(page).toHaveURL(new RegExp('#/teacher/'+s2+'$'));
  await page.setViewportSize({width:390,height:844});await go(page,`course-materials/${course.id}`);await expect(page.getByText(row.title,{exact:true}).first()).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await shot('stage7-mobile-course-library',page);await page.setViewportSize({width:1440,height:1050});await go(page,`teacher/${sid}`);
 },page);
}

export async function studentWorkspaceGate(h) {
 const {browser,student,api,go,expect,check,shot,observe,sid,vid,legacy}=h;
 const page=await student.newPage();observe(page);
 await check('Actual student workspace mobile composer defaults web search off and preserves version identity',async()=>{
  await page.setViewportSize({width:390,height:844});await go(page,`workspace/${sid}?version_id=${vid}`);const composer=page.getByRole('textbox',{name:'Message your tutor',exact:true});await expect(composer).toBeVisible();await composer.scrollIntoViewIfNeeded();await expect(composer).toBeInViewport();const search=page.getByRole('switch',{name:'Web search',exact:true});await expect(search).toHaveAttribute('aria-checked','false');expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await shot('stage7-student-mobile-workspace',page);
  const raw=await api(student,'GET',`/api/sessions/${sid}/workspace?version_id=${vid}`);expect(raw.version.id).toBe(vid);await page.getByRole('button',{name:legacy?'Progress & responses':'Saved responses',exact:true}).click();await expect(page.getByRole('textbox',{name:'Edit saved response',exact:true})).toHaveValue(raw.attempts['s6-q'].answer);await shot('stage7-student-mobile-saved-response',page);
 },page);await page.close();
}
