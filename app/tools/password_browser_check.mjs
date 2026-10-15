// Real auth gate + UI check with synthetic, runtime-only credentials.
// Passwords are sent through test HTTP clients, never typed into a user's browser or logged.
import fs from 'node:fs/promises';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {createRequire} from 'node:module';
const require=createRequire(new URL('../frontend/package.json',import.meta.url));
const {chromium,expect}=require('@playwright/test');
const base=process.env.AICADEMIYA_TEST_URL;
if(!base)throw new Error('Run via the isolated integration runner.');
const out=process.env.AICADEMIYA_TEST_ARTIFACT_DIR||path.resolve(import.meta.dirname,'../artifacts/password-integration');await fs.mkdir(out,{recursive:true});
if(process.env.TMPDIR){process.env.TEMP=process.env.TMPDIR;process.env.TMP=process.env.TMPDIR;}
let browser;const checks=[],screenshots=[],errors=[];let result;
const check=async(name,fn)=>{await fn();checks.push(name);console.log('PASS',name);};
try{
 browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const teacher=await browser.newContext({viewport:{width:1440,height:1000}});
 await teacher.request.post(base+'/api/auth/demo',{data:{role:'teacher'}});
 const email='first-login-'+randomUUID()+'@example.invalid';
 const temporary='Temporary-'+randomUUID();const replacement='Changed-'+randomUUID();
 let r=await teacher.request.post(base+'/api/teacher/courses/educ7703/students',{data:{name:'First-login QA learner',email,temporary_password:temporary}});
 if(r.status()!==200)throw new Error('Provision endpoint failed: '+r.status());
 const provisioned=await r.json();
 if(!provisioned.user.must_change_password||JSON.stringify(provisioned).includes(temporary))throw new Error('Invalid provisioning projection');
 checks.push('Teacher provision creates a forced-change student without echoing password');
 const teacherPage=await teacher.newPage();teacherPage.on('pageerror',e=>errors.push(e.message));
 await teacherPage.goto(base+'/#/teacher/session-4');
 await teacherPage.locator('.teacher-page .tabs').getByRole('button',{name:'Course roster',exact:true}).click();
 await teacherPage.getByRole('button',{name:'Add student account',exact:true}).click();
 await expect(teacherPage.locator('.provision-form input[type=password]')).toBeVisible();
 await expect(teacherPage.locator('.table-wrap')).toContainText('First-login QA learner');
 await expect(teacherPage.locator('.table-wrap')).toContainText('First sign-in setup pending');
 let target=path.join(out,'teacher-provision.png');await teacherPage.screenshot({path:target,fullPage:true});screenshots.push(target);
 const student=await browser.newContext({viewport:{width:1280,height:900}});
 r=await student.request.post(base+'/api/auth/login',{data:{email,password:temporary}});if(r.status()!==200)throw new Error('Temporary login failed');
 const page=await student.newPage();page.on('pageerror',e=>errors.push(e.message));
 await check('Forced-change UI blocks direct course navigation',async()=>{
  await page.goto(base+'/#/workspace/session-4');
  await expect(page.getByRole('heading',{name:'Make this account yours.',exact:true})).toBeVisible();
  await expect(page.locator('.sidebar')).toHaveCount(0);
  await expect(page.locator('input[type=password]')).toHaveCount(3);
  await expect(page.getByRole('button',{name:'Save password and continue',exact:true})).toBeDisabled();
  const response=await student.request.get(base+'/api/courses');if(response.status()!==403)throw new Error('Password gate bypassed');
 });
 target=path.join(out,'forced-password-en.png');await page.screenshot({path:target,fullPage:true});screenshots.push(target);
 await expect(page.locator('.locale-button')).toHaveCount(0);
 await expect(page.locator('html')).toHaveAttribute('lang','en');
 await expect(page.getByRole('heading',{name:'Make this account yours.',exact:true})).toBeVisible();
 await page.setViewportSize({width:390,height:844});
 const metrics=await page.evaluate(()=>({w:innerWidth,scroll:document.documentElement.scrollWidth}));if(metrics.scroll>metrics.w)throw new Error('Password screen mobile overflow');
 target=path.join(out,'forced-password-en-mobile.png');await page.screenshot({path:target,fullPage:true});screenshots.push(target);
 checks.push('Password setup is English-only and usable at 390px');
 await check('Wrong temporary password fails; correct change releases the gate',async()=>{
  r=await student.request.post(base+'/api/auth/change-password',{data:{current_password:'Wrong-synthetic-'+randomUUID(),new_password:replacement}});if(r.status()!==400)throw new Error('Wrong current password was not rejected');
  r=await student.request.post(base+'/api/auth/change-password',{data:{current_password:temporary,new_password:replacement}});if(r.status()!==200)throw new Error('Change failed');
  const me=await (await student.request.get(base+'/api/auth/me')).json();if(me.user.must_change_password)throw new Error('Flag did not clear');
  await page.reload();await expect(page.locator('#question-select')).toBeAttached();await expect(page.locator('.password-setup-page')).toHaveCount(0);
 });
 await check('Old password stops working and the chosen password authenticates',async()=>{
  const client=await browser.newContext();
  r=await client.request.post(base+'/api/auth/login',{data:{email,password:temporary}});if(r.status()!==401)throw new Error('Old password still works');
  r=await client.request.post(base+'/api/auth/login',{data:{email,password:replacement}});if(r.status()!==200)throw new Error('New password fails');
  await client.close();
 });
 if(errors.length)throw new Error('Page errors: '+errors.join('; '));
 result={status:'passed',checks,screenshots,page_errors:errors,boundary:'Real API provisioning/login/password-change plus real browser gate, English mobile layout and reload. No real credentials; browser password inputs intentionally not filled by the agent.'};
}catch(e){
 result={status:'failed',error:String(e),checks,screenshots,page_errors:errors};
 if(browser){let index=0;for(const context of browser.contexts()){for(const page of context.pages()){index++;await page.screenshot({path:path.join(out,'failure-'+index+'.png'),fullPage:true}).catch(()=>{});await fs.writeFile(path.join(out,'failure-'+index+'.txt'),await page.locator('body').innerText().catch(()=>''));}}}
 console.error(e);process.exitCode=1;
}
finally{await fs.writeFile(path.join(out,'result.json'),JSON.stringify(result,null,2));if(browser)await browser.close();console.log(JSON.stringify({status:result.status,checks:checks.length,error:result.error}));}
