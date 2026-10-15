// Anonymous read-only production UI verification. No login or learning records.
import {chromium,expect} from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
const base=process.env.AICADEMIYA_BRAND_URL;
const out=process.env.AICADEMIYA_BRAND_OUT;
if(!base||!out)throw new Error('Set explicit brand verification URL and output directory');
await fs.mkdir(out,{recursive:true});
if(process.env.TMPDIR){process.env.TEMP=process.env.TMPDIR;process.env.TMP=process.env.TMPDIR;}
const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
const errors=[];
try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}});page.on('pageerror',e=>errors.push(e.message));
 const response=await page.goto(base);expect(response.status()).toBe(200);
 await expect(page.getByRole('button',{name:'Sign in',exact:true})).toBeVisible();
 const logo=page.locator('.login-emblem');await expect(logo).toBeVisible();
 await expect.poll(()=>logo.evaluate(i=>i.complete&&i.naturalWidth>0)).toBe(true);
 await page.screenshot({path:path.join(out,'login-desktop.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});await expect(page.getByRole('button',{name:'Sign in',exact:true})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:path.join(out,'login-mobile.png'),fullPage:true});expect(errors).toEqual([]);
 await fs.writeFile(path.join(out,'browser-readback.json'),JSON.stringify({status:'passed',anonymous_only:true,learning_writes:0,login_visible:true,new_logo_loaded:true,mobile_overflow:false,page_errors:errors},null,2));
 console.log(JSON.stringify({status:'passed',artifact_dir:out,anonymous_only:true}));
}finally{await browser.close();}
