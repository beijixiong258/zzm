"""Stage9 Linux/LAN avatar/feedback HTTP and real Chrome acceptance on a fresh CT255 QA root."""
from pathlib import Path
import datetime,json,os,shlex,shutil,socket,subprocess,sys,time,uuid
import httpx
ROOT=Path(__file__).resolve().parents[1]
RELEASE='/opt/aicademiya/releases/AIcademiya_V2-20261008-people'
TOKEN=uuid.uuid4().hex[:10]
OUT=ROOT/'artifacts/stage11'/('ct255-qa-'+TOKEN)
DATA='/var/lib/aicademiya-qa/stage11-'+TOKEN
BASE='http://192.168.32.55:18774'
SSH=['ssh','-i','C:/Users/17193/.ssh/id_ed25519_aicademiya_pve','-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8','root@192.168.10.16']
def guest(args,check=True,timeout=45):
 r=subprocess.run(SSH+[shlex.join(['pct','exec','255','--']+args)],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout)
 if check and r.returncode:raise RuntimeError(r.stderr or r.stdout)
 return r

def ready():
 with httpx.Client(trust_env=False,timeout=2) as c:
  deadline=time.monotonic()+40
  while time.monotonic()<deadline:
   try:
    if c.get(BASE+'/api/health').status_code==200:
     boot=c.get(BASE+'/api/bootstrap').json();assert boot['demo_enabled'] and boot['ai']['mode']=='demo'
     assert c.get(BASE+'/openapi.json').json()['info']['version']=='0.9.0'
     return
   except httpx.RequestError:pass
   time.sleep(.2)
 raise RuntimeError('Linux QA service readiness timeout')

def database_probe(data,ids):
 code='''import json,sqlite3
from pathlib import Path
p=Path(DATA)/'aicademiya.sqlite3';ids=IDS
with sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True) as c:
 c.row_factory=sqlite3.Row
 r={'integrity':c.execute('PRAGMA integrity_check').fetchone()[0],'foreign_key_violations':len(c.execute('PRAGMA foreign_key_check').fetchall()),'schema_version':c.execute('PRAGMA user_version').fetchone()[0]}
 r['course_staff_rows']=c.execute('SELECT count(*) FROM course_staff').fetchone()[0]
 r['account_import_rows']=c.execute('SELECT count(*) FROM account_imports').fetchone()[0]
 r['account_avatar_rows']=c.execute('SELECT count(*) FROM account_avatars').fetchone()[0]
 r['feedback_rows']=c.execute('SELECT count(*) FROM feedback').fetchone()[0]
 if ids.get('avatar_user'):
  import hashlib
  raw=c.execute('SELECT content FROM account_avatars WHERE user_id=?',(ids['avatar_user'],)).fetchone()[0]
  assert hashlib.sha256(raw).hexdigest()==ids['avatar_sha256']
  r['avatar_bytes_match']=True
 if ids.get('feedback_reviewed'):
  row=c.execute('SELECT reply,revision,status FROM feedback WHERE id=?',(ids['feedback_reviewed'],)).fetchone()
  assert tuple(row)==(ids['expected_reply'],ids['expected_revision'],'reviewed')
  r['feedback_reply_matches']=True
 assert r['integrity']=='ok' and r['foreign_key_violations']==0 and r['schema_version']==8
 print(json.dumps(r))
'''.replace('DATA',repr(data)).replace('IDS',repr(ids))
 return json.loads(guest([RELEASE+'/.venv/bin/python','-c',code]).stdout)

def prepare_fixture(data,out):
 import tarfile,hashlib
 from run_stage11_integration import catalog
 folder=out/'synthetic-fixture';folder.mkdir();catalog(folder)
 (folder/'server.py').write_text("from pathlib import Path\nimport uvicorn\nfrom backend.aicademiya.main import create_app\nf=Path(__file__).resolve().parent\napp=create_app(data_dir=f,catalog_path=f/'catalog.json',demo_enabled=True)\nuvicorn.run(app,host='192.168.32.55',port=18774,log_level='warning')\n")
 archive=out/'fixture.tar.gz'
 with tarfile.open(archive,'w:gz')as t:
  for p in folder.rglob('*'):
   if p.is_file():t.add(p,arcname=p.relative_to(folder).as_posix())
 incoming='/root/aicademiya-stage4-incoming/'+RELEASE.split('/')[-1]+'/'+TOKEN+'-'+out.name+'-fixture.tar.gz'
 copy=['scp','-i','C:/Users/17193/.ssh/id_ed25519_aicademiya_pve','-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes',str(archive),'root@192.168.10.16:'+incoming]
 subprocess.run(copy,check=True,capture_output=True,timeout=45)
 subprocess.run(SSH+[shlex.join(['pct','push','255',incoming,data+'/fixture.tar.gz','--perms','0600'])],check=True,capture_output=True,timeout=30)
 code="import tarfile,hashlib,subprocess;from pathlib import Path;p=Path("+repr(data+'/fixture.tar.gz')+");assert hashlib.sha256(p.read_bytes()).hexdigest()=="+repr(hashlib.sha256(archive.read_bytes()).hexdigest())+";t=tarfile.open(p);t.extractall(p.parent,filter='data');t.close();subprocess.run(['chown','-R','aicademiya:aicademiya',str(p.parent)],check=True)"
 guest(['python3','-c',code])

def main():
 OUT.mkdir(parents=True)
 report={'status':'running','release':RELEASE,'production_database_touched':False,'real_model_requests':0,'groups':[]}
 assert guest(['hostname']).stdout.strip()=='aicademiya-v2'
 before=guest(['readlink','-f','/opt/aicademiya/current']).stdout.strip();assert before!=RELEASE
 guest(['python3','-c','import socket;s=socket.socket();s.settimeout(1);assert s.connect_ex(("192.168.32.55",18774))!=0,"QA port occupied";s.close()'])
 guest(['install','-d','-m','700','-o','aicademiya','-g','aicademiya',DATA])
 commands=[('people-api',[sys.executable,'tools/stage11_api_acceptance.py']),('people-browser',[shutil.which('node'),'tools/stage11_browser_acceptance.mjs']),('avatar-api',[sys.executable,'tools/stage9_api_acceptance.py']),('avatar-browser',[shutil.which('node'),'tools/stage9_browser_acceptance.mjs']),('security',[shutil.which('node'),'tools/stage10_browser_acceptance.mjs'])]
 try:
  for group,command in commands:
   out=OUT/group;out.mkdir();data=DATA+'/'+group;unit='aicademiya-qa-stage11-'+TOKEN+'-'+group
   record={'name':group,'unit':unit,'data_dir':data,'status':'failed'}
   guest(['install','-d','-m','700','-o','aicademiya','-g','aicademiya',data])
   prepare_fixture(data,out)
   envs={'PYTHONPATH':RELEASE,'LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1','AICADEMIYA_DATA_DIR':data,'AICADEMIYA_DEMO_ENABLED':'true','AICADEMIYA_AI_MODE':'demo','AICADEMIYA_AI_PROVIDER':'','AICADEMIYA_AI_BASE_URL':'','AICADEMIYA_AI_MODEL':'','AICADEMIYA_AI_API_KEY':'','AICADEMIYA_WEB_SEARCH_ENABLED':'false','TAVILY_API_KEY':'','AICADEMIYA_ALLOWED_ORIGINS':BASE,'AICADEMIYA_COOKIE_SECURE':'false'}
   args=['systemd-run','--unit='+unit,'--collect','--uid=aicademiya','--gid=aicademiya','--working-directory='+RELEASE,'--property=UMask=0077','--property=NoNewPrivileges=true']+['--setenv='+k+'='+v for k,v in envs.items()]+[RELEASE+'/.venv/bin/python',data+'/server.py']
   try:
    guest(args);ready()
    env=os.environ.copy();
    for name in ('AICADEMIYA_QA_DB','AICADEMIYA_QA_CONTROL','AICADEMIYA_QA_METRICS','AICADEMIYA_QA_LOGIN_PASSWORD'):env.pop(name,None)
    env.update(AICADEMIYA_QA_TARGET_API='0.9.0',AICADEMIYA_QA_TARGET_SCHEMA='8',AICADEMIYA_QA_PYTHON=sys.executable,AICADEMIYA_TEST_URL=BASE,AICADEMIYA_TEST_ARTIFACT_DIR=str(out),NO_PROXY='127.0.0.1,localhost,::1,192.168.32.55',NODE_TLS_REJECT_UNAUTHORIZED='1')
    with (out/'harness.log').open('w',encoding='utf-8') as log:
     done=subprocess.run(command+['--base-url',BASE,'--confirm-test-data','--artifact-dir',str(out)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300)
    record['exit_code']=done.returncode
    if (out/'result.json').is_file():record['acceptance']=json.loads((out/'result.json').read_text(encoding='utf-8'))
    if done.returncode or record.get('acceptance',{}).get('status')!='passed':raise RuntimeError(group+' Linux QA failed: '+str(out/'harness.log'))
    ids=record['acceptance'].get('ids',{})
    if ids.get('avatar_user'):
     guest(['systemctl','restart',unit]);ready()
     with httpx.Client(base_url=BASE,trust_env=False,timeout=20) as c:
      import hashlib
      c.post('/api/auth/demo',json={'role':'student'}).raise_for_status()
      me=c.get('/api/auth/me').json()['user'];assert me['avatar_url']==ids['avatar_url']
      raw=c.get(me['avatar_url']);raw.raise_for_status();assert hashlib.sha256(raw.content).hexdigest()==ids['avatar_sha256']
      item=c.get('/api/feedback/'+ids['feedback_reviewed']);item.raise_for_status()
      assert item.json()['reply']==ids['expected_reply'] and item.json()['revision']==ids['expected_revision']
      c.post('/api/auth/demo',json={'role':'admin'}).raise_for_status()
      assert c.get('/api/admin/feedback').json()['total']==ids['feedback_total']
     record['linux_restart_avatar_feedback_verified']=True
    if 'registration_enabled' in ids:
     guest(['systemctl','restart',unit]);ready()
     with httpx.Client(base_url=BASE,trust_env=False,timeout=20) as c:
      assert c.get('/api/bootstrap').json()['registration_enabled'] is False
      c.post('/api/auth/demo',json={'role':'admin'}).raise_for_status()
      assert c.get('/api/admin/access-settings').json()['registration_enabled'] is False
     record['linux_restart_registration_verified']=True
    if ids.get('staff_user_ids'):
     guest(['systemctl','restart',unit]);ready()
     with httpx.Client(base_url=BASE,trust_env=False,timeout=20) as c:
      c.post('/api/auth/demo',json={'role':'admin'}).raise_for_status()
      st=c.get('/api/courses/'+ids['course']+'/staff').json()
      assert st['course']['owner_id']==ids['primary'] and sorted(x['user']['id'] for x in st['staff'])==ids['staff_user_ids']
      state=c.get('/api/admin/users/import/'+ids['import_id']).json();assert state['status']=='committed' and state['result']==ids['import_result']
      if ids.get('learner_answer'):
       c.post('/api/auth/demo',json={'role':'student','student_index':2}).raise_for_status()
       w=c.get('/api/sessions/'+ids['learner_session']+'/workspace',params={'version_id':ids['learner_version']}).json()
       assert w['attempts'][ids['learner_question']]['answer']==ids['learner_answer']
     record['linux_restart_staff_import_work_verified']=True
    record['sqlite']=database_probe(data,ids)
    record['status']='passed'
   finally:
    guest(['systemctl','stop',unit],check=False)
    record['qa_service_stopped']=guest(['systemctl','is-active',unit],check=False).stdout.strip() not in ('active','activating','deactivating')
    if not record['qa_service_stopped']:record['status']='failed'
    (out/'server.log').write_text(guest(['journalctl','-u',unit,'--no-pager','-n','350'],check=False).stdout,encoding='utf-8')
    report['groups'].append(record);(OUT/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'group':group,'status':record['status'],'checks':len(record.get('acceptance',{}).get('checks',[])),'stopped':record['qa_service_stopped']}),flush=True)
  report['status']='passed' if all(g['status']=='passed' for g in report['groups']) else 'failed'
 except Exception as exc:report['error']=str(exc);report['status']='failed'
 finally:
  report['production_service_active']=guest(['systemctl','is-active','aicademiya.service']).stdout.strip()=='active'
  report['production_link_unchanged']=guest(['readlink','-f','/opt/aicademiya/current']).stdout.strip()==before
  with socket.socket() as s:s.settimeout(2);report['qa_listener_closed']=s.connect_ex(('192.168.32.55',18774))!=0
  if not all(report[k] for k in ('production_service_active','production_link_unchanged','qa_listener_closed')):report['status']='failed'
  (OUT/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
  print(json.dumps({'status':report['status'],'result':str(OUT/'result.json'),'error':report.get('error'),'production_link_unchanged':report['production_link_unchanged']}),flush=True)
 if report['status']!='passed':raise SystemExit(1)
if __name__=='__main__':main()
