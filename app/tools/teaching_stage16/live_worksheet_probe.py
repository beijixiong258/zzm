"""Stage16 actual teaching-provider worksheet extraction in isolated CT255 QA.
Synthetic originals/accounts only; no production DB/unit/config or model restart.
A private fresh QA installation gives router requests their own HMAC scope.
"""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,io,json,shlex,subprocess,sys,tarfile,time,uuid
import httpx

APP=Path(__file__).resolve().parents[2]
SSH=['ssh','-4','-i','C:/Users/17193/.ssh/id_ed25519_aicademiya_pve','-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8','root@192.168.10.16']
RELEASE=APP/'artifacts/stage16/release-candidate-r2/extracted/AIcademiya_V2-stage16-workflow-candidate-r2'
def guest(args,timeout=45):
 r=subprocess.run(SSH+[shlex.join(['pct','exec','255','--',*args])],capture_output=True,text=True,timeout=timeout)
 if r.returncode:raise RuntimeError(r.stderr or r.stdout)
 return r.stdout

def gpu():
 code="""import json,subprocess,urllib.request
s=json.load(urllib.request.urlopen('http://127.0.0.1:18280/status',timeout=5));print(json.dumps({'capacity':s['teaching_capacity'],'vision':s.get('vision_teaching_capacity'),'queue':s['queue'],'phase':s.get('resources',{}).get('phase'),'workers':[{k:w.get(k)for k in ['name','busy','healthy']}for w in s['workers']],'allocations':subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid','--format=csv,noheader,nounits'],text=True).splitlines()}))"""
 r=subprocess.run(['ssh','-o','BatchMode=yes','ubuntu-gpu','python3 -c '+shlex.quote(code)],capture_output=True,text=True,timeout=20)
 assert r.returncode==0,r.stderr
 return json.loads(r.stdout)

def main():
 tag=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6]
 out=APP/'artifacts/stage16/live-worksheet'/tag;out.mkdir(parents=True)
 qa='/var/lib/aicademiya-qa/stage16-worksheet-'+tag;source=qa+'/source';unit='aicademiya-qa-s16-'+tag.lower();base='http://192.168.32.55:18776'
 live=guest(['readlink','-f','/opt/aicademiya/current']).strip();python=live+'/.venv/bin/python'
 original_service=guest(['systemctl','show','aicademiya.service','--property=MainPID','--value']).strip()
 health=json.loads(guest(['python3','-c',"import json,urllib.request;print(json.dumps(json.load(urllib.request.urlopen('http://192.168.32.55:18773/api/health',timeout=5))))"]))
 assert health['status']=='ok'
 guest(['python3','-c',"import socket;s=socket.socket();s.bind(('192.168.32.55',18776));s.close()"])
 catalog={'schema_version':1,'course':{'id':'s16-live','code':'SYNTHETIC','title':'Stage16 real-provider synthetic QA','description':'No classroom identities'},'sessions':[{'id':'s16-live-session','course_id':'s16-live','number':1,'title':'Worksheet extraction QA','subtitle':'Synthetic sources','status':'published','estimated_minutes':15,'learning_objectives':[],'instructions':'Use supplied evidence only.','reference_policy':'after_attempt','teaching_language':'en','groups':[{'id':'g','title':'Core','kind':'core'}],'questions':[],'reference_answers':{},'materials':[]}]}
 from docx import Document
 def docx(name,lines):
  doc=Document()
  for line in lines:doc.add_paragraph(line)
  p=out/name;doc.save(p);return p
 paired=docx('paired-worksheet.docx',['Worksheet','Section A','1. Copy the exact label supplied for Item A1.','2. Choose the supplied letter for Item A2.','A. red','B. blue','C. green','Section B','1. Fill in the source marker: _____.','2. What value is supplied for the missing item?'])
 key=docx('supplied-key.docx',['Answer key','Section A','1. VIOLET-67','2. C','Section B','1. copper heron'])
 inline=docx('inline-worksheet.docx',['Worksheet','1. Transcribe the supplied result: x² ≥ 16.','Answer: x ≥ 4','2. Copy the listed label.','Answer: amber-L9'])
 missing=docx('without-answers.docx',['Worksheet','1. What is 2 + 2?','2. Name a primary colour.'])
 server="""from pathlib import Path
import os,json,time,httpx,uvicorn
from backend.aicademiya.main import create_app
root=Path(__file__).resolve().parent
class Recorder(httpx.BaseTransport):
 def __init__(self):self.real=httpx.HTTPTransport(retries=0,trust_env=False)
 def handle_request(self,request):
  row={'method':request.method,'path':request.url.path,'request':json.loads(request.content)if request.content else None,'actual_HTTP':True};start=time.monotonic()
  try:
   r=self.real.handle_request(request);r.read();row.update(status_code=r.status_code,response=r.json(),router_headers={k:r.headers.get(k)for k in ['X-AIcademiya-Worker','X-KV-Restored']});return r
  except Exception as e:row['error_type']=type(e).__name__;raise
  finally:
   row['seconds']=time.monotonic()-start
   with(root/'model-exchanges.jsonl').open('a')as f:f.write(json.dumps(row,ensure_ascii=False)+'\\n')
 def close(self):pass
app=create_app(data_dir=root/'data',catalog_path=root/'catalog.json',frontend_dir=Path(SOURCE)/'frontend/dist',demo_enabled=True,document_worker_command=None,ai_transport=Recorder())
uvicorn.run(app,host='192.168.32.55',port=18776,log_level='warning')
""".replace('SOURCE',repr(source))
 with tarfile.open(RELEASE.parents[1]/(RELEASE.name+'-code.tar.gz'),'r:gz')as package:
  blobs={'source/'+m.name.split('/',1)[1]:package.extractfile(m).read()for m in package.getmembers()if m.isfile()}
 assert len(blobs)==117
 blobs.update({'server.py':server.encode(),'catalog.json':json.dumps(catalog).encode()})
 hashes={n:hashlib.sha256(b).hexdigest()for n,b in blobs.items()};blobs['snapshot-manifest.json']=json.dumps(hashes).encode();buf=io.BytesIO()
 with tarfile.open(fileobj=buf,mode='w:gz')as tf:
  for n,b in blobs.items():info=tarfile.TarInfo(n);info.size=len(b);info.mode=0o644;tf.addfile(info,io.BytesIO(b))
 stage="from pathlib import Path;import sys,tarfile,io,json,hashlib,os,pwd;p=Path("+repr(qa)+");p.mkdir(mode=0o700);u=pwd.getpwnam('aicademiya');assert u.pw_uid==999;b=sys.stdin.buffer.read();assert hashlib.sha256(b).hexdigest()=="+repr(hashlib.sha256(buf.getvalue()).hexdigest())+";tarfile.open(fileobj=io.BytesIO(b),mode='r:gz').extractall(p,filter='data');m=json.loads((p/'snapshot-manifest.json').read_text());assert all(hashlib.sha256((p/n).read_bytes()).hexdigest()==h for n,h in m.items());\nfor x in [p,*p.rglob('*')]:os.chown(x,u.pw_uid,u.pw_gid)\nprint(json.dumps({'verified_files':len(m),'qa':str(p)}))"
 r=subprocess.run(SSH+[shlex.join(['pct','exec','255','--','python3','-c',stage])],input=buf.getvalue(),capture_output=True,timeout=90);assert r.returncode==0,r.stderr
 env={'PYTHONPATH':source,'PYTHONDONTWRITEBYTECODE':'1','LANG':'C.UTF-8','AICADEMIYA_DATA_DIR':qa+'/data','AICADEMIYA_AI_MODE':'openai','AICADEMIYA_AI_PROVIDER':'aicademiya-router','AICADEMIYA_AI_BASE_URL':'http://127.0.0.1:18280/v1','AICADEMIYA_AI_MODEL':'AIcademiya-64kx3-Qwen3.8-27B','AICADEMIYA_AI_API_KEY':'','AICADEMIYA_DEMO_ENABLED':'true','AICADEMIYA_DOCUMENT_WORKER_COMMAND':'','AICADEMIYA_WEB_SEARCH_ENABLED':'false','TAVILY_API_KEY':'','AICADEMIYA_ALLOWED_ORIGINS':base,'AICADEMIYA_COOKIE_SECURE':'false','NO_PROXY':'127.0.0.1,localhost,192.168.32.55','no_proxy':'127.0.0.1,localhost,192.168.32.55'}
 start=['systemd-run','--unit='+unit,'--collect','--uid=aicademiya','--gid=aicademiya','--working-directory='+source,'--property=UMask=0077','--property=RuntimeMaxSec=3600','--property=NoNewPrivileges=true','--property=ProtectSystem=strict','--property=ProtectHome=true','--property=PrivateTmp=true','--property=ReadWritePaths='+qa]+['--setenv='+k+'='+v for k,v in env.items()]+[python,qa+'/server.py']
 report={'status':'running','qa':qa,'unit':unit,'base_url':base,'source_release':str(RELEASE),'production_release':live,'production_pid':original_service,'cases':[], 'real_provider':True,'production_changed':False}
 def save():(out/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 save();print(json.dumps({'artifact_dir':str(out),'qa':qa}),flush=True)
 def call(client,method,path,**kwargs):
  r=client.request(method,path,**kwargs)
  if r.status_code!=200:raise RuntimeError(f'{method} {path}: {r.status_code} {r.text[:1500]}')
  return r.json()
 try:
  report['before_gpu']=gpu();assert report['before_gpu']['capacity']==3 and report['before_gpu']['queue']==0 and all(not w['busy']for w in report['before_gpu']['workers'])
  guest(start)
  with httpx.Client(base_url=base,trust_env=False,timeout=650)as c:
   end=time.monotonic()+40
   while True:
    try:
     if c.get('/api/bootstrap',timeout=2).status_code==200:break
    except httpx.RequestError:pass
    if time.monotonic()>end:raise TimeoutError('Owned QA readiness')
    time.sleep(.3)
   call(c,'POST','/api/auth/demo',json={'role':'teacher'})
   status=call(c,'GET','/api/ai/connection');assert status['status']=='connected'and status['check_kind']=='router_health';report['live_connection']=status;save()
   def upload(path,kind):
    return call(c,'POST','/api/sessions/s16-live-session/materials',data={'kind':kind,'visibility':'teacher','processing':'preview'},files={'file':(path.name,path.read_bytes())})
   mkey=upload(key,'answer_key')
   for label,path,answer,count,expected in [('paired',paired,mkey['id'],4,['VIOLET-67','C','copper heron',None]),('inline',inline,None,2,['x ≥ 4','amber-L9']),('missing',missing,None,2,[None,None])]:
    mid=upload(path,'worksheet')['id'];before=call(c,'GET','/api/courses/s16-live/materials')['materials']
    p=call(c,'POST','/api/sessions/s16-live-session/worksheet-import/from-material',json={'material_id':mid,'answer_material_id':answer,'use_ai':True})
    (out/(label+'-preview.json')).write_text(json.dumps(p,ensure_ascii=False,indent=2))
    q=p['draft']['questions'];refs=p['draft']['reference_answers'];assert p['method']=='ai_materials' and len(q)==count,(label,len(q),p['warnings'])
    matched=[refs.get(x['id'])for x in q];assert matched==expected,(label,matched,expected)
    if label=='paired':assert q[1]['type']=='single_choice'and len(q[1]['options'])==3 and '_____'in q[2]['prompt']
    if label=='inline':assert 'x² ≥ 16'in q[0]['prompt']
    after=call(c,'GET','/api/courses/s16-live/materials')['materials'];assert [x['id']for x in before]==[x['id']for x in after]
    body={k:p['draft'][k]for k in ['groups','questions','reference_answers']};body['mode']='replace'
    call(c,'POST','/api/sessions/s16-live-session/worksheet-import/'+p['import_id']+'/commit',json=body)
    saved=call(c,'GET','/api/sessions/s16-live-session');assert saved['reference_answers']==refs and [x['id']for x in saved['questions']]==[x['id']for x in q]
    original=c.get('/api/materials/'+mid+'/download');assert original.status_code==200 and original.content==path.read_bytes()
    report['cases'].append({'name':label,'material_id':mid,'question_count':len(q),'matched_answers':matched,'original_unchanged':True,'same_material_ids':True});save();print(json.dumps(report['cases'][-1],ensure_ascii=False),flush=True)
  report['after_gpu']=gpu();assert report['after_gpu']['capacity']==3 and report['after_gpu']['allocations']==report['before_gpu']['allocations']
  assert guest(['readlink','-f','/opt/aicademiya/current']).strip()==live
  assert guest(['systemctl','show','aicademiya.service','--property=MainPID','--value']).strip()==original_service
  report['status']='passed'
 except BaseException as exc:report.update(status='failed',error_type=type(exc).__name__,error=str(exc));raise
 finally:
  try:
   data=guest(['python3','-c',"from pathlib import Path;print(Path("+repr(qa+'/model-exchanges.jsonl')+").read_text())"])
   (out/'model-exchanges.jsonl').write_text(data,encoding='utf-8');report['actual_generation_calls']=sum(json.loads(x).get('path')=='/v1/chat/completions'for x in data.splitlines()if x.strip())
  except Exception as e:report['capture_error']=type(e).__name__
  guest(['systemctl','stop',unit])
  report['qa_stopped']=guest(['python3','-c',"import socket;s=socket.socket();s.settimeout(2);print(s.connect_ex(('192.168.32.55',18776))!=0);s.close()"]).strip()=='True'
  save();print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':main()
