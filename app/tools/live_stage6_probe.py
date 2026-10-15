"""Actual local-model teacher-workbench probe, isolated SQLite + owned forwarder."""
from pathlib import Path
import json,os,sys,threading,time,uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import httpx
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
UPSTREAM='http://192.168.32.5:18280';MODEL='AIcademiya-64kx3-Qwen3.8-27B'
def health():
 h=httpx.get(UPSTREAM+'/health',trust_env=False,timeout=10).json()
 assert h.get('model')==MODEL and h['queue']==0 and h['workers'] and all(w['healthy'] and not w['busy'] for w in h['workers']), 'No idle healthy model window; do not send inference'
 return {'model':h['model'],'queue':h['queue'],'workers':[{'name':w['name'],'healthy':w['healthy'],'busy':w['busy']} for w in h['workers']]}
def main():
 out=ROOT/'artifacts/stage6'/('live-teacher-'+uuid.uuid4().hex[:10]);out.mkdir(parents=True)
 calls=[];turns=[];report={'status':'failed','synthetic_only':True,'production_data_touched':False,'model_services_changed':False,'initial_health':health(),'turns':turns,'calls':calls}
 class Forward(BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def do_POST(self):
   body=self.rfile.read(int(self.headers.get('Content-Length','0')));request=json.loads(body)
   start=time.monotonic()
   try:
    with httpx.Client(trust_env=False,timeout=610) as c:r=c.post(UPSTREAM+self.path,content=body,headers={'Content-Type':'application/json'})
    record={'status':r.status_code,'seconds':round(time.monotonic()-start,3),'model':request.get('model'),'scope_present':bool(request.get('user')),'messages':request['messages'],'response':r.json()}
    calls.append(record)
    with (out/'model-exchanges.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(record,ensure_ascii=False)+'\n')
    self.send_response(r.status_code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(r.content)));self.end_headers();self.wfile.write(r.content)
   except Exception as exc:
    calls.append({'error':type(exc).__name__});self.send_error(502,'Upstream model request failed')
 forward=ThreadingHTTPServer(('127.0.0.1',18280),Forward);thread=threading.Thread(target=forward.serve_forever,daemon=True);thread.start()
 os.environ.update(AICADEMIYA_DATA_DIR=str(out/'data'),AICADEMIYA_DEMO_ENABLED='true',AICADEMIYA_AI_MODE='openai',AICADEMIYA_AI_PROVIDER='aicademiya-router',AICADEMIYA_AI_BASE_URL='http://127.0.0.1:18280/v1',AICADEMIYA_AI_MODEL=MODEL,AICADEMIYA_AI_API_KEY='',AICADEMIYA_WEB_SEARCH_ENABLED='false',TAVILY_API_KEY='',NO_PROXY='127.0.0.1,localhost,::1')
 from fastapi.testclient import TestClient
 from backend.aicademiya.main import create_app
 from backend.aicademiya.models import TeachingProfile
 app=create_app(data_dir=out/'data',demo_enabled=True)
 def expect(r,code=200):
  if r.status_code!=code:raise RuntimeError(f'API {r.status_code}: {r.text[:600]}')
  return r.json()
 try:
  with TestClient(app) as teacher:
   expect(teacher.post('/api/auth/demo',json={'role':'teacher'}))
   course=expect(teacher.post('/api/courses',json={'code':'LIVE-WORKBENCH','title':'Synthetic teacher-workbench model trial'}))
   session=expect(teacher.post(f"/api/courses/{course['id']}/sessions",json={'title':'Reliability and validity — synthetic','learning_objectives':['Distinguish score consistency from valid interpretation.']}));sid=session['id']
   profile=TeachingProfile(background='Isolated synthetic teacher trial, not real student work.',response_detail='concise',response_strategies='Identify the specific misconception. Give one indirect conceptual hint. Address an embedded follow-up before returning to the task. Keep praise brief.',phases=['warmup','worksheet','wrap_up']).model_dump()
   q={'id':'live-q1','group_id':'core','ordinal':1,'type':'open_response','prompt':'Which assessment principle concerns consistency across raters or repeated administrations? Explain briefly.','options':[],'answer_slots':1,'images':[],'source_label':'Synthetic QA question'}
   extracted=expect(teacher.post(f'/api/teacher/sessions/{sid}/instruction-import/preview',files={'file':('synthetic-instructions.txt',b'Use focused feedback and a calm tone. This instruction was explicitly imported into a synthetic test.','text/plain')}))
   assert extracted['text'] and len(calls)==0
   expect(teacher.patch(f'/api/sessions/{sid}',json={'teaching_profile':profile,'instructions':extracted['text'],'groups':[{'id':'core','title':'Assessment concepts','kind':'core'}],'questions':[q],'reference_answers':{'live-q1':'Reliability'}}))
   material=expect(teacher.post(f'/api/sessions/{sid}/materials',files={'file':('synthetic-reading.txt',b'Reliability is consistency across occasions or raters when ability is stable. Validity concerns the evidence for intended score interpretations and use. A consistently wrong measure can be reliable but invalid.','text/plain')}))
   source=expect(teacher.post(f'/api/teacher/sessions/{sid}/source-review',json={'question_id':'live-q1','phase':'worksheet'}))
   assert source['public_evidence'][0]['material_id']==material['id'] and source['private_reference']['text']=='Reliability' and len(calls)==0
   info=expect(teacher.get(f'/api/teacher/sessions/{sid}/preview'))
   work=expect(teacher.post(f'/api/teacher/sessions/{sid}/preview/reset',json={'expected_revision':info['current_revision']}));pid=work['preview']['id'];report.update(session_id=sid,preview_id=pid,material_id=material['id'])
   def invoke(text=None,action='message'):
    health();before=len(calls);started=time.monotonic();rid=uuid.uuid4().hex
    body={'request_id':rid,'preview_id':pid}
    if text is not None:body.update(message=text,action=action,web_search=False)
    r=teacher.post(f'/api/sessions/{sid}/tutor/'+('start' if text is None else 'turn'),json=body)
    entry={'input':text,'action':action,'http_status':r.status_code,'seconds':round(time.monotonic()-started,3),'model_calls':len(calls)-before,'body':r.json()};turns.append(entry)
    (out/'turns.json').write_text(json.dumps(turns,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'turn':len(turns),'status':r.status_code,'phase':entry['body'].get('tutor',{}).get('phase'),'seconds':entry['seconds']}),flush=True)
    return expect(r)
   work=invoke()
   work=invoke('I remember that tests should be useful and fair, but I am unsure how consistency differs from validity.')
   work=invoke('I think it is validity because the test measures what it intends to measure.')
   assert work['tutor']['current_question_id']=='live-q1'
   # Inspect what the actual provider received, not merely a projected UI list.
   provider_request=next(x for x in reversed(calls) if x.get('messages') and 'private_current_reference' in x['messages'][0]['content'])
   sysmsg=provider_request['messages'][0]['content'];static=json.loads(sysmsg[sysmsg.index('{'):])
   assert static['public_evidence']==[{k:v for k,v in x.items() if k!='material_id'} for x in source['public_evidence']]
   assert static['compiled_teaching']==source['compiled']['text'] and static['private_current_reference']['reference']=='Reliability'
   report['source_preview_matches_actual_request']=True
   work=invoke('Could you give me another hint?',action='hint')
   work=invoke('Reliability, because scores should remain consistent across raters or occasions when ability has not changed. Can it still be invalid?')
   assert work['attempts']['live-q1']['reference_revealed'] and work['tutor']['phase']=='wrap_up'
   raw=teacher.get(f'/api/sessions/{sid}/transcript?format=txt');assert raw.status_code==200
   (out/'before-reset-raw-transcript.txt').write_text(raw.text,encoding='utf-8')
   before=len(calls)
   expect(teacher.patch(f'/api/sessions/{sid}',json={'instructions':extracted['text']+'\nUse the revised synthetic instruction marker: saved-draft-B.'}))
   stale=expect(teacher.get(f'/api/sessions/{sid}/workspace'));assert stale['preview']['stale'] and stale['read_only']
   expect(teacher.post(f'/api/sessions/{sid}/tutor/turn',json={'request_id':'stale-no-call','preview_id':pid,'message':'This stale turn must not invoke the model.'}),409)
   assert len(calls)==before;report['stale_rejected_without_inference']=True
   info=expect(teacher.get(f'/api/teacher/sessions/{sid}/preview'))
   fresh=expect(teacher.post(f'/api/teacher/sessions/{sid}/preview/reset',json={'expected_revision':info['current_revision']}));newpid=fresh['preview']['id'];assert newpid!=pid and not fresh['messages'] and not fresh['attempts']
   expect(teacher.post(f'/api/sessions/{sid}/tutor/start',json={'request_id':'old-id','preview_id':pid}),409);assert len(calls)==before
   pid=newpid;work=invoke();assert 'saved-draft-B' in calls[-1]['messages'][0]['content']
   report.update(status='passed',fresh_preview_id=pid,new_saved_instruction_reached_model=True,reference_gate_preserved=True)
 except Exception as exc:report['error']=str(exc)
 finally:
  forward.shutdown();forward.server_close();thread.join(timeout=5)
  report['owned_forwarder_stopped']=not thread.is_alive();report['model_requests']=len(calls);report['application_turns']=len(turns)
  (out/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
  print(json.dumps({'status':report['status'],'report':str(out/'result.json'),'error':report.get('error'),'model_requests':len(calls),'application_turns':len(turns),'owned_forwarder_stopped':report['owned_forwarder_stopped']},ensure_ascii=False),flush=True)
 if report['status']!='passed':raise SystemExit(1)
if __name__=='__main__':main()
