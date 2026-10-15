"""Actual candidate CT255 app -> restricted installed Office worker -> source API/persistence.
Synthetic accounts/course; genuine source bytes; no teaching-model/search requests.
"""
from pathlib import Path
import argparse,hashlib,json,os,shlex,shutil,socket,subprocess,sys,tarfile,time,uuid
import httpx
from run_remote_stage12_acceptance import guest,SSH,RELEASE
from run_stage12_real_reading import make_catalog
RELEASE="/opt/aicademiya/releases/AIcademiya_V2-20261011-materials-candidate"
ROOT=Path(__file__).resolve().parents[1]
_source=next(x for x in json.loads((ROOT/"artifacts/ocr-stage1/dataset/sources.json").read_text(encoding="utf-8"))["sources"]if x["id"]=="src15")
SOURCE=Path(_source["path"]);SHA=_source["sha256"]

def save(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def remote_json(code):return json.loads(guest([RELEASE+'/.venv/bin/python','-c',code],timeout=60).stdout)
def file_json(path):return remote_json('from pathlib import Path;import json;print(Path('+repr(path)+').read_text())')
def main():
 token=uuid.uuid4().hex[:10];out=ROOT/'artifacts/stage13'/('ct255-documents-'+token);out.mkdir(parents=True)
 qa='/var/lib/aicademiya-qa/stage13-documents-'+token;data=qa+'/data';base='http://192.168.32.55:18774';unit='aicademiya-qa-stage13-documents-'+token
 report={'status':'running','release':RELEASE,'qa':qa,'unit':unit,'checks':[],'ids':{},'synthetic_accounts_only':True,'actual_app_upload':False,'teaching_model_calls':0,'search_calls':0}
 def check(text):report['checks'].append(text);save(out/'result.json',report);print(json.dumps({'check':text}),flush=True)
 before=guest(['readlink','-f','/opt/aicademiya/current']).stdout.strip();assert before!=RELEASE
 with SOURCE.open('rb')as f:assert hashlib.file_digest(f,'sha256').hexdigest()==SHA
 with socket.socket()as s:s.settimeout(2);assert s.connect_ex(('192.168.32.55',18774))!=0,'QA listener occupied'
 # Check the actual installed root-owned worker, not merely a development probe.
 code="from pathlib import Path;import json;print(Path('/opt/aicademiya-documents/releases/stage13-materials-20261011/install-result.json').read_text())"
 p=subprocess.run(['ssh','-o','BatchMode=yes','ubuntu-gpu','python3 -c '+shlex.quote(code)],capture_output=True,text=True,timeout=20);assert p.returncode==0,p.stderr;install=json.loads(p.stdout)
 assert install['status']=='candidate_installed'
 for name,digest in install['code_sha256'].items():
  with (ROOT/'tools'/name).open('rb')as f:assert hashlib.file_digest(f,'sha256').hexdigest()==digest,name
 report.update(installed_source_match=True,device='cuda',installed_worker=install)
 fixture=out/'fixture';fixture.mkdir();make_catalog(fixture)
 worker=[RELEASE+'/.venv/bin/python',RELEASE+'/tools/document_stage12/document_ssh_bridge.py','--ssh-host','aicademiya-docs@192.168.32.5','--ssh-key','/var/lib/aicademiya/worker-ssh-stage13/id_ed25519','--known-hosts','/var/lib/aicademiya/worker-ssh-stage13/known_hosts','--remote-python','/opt/aicademiya-documents/runtime/.venv/bin/python','--remote-service','/opt/aicademiya-documents/releases/stage13-materials-20261011/document_stage12/document_worker_service.py','--timeout','420']
 server="from pathlib import Path\nimport os,uvicorn\nfrom backend.aicademiya.main import create_app\nf=Path(__file__).resolve().parent\napp=create_app(data_dir=Path(os.environ['AICADEMIYA_DATA_DIR']),catalog_path=f/'catalog.json',frontend_dir=Path("+repr(RELEASE+'/frontend/dist')+"),demo_enabled=True,document_worker_command="+repr(worker)+",document_worker_timeout=470)\nuvicorn.run(app,host='192.168.32.55',port=18774,log_level='warning')\n"
 (fixture/'server.py').write_text(server,encoding='utf-8')
 archive=out/'fixture.tar.gz'
 with tarfile.open(archive,'w:gz')as t:
  for f in fixture.rglob('*'):
   if f.is_file():t.add(f,arcname=f.relative_to(fixture).as_posix())
 incoming='/root/aicademiya-stage4-incoming/'+RELEASE.split('/')[-1]+'/'+token+'-document-fixture.tar.gz'
 subprocess.run(['scp',*SSH[1:-1],str(archive),'root@192.168.10.16:'+incoming],check=True,capture_output=True,timeout=30)
 guest(['install','-d','-m','700','-o','aicademiya','-g','aicademiya',qa])
 subprocess.run(SSH+[shlex.join(['pct','push','255',incoming,qa+'/fixture.tar.gz','--perms','0600'])],check=True,capture_output=True,timeout=30)
 guest(['python3','-c',"from pathlib import Path;import tarfile,hashlib,subprocess;p=Path("+repr(qa+'/fixture.tar.gz')+");assert hashlib.sha256(p.read_bytes()).hexdigest()=="+repr(hashlib.sha256(archive.read_bytes()).hexdigest())+";t=tarfile.open(p);t.extractall(p.parent,filter='data');t.close();subprocess.run(['chown','-R','aicademiya:aicademiya',str(p.parent)],check=True)"])
 envs={'AICADEMIYA_DOCUMENT_FORMATS':'pdf,pptx,docx,doc','PYTHONPATH':RELEASE,'PYTHONDONTWRITEBYTECODE':'1','LANG':'C.UTF-8','AICADEMIYA_DATA_DIR':data,'AICADEMIYA_DEMO_ENABLED':'true','AICADEMIYA_AI_MODE':'demo','AICADEMIYA_AI_BASE_URL':'','AICADEMIYA_AI_PROVIDER':'','AICADEMIYA_AI_MODEL':'','AICADEMIYA_AI_API_KEY':'','AICADEMIYA_WEB_SEARCH_ENABLED':'false','TAVILY_API_KEY':'','AICADEMIYA_ALLOWED_ORIGINS':base,'AICADEMIYA_COOKIE_SECURE':'false'}
 def start_service(target_data):
  envs['AICADEMIYA_DATA_DIR']=target_data
  args=['systemd-run','--unit='+unit,'--collect','--uid=aicademiya','--gid=aicademiya','--working-directory='+RELEASE,'--property=UMask=0077','--property=NoNewPrivileges=true','--property=ProtectSystem=strict','--property=ProtectHome=true','--property=PrivateTmp=true','--property=ReadWritePaths='+qa]+['--setenv='+k+'='+v for k,v in envs.items()]+[RELEASE+'/.venv/bin/python',qa+'/server.py']
  guest(args);ready()
 def ready():
  deadline=time.monotonic()+40
  with httpx.Client(base_url=base,trust_env=False,timeout=3)as c:
   while time.monotonic()<deadline:
    try:
     if c.get('/api/health').status_code==200:
      assert c.get('/openapi.json').json()['info']['version']=='0.11.0';assert c.get('/api/bootstrap').json()['ai']['mode']=='demo';return
    except httpx.RequestError:pass
    time.sleep(.25)
  raise RuntimeError('Owned Linux QA startup failed')
 def call(c,method,url,body=None,**kwargs):
  r=c.request(method,url,**({'json':body}if body is not None else{}),**kwargs)
  if r.status_code!=200:raise RuntimeError(f'{method} {url}: {r.status_code} {r.text[:1000]}')
  return r.json()
 try:
  start_service(data)
  with httpx.Client(base_url=base,trust_env=False,timeout=60)as teacher,httpx.Client(base_url=base,trust_env=False,timeout=60)as student:
   call(teacher,'POST','/api/auth/demo',{'role':'teacher'});call(student,'POST','/api/auth/demo',{'role':'student'})
   assert call(teacher,'GET','/api/document-processing')['available'];check('Exact staged app running as production user exposes configured restricted worker')
   with SOURCE.open('rb')as f:item=call(teacher,'POST','/api/sessions/s12-session/materials',files={'file':(SOURCE.name,f,'application/vnd.openxmlformats-officedocument.presentationml.presentation')},data={'processing':'full_document','kind':'reading','visibility':'student'})
   mid=item['id'];report['ids']['material']=mid;report['actual_app_upload']=True;ep='/api/materials/'+mid+'/document';started=time.monotonic();deadline=started+450;last=None
   while True:
    summary=call(teacher,'GET',ep);job=summary['latest_job'];save(out/'job-readback.json',job)
    if job and job['status']=='failed':raise RuntimeError('Actual installed GPU job failed: '+str(job))
    if job and job['status']=='completed':break
    if time.monotonic()>deadline:raise TimeoutError('Actual installed GPU processing deadline')
    if job and job['status']!=last:print(json.dumps({'job':job['status']}),flush=True);last=job['status']
    time.sleep(2)
   report['job_seconds']=time.monotonic()-started;doc=summary['document'];assert doc['page_count']==27 and doc['source_format']=='pptx' and doc['has_rendered_pdf'] and doc['source_sha256']==SHA
   parse_root=data+'/uploads/documents/'+job['id'];receipt=file_json(parse_root+'/receipt.json');supervisor=file_json(parse_root+'/raw/supervisor.json');transfer=file_json(parse_root+'/raw/ssh-job.json')
   assert supervisor['device']=='cuda'and supervisor['status']=='complete'and supervisor['model_processed_pages']>0 and supervisor['owned_processes_closed']
   assert transfer['returncode']==0 and len(receipt['page_timings'])==27
   report.update(owned_processes_closed=True,receipt=receipt,supervisor=supervisor,transfer=transfer);check('Fresh 27-slide Office GPU inference through actual app and restricted installed SSH worker committed successfully')
   pages=[call(teacher,'GET',ep+'/pages/'+str(n),params={'revision_id':doc['revision_id']})for n in range(1,28)];save(out/'parsed-pages.json',pages)
   assert [p['number']for p in pages]==list(range(1,28));assert sum(len(p['blocks'])for p in pages)>27
   # Exercise revision audit without claiming OCR accuracy: exclude one native block only in this isolated QA course.
   first_page=next(p for p in pages if any(b['quality']=='extracted' for b in p['blocks']));table=next(b for b in first_page['blocks']if b['quality']=='extracted');corrected=table['text'];review_page=first_page['number']
   review=call(teacher,'POST',ep+'/reviews',{'request_id':'linux-gpu-review','expected_revision':doc['revision_id'],'changes':[{'block_id':table['id'],'quality':'excluded','text':corrected,'reason':'Synthetic isolated QA: exercise audited exclusion; not an accuracy approval or source edit.'}]})
   assert call(teacher,'GET',ep+'/reviews/linux-gpu-review')==review;reviewed=call(teacher,'GET',ep)['document'];assert reviewed['revision_id']==review['document']['revision_id']
   report['ids']['reviewed_revision']=reviewed['revision_id'];check('Explicit audited exclusion creates a new revision without approving uncertain source text')
   detail=call(teacher,'GET','/api/sessions/s12-session');questions=detail['questions']
   for q in questions:q['source_material_ids']=[mid];q['source_links']=[]
   call(teacher,'PATCH','/api/sessions/s12-session',{'questions':questions})
   version=call(teacher,'POST','/api/teacher/courses/s12-course/versions/publish',{'label':'Synthetic installed-GPU acceptance'});vid=version['id'];report['ids']['version']=vid
   def read_published(client):
    projected=call(client,'GET',ep,params={'version_id':vid});assert projected['document']['revision_id']==reviewed['revision_id']
    original=client.get('/api/materials/'+mid+'/download',params={'version_id':vid});assert original.status_code==200 and hashlib.sha256(original.content).hexdigest()==SHA
    p=call(client,'GET',ep+'/pages/'+str(review_page),params={'version_id':vid,'revision_id':reviewed['revision_id']});assert next(b for b in p['blocks']if b['id']==table['id'])['quality']=='excluded'
    pdf=client.get(ep+'/pdf',params={'version_id':vid,'revision_id':reviewed['revision_id']});assert pdf.status_code==200 and pdf.content.startswith(b'%PDF-');report['rendered_pdf_sha256']=hashlib.sha256(pdf.content).hexdigest()
   read_published(student);check('Explicit synthetic publication pins reviewed revision and original Office bytes and derived PDF for student')
   save(out/'result.json',report)
   report['browser_acceptance']=False
   guest(['systemctl','restart',unit]);ready();read_published(student);check('Application restart preserves original, reviewed source and published edition without reprocessing')
   guest(['systemctl','stop',unit]);backup=qa+'/backup';restored=qa+'/restored'
   backup_result=json.loads(guest([RELEASE+'/.venv/bin/python',RELEASE+'/tools/backup_data.py','backup','--data-dir',data,'--materials-root',qa,'--destination',backup],timeout=60).stdout)
   restore_result=json.loads(guest([RELEASE+'/.venv/bin/python',RELEASE+'/tools/backup_data.py','restore','--source',backup,'--destination',restored],timeout=60).stdout)
   assert restore_result['records_match']and restore_result['files_match']
   guest(['python3','-c',"from pathlib import Path;Path("+repr(data)+").rename("+repr(data+'-retained')+")"])
   guest(['chown','-R','aicademiya:aicademiya',restored]);start_service(restored);read_published(student)
   report['backup_restore']={'backup':backup_result,'restore':restore_result,'old_data_path_unavailable':True};check('Actual SQLite/upload backup restores into new root; published Office/derived PDF and reviewed blocks work with old source path unavailable')
   report['status']='passed'
   report['semantic_accuracy_accepted']=False
 except BaseException as e:
  report.update(status='failed',error_type=type(e).__name__,error=str(e));print(json.dumps({'status':'failed','error':str(e)}),flush=True)
 finally:
  guest(['systemctl','stop',unit],check=False)
  report['qa_service_stopped']=guest(['systemctl','is-active',unit],check=False).stdout.strip()not in ('active','activating','deactivating')
  report['production_link_unchanged']=guest(['readlink','-f','/opt/aicademiya/current']).stdout.strip()==before
  with socket.socket()as s:s.settimeout(2);report['qa_listener_closed']=s.connect_ex(('192.168.32.55',18774))!=0
  if not all(report[k]for k in ['qa_service_stopped','production_link_unchanged','qa_listener_closed']):report['status']='failed'
  (out/'server.log').write_text(guest(['journalctl','-u',unit,'--no-pager','-n','250'],check=False).stdout,encoding='utf-8');save(out/'result.json',report)
  print(json.dumps({'status':report['status'],'result':str(out/'result.json'),'checks':len(report['checks']),'error':report.get('error')}),flush=True)
 return 0 if report['status']=='passed'else 1
if __name__=='__main__':raise SystemExit(main())
