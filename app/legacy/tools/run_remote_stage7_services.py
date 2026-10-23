"""One real model + one real Tavily service check in staged CT255 isolated data, never production settings."""
from pathlib import Path
import argparse,json,os,shlex,subprocess,sys,time,uuid
import httpx
ROOT=Path(__file__).resolve().parents[1]
SSH=['ssh','-i','C:/Users/17193/.ssh/id_ed25519_aicademiya_pve','-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8','root@192.168.10.16']
def guest(args,check=True,input=None,timeout=45):
 r=subprocess.run(SSH+[shlex.join(['pct','exec','255','--']+args)],input=input,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout)
 if check and r.returncode:raise RuntimeError(r.stderr or r.stdout)
 return r

def main():
 p=argparse.ArgumentParser();p.add_argument('--release',required=True);a=p.parse_args();release=a.release
 assert release.startswith('/opt/aicademiya/releases/AIcademiya_V2-') and '..' not in release
 token=uuid.uuid4().hex[:10];out=ROOT/'artifacts/stage7'/('ct255-live-services-'+token);out.mkdir(parents=True)
 data='/var/lib/aicademiya-qa/stage7-live-services-'+token;unit='aicademiya-qa-stage7-services-'+token;base='http://192.168.32.55:18774'
 report={'status':'failed','release':release,'data_dir':data,'base_url':base,'production_settings_changed':False,'model_services_changed':False,'checks':[]}
 before=guest(['readlink','-f','/opt/aicademiya/current']).stdout.strip();assert before!=release
 started=False
 try:
  with httpx.Client(trust_env=False,timeout=10) as c:h=c.get('http://192.168.32.5:18280/health').json()
  assert h.get('model')=='AIcademiya-64kx3-Qwen3.8-27B' and h['queue']==0 and all(w['healthy'] and not w['busy'] for w in h['workers']),'No idle healthy model window'
  report['idle_health']={'model':h['model'],'queue':h['queue'],'workers':[{'name':w['name'],'healthy':w['healthy'],'busy':w['busy']} for w in h['workers']]}
  guest(['python3','-c','import socket;s=socket.socket();s.settimeout(1);assert s.connect_ex(("192.168.32.55",18774))!=0;s.close()'])
  guest(['install','-d','-m','700','-o','aicademiya','-g','aicademiya',data])
  server="""from pathlib import Path
import json,os,sys
root=Path(os.environ['AICADEMIYA_DATA_DIR']);release=Path(sys.argv[1]);sys.path.insert(0,str(release))
catalog=root/'catalog.json';catalog.write_text(json.dumps({'schema_version':1,'course':{'id':'synthetic-stage7-services','code':'S7-LIVE','title':'Synthetic services check','description':'No real curriculum or learner data'},'sessions':[]}))
from backend.aicademiya.main import create_app
import uvicorn
app=create_app(data_dir=root,catalog_path=catalog,demo_enabled=True)
uvicorn.run(app,host='192.168.32.55',port=18774,log_level='warning')
"""
  guest(['python3','-c',f'from pathlib import Path;p=Path({(data+"/server.py")!r});p.write_text({server!r});p.chmod(0o640)'])
  guest(['chown','aicademiya:aicademiya',data+'/server.py'])
  command='set -a; . /etc/aicademiya/aicademiya.conf; export AICADEMIYA_DATA_DIR='+shlex.quote(data)+' AICADEMIYA_DEMO_ENABLED=true AICADEMIYA_ALLOWED_ORIGINS='+shlex.quote(base)+' PYTHONDONTWRITEBYTECODE=1; exec '+shlex.quote(release+'/.venv/bin/python')+' '+shlex.quote(data+'/server.py')+' '+shlex.quote(release)
  guest(['systemd-run','--unit='+unit,'--collect','--uid=aicademiya','--gid=aicademiya','--working-directory='+release,'--property=UMask=0077','--property=NoNewPrivileges=true','/bin/bash','-c',command]);started=True
  with httpx.Client(base_url=base,trust_env=False,timeout=620) as c:
   deadline=time.monotonic()+40
   while time.monotonic()<deadline:
    try:
     if c.get('/api/health',timeout=2).status_code==200:break
    except httpx.RequestError:pass
    time.sleep(.2)
   else:raise RuntimeError('Owned staged service did not start')
   assert c.get('/openapi.json').json()['info']['version']=='0.6.0'
   assert c.post('/api/auth/demo',json={'role':'admin'}).status_code==200
   settings=c.get('/api/teacher/settings').json();assert settings['ai']['mode']=='openai' and settings['ai']['model']==h['model'] and settings['ai']['base_url']=='http://127.0.0.1:18280/v1'
   assert settings['ai']['connection']['status']=='not_checked';t=time.monotonic();r=c.post('/api/teacher/settings/test');result=r.json()
   report['model_check']={'http_status':r.status_code,'seconds':round(time.monotonic()-t,3),'result':result};assert r.status_code==200 and result['ok']
   read=c.get('/api/teacher/settings').json();assert read['ai']['connection']==result['connection'];report['checks'].append('Real staged app through CT255 loopback router returns and persists model check')
   search=c.get('/api/teacher/search-settings').json();report['search_initial']={k:search[k] for k in ('enabled','configured','api_key_source')}
   assert search['configured'],'No existing server-side Tavily key; no credential is guessed'
   if not search['enabled']:assert c.put('/api/teacher/search-settings',json={'enabled':True}).status_code==200
   t=time.monotonic();r=c.post('/api/teacher/search-settings/test');result=r.json();report['search_check']={'http_status':r.status_code,'seconds':round(time.monotonic()-t,3),'result':result}
   assert r.status_code==200 and result['ok'];read=c.get('/api/teacher/search-settings').json();assert read['connection']==result['connection'];report['checks'].append('One actual Tavily basic public query returns and persists saved-config status')
   # Only status projections are written to this report; never raw credentials.
   report['bounded_application_calls']={'model_tests':1,'search_tests':1}
   expected_model=c.get('/api/teacher/settings').json()['ai']['connection'];expected_search=read['connection']
   guest(['systemctl','restart',unit]);deadline=time.monotonic()+40
   while time.monotonic()<deadline:
    try:
     if c.get('/api/health',timeout=2).status_code==200:break
    except httpx.RequestError:pass
    time.sleep(.2)
   else:raise RuntimeError('Owned QA restart did not become ready')
   assert c.get('/api/teacher/settings').json()['ai']['connection']==expected_model
   assert c.get('/api/teacher/search-settings').json()['connection']==expected_search
   report['checks'].append('Actual Linux process restart preserves both real check timestamps without another probe')
   dbprobe='import sqlite3,json; c=sqlite3.connect('+repr(data+'/aicademiya.sqlite3')+');print(json.dumps({"integrity":c.execute("PRAGMA integrity_check").fetchone()[0],"schema":c.execute("PRAGMA user_version").fetchone()[0],"fk":len(c.execute("PRAGMA foreign_key_check").fetchall())}))'
   report['sqlite']=json.loads(guest([release+'/.venv/bin/python','-c',dbprobe]).stdout)
   assert report['sqlite']=={'integrity':'ok','schema':5,'fk':0}
   report['status']='passed'
 except Exception as e:report['error']=str(e)
 finally:
  if started:guest(['systemctl','stop',unit],check=False)
  report['owned_qa_service_stopped']=guest(['systemctl','is-active',unit],check=False).stdout.strip() not in ('active','activating','deactivating')
  report['production_link_unchanged']=guest(['readlink','-f','/opt/aicademiya/current']).stdout.strip()==before
  report['production_active']=guest(['systemctl','is-active','aicademiya.service']).stdout.strip()=='active'
  if not all(report[k] for k in ('owned_qa_service_stopped','production_link_unchanged','production_active')):report['status']='failed'
  (out/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'status':report['status'],'result':str(out/'result.json'),'error':report.get('error'),'stopped':report['owned_qa_service_stopped']}))
 return 0 if report['status']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
