"""Bounded real-model API spike on isolated SQLite and an owned loopback forwarder.
No production data or model/router configuration is modified.
"""
from pathlib import Path
import argparse,json,os,sys,threading,time,uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import httpx

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--resource-window-confirmed',action='store_true');parser.add_argument('--full',action='store_true');args=parser.parse_args()
 if not args.resource_window_confirmed:raise SystemExit('Confirm an available resource window before actual inference.')
 out=ROOT/'artifacts'/'stage3'/('live-spike-'+uuid.uuid4().hex[:10]);out.mkdir(parents=True)
 calls=[];turns=[];result={'status':'failed','data_dir':str(out/'data'),'production_data_touched':False,'model_services_changed':False,'calls':calls,'turns':turns}
 def ready():
  with httpx.Client(trust_env=False,timeout=10) as c:h=c.get('http://192.168.32.5:18280/health').json()
  if h['queue'] or not all(w['healthy'] and not w['busy'] for w in h['workers']):raise RuntimeError('Model workers are not idle/healthy; no additional inference sent')
  return {'model':h.get('model'),'queue':h['queue'],'workers':[{'name':w['name'],'busy':w['busy'],'healthy':w['healthy']} for w in h['workers']]}
 result['initial_health']=ready()
 class Forward(BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def do_POST(self):
   payload=self.rfile.read(int(self.headers.get('Content-Length','0')))
   start=time.monotonic()
   try:
    with httpx.Client(trust_env=False,timeout=610) as c:r=c.post('http://192.168.32.5:18280'+self.path,content=payload,headers={'Content-Type':'application/json'})
    content=r.content
    record={'status':r.status_code,'seconds':round(time.monotonic()-start,3),'response':r.json()}
    calls.append(record)
    with (out/'model-responses.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(record,ensure_ascii=False)+'\n')
    self.send_response(r.status_code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(content)));self.end_headers();self.wfile.write(content)
   except Exception as e:
    calls.append({'error':type(e).__name__});self.send_error(502,'Upstream model request failed')
 forward=ThreadingHTTPServer(('127.0.0.1',18280),Forward)
 thread=threading.Thread(target=forward.serve_forever,daemon=True);thread.start()
 os.environ.update(AICADEMIYA_DATA_DIR=str(out/'data'),AICADEMIYA_DEMO_ENABLED='true',AICADEMIYA_AI_MODE='openai',AICADEMIYA_AI_PROVIDER='aicademiya-router',AICADEMIYA_AI_BASE_URL='http://127.0.0.1:18280/v1',AICADEMIYA_AI_MODEL='AIcademiya-64kx3-Qwen3.8-27B',AICADEMIYA_AI_API_KEY='',AICADEMIYA_WEB_SEARCH_ENABLED='false',TAVILY_API_KEY='',NO_PROXY='127.0.0.1,localhost,::1')
 from fastapi.testclient import TestClient
 from backend.aicademiya.main import create_app
 from backend.aicademiya.models import TeachingProfile
 app=create_app(data_dir=out/'data',demo_enabled=True)
 def expect(r):
  if r.status_code>=400:raise RuntimeError(f'API {r.status_code}: {r.text[:1000]}')
  return r.json()
 try:
  with TestClient(app) as teacher:
   expect(teacher.post('/api/auth/demo',json={'role':'teacher'}))
   with TestClient(app) as learner:
    expect(learner.post('/api/auth/demo',json={'role':'student','student_index':1}))
    course=expect(teacher.post('/api/courses',json={'code':'LIVE-QA','title':'Synthetic guided model probe','description':'Synthetic isolated QA; not a student course.'}))
    session=expect(teacher.post(f"/api/courses/{course['id']}/sessions",json={'title':'Reliability and validity','learning_objectives':['Distinguish consistency from intended measurement.']}))
    sid=session['id'];profile=TeachingProfile(background='This is an isolated synthetic learning test.',student_profile='Adult learner with basic assessment knowledge.',response_detail='concise',response_strategies='Give a focused hint for a misconception, invite revision, and address a follow-up without losing the current question.',phases=['warmup','worksheet','quiz','reading','wrap_up'] if args.full else ['warmup','worksheet','wrap_up'],reading_question_count=1).model_dump()
    question={'id':'live-q1','group_id':'core','ordinal':1,'type':'open_response','prompt':'Which assessment principle concerns consistency of scores across raters or repeated administrations? Explain briefly.','options':[],'answer_slots':1,'images':[],'source_label':'Synthetic assessment question'}
    expect(teacher.patch(f'/api/sessions/{sid}',json={'teaching_profile':profile,'groups':[{'id':'core','title':'Assessment concepts','kind':'core'}],'questions':[question],'reference_answers':{'live-q1':'Reliability'},'status':'published'}))
    material=expect(teacher.post(f'/api/sessions/{sid}/materials',data={'visibility':'student','kind':'reading'},files={'file':('assessment-reading.txt',b'Reliability concerns consistency across repeated measurements or raters when ability is stable. Validity concerns evidence supporting the intended interpretation and use of scores. A test can be consistent while measuring the wrong construct.','text/plain')}))
    vid=expect(teacher.post(f"/api/teacher/courses/{course['id']}/versions/publish",json={'label':'Synthetic live probe'}))['id']
    expect(learner.post('/api/courses/join',json={'join_code':course['join_code']}))
    result.update(session_id=sid,version_id=vid,material_id=material['id'])
    def invoke(text=None,action='message'):
     ready();start=time.monotonic();rid=uuid.uuid4().hex
     url=f'/api/sessions/{sid}/tutor/'+('start' if text is None else 'turn')+f'?version_id={vid}'
     body={'request_id':rid} if text is None else {'message':text,'request_id':rid,'action':action,'web_search':False}
     r=learner.post(url,json=body);entry={'input':text,'action':action,'http_status':r.status_code,'seconds':round(time.monotonic()-start,3),'body':r.json()}
     turns.append(entry);(out/'turns.json').write_text(json.dumps(turns,ensure_ascii=False,indent=2),encoding='utf-8')
     print(json.dumps({'turn':len(turns),'status':r.status_code,'seconds':entry['seconds'],'phase':entry['body'].get('tutor',{}).get('phase'),'detail':entry['body'].get('detail')},ensure_ascii=False),flush=True)
     return expect(r)
    work=invoke()
    work=invoke('I remember that tests should be fair and useful, but I am still unsure about the distinction between validity and consistency.')
    work=invoke('I think validity, because the test should measure what it claims to measure.')
    assert work['tutor']['current_question_id']=='live-q1'
    work=invoke('Could you give me another hint?',action='hint')
    work=invoke('Reliability, because scores should be consistent across raters and occasions when ability has not changed. Can a test be reliable without being valid?')
    assert work['attempts']['live-q1']['reference_revealed']
    if args.full:
     work=invoke('Yes')
     for _ in range(5):
      assert work['tutor']['phase']=='quiz';work=invoke('1')
     assert work['tutor']['phase']=='reading'
     work=invoke('Consistency is necessary but not sufficient: evidence about the intended construct matters because a consistently wrong measure would not justify the intended interpretation.')
    assert work['tutor']['phase']=='wrap_up'
    work=invoke('Thank you, I am ready to finish.')
    assert work['tutor']['phase']=='complete'
    transcript=learner.get(f'/api/sessions/{sid}/transcript?version_id={vid}&format=txt');assert transcript.status_code==200
    (out/'raw-transcript.txt').write_text(transcript.text,encoding='utf-8')
    result['status']='passed'
 except Exception as e:result['error']=str(e)
 finally:
  forward.shutdown();forward.server_close();thread.join(timeout=5)
  result['owned_forwarder_stopped']=not thread.is_alive()
  result['model_call_count']=len(calls);result['application_request_count']=len(turns)
  (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
  print(json.dumps({'status':result['status'],'result':str(out/'result.json'),'error':result.get('error'),'owned_forwarder_stopped':result['owned_forwarder_stopped']},ensure_ascii=False),flush=True)
 if result['status']!='passed':raise SystemExit(1)
if __name__=='__main__':main()
