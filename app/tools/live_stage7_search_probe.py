"""One actual saved-settings Tavily check with existing local app credentials, fresh synthetic data only."""
from pathlib import Path
import json,os,sys,time,uuid
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
def main():
 out=ROOT/'artifacts/stage7'/('live-search-check-'+uuid.uuid4().hex[:10]);out.mkdir(parents=True)
 report={'status':'failed','production_data_touched':False,'original_private_config_modified':False,'model_calls':0,'search_calls':0}
 try:
  # Resolve privately using the normal launcher's environment-over-file precedence.
  config=json.loads((ROOT/'local-settings-v2.json').read_text(encoding='utf-8-sig'))
  key=os.environ.get('TAVILY_API_KEY',config.get('TAVILY_API_KEY','')).strip()
  assert key,'No existing application Tavily key; none is guessed'
  os.environ.update(AICADEMIYA_DATA_DIR=str(out/'data'),AICADEMIYA_DEMO_ENABLED='true',AICADEMIYA_AI_MODE='openai',AICADEMIYA_AI_PROVIDER='',AICADEMIYA_AI_BASE_URL='',AICADEMIYA_AI_MODEL='',AICADEMIYA_AI_API_KEY='',AICADEMIYA_WEB_SEARCH_ENABLED='true',TAVILY_API_KEY=key)
  key=None;config=None
  catalog=out/'catalog.json';catalog.write_text(json.dumps({'schema_version':1,'course':{'id':'synthetic-search-check','code':'S7-SEARCH','title':'Synthetic service check','description':'No classroom content'},'sessions':[]}),encoding='utf-8')
  from fastapi.testclient import TestClient
  from backend.aicademiya.main import create_app
  app=create_app(data_dir=out/'data',catalog_path=catalog,demo_enabled=True)
  original=app.state.tutor.search.search
  def counted(*args,**kwargs):
   report['search_calls']+=1;return original(*args,**kwargs)
  def forbidden(*args,**kwargs):
   report['model_calls']+=1;raise AssertionError('This search-only check must never call a model')
  app.state.tutor.search.search=counted;app.state.tutor.complete=forbidden
  with TestClient(app) as c:
   assert c.post('/api/auth/demo',json={'role':'admin'}).status_code==200
   state=c.get('/api/teacher/search-settings').json();assert state['configured'] and state['connection']['status']=='not_checked'
   started=time.monotonic();r=c.post('/api/teacher/search-settings/test');report['seconds']=round(time.monotonic()-started,3);report['http_status']=r.status_code;report['result']=r.json()
   assert r.status_code==200 and r.json()['ok'];after=c.get('/api/teacher/search-settings').json()
   assert after['connection']==r.json()['connection'];report['readback_connection']=after['connection']
   assert report['search_calls']==1 and report['model_calls']==0;report['status']='passed'
 except Exception as e:report['error']=str(e)
 (out/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'status':report['status'],'search_calls':report['search_calls'],'model_calls':report['model_calls'],'result':str(out/'result.json'),'error':report.get('error')}));return 0 if report['status']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
