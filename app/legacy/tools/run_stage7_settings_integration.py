"""Stage7 settings integration: actual built UI/HTTP/SQLite, provider transports are explicit protocol fixtures."""
from pathlib import Path
from datetime import datetime, timezone
import argparse,json,os,subprocess,sys,uuid,sqlite3
import httpx
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from run_stage4_integration import free_port,ready,stop,listener_closed

def serve(port,out):
 import uvicorn
 sys.path.insert(0,str(ROOT))
 from backend.aicademiya.main import create_app
 counts={'model_protocol_calls':0,'search_protocol_calls':0,'external_model_calls':0,'external_search_calls':0}
 def persist(): (out/'provider-metrics.json').write_text(json.dumps(counts,indent=2),encoding='utf-8')
 def model(request):
  assert request.url.host=='127.0.0.1' and request.url.port==9
  body=json.loads(request.content);assert body['max_tokens']==32
  counts['model_protocol_calls']+=1;persist()
  if body['model']=='synthetic-fail': return httpx.Response(503,json={'error':'explicit synthetic provider failure'})
  return httpx.Response(200,json={'choices':[{'message':{'role':'assistant','content':'OK — explicit protocol fixture, not a model'}}]})
 def search(request):
  assert str(request.url)=='https://api.tavily.com/search'
  body=json.loads(request.content);assert body['search_depth']=='basic' and body['max_results']==5 and body['auto_parameters'] is False
  assert body['query']=='public education formative assessment research'
  counts['search_protocol_calls']+=1;persist()
  return httpx.Response(200,json={'results':[{'title':'Explicit synthetic search fixture','url':'https://example.invalid/synthetic','content':'Synthetic public-topic excerpt; not an actual web result.'}], 'usage':{'credits':0}})
 app=create_app(data_dir=out/'data',catalog_path=out/'catalog.json',demo_enabled=True,ai_transport=httpx.MockTransport(model))
 app.state.tutor.search.transport=httpx.MockTransport(search)
 persist();uvicorn.run(app,host='127.0.0.1',port=port,log_level='warning')

def main():
 p=argparse.ArgumentParser();p.add_argument('--serve',type=int);p.add_argument('--out');a=p.parse_args()
 if a.serve:serve(a.serve,Path(a.out));return
 out=ROOT/'artifacts/stage7'/('settings-integration-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]);out.mkdir(parents=True)
 (out/'catalog.json').write_text(json.dumps({'schema_version':1,'course':{'id':'synthetic-settings-course','code':'S7-QA','title':'Synthetic settings acceptance','description':'No real course data'},'sessions':[]}),encoding='utf-8')
 env=os.environ.copy();env.update(AICADEMIYA_DATA_DIR=str(out/'data'),AICADEMIYA_DEMO_ENABLED='true',AICADEMIYA_AI_MODE='openai',AICADEMIYA_AI_PROVIDER='',AICADEMIYA_AI_BASE_URL='http://127.0.0.1:9/v1',AICADEMIYA_AI_MODEL='Synthetic model',AICADEMIYA_AI_API_KEY='',AICADEMIYA_WEB_SEARCH_ENABLED='true',TAVILY_API_KEY='synthetic-environment-key',AICADEMIYA_COOKIE_SECURE='false',NO_PROXY='127.0.0.1,localhost,::1',no_proxy='127.0.0.1,localhost,::1')
 for name in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'):env.pop(name,None)
 scratch=os.environ['TMPDIR'];env.update(TMPDIR=scratch,TEMP=scratch,TMP=scratch)
 result={'status':'failed','evidence':'Actual app HTTP/SQLite/browser; provider transports explicitly mocked, NO real model/search claims','groups':[]}
 try:
  for phase in ('browser','restart'):
   port=free_port();base=f'http://127.0.0.1:{port}';log=(out/(phase+'-server.log')).open('w',encoding='utf-8');proc=None;rec={'phase':phase}
   try:
    proc=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--serve',str(port),'--out',str(out)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT);ready(proc,base)
    if phase=='browser':
     done=subprocess.run(['node','tools/stage7_settings_acceptance.mjs','--base-url',base,'--artifact-dir',str(out),'--confirm-test-data'],cwd=ROOT,env=env,timeout=240,capture_output=True,text=True)
     (out/'browser.log').write_text(done.stdout+'\n'+done.stderr,encoding='utf-8');rec['browser']=json.loads((out/'browser-result.json').read_text());assert done.returncode==0 and rec['browser']['status']=='passed',done.stdout+done.stderr
     with httpx.Client(base_url=base,trust_env=False) as c:
      assert c.post('/api/auth/demo',json={'role':'admin'}).status_code==200
      r=c.get('/api/teacher/settings').json();search=c.get('/api/teacher/search-settings').json();snapshot={'model':r,'search':search}
      (out/'saved-status.json').write_text(json.dumps(snapshot,indent=2),encoding='utf-8')
    else:
     with httpx.Client(base_url=base,trust_env=False) as c:
      assert c.post('/api/auth/demo',json={'role':'admin'}).status_code==200
      observed={'model':c.get('/api/teacher/settings').json(),'search':c.get('/api/teacher/search-settings').json()};assert observed==snapshot
      assert observed['search']['api_key_source']=='none' and not observed['search']['configured']
      rec['settings_and_check_timestamps_survive_process_restart']=True;rec['explicit_clear_blocks_environment_revival']=True
     counts=json.loads((out/'provider-metrics.json').read_text());assert counts['model_protocol_calls']==counts['search_protocol_calls']==0
    rec['provider_metrics']=json.loads((out/'provider-metrics.json').read_text());rec['status']='passed'
   finally:
    if proc:stop(proc)
    log.close();rec['owned_server_stopped']=bool(proc and proc.poll() is not None);rec['owned_listener_closed']=listener_closed(port);result['groups'].append(rec)
  with sqlite3.connect(out/'data/aicademiya.sqlite3') as c:
   result['sqlite']={'integrity':c.execute('PRAGMA integrity_check').fetchone()[0],'foreign_key_violations':len(c.execute('PRAGMA foreign_key_check').fetchall()),'schema':c.execute('PRAGMA user_version').fetchone()[0]}
   assert c.execute("SELECT value FROM settings WHERE key='web_search_api_key'").fetchone()[0]==''
  assert result['sqlite']=={'integrity':'ok','foreign_key_violations':0,'schema':int(os.environ.get('AICADEMIYA_QA_TARGET_SCHEMA','5'))};assert all(x['owned_server_stopped'] and x['owned_listener_closed'] for x in result['groups']);result['status']='passed'
 except Exception as e:result['error']=str(e)
 (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps({'status':result['status'],'result':str(out/'result.json'),'error':result.get('error')}));return 0 if result['status']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
