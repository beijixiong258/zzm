"""Stage8 actual built UI/HTTP/SQLite lifecycle acceptance. Synthetic data; no real model/search."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,os,shutil,socket,sqlite3,subprocess,sys,time,uuid
import httpx
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from run_stage4_integration import free_port,ready,stop,listener_closed
from stage7_qa_helpers import ProtocolFixtures

def serve(port,folder):
 import uvicorn
 sys.path.insert(0,str(ROOT))
 from backend.aicademiya.main import create_app
 fixture=ProtocolFixtures(folder/'provider-metrics.json')
 app=create_app(data_dir=folder/'data',catalog_path=folder/'catalog.json',demo_enabled=True,ai_transport=httpx.MockTransport(fixture.model))
 fixture.instrument(app)
 uvicorn.run(app,host='127.0.0.1',port=port,log_level='warning')

def evidence(folder):
 with sqlite3.connect(folder/'data/aicademiya.sqlite3') as c:
  tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
  report={'integrity':c.execute('PRAGMA integrity_check').fetchone()[0],'schema':c.execute('PRAGMA user_version').fetchone()[0],'fk_violations':len(c.execute('PRAGMA foreign_key_check').fetchall()),'table_counts':{t:c.execute('SELECT count(*) FROM "'+t+'"').fetchone()[0] for t in tables}}
  assert report['integrity']=='ok' and report['schema']==int(os.environ.get('AICADEMIYA_QA_TARGET_SCHEMA','6')) and report['fk_violations']==0
 return report

def main():
 p=argparse.ArgumentParser();p.add_argument('--serve',type=int);p.add_argument('--folder');p.add_argument('--skip-browser',action='store_true');p.add_argument('--skip-api',action='store_true');a=p.parse_args()
 if a.serve:
  folder=Path(a.folder).resolve();assert folder.is_relative_to(ROOT/'artifacts/stage8') and (folder/'catalog.json').is_file();serve(a.serve,folder);return 0
 assert not(a.skip_browser and a.skip_api)
 index=ROOT/'frontend/dist/index.html'
 if not a.skip_browser:
  newest=max(f.stat().st_mtime for name in ('src','public') for f in (ROOT/'frontend'/name).rglob('*') if f.is_file());assert index.is_file() and index.stat().st_mtime>=newest,'Build current frontend/dist first; no stale build accepted'
 out=ROOT/'artifacts/stage8'/('integration-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]);out.mkdir(parents=True)
 env=os.environ.copy();scratch=os.environ['TMPDIR'];env.update(TMPDIR=scratch,TEMP=scratch,TMP=scratch,AICADEMIYA_DEMO_ENABLED='true',AICADEMIYA_AI_MODE='demo',AICADEMIYA_AI_PROVIDER='',AICADEMIYA_AI_BASE_URL='',AICADEMIYA_AI_MODEL='',AICADEMIYA_AI_API_KEY='',AICADEMIYA_WEB_SEARCH_ENABLED='false',TAVILY_API_KEY='',AICADEMIYA_COOKIE_SECURE='false',NO_PROXY='127.0.0.1,localhost,::1',no_proxy='127.0.0.1,localhost,::1')
 for name in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'):env.pop(name,None)
 groups=[]
 for name,command in [('api',[sys.executable,'tools/stage8_api_acceptance.py']),('browser',['node','tools/stage8_browser_acceptance.mjs'])]:
  if (name=='api' and a.skip_api)or(name=='browser'and a.skip_browser):continue
  folder=out/name;folder.mkdir();(folder/'data').mkdir();(folder/'catalog.json').write_text(json.dumps({'schema_version':1,'course':{'id':'synthetic-baseline','code':'BASE','title':'Synthetic baseline','description':'No real curriculum'},'sessions':[]}),encoding='utf-8')
  port=free_port();base=f'http://127.0.0.1:{port}';e=env.copy();e.update(AICADEMIYA_DATA_DIR=str(folder/'data'),AICADEMIYA_QA_DB=str(folder/'data/aicademiya.sqlite3'),AICADEMIYA_QA_CONTROL='true',AICADEMIYA_QA_PYTHON=sys.executable)
  rec={'name':name,'status':'failed'};proc=None;log=(folder/'server.log').open('w',encoding='utf-8')
  try:
   proc=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--serve',str(port),'--folder',str(folder)],cwd=ROOT,env=e,stdout=log,stderr=subprocess.STDOUT);ready(proc,base)
   done=subprocess.run(command+['--base-url',base,'--artifact-dir',str(folder),'--confirm-test-data'],cwd=ROOT,env=e,capture_output=True,text=True,timeout=600)
   (folder/'harness.log').write_text(done.stdout+'\n'+done.stderr,encoding='utf-8');rec['acceptance']=json.loads((folder/'result.json').read_text());assert done.returncode==0 and rec['acceptance']['status']=='passed',done.stdout+done.stderr
   metrics=json.loads((folder/'provider-metrics.json').read_text());assert metrics['model_calls']==metrics['search_calls']==metrics['model_protocol_calls']==metrics['search_protocol_calls']==0;rec['provider_metrics']=metrics
   if name=='api':
    ids=rec['acceptance']['ids'];stop(proc);assert listener_closed(port);proc=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--serve',str(port),'--folder',str(folder)],cwd=ROOT,env=e,stdout=log,stderr=subprocess.STDOUT);ready(proc,base)
    with httpx.Client(base_url=base,trust_env=False) as c:
     assert c.post('/api/auth/demo',json={'role':'teacher'}).status_code==200
     detail=c.get('/api/courses/'+ids['target_course']).json();assert detail['trashed_at']==ids['final_trashed_at']
     assert any(row['id']==ids['target_course'] for row in c.get('/api/courses/trash').json()['courses'])
     assert c.post('/api/courses/'+ids['target_course']+'/restore',json={}).status_code==200
     assert c.get('/api/courses/'+ids['target_course']).json()['trashed_at'] is None
     assert c.get('/api/courses/'+ids['target_course']+'/sessions').status_code==200
    rec['real_process_restart_preserves_trash_and_restore']=True
   rec['status']='passed'
  except Exception as exc:rec['error']=str(exc)
  finally:
   if proc:stop(proc)
   log.close();rec['owned_server_stopped']=bool(proc and proc.poll() is not None);rec['owned_listener_closed']=listener_closed(port)
   if not rec['owned_server_stopped']or not rec['owned_listener_closed']:rec['status']='failed'
   try:rec['sqlite']=evidence(folder)
   except Exception as ex:rec['sqlite_error']=str(ex);rec['status']='failed'
   groups.append(rec);(out/'result.json').write_text(json.dumps({'status':'running','groups':groups},indent=2),encoding='utf-8')
   print(json.dumps({'group':name,'status':rec['status'],'checks':len(rec.get('acceptance',{}).get('checks',[])),'error':rec.get('error')},ensure_ascii=False),flush=True)
 result={'status':'passed'if all(g['status']=='passed'for g in groups)else'failed','final_acceptance':not a.skip_api and not a.skip_browser and all(g['status']=='passed'for g in groups),'groups':groups,'checked':sum(len(g.get('acceptance',{}).get('checks',[]))for g in groups),'synthetic_only':True,'production_data_changed':False,'real_model_or_search_calls':0}
 (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'status':result['status'],'final_acceptance':result['final_acceptance'],'result':str(out/'result.json')}));return 0 if result['status']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
