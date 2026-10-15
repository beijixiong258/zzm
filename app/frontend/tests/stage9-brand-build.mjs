// Owned esbuild fixture only. Never writes frontend/dist or public assets.
import * as esbuild from "esbuild";
import fs from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";
const root=path.resolve(import.meta.dirname,"..");
const out=path.resolve(root,"../artifacts/stage9/branding");
await fs.mkdir(out,{recursive:true});
const marks={};
for(const name of ["aicademiya-mark.svg","aicademiya-mark-light.svg"])
  marks[`/${name}`]=`data:image/svg+xml;base64,${(await fs.readFile(path.join(root,"public",name))).toString("base64")}`;
const embedMark={name:"embed-unchanged-v4-mark",setup(build){build.onLoad({filter:/[\\/]src[\\/]ui\.tsx$/},async args=>{
  let contents=await fs.readFile(args.path,"utf8");
  for(const [url,data] of Object.entries(marks))contents=contents.replaceAll(JSON.stringify(url),JSON.stringify(data));
  return {contents,loader:"tsx",resolveDir:path.dirname(args.path)};
});}};
const records=[];
const entries=[["stage9-brand-harness.tsx","preview.html",true]];
if(!process.argv.includes("--components-only"))entries.push(["stage9-brand-app-harness.tsx","app-fixture.html",false]);
for(const [entry,file,offline] of entries){
  const result=await esbuild.build({absWorkingDir:root,entryPoints:[`tests/${entry}`],bundle:true,write:false,outfile:"fixture.js",format:"iife",jsx:"automatic",target:"chrome120",minify:true,metafile:true,define:{"process.env.NODE_ENV":'"production"'},plugins:[embedMark]});
  const script=result.outputFiles.find(f=>f.path.endsWith(".js")).text.replaceAll("</script", "<\\/script");
  const css=result.outputFiles.find(f=>f.path.endsWith(".css"))?.text||"";
  const csp=offline?'<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'unsafe-inline\'; style-src \'unsafe-inline\'; img-src data:; connect-src \'none\'; form-action \'none\'; base-uri \'none\'">':"";
  const html=`<!doctype html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">${csp}<title>Stage9 brand ${offline?"visual preview — no authentication":"synthetic App QA"}</title><style>${css}</style></head><body data-appearance="standard"><div id="root"></div><script>${script}</script></body></html>`;
  await fs.writeFile(path.join(out,file),html);
  if(offline)await fs.writeFile(path.join(out,"login-panel-preview.html"),html.replace('data-appearance="standard"','data-appearance="panel"'));
  const sources={};
  for(const input of Object.keys(result.metafile.inputs).filter(f=>!f.includes("node_modules"))){const p=path.resolve(root,input);sources[input]=crypto.createHash("sha256").update(await fs.readFile(p)).digest("hex");}
  records.push({entry,file,sources});
}
await fs.writeFile(path.join(out,"fixture-build.json"),JSON.stringify({build:"owned esbuild production-mode fixture; not final dist",embeddedV4MarksUnchanged:true,records},null,2));
console.log(JSON.stringify({status:"built",output:out,preview:"preview.html (light)",panelPreview:"login-panel-preview.html",finalDistUntouched:true},null,2));
