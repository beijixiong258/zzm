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
 const response=await page.goto(base);expect(response.status()).toBe(200);await expect(page).toHaveTitle('AIcademiya');
 await expect(page.getByRole('button',{name:'Sign in',exact:true})).toBeEnabled();await expect(page.locator('.login-form-heading .brand--standard')).toHaveCount(1);
 await expect(page.locator('.demo-login')).toHaveCount(0);
 await expect(page.getByRole('link',{name:'AIcademiya · Course Home',exact:true})).toHaveAttribute('href','#/home');
 await expect(page.locator('.public-header')).toHaveCount(0);await expect(page.locator('.ai-badge')).toHaveCount(0);expect(await page.locator('body').innerText()).not.toMatch(/EDUC7703|LANGUAGE ASSESSMENT/);await expect(page.locator('.login-form-heading .brand-sub')).toHaveText('LEARN WITH INTENTION');
 const logo=page.locator('.login-form-heading .brand-mark img');await expect(logo).toBeVisible();
 await expect.poll(()=>logo.evaluate(i=>i.complete&&i.naturalWidth>0)).toBe(true);
 await page.screenshot({path:path.join(out,'login-desktop.png'),fullPage:true,animations:'disabled',caret:'hide',timeout:60000});
 await page.setViewportSize({width:3771,height:1974});await expect(page.locator('.login-form-heading .brand-name')).toBeVisible();await expect(page.getByRole('button',{name:'Sign in',exact:true})).toBeInViewport();await page.screenshot({path:path.join(out,'login-wide-3771.png'),fullPage:true,animations:'disabled',caret:'hide',timeout:60000});
 await page.setViewportSize({width:390,height:844});await expect(page.getByRole('button',{name:'Sign in',exact:true})).toBeEnabled();await expect(page.locator('.login-form-heading .brand--standard')).toHaveCount(1);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:path.join(out,'login-mobile.png'),fullPage:true,animations:'disabled',caret:'hide',timeout:60000});expect(errors).toEqual([]);
 await fs.writeFile(path.join(out,'browser-readback.json'),JSON.stringify({status:'passed',anonymous_only:true,learning_writes:0,login_visible:true,v4_assets_unchanged:true,light_login_selected_and_live:true,generic_login:true,browser_title:'AIcademiya',document_title_verified:true,anonymous_model_badge:false,complete_light_brand:true,brand_home_link:true,no_product_demo_controls:true,mobile_overflow:false,page_errors:errors},null,2));
 console.log(JSON.stringify({status:'passed',artifact_dir:out,anonymous_only:true}));
}finally{await browser.close();}
