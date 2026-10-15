"""Retry only the previously failed actual teaching request; no upload/reprocess.
Keep the failed report/exchanges and verify exact source-image/edition identity.
"""
from pathlib import Path
import base64,hashlib,json,sys,time
import httpx
APP=Path(__file__).resolve().parents[2];sys.path[:0]=[str(APP/'tools/material_stage14'),str(APP/'tools/teaching_stage15')]
from prepare_app_acceptance import guest
from run_fresh_app import gpu_state

def main():
 root=APP/'artifacts/stage15/fresh-app-r1';meta=json.loads((root/'meta.json').read_text());raw=(root/'api-result.json').read_bytes();report=json.loads(raw);assert report['status']in ('failed','failed_after_quote_fix')and report['version_id'];recover_done=report['status']=='failed_after_quote_fix';failed=root/('retry-harness-failed-r1.json'if recover_done else'api-result-failed-r1.json');assert not failed.exists();failed.write_bytes(raw)
 state=gpu_state();assert state['phase']=='teaching'and state['capacity']==3
 def remote(code):return json.loads(guest([meta['interpreter'],'-c',code]))
 def exchanges():return remote("from pathlib import Path;import json;print(json.dumps([json.loads(s)for s in Path("+repr(meta['qa']+'/model-exchanges.jsonl')+").read_text().splitlines()]))")
 if recover_done:
  state=remote("import sqlite3,json;c=sqlite3.connect('file:"+meta['data']+"/aicademiya.sqlite3?mode=ro',uri=True);print(json.dumps(c.execute('select status from tutor_requests where session_id=? and user_id=? and version_id=? and request_id=?',('s12-session','demo-student-1',"+repr(report['version_id'])+",'fresh-stage15-table')).fetchone()[0]))");assert state=='done'
 def call(c,method,path,body=None,**kwargs):
  r=c.request(method,path,**({'json':body}if body is not None else{}),**kwargs);assert r.status_code==200,(r.status_code,r.text[:1500]);return r.json()
 old=exchanges();guest(meta['start_command']);version=report['version_id'];body={'request_id':'fresh-stage15-table','message':'Read the original table image in method-trait.png. For the Multiple-choice method, state the exact number of Grammar, Discourse and Sociolinguistic items and the exercise type for each. Cite the original source image.'}
 try:
  with httpx.Client(base_url=meta['base_url'],trust_env=False,timeout=650)as c:
   end=time.monotonic()+40
   while True:
    try:
     if c.get('/api/health',timeout=2).status_code==200:break
    except httpx.RequestError:pass
    if time.monotonic()>end:raise TimeoutError('QA resume readiness')
    time.sleep(.2)
   call(c,'POST','/api/auth/demo',{'role':'student'});before=call(c,'GET','/api/sessions/s12-session/workspace',params={'version_id':version});prior=[m for m in before['messages']if m['role']=='user'and m['content']==body['message']];assert len(prior)==1
   work=call(c,'POST','/api/sessions/s12-session/tutor/turn',body,params={'version_id':version});last=work['messages'][-1];assert all(str(n)in last['content']for n in (45,29,28));assert work['attempts']=={}and work['progress']['answered']==0
   actual=[m for m in work['messages']if m['role']=='user'and m['content']==body['message']];assert [{k:m[k]for k in ('id','role','content','created_at')}for m in actual]==[{k:m[k]for k in ('id','role','content','created_at')}for m in prior]
   mid=report['ids']['method-trait.png'];summary=call(c,'GET','/api/materials/'+mid+'/document',params={'version_id':version})
   cites=[x for x in last['citations']if x.get('material_id')==mid];assert cites
   for x in cites:assert x['version_id']==version and x['revision_id']==summary['document']['revision_id']and c.get(x['url'].split('#')[0]).status_code==200
   all_calls=exchanges();assert all_calls[:len(old)]==old
   if recover_done:assert len(all_calls)==len(old)
   original_failure=json.loads((root/'failed-model-exchanges-r1.json').read_text());assert all_calls[:len(original_failure)]==original_failure;new=all_calls[len(original_failure):];images=[]
   for row in new:
    for message in row['request']['messages']:
     if isinstance(message.get('content'),list):
      for part in message['content']:
       if part.get('type')=='image_url':images.append((row,hashlib.sha256(base64.b64decode(part['image_url']['url'].split(',',1)[1])).hexdigest()))
   job=json.loads((root/'method-trait.png.job.json').read_text());bundle=meta['data']+'/uploads/documents/'+job['id']
   page_hashes=remote("from pathlib import Path;import hashlib,json;r=Path("+repr(bundle)+");m=json.loads((r/'manifest.json').read_text());print(json.dumps([hashlib.sha256((r/p['image']).read_bytes()).hexdigest()for p in m['pages']]))")
   assert images and all(row['router_headers']['X-AIcademiya-Worker']=='t10b'and row['router_headers']['X-KV-Restored']=='false'and digest in page_hashes for row,digest in images)
   assert meta['private_note']not in json.dumps(new,ensure_ascii=False)
   repeated=call(c,'POST','/api/sessions/s12-session/tutor/turn',body,params={'version_id':version});assert repeated['messages'][-1]==last and len(exchanges())==len(all_calls)
   (root/'model-exchanges.json').write_text(json.dumps(all_calls,ensure_ascii=False,indent=2)+'\n')
   report.pop('error',None);report.pop('error_type',None);report.update(status='fresh_api_passed_browser_review_pending',teaching_message=last,actual_provider_calls=len(all_calls),retry_provider_calls=len(new),same_failed_request_retried=True,original_user_message_preserved_once=True,qa_retained_for_browser=True,acknowledged_success_recovered_without_inference=recover_done)
   after=gpu_state();original={x['gpu_uuid']:x['pid']for x in report['before_gpu']['allocations']};assert all(x['pid']==original[x['gpu_uuid']]for x in after['allocations']if x['gpu_uuid']!='GPU-105b82fb-41db-d6a1-13f0-ceddf5bed313');assert after['phase']=='teaching'and after['capacity']==3
   report.update(after_gpu=after,anchor_pids_preserved=True,rendered_quote_branch_used_in_live_retry=any(x.get('quote_basis')for x in cites));report['checks'].append('Fresh-source actual retry succeeded with exact original image citation; retained HTML quotation failures are separately verified by CPU replay')
 except BaseException as e:report.update(status='failed_after_quote_fix',error_type=type(e).__name__,error=str(e));guest(['systemctl','stop',meta['unit']]);raise
 finally:(root/'api-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'status':report['status'],'retry_provider_calls':report.get('retry_provider_calls'),'error':report.get('error')}),flush=True)
if __name__=='__main__':main()
