// Actual built UI + HTTP/SQLite, synthetic isolated only. One explicit GET fault injection.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {parseArgs} from 'node:util';
const require=createRequire(new URL('../frontend/package.json',import.meta.url));
const {chromium,expect}=require('@playwright/test');
const {values:a}=parseArgs({options:{'base-url':{type:'string'},'artifact-dir':{type:'string'},'confirm-test-data':{type:'boolean'}}});
const base=a['base-url'],out=a['artifact-dir'];
if(!base||!out||!a['confirm-test-data']||new URL(base).port==='18773')throw Error('Explicit isolated QA required');
await fs.mkdir(out,{recursive:true});
const checks=[],events=[],errors=[],shots=[],ids={};let browser,page;
const call=async(ctx,method,url,data,expected=200,headers={})=>{
 const r=await ctx.request.fetch(base+url,{method,...(data===undefined?{}:{data}),headers});
 events.push({method,path:url,status:r.status()});expect(r.status()).toBe(expected);
 return r.headers()['content-type']?.includes('json')?r.json():r.body();
};
const shot=async(name)=>{const f=path.join(out,name+'.png');await page.screenshot({path:f,animations:'disabled',caret:'hide',fullPage:true});shots.push(f);};
try{
 browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 const admin=await browser.newContext({viewport:{width:1440,height:1000}}),anon=await browser.newContext({viewport:{width:1440,height:1000}}),student=await browser.newContext(),teacher=await browser.newContext(),existing=await browser.newContext();
 page=await admin.newPage();page.setDefaultTimeout(15000);page.on('pageerror',e=>errors.push(e.message));
 expect((await call(anon,'GET','/api/bootstrap')).registration_enabled).toBe(true);
 await call(anon,'GET','/api/admin/access-settings',undefined,401);
 for(const [ctx,role] of [[admin,'admin'],[student,'student'],[teacher,'teacher']])await call(ctx,'POST','/api/auth/demo',{role});
 for(const ctx of [student,teacher]){await call(ctx,'GET','/api/admin/access-settings',undefined,403);await call(ctx,'PUT','/api/admin/access-settings',{registration_enabled:false},403);}
 checks.push('Admin API is inaccessible to anonymous, student and teacher; fresh policy preserves invite-only signup');
 const course=await call(admin,'POST','/api/courses',{title:'Synthetic public-test security',code:'SECURITY',description:'Synthetic isolated only'});
 const token=crypto.randomBytes(8).toString('hex'),password=crypto.randomBytes(20).toString('base64url')+'A1';
 const initial={name:'Synthetic existing learner',email:`existing-${token}@example.invalid`,password,join_code:course.join_code};
 const before=(await call(existing,'POST','/api/auth/register',initial)).user;expect(before.role).toBe('student');await call(existing,'POST','/api/auth/logout',{});
 checks.push('Open registration creates a student through a valid synthetic invite, never a staff account');
 await page.goto(base+'/#/settings/users');const region=page.getByRole('region',{name:'New student registration',exact:true});
 await expect(region.getByText('Saved status: Open',{exact:true})).toBeVisible();
 const checkbox=region.getByLabel('Allow new student registration',{exact:true}),save=region.getByRole('button',{name:'Save registration setting',exact:true});
 await checkbox.uncheck();await expect(region.getByText('Saved status: Open',{exact:true})).toBeVisible();await save.click();
 await expect(region.getByText('Saved status: Closed',{exact:true})).toBeVisible();await expect(region.getByText('Changes saved and verified.',{exact:true})).toBeVisible();await expect(save).toBeDisabled();await shot('registration-admin-closed-desktop');
 expect((await call(admin,'GET','/api/admin/access-settings')).registration_enabled).toBe(false);expect((await call(anon,'GET','/api/bootstrap')).registration_enabled).toBe(false);
 checks.push('Actual administrator checkbox saves via PUT then independent GET before displaying Closed');
 const denied={name:'Synthetic blocked learner',email:`blocked-${token}@example.invalid`,password,join_code:course.join_code};
 await call(anon,'POST','/api/auth/register',denied,403);await call(anon,'GET','/api/auth/me',undefined,401);
 await call(existing,'POST','/api/auth/login',{email:initial.email,password});expect((await call(existing,'GET','/api/auth/me')).user.id).toBe(before.id);
 await call(admin,'POST',`/api/teacher/courses/${encodeURIComponent(course.id)}/students`,{name:'Synthetic staff-provisioned learner',email:`provisioned-${token}@example.invalid`,temporary_password:password});
 checks.push('Closed policy blocks direct valid-invite registration but preserves existing login and authorized staff provisioning');
 const ap=await anon.newPage();ap.on('pageerror',e=>errors.push(e.message));await ap.goto(base);await expect(ap.getByRole('button',{name:'Sign in',exact:true})).toBeEnabled();await expect(ap.getByRole('button',{name:'Create student account',exact:true})).toHaveCount(0);await expect(ap.getByRole('status')).toContainText('registration is currently closed');await expect(ap.locator('.brand--standard')).toBeVisible();
 page=ap;await shot('login-registration-closed-desktop');await ap.setViewportSize({width:390,height:844});expect(await ap.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await shot('login-registration-closed-mobile');page=(await admin.pages())[0];
 checks.push('Actual anonymous light Login shows closure without disabling sign-in at desktop and390px');
 await call(admin,'PUT','/api/admin/access-settings',{registration_enabled:true},403,{Origin:'https://attacker.example.invalid'});expect((await call(admin,'GET','/api/admin/access-settings')).registration_enabled).toBe(false);
 checks.push('Cross-origin cookie mutation is rejected, state independently unchanged');
 await checkbox.check();await save.click();await expect(region.getByText('Saved status: Open',{exact:true})).toBeVisible();await ap.reload();await expect(ap.getByRole('button',{name:'Create student account',exact:true})).toBeVisible();
 const created=(await call(anon,'POST','/api/auth/register',denied)).user;expect(created.role).toBe('student');await call(anon,'POST','/api/auth/logout',{});
 checks.push('Reopen restores signup; formerly denied identity registers once, proving no account was created while closed');
 // Abort only the GET that acknowledges an actual accepted PUT. Never forge mutation responses.
 let abortNext=true,mutations=0;
 await page.route('**/api/admin/access-settings',async route=>{if(route.request().method()==='PUT')mutations++;if(route.request().method()==='GET'&&abortNext){abortNext=false;await route.abort('failed');}else await route.continue();});
 await checkbox.uncheck();await save.click();await expect(region.getByRole('alert')).toContainText('Save could not be verified');await expect(region.getByText('Saved status could not be verified.',{exact:true})).toBeVisible();await expect(save).toBeDisabled();expect((await call(admin,'GET','/api/admin/access-settings')).registration_enabled).toBe(false);
 await region.getByRole('button',{name:'Reload saved setting',exact:true}).click();await expect(region.getByText('Saved status: Closed',{exact:true})).toBeVisible();expect(mutations).toBe(1);await page.unroute('**/api/admin/access-settings');
 checks.push('Accepted write plus dropped readback does not claim saved success; explicit reload recovers with GET only');
 await page.setViewportSize({width:390,height:844});await region.scrollIntoViewIfNeeded();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await shot('registration-admin-closed-mobile');
 await page.setViewportSize({width:1440,height:1000});await page.getByRole('button',{name:'Sign out',exact:true}).click();await expect(page.locator('.login-layout')).toBeVisible();await expect(page.getByRole('button',{name:'Create student account',exact:true})).toHaveCount(0);
 checks.push('Sign-out refreshes public registration policy; administrator form fits mobile');
 const headers=(await anon.request.get(base+'/')).headers();expect(headers['x-content-type-options']).toBe('nosniff');expect(headers['content-security-policy']).toContain('frame-ancestors');expect((await anon.request.get(base+'/api/bootstrap')).headers()['cache-control']).toContain('no-store');
 checks.push('Browser loaded real built scripts/styles under security headers; API responses are not cacheable');
 ids.registration_enabled=false;ids.existing_user=before.id;ids.created_after_reopen=created.id;expect(errors).toEqual([]);
}catch(e){errors.push(String(e));if(page)await shot('failure').catch(()=>{});process.exitCode=1;}
finally{await browser?.close();const r={status:errors.length?'failed':'passed',checks,events,errors,shots,ids,owned_browser_closed:true,synthetic_only:true,real_http:true,explicit_get_fault_injections:1,intercepted_mutation_responses:0,real_model_or_search_calls:0};await fs.writeFile(path.join(out,'result.json'),JSON.stringify(r,null,2));console.log(JSON.stringify({status:r.status,checks:checks.length,errors,result:path.join(out,'result.json')}));}
