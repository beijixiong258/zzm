import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {api,type UploadProgress} from '../src/api';
import {selectMaterialFiles,uploadMaterialQueue,uploadSuccessMessage,type MaterialUpload} from '../src/material-upload';
import Materials from '../src/Materials';
import {fileSize} from '../src/MaterialManager';
import type {Material} from '../src/types';
const material:Material={id:'m',title:'w.txt',kind:'worksheet',visibility:'teacher',source_label:'Synthetic',status:'ready',excerpt:'Synthetic source',download_url:'/api/materials/m/download'};
afterEach(()=>vi.unstubAllGlobals());

describe('Stage16 selected files and real transport progress',()=>{
 it('retains relative folder paths and separates equal basenames',()=>{
  const a=new File(['a'],'sheet.xlsx'),b=new File(['b'],'sheet.xlsx');Object.defineProperty(a,'webkitRelativePath',{value:'Folder/A/sheet.xlsx'});Object.defineProperty(b,'webkitRelativePath',{value:'Folder/B/sheet.xlsx'});
  const rows=selectMaterialFiles([a,b]);expect(rows.map(x=>x.relativePath)).toEqual(['Folder/A/sheet.xlsx','Folder/B/sheet.xlsx']);expect(rows[0].key).not.toBe(rows[1].key);
 });
 it('reports file sizes',()=>{expect(fileSize(12)).toBe('12 B');expect(fileSize(1024)).toBe('1.0 KiB');expect(fileSize(1048576)).toBe('1.0 MiB');});
 it('retains per-file kinds, answer-key privacy and measured queue progress',async()=>{
  const rows=selectMaterialFiles([new File(['x'],'w.txt'),new File(['y'],'a.txt')]);rows[0].kind='worksheet';rows[1].kind='answer_key';const changes:MaterialUpload[]=[];
  const upload=vi.fn(async(_sid:string,_file:File,visibility:string,kind:string,_processing:unknown,onProgress?:(x:UploadProgress)=>void)=>{onProgress?.({loaded:25,total:100,complete:false});onProgress?.({loaded:100,total:100,complete:true});return {...material,kind,visibility:visibility as Material['visibility']};});
  await uploadMaterialQueue('s',rows,{visibility:'student',kind:'reading'},x=>changes.push(x),()=>true,upload);
  expect(upload.mock.calls.map(x=>[x[2],x[3]])).toEqual([['student','worksheet'],['teacher','answer_key']]);expect(changes.some(x=>x.status==='uploading'&&x.progress?.loaded===25)).toBe(true);expect(changes.at(-1)?.status).toBe('uploaded');
 });
 it('uses browser byte events and waits for HTTP acknowledgement after 100% sent',async()=>{
  let instance:FakeXHR;
  class FakeXHR{status=0;response:unknown=null;responseType='';withCredentials=false;url='';method='';body:unknown;upload:{onprogress?:Function;onload?:Function}={};onload?:Function;onerror?:Function;onabort?:Function;constructor(){instance=this;}open(method:string,url:string){this.method=method;this.url=url;}send(body:unknown){this.body=body;}}
  vi.stubGlobal('XMLHttpRequest',FakeXHR);const states:UploadProgress[]=[];let resolved=false;const done=api.upload('s/1',new File(['abcd'],'w.txt'),'teacher','worksheet','preview',x=>states.push(x)).then(v=>{resolved=true;return v;});
  expect(instance!.url).toBe('/api/sessions/s%2F1/materials');expect(instance!.withCredentials).toBe(true);expect((instance!.body as FormData).get('kind')).toBe('worksheet');
  instance!.upload.onprogress?.({loaded:40,total:100,lengthComputable:true});expect(states.at(-1)).toEqual({loaded:40,total:100,complete:false});instance!.upload.onload?.();await Promise.resolve();expect(resolved).toBe(false);expect(states.at(-1)?.complete).toBe(true);
  instance!.status=200;instance!.response=material;instance!.onload?.();expect(await done).toEqual(material);
 });
 it('distinguishes accepted preview, complete and mixed batches without asserting completion',()=>{
  const preview={...material,processing:'preview' as const,status:'needs_review' as const};
  const full={...material,processing:'full_document' as const,status:'processing' as const};
  expect(uploadSuccessMessage([preview])).toBe('1 file saved. Text/OCR preview only; check each file’s status below.');
  expect(uploadSuccessMessage([full])).toBe('1 file saved. Complete-document processing requested; check each file’s status below.');
  expect(uploadSuccessMessage([{...full,status:'ready'}])).toContain('processing requested');
  expect(uploadSuccessMessage([preview,full])).toBe('2 files saved. This batch includes complete-document processing and text/OCR previews. Check each file’s status below.');
 });
 it('bases the notice on accepted uploads, not a full-document file that failed',async()=>{
  const rows=selectMaterialFiles([new File(['x'],'w.pdf'),new File(['y'],'r.txt')],true);
  const upload=vi.fn(async(_sid:string,file:File)=>{if(file.name==='w.pdf')throw new Error('Explicit synthetic rejection');return material;});
  const accepted=await uploadMaterialQueue('s',rows,{visibility:'teacher',kind:'reading'},()=>{},()=>true,upload);
  expect(accepted).toHaveLength(1);expect(uploadSuccessMessage(accepted)).toBe('1 file saved. Text/OCR preview only; check each file’s status below.');
 });
 it('exposes session removal without expanding More actions',()=>{
  const html=renderToStaticMarkup(<Materials materials={[material]} teacher onArchive={async()=>{}} onReprocess={async()=>{}}/>);const at=html.indexOf('Remove from this session');expect(at).toBeGreaterThan(0);expect(at).toBeLessThan(html.indexOf('material-management-details'));
 });
});
