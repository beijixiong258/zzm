"""Actual Linux/HTTP/Chrome QA of the staged release, without production cutover."""
from pathlib import Path
import json,os,shlex,shutil,subprocess,sys,time,uuid
import httpx
ROOT=Path(__file__).resolve().parents[1]
RELEASE='/opt/aicademiya/releases/AIcademiya_V2-20261007-guided'
TOKEN=uuid.uuid4().hex[:10]
OUT=ROOT/'artifacts/stage3'/('ct255-qa-'+TOKEN)
DATA='/var/lib/aicademiya-qa/stage3-'+TOKEN
BASE='http://192.168.32.55:18774'
SSH=['ssh','-i','C:/Users/17193/.ssh/id_ed25519_aicademiya_pve','-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8','root@192.168.10.16']
def guest(args,check=True,timeout=40):
 r=subprocess.run(SSH+[shlex.join(['pct','exec','255','--']+args)],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout)
 if check and r.returncode:raise RuntimeError(r.stderr or r.stdout)
 return r

def main():
 OUT.mkdir(parents=True)
 report={'status':'running','release':RELEASE,'production_database_touched':False,'real_model_requests':0,'groups':[]}
 before=guest(['readlink','-f','/opt/aicademiya/current']).stdout.strip()
 guest(['python3','-c','import socket;s=socket.socket();s.settimeout(1);assert s.connect_ex(("192.168.32.55",18774))!=0,"QA port already occupied";s.close()'])
 guest(['install','-d','-m','700','-o','aicademiya','-g','aicademiya',DATA])
 commands=[('api',[sys.executable,'tools/stage3_api_acceptance.py']),('browser',[shutil.which('node'),'tools/stage3_browser_acceptance.mjs'])]
 try:
  for group,command in commands:
   out=OUT/group;out.mkdir();data=DATA+'/'+group;unit='aicademiya-qa-stage3-'+TOKEN+'-'+group
   record={'name':group,'unit':unit,'data_dir':data,'status':'failed'}
   guest(['install','-d','-m','700','-o','aicademiya','-g','aicademiya',data])
   envs={'LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1','AICADEMIYA_DATA_DIR':data,'AICADEMIYA_DEMO_ENABLED':'true','AICADEMIYA_AI_MODE':'demo','AICADEMIYA_AI_PROVIDER':'','AICADEMIYA_AI_BASE_URL':'','AICADEMIYA_AI_MODEL':'','AICADEMIYA_AI_API_KEY':'','AICADEMIYA_WEB_SEARCH_ENABLED':'false','TAVILY_API_KEY':'','AICADEMIYA_ALLOWED_ORIGINS':BASE,'AICADEMIYA_COOKIE_SECURE':'false'}
   args=['systemd-run','--unit='+unit,'--collect','--uid=aicademiya','--gid=aicademiya','--working-directory='+RELEASE,'--property=UMask=0077','--property=NoNewPrivileges=true']+['--setenv='+k+'='+v for k,v in envs.items()]+[RELEASE+'/.venv/bin/python','-m','uvicorn','backend.aicademiya.main:app','--host','192.168.32.55','--port','18774','--workers','1']
   try:
    guest(args)
    with httpx.Client(trust_env=False,timeout=2) as c:
     deadline=time.monotonic()+40
     while time.monotonic()<deadline:
      try:
       if c.get(BASE+'/api/health').status_code==200:break
      except httpx.RequestError:pass
      time.sleep(.2)
     else:raise RuntimeError('Linux QA service readiness timed out')
     b=c.get(BASE+'/api/bootstrap').json();assert b['demo_enabled'] and b['ai']['mode']=='demo'
    env=os.environ.copy();env.update(AICADEMIYA_TEST_URL=BASE,AICADEMIYA_TEST_ARTIFACT_DIR=str(out),NO_PROXY='127.0.0.1,localhost,::1',NODE_TLS_REJECT_UNAUTHORIZED='1')
    with (out/'harness.log').open('w',encoding='utf-8') as log:
     done=subprocess.run(command+['--base-url',BASE,'--confirm-test-data','--artifact-dir',str(out)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=600)
    record['exit_code']=done.returncode
    if (out/'result.json').exists():record['acceptance']=json.loads((out/'result.json').read_text(encoding='utf-8'))
    if done.returncode:raise RuntimeError(group+' Linux acceptance failed; inspect '+str(out/'harness.log'))
    record['status']='passed'
   finally:
    guest(['systemctl','stop',unit],check=False)
    record['qa_service_stopped']=guest(['systemctl','is-active',unit],check=False).stdout.strip() not in ('active','activating','deactivating')
    (out/'server.log').write_text(guest(['journalctl','-u',unit,'--no-pager','-n','400'],check=False).stdout,encoding='utf-8')
    report['groups'].append(record);(OUT/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'group':group,'status':record['status'],'checks':len(record.get('acceptance',{}).get('checks',[])),'stopped':record['qa_service_stopped']}),flush=True)
  report['status']='passed'
 except Exception as e:report['error']=str(e);report['status']='failed'
 finally:
  report['production_service_active']=guest(['systemctl','is-active','aicademiya.service']).stdout.strip()=='active'
  report['production_link_unchanged']=guest(['readlink','-f','/opt/aicademiya/current']).stdout.strip()==before
  (OUT/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
  print(json.dumps({'status':report['status'],'result':str(OUT/'result.json'),'error':report.get('error'),'production_link_unchanged':report['production_link_unchanged']}),flush=True)
 if report['status']!='passed':raise SystemExit(1)
if __name__=='__main__':main()
