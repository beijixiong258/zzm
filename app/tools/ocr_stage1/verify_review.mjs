import {createRequire} from 'node:module';
import path from 'node:path';
import fs from 'node:fs/promises';
import {fileURLToPath,pathToFileURL} from 'node:url';
const require=createRequire(new URL('../../frontend/package.json',import.meta.url));
const {chromium,expect}=require('@playwright/test');
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const out=path.join(root,'artifacts/ocr-stage1');
const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',args:['--disable-gpu']});
const errors=[];const checks=[];
try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 page.on('pageerror',e=>errors.push(e.message));
 await page.goto(pathToFileURL(path.join(out,'review.html')).href);
 await expect(page).toHaveTitle('AIcademiya · Document parsing evaluation');
 await expect(page.locator('#sample option')).toHaveCount(24);
 for(let i=0;i<24;i++){
  await page.selectOption('#sample',String(i));
  await page.locator('#sourceImage').evaluate(img=>img.decode());
  for(const key of ['rapidocr','minicpm','paddle']){
   await page.locator(`[data-engine=${key}]`).click();
   expect((await page.locator('#output').textContent()).length).toBeGreaterThan(0);
   checks.push({sample:i+1,engine:key,source_loaded:true,output_present:true});
  }
 }
 await page.selectOption('#sample','16');await page.locator('[data-engine=paddle]').click();
 await expect(page.locator('#reading table')).toHaveCount(2);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:path.join(out,'review-desktop.png'),fullPage:false});
 await page.setViewportSize({width:390,height:844});
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 expect(await page.locator('#sample').evaluate(e=>e.getBoundingClientRect().right<=innerWidth)).toBe(true);
 await page.locator('#readable').click();await expect(page.locator('#output')).toBeVisible();await expect(page.locator('#reading')).toBeHidden();
 await page.screenshot({path:path.join(out,'review-mobile.png'),fullPage:false});
 expect(errors).toEqual([]);
 const result={status:'passed',sample_engine_views:checks.length,all_views:checks,desktop_no_overflow:true,mobile_no_overflow:true,structured_table_rendering:true,raw_toggle:true,page_errors:errors,visual_scope:'DOM/layout/image-loading and screenshots; no claim of independent human visual audit'};
 await fs.writeFile(path.join(out,'review-browser.json'),JSON.stringify(result,null,2)+'\n');
 console.log(JSON.stringify({status:'passed',views:checks.length,report:path.join(out,'review-browser.json')}));
}finally{await browser.close();}
