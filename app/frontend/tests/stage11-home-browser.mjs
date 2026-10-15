// Actual Chrome presentation with a labelled HTTP fixture, not backend permission evidence.
import fs from 'node:fs/promises';
import path from 'node:path';
import net from 'node:net';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
const require=createRequire(new URL('../package.json',import.meta.url));
const {chromium,expect}=require('@playwright/test');
const {createServer}=await import(pathToFileURL(require.resolve('vite')).href);
const react=(await import(pathToFileURL(require.resolve('@vitejs/plugin-react')).href)).default;
const root=path.resolve(import.meta.dirname,'..');
const out=path.resolve(root,'../artifacts/stage11/presentation-'+new Date().toISOString().replace(/[:.]/g,'-'));
await fs.mkdir(out,{recursive:true});
const description='This is synthetic course content for layout verification. The description should use the available course banner width rather than remain restricted to the former narrow column.\n\n(1) Preserve the first separate teaching objective exactly as entered.\n(2) Preserve the second objective on its own line, including the empty line above the numbered items.';
const courses={first:{id:'first',code:'EDUC7703',title:'Synthetic multi-teacher course',description,admin_count:1,teacher_count:2,student_count:1,join_code:'SYNTHETIC-ONLY'},second:{id:'second',code:'EDUC1145',title:'Synthetic second course',description:'Second course description.\nA separate line.',admin_count:0,teacher_count:1,student_count:2,join_code:'SYNTHETIC-SECOND'}};
for(const c of Object.values(courses))Object.assign(c,{trashed_at:null,session_count:c.id==='first'?1:2,material_count:0,enrollment_count:c.student_count});
const checks=[],measurements=[],errors=[],shots=[],events=[];let server,browser,page,port;
const shot=async(name)=>{const f=path.join(out,name+'.png');await page.screenshot({path:f,fullPage:!name.startsWith('edit-course'),animations:'disabled',caret:'hide'});shots.push(f);};
try{
 const fixture={name:'stage11-home-fixture',configureServer(s){s.middlewares.use(async(req,res,next)=>{if(!req.url.startsWith('/api/courses/'))return next();const cid=decodeURIComponent(req.url.slice('/api/courses/'.length));const course=courses[cid];if(!course){res.statusCode=404;res.end('{}');return;}const chunks=[];for await(const c of req)chunks.push(c);if(req.method==='PATCH')Object.assign(course,JSON.parse(Buffer.concat(chunks).toString()));events.push({method:req.method,path:req.url});res.setHeader('Content-Type','application/json');res.end(JSON.stringify(course));});}};
 server=await createServer({configFile:false,root,plugins:[fixture,react()],server:{host:'127.0.0.1',port:0,strictPort:false,hmr:false,watch:null},cacheDir:path.join(out,'vite-cache'),logLevel:'error'});await server.listen();port=server.httpServer.address().port;
 browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});page=await browser.newPage({viewport:{width:1440,height:1000}});page.setDefaultTimeout(15000);page.on('pageerror',e=>errors.push(e.message));
 const url=`http://127.0.0.1:${port}/tests/stage11-home-harness.html`;await page.goto(url);await expect(page).toHaveTitle('AIcademiya · EDUC7703');
 const stats=page.locator('.course-stats');await expect(stats.locator('span')).toHaveText(['1Session','1Admin','2Teachers','1Student']);
 for(const width of [1440,2560,3771,390]){
  await page.setViewportSize({width,height:width===390?844:1000});await expect(page.locator('.course-description')).toBeVisible();
  const m=await page.locator('.course-description').evaluate(el=>{const r=el.getBoundingClientRect(),b=el.closest('.course-banner').getBoundingClientRect(),s=getComputedStyle(el);return {width:innerWidth,descriptionWidth:r.width,bannerWidth:b.width,whiteSpace:s.whiteSpace,text:el.textContent,maxWidth:s.maxWidth,overflow:document.documentElement.scrollWidth>innerWidth};});
  expect(m.whiteSpace).toBe('pre-wrap');expect(m.text).toBe(description);expect(m.overflow).toBe(false);if(width>=1440)expect(m.descriptionWidth).toBeGreaterThan(520);measurements.push(m);await shot('course-home-'+width);
 }
 checks.push('1440/2560/3771/390 actual CSS preserves linebreaks and expands description past520px on desktop without horizontal overflow');
 await page.setViewportSize({width:1440,height:1000});await page.locator('.course-selector button').nth(1).click();await expect(page).toHaveTitle('AIcademiya · EDUC1145');await expect(stats.locator('span')).toHaveText(['2Sessions','0Admins','1Teacher','2Students']);
 checks.push('Actual course switch updates browser title and each course has its own correct singular/plural role counts');
 await page.getByRole('button',{name:'Fixture Settings',exact:true}).click();await expect(page).toHaveTitle('AIcademiya');await page.getByRole('button',{name:'Fixture Login',exact:true}).click();await expect(page).toHaveTitle('AIcademiya');await expect(page.getByRole('button',{name:'Sign in',exact:true})).toBeEnabled();expect(await page.locator('.login-layout').textContent()).not.toContain('EDUC7703');checks.push('Global Settings and real enabled Login component have generic browser titles without a fixedcourse suffix');
 await page.getByRole('button',{name:'Fixture Course Home',exact:true}).click();await expect(page).toHaveTitle('AIcademiya · EDUC7703');await page.locator('summary').filter({hasText:'Course actions'}).click();await page.getByRole('button',{name:'Edit course',exact:true}).click();const dialog=page.getByRole('dialog');await expect(dialog.getByLabel('Description',{exact:true})).toHaveValue(description);
 const wide=await dialog.boundingBox();expect(wide.width).toBeGreaterThan(580);await shot('edit-course-desktop');
 const edited='Revised synthetic opening.\n\n(1) First line remains separate.\n(2) Second line remains separate.\n\nClosing paragraph.';await dialog.getByLabel('Description',{exact:true}).fill(edited);await dialog.getByRole('button',{name:'Save changes',exact:true}).click();await expect(dialog).toHaveCount(0);expect(await page.locator('.course-description').textContent()).toBe(edited);expect(courses.first.description).toBe(edited);expect(events.filter(e=>e.method==='PATCH')).toHaveLength(1);expect(events.filter(e=>e.method==='GET')).toHaveLength(2);await shot('saved-linebreaks-desktop');
 checks.push('900px-cap edit dialog retains typed newlines across actual fixture PATCH and independent GET readback');
 await page.setViewportSize({width:390,height:844});await page.locator('summary').filter({hasText:'Course actions'}).click();await page.getByRole('button',{name:'Edit course',exact:true}).click();await expect(dialog).toBeVisible();const mobile=await dialog.boundingBox();expect(mobile.x).toBeGreaterThanOrEqual(0);expect(mobile.x+mobile.width).toBeLessThanOrEqual(390);await shot('edit-course-mobile');await dialog.getByRole('button',{name:'Cancel',exact:true}).click();checks.push('Edit dialog also fits390px and ordinary cancel/navigation survives');
 expect(errors).toEqual([]);
}catch(e){errors.push(String(e));if(page)await shot('failure').catch(()=>{});process.exitCode=1;}
finally{
 await browser?.close();await server?.close();
 const closed=port?await new Promise(resolve=>{const s=net.connect(port,'127.0.0.1');s.once('connect',()=>{s.destroy();resolve(false)});s.once('error',()=>resolve(true));}):true;
 if(!closed){errors.push('Owned fixture listener remains open');process.exitCode=1;}
 const report={status:errors.length?'failed':'passed',fixture_only:true,actual_react_css_and_chrome:true,backend_authorization_evidence:false,checks,measurements,events,errors,shots,owned_browser_closed:true,owned_listener_closed:closed};await fs.writeFile(path.join(out,'result.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({status:report.status,checks:checks.length,errors,result:path.join(out,'result.json')}));
}
