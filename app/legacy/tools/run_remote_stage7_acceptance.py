"""Stage7 Linux/LAN API, CPU OCR, Chrome/Edge acceptance on a fresh CT255 QA root."""
from pathlib import Path
import json,os,shlex,shutil,socket,subprocess,sys,time,uuid
import httpx
ROOT=Path(__file__).resolve().parents[1]
RELEASE='/opt/aicademiya/releases/AIcademiya_V2-20261008-clarity'
TOKEN=uuid.uuid4().hex[:10]
OUT=ROOT/'artifacts/stage7'/('ct255-qa-'+TOKEN)
DATA='/var/lib/aicademiya-qa/stage7-'+TOKEN
BASE='http://192.168.32.55:18774'
FIXTURES=ROOT/'artifacts/stage6/integration-20261007T151825Z-322f7b25/fixtures'
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
     assert c.get(BASE+'/openapi.json').json()['info']['version']=='0.6.0'
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
 mids=ids.get('abcde',[])
 if mids:
  rows=c.execute('SELECT id,session_id,file_path FROM materials WHERE id IN ('+','.join('?' for _ in mids)+')',mids).fetchall()
  r['abcde']={'rows':len(rows),'original_files':len({v['file_path'] for v in rows}),'files_retained':all(Path(v['file_path']).is_file() for v in rows),'b_origin_preserved':next(v for v in rows if v['id']==ids['b'])['session_id']==ids['s1']}
  assert r['abcde']['rows']==r['abcde']['original_files']==5 and r['abcde']['files_retained'] and r['abcde']['b_origin_preserved']
 r['teacher_preview_rows']=c.execute('SELECT count(*) FROM teacher_previews').fetchone()[0]
 assert r['teacher_preview_rows']>0
 assert r['integrity']=='ok' and r['foreign_key_violations']==0 and r['schema_version']==5
 print(json.dumps(r))
'''.replace('DATA',repr(data)).replace('IDS',repr(ids))
 return json.loads(guest([RELEASE+'/.venv/bin/python','-c',code]).stdout)

def main():
 OUT.mkdir(parents=True)
 report={'status':'running','release':RELEASE,'production_database_touched':False,'real_model_requests':0,'groups':[]}
 assert guest(['hostname']).stdout.strip()=='aicademiya-v2'
 before=guest(['readlink','-f','/opt/aicademiya/current']).stdout.strip();assert before!=RELEASE
 guest(['python3','-c','import socket;s=socket.socket();s.settimeout(1);assert s.connect_ex(("192.168.32.55",18774))!=0,"QA port occupied";s.close()'])
 guest(['install','-d','-m','700','-o','aicademiya','-g','aicademiya',DATA])
 commands=[('api',[sys.executable,'tools/stage7_api_acceptance.py']),('browser',[shutil.which('node'),'tools/stage7_browser_acceptance.mjs'])]
 try:
  for group,command in commands:
   out=OUT/group;out.mkdir();data=DATA+'/'+group;unit='aicademiya-qa-stage7-'+TOKEN+'-'+group
   record={'name':group,'unit':unit,'data_dir':data,'status':'failed'}
   guest(['install','-d','-m','700','-o','aicademiya','-g','aicademiya',data])
   envs={'LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1','AICADEMIYA_DATA_DIR':data,'AICADEMIYA_DEMO_ENABLED':'true','AICADEMIYA_AI_MODE':'demo','AICADEMIYA_AI_PROVIDER':'','AICADEMIYA_AI_BASE_URL':'','AICADEMIYA_AI_MODEL':'','AICADEMIYA_AI_API_KEY':'','AICADEMIYA_WEB_SEARCH_ENABLED':'false','TAVILY_API_KEY':'','AICADEMIYA_ALLOWED_ORIGINS':BASE,'AICADEMIYA_COOKIE_SECURE':'false'}
   args=['systemd-run','--unit='+unit,'--collect','--uid=aicademiya','--gid=aicademiya','--working-directory='+RELEASE,'--property=UMask=0077','--property=NoNewPrivileges=true']+['--setenv='+k+'='+v for k,v in envs.items()]+[RELEASE+'/.venv/bin/python','-m','uvicorn','backend.aicademiya.main:app','--host','192.168.32.55','--port','18774','--workers','1']
   try:
    guest(args);ready()
    env=os.environ.copy();
    for name in ('AICADEMIYA_QA_DB','AICADEMIYA_QA_CONTROL','AICADEMIYA_QA_METRICS','AICADEMIYA_QA_LOGIN_PASSWORD'):env.pop(name,None)
    env.update(AICADEMIYA_TEST_URL=BASE,AICADEMIYA_TEST_ARTIFACT_DIR=str(out),NO_PROXY='127.0.0.1,localhost,::1,192.168.32.55',NODE_TLS_REJECT_UNAUTHORIZED='1')
    with (out/'harness.log').open('w',encoding='utf-8') as log:
     done=subprocess.run(command+['--base-url',BASE,'--confirm-test-data','--artifact-dir',str(out),'--fixture-dir',str(FIXTURES)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=900)
    record['exit_code']=done.returncode
    if (out/'result.json').is_file():record['acceptance']=json.loads((out/'result.json').read_text(encoding='utf-8'))
    if done.returncode or record.get('acceptance',{}).get('status')!='passed':raise RuntimeError(group+' Linux QA failed: '+str(out/'harness.log'))
    ids=record['acceptance'].get('ids',{})
    if ids.get('expected_final'):
     guest(['systemctl','restart',unit]);ready()
     with httpx.Client(base_url=BASE,trust_env=False,timeout=20) as c:
      c.post('/api/auth/demo',json={'role':'teacher'}).raise_for_status()
      for sid,mids in ids['expected_final'].items():
       response=c.get('/api/sessions/'+sid);response.raise_for_status()
       assert sorted(m['id'] for m in response.json()['materials'])==sorted(mids)
     record['restart_memberships_preserved']=True
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
