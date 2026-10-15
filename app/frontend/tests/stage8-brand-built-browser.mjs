// Exercise production-mode owned fixture bytes, not parent's release/dist.
import {preview} from "vite";
import {chromium,expect} from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
const root=path.resolve(import.meta.dirname,"..");const out=path.resolve(root,"../artifacts/stage8/branding");
if(process.env.TMPDIR){process.env.TEMP=process.env.TMPDIR;process.env.TMP=process.env.TMPDIR;}
const server=await preview({configFile:false,root,build:{outDir:path.join(out,"scratch-build")},preview:{host:"127.0.0.1",port:18889,strictPort:true}});
let browser;const reports=[];
try{
 browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||"C:/Program Files/Google/Chrome/Application/chrome.exe"});const page=await browser.newPage({deviceScaleFactor:1});
 const errors=[],apiRequests=[];page.on("pageerror",e=>errors.push(String(e)));
 await page.route("**/*",r=>{const u=new URL(r.request().url());if(u.pathname.startsWith("/api/")){apiRequests.push(u.pathname);return r.abort();}return u.hostname==="127.0.0.1"?r.continue():r.abort();});
 for(const [name,width,height] of [["desktop",1440,1000],["mobile",390,844],["wide",3771,1974]]){
  await page.setViewportSize({width,height});await page.goto("http://127.0.0.1:18889/tests/stage8-brand.html");await page.locator(".login-form-heading .brand--panel").waitFor();await page.evaluate(async()=>{await document.fonts.ready;await Promise.all([...document.images].map(i=>i.decode()));});
  await expect(page.locator(".login-form-heading .brand-sub")).toHaveText("LEARN WITH INTENTION");await expect(page.locator(".login-layout")).not.toContainText("EDUC7703");await expect(page.locator(".login-layout")).not.toContainText("Active AI Model");
  const info=await page.evaluate(()=>{const b=document.querySelector(".login-form-heading .brand"),r=b.getBoundingClientRect(),m=b.querySelector("img").getBoundingClientRect(),t=b.querySelector(".brand-sub");return {width:innerWidth,height:innerHeight,scrollWidth:document.documentElement.scrollWidth,scrollHeight:document.documentElement.scrollHeight,brand:{x:r.x,y:r.y,width:r.width,height:r.height,color:getComputedStyle(b).color,background:getComputedStyle(b).backgroundColor},mark:{width:m.width,height:m.height},wordmarkFont:getComputedStyle(b.querySelector(".brand-name")).fontSize,taglineFont:getComputedStyle(t).fontSize,taglineDisplay:getComputedStyle(t).display};});
  expect(info.scrollWidth).toBe(width);expect(info.brand.background).toBe("rgb(49, 88, 75)");expect(info.taglineDisplay).toBe("block");reports.push({name,...info});
  await page.screenshot({path:path.join(out,`built-login-panel-${name}.png`),fullPage:true});
  await page.keyboard.press("Tab");await expect(page.locator(".login-form-heading .brand")).toBeFocused();await page.keyboard.press("Enter");expect(new URL(page.url()).hash).toBe("#/home");
 }
 expect(errors).toEqual([]);expect(apiRequests).toEqual([]);
 await fs.writeFile(path.join(out,"built-metrics.json"),JSON.stringify({fixture:true,productionModeOwnedBuild:true,errors,apiRequests,reports},null,2));console.log(JSON.stringify({productionModeFixtureViews:reports.length,errors,apiRequests}));
}finally{await browser?.close();await new Promise((resolve,reject)=>server.httpServer.close(e=>e?reject(e):resolve()));console.log("Owned Chrome and preview server closed");}
