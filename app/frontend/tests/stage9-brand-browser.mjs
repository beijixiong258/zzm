// Real owned Chrome against esbuild fixtures; all API GETs are synthetic.
import { chromium, expect } from "@playwright/test";
import { createServer } from "node:http";
import net from "node:net";
import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
const out=path.resolve(import.meta.dirname,"../../artifacts/stage9/branding");
if(process.env.TMPDIR){process.env.TEMP=process.env.TMPDIR;process.env.TMP=process.env.TMPDIR;}
const files=new Set(["preview.html","login-panel-preview.html","app-fixture.html"]);
const server=createServer(async(req,res)=>{const file=new URL(req.url,"http://localhost").pathname.slice(1);if(!files.has(file)){res.writeHead(403);res.end("Fixture only: no API/auth service");return;}res.setHeader("Content-Type","text/html; charset=utf-8");res.end(await fs.readFile(path.join(out,file)));});
await new Promise(resolve=>server.listen(0,"127.0.0.1",resolve));
const port=server.address().port,origin=`http://127.0.0.1:${port}`;
let browser;
const reports=[],checks=[],errors=[],unexpectedRequests=[],requests=[];
const sizes=[{name:"desktop",width:1440,height:1000},{name:"mobile",width:390,height:844},{name:"wide",width:3771,height:1974}];
let scenario="preview";
const componentsOnly=process.argv.includes("--components-only");
const boot={app_name:"AIcademiya",demo_enabled:false,default_locale:"en",ai:{mode:"openai",configured:false,base_url:"",model:"",last_error:null}};
const user={id:"stage9-brand-synthetic",name:"Synthetic learner",email:"brand@example.invalid",role:"student",must_change_password:false};
const settle=async page=>page.evaluate(async()=>{await document.fonts.ready;await Promise.all([...document.images].map(i=>i.decode()));});
async function measure(page,selector){return page.locator(selector).evaluate(e=>{
 const box=n=>{const b=n.getBoundingClientRect(),c=getComputedStyle(n);return {x:b.x,y:b.y,width:b.width,height:b.height,right:b.right,bottom:b.bottom,fontSize:c.fontSize,color:c.color,background:c.backgroundColor,display:c.display};};
 const parent=box(e),parts=[".brand-mark",".brand-name",".brand-sub"].map(s=>{const n=e.querySelector(s),r=document.createRange();r.selectNodeContents(n);const b=r.getBoundingClientRect();return {selector:s,...box(n),textBounds:{x:b.x,y:b.y,right:b.right,bottom:b.bottom}};});
 const main=document.querySelector(".main-content"),sidebar=document.querySelector(".sidebar");
 return {viewport:{width:innerWidth,height:innerHeight},scrollWidth:document.documentElement.scrollWidth,scrollHeight:document.documentElement.scrollHeight,brand:parent,mark:parts[0],name:parts[1],tagline:parts[2],direction:getComputedStyle(e).flexDirection,imageLoaded:e.querySelector("img").naturalWidth>0,imageSource:e.querySelector("img").src.startsWith("data:")?"embedded unchanged V4 SVG":e.querySelector("img").src,main:main?box(main):null,sidebar:sidebar?box(sidebar):null};
});}
function fit(m){expect(m.scrollWidth).toBeLessThanOrEqual(m.viewport.width);expect(m.imageLoaded).toBe(true);expect(m.tagline.display).not.toBe("none");expect(parseFloat(m.tagline.fontSize)).toBeGreaterThanOrEqual(11);for(const p of [m.mark,m.name,m.tagline]){expect(p.textBounds.x).toBeGreaterThanOrEqual(m.brand.x-0.5);expect(p.textBounds.right).toBeLessThanOrEqual(m.brand.right+0.5);expect(p.textBounds.y).toBeGreaterThanOrEqual(m.brand.y-0.5);expect(p.textBounds.bottom).toBeLessThanOrEqual(m.brand.bottom+0.5);}expect(m.brand.right).toBeLessThanOrEqual(m.viewport.width);}
try{
 browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||"C:/Program Files/Google/Chrome/Application/chrome.exe"});
 const page=await browser.newPage({deviceScaleFactor:1});
 page.on("pageerror",e=>errors.push(String(e)));
 await page.route("**/*",async route=>{
  const url=new URL(route.request().url()),method=route.request().method();
  if(url.protocol==="file:"||url.protocol==="data:")return route.continue();
  if(url.origin!==origin){unexpectedRequests.push({url:url.href,method});return route.abort();}
  if(!url.pathname.startsWith("/api/"))return route.continue();
  requests.push({scenario,url:url.pathname,method});
  if(method!=="GET"||scenario==="preview"||scenario==="live"||scenario==="component-sidebar"){unexpectedRequests.push({scenario,url:url.pathname,method});return route.fulfill({status:403,json:{detail:"Authentication not available in fixture"}});}
  if(url.pathname==="/api/bootstrap")return route.fulfill({json:boot});
  if(url.pathname==="/api/auth/me")return scenario==="anonymous"?route.fulfill({status:401,json:{detail:"Synthetic anonymous fixture"}}):route.fulfill({json:{user:{...user,role:scenario==="teacher"?"teacher":"student",name:scenario==="teacher"?"Synthetic teacher":user.name,must_change_password:scenario==="forced"}}});
  if(["/api/courses","/api/history"].includes(url.pathname))return route.fulfill({json:[]});
  unexpectedRequests.push({scenario,url:url.pathname,method});return route.fulfill({status:403,json:{detail:"Unexpected fixture request"}});
 });
 // Safe previews: actual prop, never a DOM class/image substitution.
 for(const viewport of sizes){await page.setViewportSize({width:viewport.width,height:viewport.height});for(const appearance of ["standard","panel"]){
  scenario="preview";await page.goto(`${origin}/preview.html?appearance=${appearance}`);await page.locator(".login-form-panel").waitFor();await settle(page);
  await expect(page.locator(".login-layout")).toHaveAttribute("data-brand-preview",appearance);
  const controls=page.locator(".login-form-panel input,.login-form-panel button");expect(await controls.count()).toBe(4);for(const c of await controls.all())await expect(c).toBeDisabled();
  const m=await measure(page,".login-form-heading .brand");fit(m);expect(m.mark.width).toBeGreaterThanOrEqual(viewport.name==="wide"?164:viewport.name==="desktop"?116:80);
  expect(m.brand.background).toBe(appearance==="standard"?"rgb(237, 243, 238)":"rgb(49, 88, 75)");
  const signIn=await page.getByRole("button",{name:"Sign in",exact:true}).boundingBox();expect(signIn.y+signIn.height).toBeLessThanOrEqual(viewport.height);
  const file=`login-${appearance}-${viewport.name}`;await page.screenshot({path:path.join(out,`${file}.png`),fullPage:true});await page.screenshot({path:path.join(out,`${file}-viewport.png`)});await page.locator(".login-form-panel").screenshot({path:path.join(out,`${file}-card.png`)});
  reports.push({mode:"Login preview",view:viewport.name,appearance,...m});
  // Even a manually dispatched submit cannot reach auth APIs or callback.
  await page.locator("form").evaluate(e=>e.dispatchEvent(new Event("submit",{bubbles:true,cancelable:true})));expect(await page.evaluate(()=>window.__stage9.authCalls)).toBe(0);
  await page.keyboard.press("Tab");await expect(page.locator(".brand")).toBeFocused();const focus=await page.locator(".brand").evaluate(e=>getComputedStyle(e).outlineStyle);expect(focus).toBe("solid");
  await page.keyboard.press("Enter");expect(new URL(page.url()).hash).toBe("#/home");
 }}checks.push("6 actual safe full Login previews: fit, loaded V4, disabled controls, guarded submit, native keyboard home link");
 // Default form remains live, with untouched switching/validation. No password input.
 scenario="live";await page.setViewportSize({width:390,height:844});await page.goto(`${origin}/preview.html?mode=live`);await page.locator(".brand--standard").waitFor();await expect(page.locator('input[type="email"]')).toBeEnabled();await expect(page.locator('input[type="password"]')).toHaveAttribute("autocomplete","current-password");await expect(page.getByRole("button",{name:"Sign in",exact:true})).toBeEnabled();
 await page.getByRole("button",{name:"Create student account",exact:true}).click();await expect(page.getByLabel("Full name",{exact:true})).toBeVisible();await expect(page.getByLabel("Course invitation code",{exact:true})).toBeVisible();await expect(page.locator('input[type="password"]')).toHaveAttribute("autocomplete","new-password");await expect(page.locator('input[type="password"]')).toHaveAttribute("minlength","8");await expect(page.locator('input[type="password"]')).toHaveAttribute("maxlength","512");expect(await page.locator("form").evaluate(e=>e.checkValidity())).toBe(false);
 await page.getByRole("button",{name:"Sign in",exact:true}).last().click();await expect(page.getByLabel("Full name",{exact:true})).toHaveCount(0);checks.push("Selected light, enabled form, native empty validation, register fields/autocomplete and switch-back unchanged; no credentials entered");
 // Both lockup palettes at actual sidebar widths and adjacent breakpoints.
 for(const viewport of [...sizes,{name:"mid",width:1000,height:900},{name:"boundary",width:821,height:900}]){await page.setViewportSize({width:viewport.width,height:viewport.height});for(const appearance of ["panel","standard"]){
  scenario="component-sidebar";await page.goto(`${origin}/preview.html?mode=sidebar&appearance=${appearance}#/history`);await page.locator(".sidebar .brand").waitFor();await settle(page);const m=await measure(page,".sidebar .brand");fit(m);expect(m.direction).toBe("row");expect(m.mark.right).toBeLessThan(m.name.x);expect(m.sidebar.width).toBe(viewport.width>820&&viewport.width<=1200?264:288);expect(parseFloat(m.name.fontSize)).toBeGreaterThanOrEqual(24);expect(m.mark.width).toBeGreaterThanOrEqual(44);
  reports.push({mode:"Horizontal sidebar component",view:viewport.name,appearance,...m});if(sizes.some(v=>v.name===viewport.name))await page.screenshot({path:path.join(out,`sidebar-${appearance}-${viewport.name}.png`)});
 }}
 await page.setViewportSize({width:1440,height:1000});await page.goto(`${origin}/preview.html?mode=sidebar&appearance=panel#/history`);await page.locator(".brand").waitFor();await page.keyboard.press("Tab");await expect(page.locator(".brand")).toBeFocused();await page.keyboard.press("Enter");expect(await page.evaluate(()=>window.__stage9.homeCalls)).toBe(1);
 await page.locator(".brand").click();expect(await page.evaluate(()=>window.__stage9.homeCalls)).toBe(2);
 for(const modifier of ["Shift","Control","Meta","Alt"]){await page.locator(".brand").click({modifiers:[modifier],noWaitAfter:true});expect(await page.evaluate(()=>window.__stage9.homeCalls)).toBe(2);}
 checks.push("10 sidebar palette/width cases: horizontal, readable, contained; normal click/Enter callbacks and all 4 modifier clicks retain native link behavior");
 // Current real App: no fake login; synthetic /me simply supplies fixture identity.
 if(!componentsOnly){
 for(const state of ["anonymous","forced","student","teacher"]){scenario=state;for(const viewport of state==="student"?sizes:state==="teacher"?[sizes[0],{name:"mid",width:1000,height:900},{name:"boundary",width:821,height:900}]:[sizes[0],sizes[1]]){
  await page.setViewportSize({width:viewport.width,height:viewport.height});await page.goto(`${origin}/app-fixture.html?state=${state}#/home`);
  if(state==="anonymous"){
   await page.locator(".login-form-panel").waitFor();await expect(page.locator(".public-header")).toHaveCount(0);await expect(page.locator(".brand--standard")).toBeVisible();await expect(page.locator(".login-layout")).not.toHaveAttribute("data-brand-preview");await expect(page.getByRole("button",{name:"Sign in",exact:true})).toBeEnabled();
  }else if(state==="forced"){
   await page.locator(".password-setup-card").waitFor();await expect(page.locator(".public-header .brand--standard")).toBeVisible();await expect(page.locator(".sidebar")).toHaveCount(0);expect(await page.locator('input[type="password"]').count()).toBe(3);await page.locator(".public-header .brand").click();await expect(page.locator(".password-setup-card")).toBeVisible();
  }else{
   await page.locator(".main-content .page").waitFor();if(viewport.width<=820)await page.getByRole("button",{name:"Navigation",exact:true}).click();await expect(page.locator(".sidebar .brand--panel")).toBeVisible();await settle(page);const m=await measure(page,".sidebar .brand");fit(m);expect(m.direction).toBe("row");if(viewport.width>820){expect(m.main.x).toBe(m.sidebar.width);expect(m.main.width).toBe(viewport.width-m.sidebar.width);}else{expect(m.main.x).toBe(0);expect(m.main.width).toBe(viewport.width);}reports.push({mode:"Real App synthetic identity",state,view:viewport.name,appearance:"panel",...m});
  }
  await settle(page);await page.screenshot({path:path.join(out,`app-${state}-${viewport.name}.png`),fullPage:true});
 }}
 // The actual App navigation calls its actual dirty guard from Brand.
 scenario="student";await page.setViewportSize({width:1440,height:1000});await page.goto(`${origin}/app-fixture.html?state=student#/history`);await page.locator(".sidebar .brand").waitFor();await page.evaluate(()=>{window.__stage9SetDirty(true);});await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
 page.once("dialog",dialog=>dialog.dismiss());await page.locator(".sidebar .brand").click();expect(new URL(page.url()).hash).toBe("#/history");
 page.once("dialog",dialog=>dialog.accept());await page.locator(".sidebar .brand").click();await expect.poll(()=>new URL(page.url()).hash).toBe("#/home");await page.evaluate(()=>window.__stage9SetDirty(false));
 checks.push("Real App synthetic anonymous/forced-password/student/teacher states: selected light Login, header gating, mobile drawer, paired main widths and dirty home navigation preserved");
 }
 // Opening absolute file URL works offline and cannot enable the live lane.
 scenario="preview";await page.setViewportSize({width:390,height:844});await page.goto(pathToFileURL(path.join(out,"preview.html")).href+"?mode=live");await expect(page.locator('.login-layout')).toHaveAttribute("data-brand-preview","standard");await expect(page.locator('input[type="email"]')).toBeDisabled();await settle(page);await page.screenshot({path:path.join(out,"offline-light-mobile.png"),fullPage:true});checks.push("Self-contained preview opened from absolute file URL; mode=live cannot enable auth offline");
 expect(errors).toEqual([]);expect(unexpectedRequests).toEqual([]);expect(requests.filter(r=>r.method!=="GET")).toEqual([]);expect(requests.filter(r=>["preview","live","component-sidebar"].includes(r.scenario))).toEqual([]);
 await fs.writeFile(path.join(out,componentsOnly?"component-browser-metrics.json":"browser-metrics.json"),JSON.stringify({status:"passed",componentsOnly,browser:await browser.version(),fixture:true,noRealAuthentication:true,noCredentialsEntered:true,errors,unexpectedRequests,requests,checks,reports},null,2));
 console.log(JSON.stringify({status:"passed",measuredViews:reports.length,checks,errors,unexpectedRequests,syntheticGetRequests:requests.length,authWrites:0,artifactDirectory:out},null,2));
}finally{
 await browser?.close();await new Promise((resolve,reject)=>server.close(error=>error?reject(error):resolve()));
 const closed=await new Promise(resolve=>{const socket=net.connect({host:"127.0.0.1",port});socket.once("error",()=>resolve(true));socket.once("connect",()=>{socket.destroy();resolve(false);});});
 await fs.writeFile(path.join(out,"cleanup.json"),JSON.stringify({ownedChromeClosed:!browser||!browser.isConnected(),ownedServerPort:port,serverClosed:closed},null,2));
 console.log(JSON.stringify({ownedChromeClosed:!browser||!browser.isConnected(),serverPort:port,serverClosed:closed}));
}
