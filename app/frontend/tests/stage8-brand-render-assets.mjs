// Render all derived V4 assets with owned real Chrome; no dependencies added.
import { chromium, expect } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";
const root=path.resolve(import.meta.dirname,"..");
const pub=path.join(root,"public"),out=path.resolve(root,"../artifacts/stage8/branding");
if(process.env.TMPDIR){process.env.TEMP=process.env.TMPDIR;process.env.TMP=process.env.TMPDIR;}
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_PATH||"C:/Program Files/Google/Chrome/Application/chrome.exe"});
const checks=[];
try{
 const page=await browser.newPage({deviceScaleFactor:1});
 async function render(file,width,height,output){
  const svg=await fs.readFile(file,"utf8");await page.setViewportSize({width,height});
  await page.setContent(`<style>html,body{margin:0;background:transparent}svg{width:${width}px;height:${height}px;display:block}</style>${svg}`);
  return page.screenshot({path:output,omitBackground:true});
 }
 for(const name of ["aicademiya-mark.svg","aicademiya-mark-small.svg","aicademiya-mark-light.svg","favicon.svg"]){
  const svg=await fs.readFile(path.join(pub,name),"utf8");
  await page.setContent(svg);const info=await page.evaluate(()=>{const s=document.querySelector("svg"),b=s.querySelector("#v4-original"),n=s.querySelector("#v4-non-book-outline");return {viewBox:s.getAttribute("viewBox"),bookStroke:b.getAttribute("stroke"),bookContours:b.getAttribute("data-preserved-book-contours").split(" ").length,nonBookStroke:n.getAttribute("stroke-width"),pathBounds:[...s.querySelectorAll("path")].map(p=>({id:p.id,x:p.getBBox().x,y:p.getBBox().y,width:p.getBBox().width,height:p.getBBox().height}))};});
  expect(info.viewBox).toBe("57 23 359 375");expect(info.bookStroke).toBeNull();expect(info.bookContours).toBe(8);expect(info.nonBookStroke).toBe("0.95");checks.push({name,...info});
 }
 const favicon=path.join(pub,"favicon.svg");const images=[];
 for(const size of [32,48,180]){const name=size===180?"apple-touch-icon.png":`favicon-${size}.png`;const bytes=await render(favicon,size,size,path.join(pub,name));if(size!==180)images.push({size,bytes});await render(path.join(out,"previous-public/favicon.svg"),size,size,path.join(out,`before-favicon-${size}.png`));}
 const header=Buffer.alloc(6+16*images.length);header.writeUInt16LE(1,2);header.writeUInt16LE(images.length,4);let offset=header.length;
 images.forEach(({size,bytes},i)=>{const p=6+i*16;header[p]=size;header[p+1]=size;header.writeUInt16LE(1,p+4);header.writeUInt16LE(32,p+6);header.writeUInt32LE(bytes.length,p+8);header.writeUInt32LE(offset,p+12);offset+=bytes.length;});
 await fs.writeFile(path.join(pub,"favicon.ico"),Buffer.concat([header,...images.map(i=>i.bytes)]));
 for(const label of ["baseline","selected"]){
  for(const scale of [1,4])await render(path.join(out,`${label}-full-coordinate.svg`),474*scale,408*scale,path.join(out,`${label}-full-${scale}x.png`));
 }
 for(const label of ["before","after"])await render(path.join(out,`${label}-book-only.svg`),474*4,408*4,path.join(out,`${label}-book-only-4x.png`));
 for(const size of [64,80,116,164]){
  for(const [label,file] of [["before",path.join(out,"previous-public/aicademiya-mark.svg")],["after",path.join(pub,"aicademiya-mark.svg")]])await render(file,size,Math.round(size*375/359),path.join(out,`${label}-mark-${size}.png`));
 }
 await fs.writeFile(path.join(out,"svg-browser-integrity.json"),JSON.stringify({renderer:await browser.version(),checks,icoEmbeddedSizes:images.map(i=>i.size)},null,2));
 console.log(JSON.stringify({svgChecks:checks.length,png:[32,48,180],ico:[32,48],closedOwnedBrowser:true}));
}finally{await browser.close();}
