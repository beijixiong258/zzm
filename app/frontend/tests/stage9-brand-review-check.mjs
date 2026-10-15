// Verify the review copied alone to scratch: no sibling assets are available.
import { chromium, expect } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
const out=path.resolve(import.meta.dirname,"../../artifacts/stage9/branding");
if(!process.env.TMPDIR)throw new Error("Hermes scratch TMPDIR is required for the isolated file review");
process.env.TEMP=process.env.TMPDIR;process.env.TMP=process.env.TMPDIR;
const standalone=path.join(process.env.TMPDIR,`stage9-brand-review-${process.pid}.html`);
await fs.copyFile(path.join(out,"review.html"),standalone);
const url=pathToFileURL(standalone).href;
const errors=[],unexpectedRequests=[],reports=[];
let browser;
try{
 browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||"C:/Program Files/Google/Chrome/Application/chrome.exe"});
 const page=await browser.newPage({deviceScaleFactor:1});page.on("pageerror",e=>errors.push(String(e)));
 await page.route("**/*",route=>{const request=route.request().url();if(request===url||request.startsWith("data:"))return route.continue();unexpectedRequests.push(request);return route.abort();});
 for(const viewport of [{width:1440,height:1000},{width:390,height:844}]){
  await page.setViewportSize(viewport);await page.goto(url);
  const images=await page.evaluate(async()=>{const images=[...document.querySelectorAll('.shot img')];await Promise.all(images.map(async image=>{image.loading='eager';await image.decode();}));return {count:images.length,embedded:images.every(i=>i.src.startsWith('data:image/png;base64,')&&i.naturalWidth>0),scrollWidth:document.documentElement.scrollWidth};});
  expect(images.count).toBe(12);expect(images.embedded).toBe(true);expect(images.scrollWidth).toBeLessThanOrEqual(viewport.width);
  await page.screenshot({path:path.join(out,`review-${viewport.width}-viewport.png`)});
  await page.locator('.shot').first().click();await expect(page.locator('#viewer')).toBeVisible();expect(await page.locator('#viewer .zoom img').evaluate(i=>i.naturalWidth)).toBe(1440);await page.locator('#fit').click();await expect(page.locator('.zoom')).toHaveClass('zoom fit');await page.locator('#close').click();await expect(page.locator('#viewer')).not.toBeVisible();
  await page.locator('#live-previews summary').click();
  for(const [index,appearance] of ['standard','panel'].entries()){
   const frame=page.frameLocator('iframe').nth(index);await expect(frame.locator('.login-layout')).toHaveAttribute('data-brand-preview',appearance);const controls=frame.locator('input,button');expect(await controls.count()).toBe(4);for(const control of await controls.all())await expect(control).toBeDisabled();await expect(frame.locator('.brand')).toHaveCSS('background-color',appearance==='standard'?'rgb(237, 243, 238)':'rgb(49, 88, 75)');expect(await frame.locator('.brand img').evaluate(i=>i.naturalWidth)).toBeGreaterThan(0);
  }
  reports.push({viewport,...images,twoEmbeddedPreviews:true,allAuthControlsDisabled:true,screenshotZoomWorks:true});
 }
 expect(errors).toEqual([]);expect(unexpectedRequests).toEqual([]);
 await fs.writeFile(path.join(out,'review-check.json'),JSON.stringify({status:'passed',copiedAloneToScratch:true,noExternalOrSiblingRequests:true,browser:await browser.version(),errors,unexpectedRequests,reports},null,2));
 console.log(JSON.stringify({status:'passed',copiedAloneToScratch:true,viewports:reports.length,embeddedScreenshots:12,embeddedSafePreviews:2,errors,unexpectedRequests},null,2));
}finally{await browser?.close();await fs.unlink(standalone);console.log(JSON.stringify({ownedChromeClosed:!browser||!browser.isConnected(),scratchCopyRemoved:true}));}
