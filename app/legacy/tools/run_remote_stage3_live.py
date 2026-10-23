"""Bounded staged-CT255 guided model/search smoke, using fresh synthetic data."""
from pathlib import Path
import json,os,shlex,subprocess,sys,time,uuid
import httpx
ROOT=Path(__file__).resolve().parents[1]
RELEASE='/opt/aicademiya/releases/AIcademiya_V2-20261007-guided'
TOKEN=uuid.uuid4().hex[:10]
OUT=ROOT/'artifacts/stage3'/('ct255-live-'+TOKEN)
DATA='/var/lib/aicademiya-qa/stage3-live-'+TOKEN
BASE='http://192.168.32.55:18774';UNIT='aicademiya-qa-stage3-live-'+TOKEN
SSH=['ssh','-i','C:/Users/17193/.ssh/id_ed25519_aicademiya_pve','-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes','root@192.168.10.16']
def guest(args,check=True):
 r=subprocess.run(SSH+[shlex.join(['pct','exec','255','--']+args)],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=40)
 if check and r.returncode:raise RuntimeError(r.stderr or r.stdout)
 return r

def main():
 OUT.mkdir(parents=True)
 report={'status':'running','synthetic_only':True,'production_database_touched':False,'release':RELEASE,'data_dir':DATA,'turns':[]}
 with httpx.Client(trust_env=False,timeout=10) as c:health=c.get('http://192.168.32.5:18280/health').json()
 assert health['queue']==0 and all(w['healthy'] and not w['busy'] for w in health['workers']),'No resource window; no inference started'
 report['router_requests_before']=health['requests']
 guest(['python3','-c','import socket;s=socket.socket();s.settimeout(1);assert s.connect_ex(("192.168.32.55",18774))!=0;s.close()'])
 guest(['install','-d','-m','700','-o','aicademiya','-g','aicademiya',DATA])
 command='set -a; . /etc/aicademiya/aicademiya.conf; export AICADEMIYA_DATA_DIR='+shlex.quote(DATA)+' AICADEMIYA_DEMO_ENABLED=true AICADEMIYA_ALLOWED_ORIGINS='+shlex.quote(BASE)+' PYTHONDONTWRITEBYTECODE=1; exec '+shlex.quote(RELEASE+'/.venv/bin/python')+' -m uvicorn backend.aicademiya.main:app --host 192.168.32.55 --port 18774 --workers 1'
 guest(['systemd-run','--unit='+UNIT,'--collect','--uid=aicademiya','--gid=aicademiya','--working-directory='+RELEASE,'--property=UMask=0077','--property=NoNewPrivileges=true','/bin/bash','-c',command])
 def save(): (OUT/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 def expect(r):
  if r.status_code>=400:raise RuntimeError(f'QA HTTP {r.status_code}: {r.text[:600]}')
  return r.json()
 try:
  with httpx.Client(base_url=BASE,trust_env=False,timeout=620) as teacher,httpx.Client(base_url=BASE,trust_env=False,timeout=620) as learner,httpx.Client(base_url=BASE,trust_env=False,timeout=20) as admin:
   deadline=time.monotonic()+40
   while time.monotonic()<deadline:
    try:
     if teacher.get('/api/health',timeout=2).status_code==200:break
    except httpx.RequestError:pass
    time.sleep(.2)
   else:raise RuntimeError('QA startup failed')
   boot=expect(teacher.get('/api/bootstrap'));assert boot['demo_enabled'] and boot['ai']['mode']=='openai' and boot['ai']['model']=='AIcademiya-64kx3-Qwen3.8-27B'
   expect(teacher.post('/api/auth/demo',json={'role':'teacher'}));expect(learner.post('/api/auth/demo',json={'role':'student','student_index':1}))
   course=expect(teacher.post('/api/courses',json={'title':'Synthetic staged live flow','code':'S3-LIVE','description':'Isolated live transport verification.'}))
   lesson=expect(teacher.post(f"/api/courses/{course['id']}/sessions",json={'title':'Assessment reasoning live check','number':1}))
   sid=lesson['id'];profile=lesson['teaching_profile'];profile.update(phases=['warmup','worksheet','wrap_up'],response_detail='concise',background='Synthetic isolated deployment check.',response_strategies='Hint first, support correction, and answer follow-up questions concisely.')
   expect(teacher.patch(f'/api/sessions/{sid}',json={'teaching_profile':profile,'status':'published','learning_objectives':['Distinguish consistency from intended measurement.'],'groups':[{'id':'core','title':'Assessment ideas','kind':'core'}],'questions':[{'id':'live-q','group_id':'core','ordinal':1,'type':'open_response','prompt':'Which principle concerns consistency of assessment scores across occasions or raters? Explain briefly.','options':[],'answer_slots':1,'images':[],'source_label':'Synthetic assessment question'}],'reference_answers':{'live-q':'Reliability'}}))
   expect(teacher.post(f'/api/sessions/{sid}/materials',data={'visibility':'student','kind':'reading'},files={'file':('public-reading.txt',b'Reliability concerns score consistency. Validity concerns evidence for the intended interpretation and use of scores. A test can produce consistent results while measuring the wrong construct.','text/plain')}))
   vid=expect(teacher.post(f"/api/teacher/courses/{course['id']}/versions/publish",json={'label':'Synthetic live edition'}))['id']
   expect(learner.post('/api/courses/join',json={'join_code':course['join_code']}))
   report.update(session_id=sid,version_id=vid,base_url=BASE)
   def turn(message=None,search=False):
    start=time.monotonic();body={'request_id':uuid.uuid4().hex};route='start'
    if message is not None:body.update(message=message,web_search=search,action='message');route='turn'
    r=learner.post(f'/api/sessions/{sid}/tutor/{route}',params={'version_id':vid},json=body)
    work=expect(r);reply=work['messages'][-1]
    entry={'input':message,'web_search':search,'status':r.status_code,'seconds':round(time.monotonic()-start,3),'phase':work['tutor']['phase'],'content':reply['content'],'mode':reply['mode'],'citations':reply.get('citations',[])}
    assert reply['mode']=='openai' and reply['content'].strip()
    report['turns'].append(entry);save();print(json.dumps({'turn':len(report['turns']),'search':search,'seconds':entry['seconds'],'phase':entry['phase'],'citations':len(entry['citations'])}),flush=True)
    return work
   turn();turn('I remember that assessment should be useful, but I need help distinguishing consistency from validity.')
   work=turn('Could you find a public Cambridge English source explaining assessment reliability, and give a brief explanation with retrieved sources?',True)
   urls=[c['url'] for c in work['messages'][-1]['citations'] if c.get('url')]
   assert urls and all(u.startswith('https://') for u in urls);assert not work['attempts']
   report['search_source_urls']=urls
   work=turn('Reliability, because scores should stay consistent when ability is stable. Can a reliable test still lack validity?')
   assert work['attempts']['live-q']['reference_revealed'];assert work['tutor']['phase']=='wrap_up'
   work=turn('Thank you. I am ready to finish this conversation.');assert work['tutor']['phase']=='complete'
   work=turn('Why does the purpose of a test matter?');assert work['tutor']['phase']=='complete' and work['submission']['status']=='in_progress'
   # Disable new inference in this owned QA database before read-only UI checking.
   expect(admin.post('/api/auth/demo',json={'role':'admin'}))
   expect(admin.put('/api/teacher/settings',json={'mode':'demo','base_url':'','model':'','api_key':''}))
   report['new_inference_disabled_for_saved_ui']=True
   report['status']='passed';save()
   env=os.environ.copy();env.update(AICADEMIYA_SAVED_URL=BASE,AICADEMIYA_SAVED_SESSION=sid,AICADEMIYA_SAVED_VERSION=vid,AICADEMIYA_SAVED_OUTPUT=str(OUT))
   ui=subprocess.run(['node','tools/stage3_saved_live_ui.mjs'],cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',timeout=90)
   (OUT/'ui.log').write_text(ui.stdout+'\n'+ui.stderr,encoding='utf-8')
   if ui.returncode:raise RuntimeError('Saved real-response UI check failed; inspect ui.log')
   report['saved_ui']=json.loads((OUT/'ui-result.json').read_text(encoding='utf-8'))
 except Exception as e:report['status']='failed';report['error']=str(e)
 finally:
  guest(['systemctl','stop',UNIT],check=False)
  report['owned_qa_service_stopped']=guest(['systemctl','is-active',UNIT],check=False).stdout.strip() not in ('active','activating','deactivating')
  report['production_service_active']=guest(['systemctl','is-active','aicademiya.service']).stdout.strip()=='active'
  with httpx.Client(trust_env=False,timeout=10) as c:after=c.get('http://192.168.32.5:18280/health').json()
  report['observed_router_request_delta']=after['requests']-report['router_requests_before'];report['router_queue_after']=after['queue']
  save();print(json.dumps({'status':report['status'],'result':str(OUT/'result.json'),'error':report.get('error'),'stopped':report['owned_qa_service_stopped']}),flush=True)
 if report['status']!='passed':raise SystemExit(1)
if __name__=='__main__':main()
