"""Brand-only staged readback: isolated Linux, exact static files, anonymous UI."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,time,uuid
import httpx
from stage4_stage_release import guest
ROOT=Path(__file__).resolve().parents[1]
RELEASE='AIcademiya_V2-20261007-logo-v4';TARGET='/opt/aicademiya/releases/'+RELEASE
OUT=ROOT/'artifacts/stage5/release-logo-v4';BASE='http://192.168.32.55:18774'
def main():
 token=uuid.uuid4().hex[:10];unit='aicademiya-qa-logo-v4-'+token;data='/var/lib/aicademiya-qa/logo-v4-'+token
 m=json.loads((OUT/(RELEASE+'.manifest.json')).read_text());before=guest(['readlink','-f','/opt/aicademiya/current'])
 assert before!=TARGET and guest(['systemctl','is-active','aicademiya.service'])=='active'
 guest(['python3','-c','import socket;s=socket.socket();assert s.connect_ex(("192.168.32.55",18774))!=0;s.close()'])
 guest(['install','-d','-m','700','-o','aicademiya','-g','aicademiya',data])
 env={'AICADEMIYA_DATA_DIR':data,'AICADEMIYA_DEMO_ENABLED':'false','AICADEMIYA_AI_MODE':'demo','AICADEMIYA_AI_PROVIDER':'','AICADEMIYA_AI_BASE_URL':'','AICADEMIYA_AI_MODEL':'','AICADEMIYA_AI_API_KEY':'','AICADEMIYA_WEB_SEARCH_ENABLED':'false','TAVILY_API_KEY':'','PYTHONDONTWRITEBYTECODE':'1','AICADEMIYA_COOKIE_SECURE':'false'}
 report={'status':'running','release':TARGET,'scope':'brand-only unchanged backend, anonymous readback','model_calls':0,'groups':[]}
 try:
  args=['systemd-run','--unit='+unit,'--collect','--uid=aicademiya','--gid=aicademiya','--working-directory='+TARGET,'--property=UMask=0077','--property=NoNewPrivileges=true']+['--setenv='+k+'='+v for k,v in env.items()]+[TARGET+'/.venv/bin/python','-m','uvicorn','backend.aicademiya.main:app','--host','192.168.32.55','--port','18774','--workers','1']
  guest(args)
  with httpx.Client(base_url=BASE,trust_env=False,timeout=3) as c:
   until=time.monotonic()+35
   while time.monotonic()<until:
    try:
     if c.get('/api/health').status_code==200:break
    except httpx.RequestError:pass
    time.sleep(.2)
   else:raise RuntimeError('QA readiness failed')
   boot=c.get('/api/bootstrap').json();assert not boot['demo_enabled'] and boot['ai']['mode']=='demo'
   assert c.get('/api/courses').status_code==401
   checked=[]
   for name,info in m['files'].items():
    if not name.startswith('frontend/dist/'):continue
    url='/'+name.removeprefix('frontend/dist/');response=c.get(url)
    assert response.status_code==200 and hashlib.sha256(response.content).hexdigest()==info['sha256'],url
    checked.append(url)
  browser_out=OUT/'staged-browser';process_env=os.environ.copy();process_env.update(AICADEMIYA_BRAND_URL=BASE,AICADEMIYA_BRAND_OUT=str(browser_out))
  subprocess.run(['node','frontend/tools/stage5-brand-readback.mjs'],cwd=ROOT,env=process_env,check=True,timeout=75)
  browser=json.loads((browser_out/'browser-readback.json').read_text());assert browser['status']=='passed'
  report.update(status='passed',static_files_verified=checked,browser=browser)
 finally:
  try:guest(['systemctl','stop',unit])
  except RuntimeError:pass
  stopped=guest(['python3','-c',f'import subprocess;print(subprocess.run(["systemctl","is-active",{unit!r}],capture_output=True,text=True).stdout.strip())']) not in ('active','activating','deactivating')
  report['groups']=[{'name':'brand_readback','qa_service_stopped':stopped}]
  report['production_link_unchanged']=guest(['readlink','-f','/opt/aicademiya/current'])==before
  report['production_service_active']=guest(['systemctl','is-active','aicademiya.service'])=='active'
  if not(stopped and report['production_link_unchanged'] and report['production_service_active']):report['status']='failed'
  (OUT/'qa-result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
 assert report['status']=='passed'
 print(json.dumps({'status':'passed','static_files':len(report['static_files_verified']),'qa_service_stopped':stopped,'production_changed':False,'report':str(OUT/'qa-result.json')}))
if __name__=='__main__':main()
