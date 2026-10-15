// Owned local Chrome/Vite fixture: no App wiring and no network API.
import {createServer} from "vite";
import react from "@vitejs/plugin-react";
import {chromium, expect} from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
const root=path.resolve(import.meta.dirname,"..");
const out=path.resolve(root,"../artifacts/stage8/branding");
const phase=process.argv[2] || "after";
if(phase==="before" && !(await fs.readFile(path.join(root,"src/Login.tsx"),"utf8")).includes('className="login-emblem"')) throw new Error("Before capture is pre-edit only; preserve the existing baseline evidence and do not overwrite it with current UI.");
await fs.mkdir(out,{recursive:true});
if(process.env.TMPDIR){process.env.TEMP=process.env.TMPDIR;process.env.TMP=process.env.TMPDIR;}
const server=await createServer({configFile:false,root,cacheDir:path.join(out,"vite-cache"),plugins:[react(),{name:"stage8-brand-entry",configureServer(s){s.middlewares.use((req,res,next)=>{if(req.url?.split("?")[0]!=="/stage8-brand")return next();res.setHeader("Content-Type","text/html");res.end('<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Stage8 brand fixture</title></head><body><div id="root"></div><script type="module" src="/tests/stage8-brand-harness.tsx"></script></body></html>');});}}],server:{host:"127.0.0.1",port:18888,strictPort:true,watch:null}});
let browser;
const reports=[];
try{
 await server.listen();
 browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||"C:/Program Files/Google/Chrome/Application/chrome.exe"});
 const page=await browser.newPage({deviceScaleFactor:1});
 const errors=[];page.on("pageerror",e=>errors.push(String(e)));
 await page.route("**/*",route=>new URL(route.request().url()).hostname!=="127.0.0.1"||new URL(route.request().url()).pathname.startsWith("/api/")?route.abort():route.continue());
 const sizes=[{name:"desktop",width:1440,height:1000},{name:"mobile",width:390,height:844},{name:"wide",width:3771,height:1974}];
 for(const viewport of sizes){
  await page.setViewportSize({width:viewport.width,height:viewport.height});
  const variants=phase==="before"?["standard"]:["standard","panel"];
  for(const variant of variants){
   await page.goto(`http://127.0.0.1:18888/stage8-brand?before=${phase==="before"?1:0}&variant=${variant}`);
   await page.locator(".login-form-panel").waitFor();
   if(phase!=="before" && variant==="standard") await page.locator(".login-form-heading .brand").evaluate(brand=>{brand.classList.remove("brand--panel");brand.classList.add("brand--standard");brand.querySelector("img").src="/aicademiya-mark.svg";});
   await page.evaluate(async()=>{await document.fonts.ready;await Promise.all([...document.images].map(i=>i.decode()));});
   await page.screenshot({path:path.join(out,`${phase}-login-${variant}-${viewport.name}.png`),fullPage:true});
   await page.screenshot({path:path.join(out,`${phase}-login-${variant}-${viewport.name}-viewport.png`)});
   const metrics=await page.evaluate(()=>{
    const box=(s)=>{const el=document.querySelector(s);if(!el)return null;const r=el.getBoundingClientRect(),c=getComputedStyle(el);return {x:r.x,y:r.y,width:r.width,height:r.height,fontSize:c.fontSize,display:c.display,color:c.color,background:c.backgroundColor};};
    return {viewport:{width:innerWidth,height:innerHeight},scrollWidth:document.documentElement.scrollWidth,scrollHeight:document.documentElement.scrollHeight,brand:box(".login-form-heading .brand"),mark:box(".login-form-heading img"),wordmark:box(".login-form-heading .brand-name"),tagline:box(".login-form-heading .brand-sub"),card:box(".login-form-panel"),headline:box(".login-story h1"),h2:box(".login-form-heading h2"),text:document.querySelector(".login-layout").textContent};
   });
   reports.push({phase,view:viewport.name,variant,...metrics});
   if(phase!=="before"){
    expect(metrics.scrollWidth).toBeLessThanOrEqual(viewport.width);
    expect(metrics.text).not.toContain("EDUC7703");expect(metrics.text).not.toContain("Active AI Model");
    expect(metrics.tagline.display).not.toBe("none");expect(parseFloat(metrics.tagline.fontSize)).toBeGreaterThanOrEqual(11);
    expect(metrics.brand.width).toBeGreaterThan(metrics.mark.width*2);
    expect(metrics.brand.x).toBeGreaterThanOrEqual(0);expect(metrics.brand.x+metrics.brand.width).toBeLessThanOrEqual(viewport.width);
    const content=await page.locator(".login-form-heading .brand").evaluate(e=>{const p=e.getBoundingClientRect();return [...e.querySelectorAll(".brand-mark,.brand-name,.brand-sub")].map(n=>{const r=document.createRange();r.selectNodeContents(n);const b=r.getBoundingClientRect();return {label:n.className,x:b.x,y:b.y,right:b.right,bottom:b.bottom,parent:{x:p.x,y:p.y,right:p.right,bottom:p.bottom}};});});
    for(const c of content){expect(c.x).toBeGreaterThanOrEqual(c.parent.x);expect(c.right).toBeLessThanOrEqual(c.parent.right);expect(c.y).toBeGreaterThanOrEqual(0);expect(c.bottom).toBeLessThanOrEqual(viewport.height);}
    const signInBox=await page.getByRole("button",{name:"Sign in",exact:true}).boundingBox();expect(signInBox.y+signInBox.height).toBeLessThanOrEqual(viewport.height);
    await page.keyboard.press("Tab");
    await expect(page.locator(".login-form-heading .brand")).toBeFocused();
    const focus=await page.locator(".login-form-heading .brand").evaluate(e=>({style:getComputedStyle(e).outlineStyle,width:getComputedStyle(e).outlineWidth}));
    expect(focus.style).not.toBe("none");
    await page.screenshot({path:path.join(out,`${phase}-login-${variant}-${viewport.name}-focus.png`)});
    await page.keyboard.press("Enter");expect(new URL(page.url()).hash).toBe("#/home");
    await expect(page.locator('input[type="password"]')).toHaveAttribute("autocomplete","current-password");
    await page.getByRole("button",{name:"Create student account",exact:true}).click();
    await expect(page.getByLabel("Full name",{exact:true})).toBeVisible();
    await expect(page.getByLabel("Course invitation code",{exact:true})).toBeVisible();
    await expect(page.locator('input[type="password"]')).toHaveAttribute("autocomplete","new-password");
    expect(await page.locator(".login-layout").innerText()).not.toContain("EDUC7703");
    if(viewport.name==="mobile") await page.screenshot({path:path.join(out,`after-register-${variant}-mobile.png`),fullPage:true});
   }
  }
 }
 if(phase!=="before"){
  for(const viewport of sizes){
   await page.setViewportSize({width:viewport.width,height:viewport.height});
   await page.goto("http://127.0.0.1:18888/stage8-brand?mode=sidebar");await page.locator(".sidebar .brand").waitFor();
   await expect(page.locator(".sidebar .brand-sub")).toBeVisible();
   const metrics=await page.locator(".sidebar .brand").evaluate(e=>{const r=e.getBoundingClientRect();const n=e.querySelector(".brand-name"),t=e.querySelector(".brand-sub"),m=e.querySelector("img");return {width:r.width,height:r.height,x:r.x,y:r.y,wordmarkFont:getComputedStyle(n).fontSize,taglineFont:getComputedStyle(t).fontSize,mark:{width:m.getBoundingClientRect().width,height:m.getBoundingClientRect().height}};});
   reports.push({phase,view:viewport.name,variant:"panel",mode:"sidebar",...metrics});
   await page.keyboard.press("Tab");await expect(page.locator(".sidebar .brand")).toBeFocused();
   await page.keyboard.press("Enter");expect(await page.evaluate(()=>window.__brandHomeCalls)).toBe(1);
   await page.locator(".sidebar .brand").click();expect(await page.evaluate(()=>window.__brandHomeCalls)).toBe(2);
   for(const modifier of ["Shift","Control","Meta","Alt"]){await page.locator(".sidebar .brand").click({modifiers:[modifier],noWaitAfter:true});expect(await page.evaluate(()=>window.__brandHomeCalls)).toBe(2);}
   const sidebarText=await page.locator(".sidebar .brand").evaluate(e=>{const p=e.getBoundingClientRect();return [...e.querySelectorAll(".brand-name,.brand-sub")].map(n=>{const r=document.createRange();r.selectNodeContents(n);const b=r.getBoundingClientRect();return {x:b.x,right:b.right,pLeft:p.x,pRight:p.right};});});for(const b of sidebarText){expect(b.x).toBeGreaterThanOrEqual(b.pLeft);expect(b.right).toBeLessThanOrEqual(b.pRight);}
   await page.screenshot({path:path.join(out,`after-sidebar-panel-${viewport.name}.png`)});
  }
  await page.setViewportSize({width:1440,height:1100});await page.goto("http://127.0.0.1:18888/stage8-brand?mode=comparison");await page.locator(".comparison-grid").waitFor();
  await page.screenshot({path:path.join(out,"standard-inverted-actual-sizes.png"),fullPage:true});
 }
 expect(errors).toEqual([]);
 await fs.writeFile(path.join(out,`${phase}-metrics.json`),JSON.stringify({fixture:true,noAuthOrModelCalls:true,errors,reports},null,2));
 console.log(JSON.stringify({phase,views:reports.length,errors,artifactDirectory:out},null,2));
}finally{await browser?.close();await server.close();console.log("Owned Chrome and Vite server closed");}
