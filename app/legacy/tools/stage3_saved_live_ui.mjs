// Read back stored real model/search output; new inference is disabled in this QA DB.
import{createRequire}from'node:module';import fs from'node:fs/promises';import path from'node:path';
const require=createRequire(new URL('../frontend/package.json',import.meta.url));const{chromium,expect}=require('@playwright/test');
const base=process.env.AICADEMIYA_SAVED_URL,sid=process.env.AICADEMIYA_SAVED_SESSION,vid=process.env.AICADEMIYA_SAVED_VERSION,out=process.env.AICADEMIYA_SAVED_OUTPUT;
if(!base||!sid||!vid||!out)throw Error('Explicit owned QA target required');
const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
const result={status:'failed',evidence:'Saved real CT255 model/Tavily replies, with new inference disabled',new_tutor_requests:[],page_errors:[]};
try{
 const ctx=await browser.newContext({viewport:{width:1440,height:1000}});const response=await ctx.request.post(base+'/api/auth/demo',{data:{role:'student',student_index:1}});expect(response.status()).toBe(200);
 const boot=await(await ctx.request.get(base+'/api/bootstrap')).json();expect(boot.ai.mode).toBe('demo');
 const work=await(await ctx.request.get(base+'/api/sessions/'+sid+'/workspace?version_id='+encodeURIComponent(vid))).json();
 const sourceUrls=work.messages.flatMap(m=>(m.citations||[]).filter(c=>c.url).map(c=>c.url));expect(sourceUrls.length).toBeGreaterThan(0);
 const p=await ctx.newPage();p.on('pageerror',e=>result.page_errors.push(e.message));p.on('request',r=>{if(r.method()==='POST'&&/\/tutor\/(start|turn)/.test(new URL(r.url()).pathname))result.new_tutor_requests.push(r.url())});
 await p.goto(base+'/#/workspace/'+sid+'?version_id='+encodeURIComponent(vid));
 const links=p.locator('.web-source-link');await expect(links).toHaveCount(sourceUrls.length);expect(await links.evaluateAll(xs=>xs.map(x=>x.href))).toEqual(sourceUrls);
 await links.first().click({trial:true});await p.screenshot({path:path.join(out,'sources-desktop.png'),fullPage:true});
 await p.setViewportSize({width:390,height:844});await links.last().click({trial:true});await expect(links.last()).toBeInViewport();expect(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await p.screenshot({path:path.join(out,'sources-mobile.png'),fullPage:true});
 expect(result.page_errors).toEqual([]);expect(result.new_tutor_requests).toEqual([]);
 Object.assign(result,{status:'passed',source_count:sourceUrls.length,urls:sourceUrls,mobile_source_reachable:true});
}catch(e){result.error=String(e);process.exitCode=1;}finally{await fs.writeFile(path.join(out,'ui-result.json'),JSON.stringify(result,null,2));await browser.close();console.log(JSON.stringify(result));}
