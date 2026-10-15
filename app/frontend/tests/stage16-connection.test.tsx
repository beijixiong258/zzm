import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {describe,it,expect} from 'vitest';
import {liveConnectionLabel,LiveConnectionContext} from '../src/live-connection';
import {AiBadge} from '../src/ui';
import type {LiveConnection} from '../src/types';
const live:LiveConnection={status:'connected',model:'new-model',checked_at:'2099-01-01T00:00:00Z',expires_at:'2099-01-01T00:01:00Z',message:'Endpoint reachable',check_kind:'model_listing',poll_interval_seconds:30};
describe('scheduled AI connection status',()=>{
 it('expires a previous successful check rather than showing perpetual connected',()=>{expect(liveConnectionLabel(live,Date.parse('2099-01-01T00:02:00Z')).text).toBe('Check expired');});
 it('distinguishes health from previous generation failures',()=>{
  const html=renderToStaticMarkup(<LiveConnectionContext.Provider value={live}><AiBadge ai={{mode:'openai',model:'old-model',base_url:'',configured:true,last_error:'Old generation error'}} detail/></LiveConnectionContext.Provider>);
  expect(html).toContain('Endpoint reachable');expect(html).toContain('new-model');expect(html).toContain('Auto-check every 30s');expect(html).not.toContain('Last check passed');
 });
 it('does not reuse an old success timestamp when status transport fails',()=>{
  const html=renderToStaticMarkup(<LiveConnectionContext.Provider value={{...live,status:'unavailable',checked_at:null,expires_at:null}}><AiBadge ai={{mode:'openai',model:'old',base_url:'',configured:true,connection:{status:'connected',checked_at:'2020-01-01',message:null}}} detail/></LiveConnectionContext.Provider>);
  expect(html).toContain('Status unavailable');expect(html).not.toContain('Last checked');
 });
});
