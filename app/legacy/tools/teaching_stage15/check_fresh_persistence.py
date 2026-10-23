"""Restart + relocate only the fresh Stage15 QA data. GET verification, no model."""
from pathlib import Path
import hashlib,json,sys,time
import httpx
APP=Path(__file__).resolve().parents[2];sys.path.insert(0,str(APP/'tools/material_stage14'))
from prepare_app_acceptance import guest

def main():
 root=APP/'artifacts/stage15/fresh-app-r1';meta=json.loads((root/'meta.json').read_text());api=json.loads((root/'api-result.json').read_text());assert api['status']=='fresh_api_passed_browser_review_pending'
 assert json.loads((root/'browser-r2/result.json').read_text())['status']=='passed';assert meta['qa']=='/var/lib/aicademiya-qa/stage15-fresh-r1'and meta['data']==meta['qa']+'/data'
 report={'status':'running','production_changed':False,'new_provider_calls':0,'checks':[]}
 def remote(code):return json.loads(guest([meta['interpreter'],'-c',code]))
 def calls():return remote("from pathlib import Path;import json;print(json.dumps(len(Path("+repr(meta['qa']+'/model-exchanges.jsonl')+").read_text().splitlines())))")
 def ready():
  end=time.monotonic()+40
  while time.monotonic()<end:
   try:
    if httpx.get(meta['base_url']+'/api/health',trust_env=False,timeout=2).status_code==200:return
   except httpx.RequestError:pass
   time.sleep(.2)
  raise TimeoutError('QA restart readiness')
 def verify():
  with httpx.Client(base_url=meta['base_url'],trust_env=False,timeout=20)as teacher,httpx.Client(base_url=meta['base_url'],trust_env=False,timeout=20)as student:
   teacher.post('/api/auth/demo',json={'role':'teacher'}).raise_for_status();student.post('/api/auth/demo',json={'role':'student'}).raise_for_status()
   for name,spec in meta['inputs'].items():
    mid=api['ids'][name];r=student.get('/api/materials/'+mid+'/download',params={'version_id':api['version_id']});r.raise_for_status();assert hashlib.sha256(r.content).hexdigest()==spec['sha256']
    summary=student.get('/api/materials/'+mid+'/document',params={'version_id':api['version_id']});summary.raise_for_status();assert summary.json()['document']['source_sha256']==spec['sha256']
    if name=='source-notes.pptx':assert summary.json()['supplements']==[]
   w=student.get('/api/sessions/s12-session/workspace',params={'version_id':api['version_id']});w.raise_for_status();work=w.json();assert work['attempts']=={}and work['progress']['answered']==0
   last=next(m for m in work['messages']if m['id']==api['teaching_message']['id']);assert last==api['teaching_message']
   for cite in last['citations']:
    r=student.get(cite['url'].split('#')[0]);r.raise_for_status();assert r.headers['content-type'].startswith('application/pdf')
 before_calls=calls()
 try:
  guest(['systemctl','restart',meta['unit']]);ready();verify();report['checks'].append('Restart preserves every new original and exact accepted source/image citation')
  guest(['systemctl','stop',meta['unit']]);backup=meta['qa']+'/backup-r1';restored=meta['qa']+'/restored-r1'
  report['backup']=json.loads(guest(['runuser','-u','aicademiya','--',meta['interpreter'],meta['source']+'/tools/backup_data.py','backup','--data-dir',meta['data'],'--materials-root',meta['qa'],'--destination',backup],timeout=180))
  report['restore']=json.loads(guest(['runuser','-u','aicademiya','--',meta['interpreter'],meta['source']+'/tools/backup_data.py','restore','--source',backup,'--destination',restored],timeout=180));assert report['restore']['records_match']and report['restore']['files_match']
  guest(['python3','-c',"from pathlib import Path;p=Path("+repr(meta['data'])+");q=p.with_name('data-retained');assert not q.exists();p.rename(q)"])
  newmeta={**meta,'data':restored,'environment':{**meta['environment'],'AICADEMIYA_DATA_DIR':restored},'start_command':[('--setenv=AICADEMIYA_DATA_DIR='+restored)if x.startswith('--setenv=AICADEMIYA_DATA_DIR=')else x for x in meta['start_command']],'restored_data':True}
  (root/'meta-restored.json').write_text(json.dumps(newmeta,indent=2)+'\n');guest(newmeta['start_command']);ready();verify()
  check="import sqlite3,json;from pathlib import Path;r=Path("+repr(restored)+");c=sqlite3.connect('file:'+str(r/'aicademiya.sqlite3')+'?mode=ro',uri=True);assert not Path("+repr(meta['data'])+").exists();assert c.execute(\"select status from tutor_requests where request_id='fresh-stage15-table'\").fetchone()[0]=='done';print(json.dumps({'integrity':c.execute('pragma integrity_check').fetchone()[0],'foreign_keys':len(c.execute('pragma foreign_key_check').fetchall()),'old_data_root_unavailable':True,'same_request_done':True}))"
  report['database']=remote(check);assert report['database']['integrity']=='ok'and report['database']['foreign_keys']==0;assert calls()==before_calls
  report['checks'].append('Relocated restore serves all4 originals and image citations with old upload root unavailable; completed request retained; no model calls');report['status']='passed'
 except BaseException as e:report.update(status='failed',error_type=type(e).__name__,error=str(e));raise
 finally:
  guest(['systemctl','stop',meta['unit']]);report['qa_closed']=guest(['systemctl','show',meta['unit'],'--property=ActiveState','--value']).strip()!='active';report['production_unchanged']=guest(['readlink','-f','/opt/aicademiya/current']).strip()==meta['production_release'];(root/'persistence-result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':report['status'],'qa_closed':report['qa_closed'],'production_unchanged':report['production_unchanged']}),flush=True)
if __name__=='__main__':main()
