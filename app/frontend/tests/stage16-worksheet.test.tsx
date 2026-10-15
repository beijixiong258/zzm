import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {api} from '../src/api';
import WorksheetImport from '../src/WorksheetImport';
import type {SessionDetail} from '../src/types';
const session={id:'s',course_id:'c',materials:[],questions:[],groups:[],reference_answers:{}} as unknown as SessionDetail;
afterEach(()=>vi.unstubAllGlobals());

describe('Stage16 worksheet source reuse',()=>{
 it('selects existing materials instead of asking for another file, with AI enabled',()=>{
  const html=renderToStaticMarkup(<WorksheetImport session={session} onCommitted={()=>{}}/>);
  expect(html).toContain('Select worksheet from the materials');
  expect(html).toContain('aria-label="Worksheet material"');
  expect(html).toContain('aria-label="Answer key material"');
  expect(html).not.toContain('type="file"');
  expect(html).toMatch(/type="checkbox"[^>]*checked=""/);
 });
 it('posts only selected source IDs and explicit AI preference as JSON',async()=>{
  const fetch=vi.fn(async()=>new Response(JSON.stringify({import_id:'p'}),{status:200,headers:{'content-type':'application/json'}}));
  vi.stubGlobal('fetch',fetch);
  await api.worksheetFromMaterial('s/1','worksheet-id','answer-id');
  expect(fetch.mock.calls[0][0]).toBe('/api/sessions/s%2F1/worksheet-import/from-material');
  const options=fetch.mock.calls[0][1] as RequestInit;
  expect(options.method).toBe('POST');
  expect(JSON.parse(options.body as string)).toEqual({material_id:'worksheet-id',answer_material_id:'answer-id',use_ai:true});
  expect(options.body).not.toBeInstanceOf(FormData);
 });
 it('keeps absence of a supplied key explicit and permits a local preview',async()=>{
  const fetch=vi.fn(async()=>new Response('{}',{status:200}));vi.stubGlobal('fetch',fetch);
  await api.worksheetFromMaterial('s','m',null,false);
  expect(JSON.parse((fetch.mock.calls[0][1] as RequestInit).body as string)).toEqual({material_id:'m',answer_material_id:null,use_ai:false});
 });
});
