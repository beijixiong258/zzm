"""Actual installed Stage16 CT app -> restricted UID999 SSH worker acceptance.
Only synthetic uploads in an owned QA service. Old production site stays live.
"""
from pathlib import Path
import hashlib,io,json,shlex,subprocess,sys,tarfile,time
import httpx
APP=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).resolve().parent))
from live_worksheet_probe import guest,gpu,SSH
QA='/var/lib/aicademiya-qa/stage16-release-r4';RELEASE='/opt/aicademiya/releases/AIcademiya_V2-stage16-workflow-r4';PY=RELEASE+'/.venv/bin/python'
BASE='http://192.168.32.55:18776';UNIT='aicademiya-qa-stage16-worker-r4'
EVIDENCE=APP/'artifacts/stage16/legacy-real/20261013T185410Z-bb5cb6e1/evidence/originals'

def main():
 out=APP/'artifacts/stage16/installed-worker-app-r2';out.mkdir(exist_ok=False)
 q="from pathlib import Path;print(Path('/home/adminz/llm/operations/stage16-worker-r1/install-result.json').read_text())"
 r=subprocess.run(['ssh','-o','BatchMode=yes','ubuntu-gpu','python3 -c '+shlex.quote(q)],capture_output=True,text=True,timeout=25);assert r.returncode==0,r.stderr
 install=json.loads(r.stdout);assert install['status']=='installed_cpu_verified_pending_app_worker_acceptance'and install['active_binding_changed']
 before=gpu();assert before['capacity']==3 and before['queue']==0 and all(not w['busy']for w in before['workers'])
 original_release=guest(['readlink','-f','/opt/aicademiya/current']).strip();assert original_release!=RELEASE
 guest(['python3','-c',"import socket;s=socket.socket();s.bind(('192.168.32.55',18776));s.close()"])
 worker=[PY,RELEASE+'/tools/document_stage12/document_ssh_bridge.py','--ssh-host','aicademiya-docs@192.168.32.5','--ssh-key','/var/lib/aicademiya/worker-ssh-stage14/id_ed25519','--known-hosts','/var/lib/aicademiya/worker-ssh-stage14/known_hosts','--timeout','1200']
 root=QA+'/worker-app'
 catalog={'schema_version':1,'course':{'id':'s16-worker','code':'SYNTHETIC','title':'Stage16 installed worker QA','description':'No classroom identities'},'sessions':[{'id':'s16-worker','course_id':'s16-worker','number':1,'title':'Formats','subtitle':'Synthetic source proof','status':'published','estimated_minutes':15,'learning_objectives':[],'instructions':'Source review','reference_policy':'after_attempt','teaching_language':'en','groups':[],'questions':[],'reference_answers':{},'materials':[]}]}
 server="from pathlib import Path\nimport uvicorn\nfrom backend.aicademiya.main import create_app\nr=Path(__file__).resolve().parent\napp=create_app(data_dir=r/'data',catalog_path=r/'catalog.json',frontend_dir=Path("+repr(RELEASE+'/frontend/dist')+"),demo_enabled=True,document_worker_command="+repr(worker)+",document_worker_timeout=1250)\nuvicorn.run(app,host='192.168.32.55',port=18776,log_level='warning')\n"
 blobs={'server.py':server.encode(),'catalog.json':json.dumps(catalog).encode()};buf=io.BytesIO()
 with tarfile.open(fileobj=buf,mode='w:gz')as tf:
  for n,b in blobs.items():x=tarfile.TarInfo(n);x.size=len(b);x.mode=0o600;tf.addfile(x,io.BytesIO(b))
 code="from pathlib import Path;import sys,io,tarfile,os,pwd;p=Path("+repr(root)+");p.mkdir(mode=0o700);tarfile.open(fileobj=io.BytesIO(sys.stdin.buffer.read()),mode='r:gz').extractall(p,filter='data');u=pwd.getpwnam('aicademiya');\nfor x in [p,*p.rglob('*')]:os.chown(x,u.pw_uid,u.pw_gid)"
 r=subprocess.run(SSH+[shlex.join(['pct','exec','255','--','python3','-c',code])],input=buf.getvalue(),capture_output=True,timeout=30);assert r.returncode==0,r.stderr
 env={'PYTHONPATH':RELEASE,'PYTHONDONTWRITEBYTECODE':'1','LANG':'C.UTF-8','AICADEMIYA_DATA_DIR':root+'/data','AICADEMIYA_DEMO_ENABLED':'true','AICADEMIYA_AI_MODE':'openai','AICADEMIYA_AI_PROVIDER':'aicademiya-router','AICADEMIYA_AI_BASE_URL':'http://127.0.0.1:18280/v1','AICADEMIYA_AI_MODEL':'AIcademiya-64kx3-Qwen3.8-27B','AICADEMIYA_AI_API_KEY':'','AICADEMIYA_DOCUMENT_FORMATS':'pdf,pptx,ppt,docx,doc,xls,xlsx,txt,md,png,jpg,jpeg,webp','AICADEMIYA_WEB_SEARCH_ENABLED':'false','TAVILY_API_KEY':'','AICADEMIYA_ALLOWED_ORIGINS':BASE,'AICADEMIYA_COOKIE_SECURE':'false','NO_PROXY':'127.0.0.1,localhost,192.168.32.55'}
 start=['systemd-run','--unit='+UNIT,'--collect','--uid=aicademiya','--gid=aicademiya','--working-directory='+RELEASE,'--property=UMask=0077','--property=RuntimeMaxSec=5400','--property=NoNewPrivileges=true','--property=ProtectSystem=strict','--property=ProtectHome=true','--property=PrivateTmp=true','--property=ReadWritePaths='+root]+['--setenv='+k+'='+v for k,v in env.items()]+[PY,root+'/server.py']
 report={'status':'running','installed_worker_uid':999,'actual_restricted_ssh':True,'qa':root,'unit':UNIT,'cases':[],'before_gpu':before,'production_changed':False}
 def save():(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
 def call(c,method,path,**kwargs):
  r=c.request(method,path,**kwargs)
  if r.status_code!=200:raise RuntimeError(f'{method} {path}: {r.status_code} {r.text[:1200]}')
  return r.json()
 save();print(json.dumps({'artifact_dir':str(out),'qa':root}),flush=True)
 try:
  guest(start)
  with httpx.Client(base_url=BASE,trust_env=False,timeout=650)as c:
   end=time.monotonic()+40
   while True:
    try:
     if c.get('/api/bootstrap',timeout=2).status_code==200:break
    except httpx.RequestError:pass
    if time.monotonic()>end:raise TimeoutError('QA readiness')
    time.sleep(.3)
   call(c,'POST','/api/auth/demo',json={'role':'teacher'})
   cap=call(c,'GET','/api/document-processing');assert all(x in cap['formats']for x in ['doc','ppt','xls','xlsx']);report['capability']=cap
   assert c.get('/').content==(APP/'frontend/dist/index.html').read_bytes()
   for fmt in ['xls','xlsx','doc','ppt']:
    source=EVIDENCE/('synthetic.'+fmt);blob=source.read_bytes();digest=hashlib.sha256(blob).hexdigest()
    material=call(c,'POST','/api/sessions/s16-worker/materials',data={'processing':'full_document','kind':'worksheet'if fmt=='doc'else'reference','visibility':'teacher'},files={'file':(source.name,blob)})
    mid=material['id'];report.setdefault('accepted_uploads',{})[fmt]=mid;save();deadline=time.monotonic()+1250
    while True:
     status=call(c,'GET','/api/materials/'+mid+'/document');job=status['latest_job']
     if job and job['status']=='completed':break
     if job and job['status']=='failed':raise RuntimeError(fmt+' installed processing failed: '+str(job))
     if time.monotonic()>deadline:raise TimeoutError(fmt+' processing deadline')
     time.sleep(1)
    document=status['document'];assert document['source_format']==fmt and document['source_sha256']==digest
    original=c.get('/api/materials/'+mid+'/download');assert original.status_code==200 and original.content==blob
    bundle=root+'/data/uploads/documents/'+job['id']
    code="from pathlib import Path;import json;p=Path("+repr(bundle)+");print(json.dumps({name:json.loads((p/name).read_text())for name in ['manifest.json','receipt.json','raw/supervisor.json','raw/ssh-job.json']}))"
    evidence=json.loads(guest([PY,'-c',code]));(out/(fmt+'-worker.json')).write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
    supervisor=evidence['raw/supervisor.json'];assert supervisor['status']=='complete'and supervisor['owned_processes_closed']and evidence['raw/ssh-job.json']['returncode']==0
    assert evidence['manifest.json']['source_sha256']==digest
    if fmt in ['xls','xlsx']:assert not supervisor['gpu_lease_used'];assert status['supplements'] and all(s['visibility']=='teacher'for s in status['supplements'])
    if fmt=='ppt':assert len([s for s in status['supplements']if s['kind']=='speaker_notes'])==2
    report['cases'].append({'format':fmt,'material_id':mid,'revision_id':document['revision_id'],'page_count':document['page_count'],'source_sha256':digest,'gpu_lease_used':supervisor['gpu_lease_used'],'original_unchanged':True,'supplements':status['supplements']});save();print(json.dumps({'format':fmt,'passed':True,'pages':document['page_count'],'gpu_lease_used':supervisor['gpu_lease_used']}),flush=True)
   detail=call(c,'GET','/api/sessions/s16-worker');assert len(detail['materials'])==4
  end=time.monotonic()+120
  while True:
   report['after_gpu']=gpu()
   if report['after_gpu']['capacity']==3 and report['after_gpu']['queue']==0 and all(not w['busy']and w['healthy']for w in report['after_gpu']['workers']):break
   if time.monotonic()>end:raise TimeoutError('Teaching capacity was not restored after owned document jobs')
   time.sleep(1)
  anchors=lambda state:[a for a in state['allocations']if 'GPU-105b82fb-41db-d6a1-13f0-ceddf5bed313'not in a]
  assert anchors(before)==anchors(report['after_gpu'])
  assert guest(['readlink','-f','/opt/aicademiya/current']).strip()==original_release
  report['status']='passed'
 except BaseException as exc:report.update(status='failed',error_type=type(exc).__name__,error=str(exc));raise
 finally:
  guest(['systemctl','stop',UNIT],timeout=120)
  report['qa_stopped']=guest(['python3','-c',"import socket;s=socket.socket();s.settimeout(2);print(s.connect_ex(('192.168.32.55',18776))!=0);s.close()"]).strip()=='True';save()
  encoded=json.dumps(report,indent=2).encode();code="from pathlib import Path;import sys,json;p=Path("+repr(QA+'/worker-app-result.json')+");b=sys.stdin.buffer.read();json.loads(b);p.write_bytes(b);assert p.read_bytes()==b"
  r=subprocess.run(SSH+[shlex.join(['pct','exec','255','--','python3','-c',code])],input=encoded,capture_output=True,timeout=30);assert r.returncode==0,r.stderr
  print(json.dumps(report,indent=2),flush=True)
if __name__=='__main__':main()
