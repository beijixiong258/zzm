"""One real Stage7 model connection check, isolated DB and owned loopback forwarder."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json,os,sys,threading,time,uuid,socket
import httpx
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
MODEL='AIcademiya-64kx3-Qwen3.8-27B';UPSTREAM='http://192.168.32.5:18280'
def main():
 out=ROOT/'artifacts/stage7'/('live-model-check-'+uuid.uuid4().hex[:10]);out.mkdir(parents=True)
 report={'status':'failed','synthetic_only':True,'production_data_touched':False,'shared_model_services_changed':False,'calls':[]}
 forward=thread=None
 try:
  h=httpx.get(UPSTREAM+'/health',trust_env=False,timeout=10).json()
  assert h.get('model')==MODEL and h['queue']==0 and all(w['healthy'] and not w['busy'] for w in h['workers']),'No idle healthy model window'
  report['idle_health']={'model':h['model'],'queue':h['queue'],'workers':[{'name':w['name'],'healthy':w['healthy'],'busy':w['busy']} for w in h['workers']]}
  class Forward(BaseHTTPRequestHandler):
   def log_message(self,*args):pass
   def do_POST(self):
    body=self.rfile.read(int(self.headers.get('Content-Length','0')));p=json.loads(body);started=time.monotonic()
    assert p['model']==MODEL and p.get('user') and 'connectivity test' in p['messages'][0]['content']
    with httpx.Client(trust_env=False,timeout=610) as c:r=c.post(UPSTREAM+self.path,content=body,headers={'Content-Type':'application/json'})
    response=r.json();report['calls'].append({'http_status':r.status_code,'seconds':round(time.monotonic()-started,3),'max_tokens':p.get('max_tokens'),'server_scope_present':bool(p.get('user')),'response':response})
    self.send_response(r.status_code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(r.content)));self.end_headers();self.wfile.write(r.content)
  forward=ThreadingHTTPServer(('127.0.0.1',18280),Forward);thread=threading.Thread(target=forward.serve_forever,daemon=True);thread.start()
  os.environ.update(AICADEMIYA_DATA_DIR=str(out/'data'),AICADEMIYA_DEMO_ENABLED='true',AICADEMIYA_AI_MODE='openai',AICADEMIYA_AI_PROVIDER='aicademiya-router',AICADEMIYA_AI_BASE_URL='http://127.0.0.1:18280/v1',AICADEMIYA_AI_MODEL=MODEL,AICADEMIYA_AI_API_KEY='',AICADEMIYA_WEB_SEARCH_ENABLED='false',TAVILY_API_KEY='')
  catalog=out/'catalog.json';catalog.write_text(json.dumps({'schema_version':1,'course':{'id':'synthetic-model-check','code':'S7-LIVE','title':'Synthetic connectivity check','description':'No teaching content'},'sessions':[]}),encoding='utf-8')
  from fastapi.testclient import TestClient
  from backend.aicademiya.main import create_app
  app=create_app(data_dir=out/'data',catalog_path=catalog,demo_enabled=True)
  with TestClient(app) as c:
   assert c.post('/api/auth/demo',json={'role':'admin'}).status_code==200
   before=c.get('/api/teacher/settings').json();assert before['ai']['connection']['status']=='not_checked' and not report['calls']
   r=c.post('/api/teacher/settings/test');report['http_status']=r.status_code;report['result']=r.json()
   read=c.get('/api/teacher/settings').json();report['readback_connection']=read['ai']['connection']
   assert r.status_code==200 and r.json()['ok'] and read['ai']['connection']['status']=='connected'
   assert len(report['calls'])==1 and read['ai']['connection']['checked_at']
   report['status']='passed'
 except Exception as exc:report['error']=str(exc)
 finally:
  if forward:forward.shutdown();forward.server_close()
  if thread:thread.join(timeout=5)
  report['owned_forwarder_stopped']=not thread or not thread.is_alive()
  (out/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
  print(json.dumps({'status':report['status'],'calls':len(report['calls']),'report':str(out/'result.json'),'error':report.get('error'),'owned_forwarder_stopped':report['owned_forwarder_stopped']}))
 return 0 if report['status']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
