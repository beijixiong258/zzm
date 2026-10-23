"""Stage10 real browser and persistent access-control acceptance, synthetic data only."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, json, os, subprocess, sys, uuid
import httpx
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from run_stage4_integration import free_port, ready, stop, listener_closed
from run_stage9_integration import serve, evidence

def main():
 p=argparse.ArgumentParser();p.add_argument('--serve',type=int);p.add_argument('--folder');a=p.parse_args()
 if a.serve:
  folder=Path(a.folder).resolve();assert folder.is_relative_to(ROOT/'artifacts/stage10') and (folder/'catalog.json').is_file();serve(a.serve,folder);return 0
 assert datetime.now().isoformat()<'2026-10-08T13:20:00','Do not start a new acceptance run beyond safe deadline margin'
 index=ROOT/'frontend/dist/index.html';newest=max(f.stat().st_mtime for n in ('src','public') for f in (ROOT/'frontend'/n).rglob('*') if f.is_file());assert index.is_file()and index.stat().st_mtime>=newest,'Build current frontend/dist first'
 out=ROOT/'artifacts/stage10'/('integration-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]);out.mkdir(parents=True);(out/'data').mkdir();(out/'catalog.json').write_text(json.dumps({'schema_version':1,'course':{'id':'synthetic-baseline','code':'BASE','title':'Synthetic baseline','description':'No real curriculum'},'sessions':[]}),encoding='utf-8')
 env=os.environ.copy();scratch=os.environ['TMPDIR'];env.update(TMPDIR=scratch,TEMP=scratch,TMP=scratch,AICADEMIYA_DATA_DIR=str(out/'data'),AICADEMIYA_DEMO_ENABLED='true',AICADEMIYA_AI_MODE='demo',AICADEMIYA_AI_PROVIDER='',AICADEMIYA_AI_BASE_URL='',AICADEMIYA_AI_MODEL='',AICADEMIYA_AI_API_KEY='',AICADEMIYA_WEB_SEARCH_ENABLED='false',TAVILY_API_KEY='',AICADEMIYA_COOKIE_SECURE='false',AICADEMIYA_ALLOWED_ORIGINS='',NO_PROXY='127.0.0.1,localhost,::1',no_proxy='127.0.0.1,localhost,::1')
 for n in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'):env.pop(n,None)
 port=free_port();base=f'http://127.0.0.1:{port}';r={'status':'failed','synthetic_only':True,'real_model_or_search_calls':0};proc=None;log=(out/'server.log').open('w',encoding='utf-8')
 def start():
  process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--serve',str(port),'--folder',str(out)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT);ready(process,base);return process
 try:
  proc=start();done=subprocess.run(['node','tools/stage10_browser_acceptance.mjs','--base-url',base,'--artifact-dir',str(out/'browser'),'--confirm-test-data'],cwd=ROOT,env=env,capture_output=True,text=True,timeout=240)
  (out/'harness.log').write_text(done.stdout+'\n'+done.stderr,encoding='utf-8');r['browser']=json.loads((out/'browser/result.json').read_text());assert done.returncode==0 and r['browser']['status']=='passed',done.stdout+done.stderr
  metrics=json.loads((out/'provider-metrics.json').read_text());assert metrics['model_calls']==metrics['search_calls']==metrics['model_protocol_calls']==metrics['search_protocol_calls']==0;r['provider_metrics']=metrics
  stop(proc);assert listener_closed(port);proc=start()
  with httpx.Client(base_url=base,trust_env=False)as c:
   assert c.get('/api/bootstrap').json()['registration_enabled']is False
   assert c.post('/api/auth/demo',json={'role':'admin'}).status_code==200
   assert c.get('/api/admin/access-settings').json()['registration_enabled']is False
  r['real_restart_registration_persists']=True;r['status']='passed'
 except Exception as e:r['error']=str(e)
 finally:
  if proc:stop(proc)
  log.close();r['owned_server_stopped']=bool(proc and proc.poll()is not None);r['owned_listener_closed']=listener_closed(port)
  if not r['owned_server_stopped']or not r['owned_listener_closed']:r['status']='failed'
  try:r['sqlite']=evidence(out)
  except Exception as e:r['sqlite_error']=str(e);r['status']='failed'
  (out/'result.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8');print(json.dumps({'status':r['status'],'error':r.get('error'),'checks':len(r.get('browser',{}).get('checks',[])),'result':str(out/'result.json')}))
 return 0 if r['status']=='passed'else 1
if __name__=='__main__':raise SystemExit(main())
