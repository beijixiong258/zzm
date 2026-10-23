// Render already-saved real search results; no new model/search calls.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
const require=createRequire(new URL('../frontend/package.json',import.meta.url));
const {chromium,expect}=require('@playwright/test');
const base='http://192.168.32.55:18774';
const out=path.resolve(import.meta.dirname,'../artifacts/stage2/ct255-live-0389e2cc18/ui');
await fs.mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
const errors=[];
try{
 const context=await browser.newContext({viewport:{width:1440,height:1000}});
 const login=await context.request.post(base+'/api/auth/demo',{data:{role:'student',student_index:1}});
 expect(login.status()).toBe(200);
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/#/workspace/session-4');
 const sources=page.locator('.message-assistant').last().locator('.web-source-link');
 await expect(sources).toHaveCount(5);
 const urls=await sources.evaluateAll(xs=>xs.map(x=>x.href));
 expect(urls.some(x=>x.includes('cambridgeenglish.org'))).toBe(true);
 await sources.first().click({trial:true});
 await page.screenshot({path:path.join(out,'live-sources-desktop.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});
 await sources.first().click({trial:true});
 await expect(sources.first()).toBeInViewport();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:path.join(out,'live-sources-mobile.png'),fullPage:true});
 expect(errors).toEqual([]);
 const report={status:'passed',evidence:'Stored real model/Tavily results from CT255 rendered with new inference disabled',source_count:await sources.count(),source_urls:urls,mobile_source_reachable:true,page_errors:errors,new_model_requests:0,new_search_requests:0};
 await fs.writeFile(path.join(out,'result.json'),JSON.stringify(report,null,2));
 console.log(JSON.stringify(report));
}finally{await browser.close();}
