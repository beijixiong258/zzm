"""Fresh HTTP uploads -> installed UID999 worker -> original-source teaching.
No processor/provider doubles; QA accounts/data only. Retain QA UI on success.
"""
from pathlib import Path
import argparse,base64,hashlib,json,shlex,subprocess,sys,time
import httpx
APP=Path(__file__).resolve().parents[2];sys.path.insert(0,str(APP/'tools/material_stage14'))
from prepare_app_acceptance import guest
GPU='GPU-105b82fb-41db-d6a1-13f0-ceddf5bed313'
def gpu_state():
 code="""import json,subprocess,urllib.request
from pathlib import Path
v=json.load(urllib.request.urlopen('http://127.0.0.1:18280/status'));rows=[]
for line in subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,used_memory','--format=csv,noheader,nounits'],text=True).splitlines():
 u,p,m=[x.strip()for x in line.split(',')];rows.append({'gpu_uuid':u,'pid':int(p),'uid':Path('/proc/'+p).stat().st_uid,'used_mib':int(m)})
print(json.dumps({'phase':v['resources']['phase'],'capacity':v['teaching_capacity'],'queue':v['queue'],'workers':[{k:w.get(k)for k in ['name','busy','healthy','supports_vision']}for w in v['workers']],'allocations':rows}))
"""
 r=subprocess.run(['ssh','-4','-o','BatchMode=yes','ubuntu-gpu','python3 -c '+shlex.quote(code)],capture_output=True,text=True,timeout=20);assert r.returncode==0,r.stderr;return json.loads(r.stdout)
def main():
 p=argparse.ArgumentParser();p.add_argument('--meta',required=True);a=p.parse_args();meta=json.loads(Path(a.meta).read_text());out=Path(meta['artifact_dir']);file=out/'api-result.json';report=json.loads(file.read_text())if file.exists()else {'status':'running','ids':{},'checks':[],'gpu_samples':[],'scope':'Fresh actual uploads/installed worker/real model; isolated QA, not production promotion'}
 def save():file.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 def check(text):report['checks'].append(text);save();print(json.dumps({'check':text}),flush=True)
 def remote(code):return json.loads(guest([meta['interpreter'],'-c',code]))
 def call(c,method,path,body=None,**kwargs):
  r=c.request(method,path,**({'json':body}if body is not None else{}),**kwargs)
  if r.status_code!=200:raise RuntimeError(f'{method} {path}: {r.status_code} {r.text[:1800]}')
  return r.json()
 try:
  report['before_gpu']=gpu_state();assert report['before_gpu']['phase']=='teaching'and report['before_gpu']['capacity']==3
  if guest(['systemctl','show',meta['unit'],'--property=ActiveState','--value']).strip()!='active':guest(meta['start_command'])
  with httpx.Client(base_url=meta['base_url'],trust_env=False,timeout=650)as teacher,httpx.Client(base_url=meta['base_url'],trust_env=False,timeout=650)as student:
   end=time.monotonic()+40
   while True:
    try:
     r=teacher.get('/api/bootstrap',timeout=2)
     if r.status_code==200:break
    except httpx.RequestError:pass
    if time.monotonic()>end:raise TimeoutError('Fresh QA site readiness')
    time.sleep(.2)
   call(teacher,'POST','/api/auth/demo',{'role':'teacher'});call(student,'POST','/api/auth/demo',{'role':'student'})
   assert call(teacher,'GET','/api/document-processing')['available'];assert guest(['readlink','-f','/opt/aicademiya/current']).strip()==meta['production_release']
   summaries={}
   for name,spec in meta['inputs'].items():
    mid=report['ids'].get(name)
    if not mid:
     with(out/'fixture'/name).open('rb')as f:item=call(teacher,'POST','/api/sessions/s12-session/materials',files={'file':(name,f,'application/octet-stream')},data={'processing':'full_document','kind':'reading','visibility':'student'})
     mid=item['id'];report['ids'][name]=mid;save()
    end=time.monotonic()+1250;sample_due=0
    while True:
     summary=call(teacher,'GET','/api/materials/'+mid+'/document');job=summary['latest_job'];(out/(name+'.job.json')).write_text(json.dumps(job,indent=2))
     if job and job['status']=='failed':raise RuntimeError('Fresh processing failed: '+name+' '+str(job))
     if job and job['status']=='completed':break
     if time.monotonic()>end:raise TimeoutError('Fresh document deadline: '+name)
     if time.monotonic()>=sample_due:report['gpu_samples'].append({'source':name,**gpu_state()});save();sample_due=time.monotonic()+6
     time.sleep(1)
    assert summary['document']['source_sha256']==spec['sha256']and summary['document']['source_format']==spec['format']
    raw=teacher.get('/api/materials/'+mid+'/download');assert raw.status_code==200 and hashlib.sha256(raw.content).hexdigest()==spec['sha256']
    root=meta['data']+'/uploads/documents/'+job['id'];code="from pathlib import Path;import json;p=Path("+repr(root)+");print(json.dumps({n:json.loads((p/n).read_text())for n in ['manifest.json','receipt.json','raw/supervisor.json','raw/ssh-job.json']}))";evidence=remote(code)
    (out/(name+'.worker.json')).write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n');supervisor=evidence['raw/supervisor.json'];receipt=evidence['receipt.json'];manifest=evidence['manifest.json']
    assert supervisor['status']=='complete'and supervisor['owned_processes_closed']and evidence['raw/ssh-job.json']['returncode']==0
    if name in ('lesson-source.pdf','method-trait.png'):
     assert supervisor['gpu_lease_used']and supervisor['fresh_inference']and supervisor['visual_backend']=='native+live-page-markdown'
     assert receipt['visual_transcription_complete']and receipt['model_calls']==len(receipt['selected_pages'])and not receipt['imported_evidence'],receipt
     assert any(s['source']==name and any(a['gpu_uuid']==GPU and a['uid']==999 for a in s['allocations'])for s in report['gpu_samples']),'No actual UID999 GPU allocation observed'
     before=json.loads(guest([meta['interpreter'],'-c',"from pathlib import Path;print(Path("+repr(root+'/raw/stage15-prepared-manifest.json')+").read_text())"]))
     after={b['id']:b for p in manifest['pages']for b in p['blocks']};assert all(after.get(b['id'])==b for p in before['pages']for b in p['blocks'])
    if name=='source-ledger.txt':assert not supervisor['gpu_lease_used']and ''.join(b['text']for p in manifest['pages']for b in p['blocks'])==meta['native_text']
    summaries[name]=summary;check('Fresh '+name+' original/worker/source representation/application commit verified')
   notes=summaries['source-notes.pptx']['supplements'];note=next(x for x in notes if x['kind']=='speaker_notes');assert meta['private_note']in teacher.get('/api/materials/'+report['ids']['source-notes.pptx']+'/document/supplements/'+note['id']+'/text',params={'revision_id':summaries['source-notes.pptx']['document']['revision_id']}).text
   detail=call(teacher,'GET','/api/sessions/s12-session');questions=detail['questions']
   for q in questions:q['source_material_ids']=[report['ids']['method-trait.png']];q['source_links']=[]
   call(teacher,'PATCH','/api/sessions/s12-session',{'questions':questions,'teaching_language':'en','teaching_profile':{**detail['teaching_profile'],'phases':['worksheet','wrap_up']}})
   version=call(teacher,'POST','/api/teacher/courses/s12-course/versions/publish',{'label':'Fresh Stage15 source processing QA'})['id'];report['version_id']=version;save()
   assert call(student,'GET','/api/materials/'+report['ids']['source-notes.pptx']+'/document',params={'version_id':version})['supplements']==[]
   call(student,'POST','/api/sessions/s12-session/tutor/start',{'request_id':'fresh-stage15-start'},params={'version_id':version})
   body={'request_id':'fresh-stage15-table','message':'Read the original table image in method-trait.png. For the Multiple-choice method, state the exact number of Grammar, Discourse and Sociolinguistic items and the exercise type for each. Cite the original source image.'}
   work=call(student,'POST','/api/sessions/s12-session/tutor/turn',body,params={'version_id':version});last=work['messages'][-1];assert all(str(n)in last['content']for n in (45,29,28));assert work['attempts']=={}and work['progress']['answered']==0
   citations=[c for c in last['citations']if c.get('material_id')==report['ids']['method-trait.png']];assert citations
   for c in citations:assert c['version_id']==version and c['revision_id']==summaries['method-trait.png']['document']['revision_id']and student.get(c['url'].split('#')[0]).status_code==200
   exchanges=remote("from pathlib import Path;import json;p=Path("+repr(meta['qa']+'/model-exchanges.jsonl')+");print(json.dumps([json.loads(s)for s in p.read_text().splitlines()]))")
   images=[row for row in exchanges if any(isinstance(m.get('content'),list)and any(p.get('type')=='image_url'for p in m['content'])for m in row['request']['messages'])];assert images and all(x['router_headers']['X-AIcademiya-Worker']=='t10b'and x['router_headers']['X-KV-Restored']=='false'for x in images)
   assert meta['private_note']not in json.dumps(exchanges,ensure_ascii=False)
   again=call(student,'POST','/api/sessions/s12-session/tutor/turn',body,params={'version_id':version});assert again['messages'][-1]==last
   total=remote("from pathlib import Path;import json;print(json.dumps(len(Path("+repr(meta['qa']+'/model-exchanges.jsonl')+").read_text().splitlines())))");assert total==len(exchanges)
   report.update(teaching_message=last,actual_provider_calls=len(exchanges));(out/'model-exchanges.json').write_text(json.dumps(exchanges,ensure_ascii=False,indent=2)+'\n');check('Fresh-source real image teaching/citations/hidden notes and durable retry verified')
  end=time.monotonic()+90
  while True:
   state=gpu_state()
   if state['phase']=='teaching'and state['capacity']==3:break
   if time.monotonic()>end:raise TimeoutError('Teaching replicas did not return ready')
   time.sleep(.5)
  before={a['gpu_uuid']:a['pid']for a in report['before_gpu']['allocations']};after={a['gpu_uuid']:a['pid']for a in state['allocations']};assert all(after[u]==pid for u,pid in before.items()if u!=GPU)
  report.update(status='fresh_api_passed_browser_review_pending',after_gpu=state,anchor_pids_preserved=True,qa_retained_for_browser=True);save();print(json.dumps({'status':report['status'],'path':str(file)}),flush=True)
 except BaseException as e:
  report.update(status='failed',error_type=type(e).__name__,error=str(e));save();guest(['systemctl','stop',meta['unit']]);(out/'server.log').write_text(guest(['journalctl','-u',meta['unit'],'--no-pager','-n','140']),encoding='utf-8');raise
if __name__=='__main__':main()
