"""Isolated real HTTP → SSH CPU parsing → source review → actual local-model reading.

Uses synthetic accounts/course only, genuine supplied chapter bytes, no provider
fixtures/interception. Resume a completed parse instead of re-OCR after later
acceptance failures. Owned server/tunnel are always closed on exit.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,os,socket,subprocess,sys,time,uuid
import httpx
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))
from run_stage4_integration import free_port,ready,stop,listener_closed
SOURCE=Path('D:/中转站/Z/Session 4/Chap 5 standardized testing.pdf')
SHA='5ffdc6a8dce6d5136397afb13bcaf627a5396f8c004ab1007d6493981ca8e723'

def save(p,data):p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def serve(folder,port,exchange_dir=None):
 import uvicorn
 from backend.aicademiya.main import create_app
 app=create_app(data_dir=folder/'data',catalog_path=folder/'catalog.json',frontend_dir=ROOT/'frontend/dist',demo_enabled=True,
     document_worker_command=[sys.executable,str(ROOT/'tools/document_stage12/document_ssh_bridge.py'),'--ssh-host','ubuntu-gpu','--timeout','3600'],document_worker_timeout=3700)
 original=app.state.tutor.completion_message
 def record(settings,messages,**kwargs):
  begin=time.monotonic();row={'model':settings['model'],'messages':messages,'response_schema':kwargs.get('response_format'),'real_provider_call':True}
  try:
   response=original(settings,messages,**kwargs);row['response']=response;return response
  except Exception as e:row['error_type']=type(e).__name__;raise
  finally:
   row['seconds']=time.monotonic()-begin
   with ((exchange_dir or folder)/'model-exchanges.jsonl').open('a',encoding='utf-8')as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
 app.state.tutor.completion_message=record
 uvicorn.run(app,host='127.0.0.1',port=port,log_level='warning')

def make_catalog(folder):
 from run_stage11_integration import catalog
 catalog(folder);p=folder/'catalog.json';data=json.loads(p.read_text())
 data['course'].update(id='s12-course',code='READ-QA',title='Isolated document reading acceptance',description='Synthetic course and accounts; actual source PDF and actual local-model calls.')
 s=data['sessions'][0];s.update(id='s12-session',course_id='s12-course',title='Complete source reading',instructions='Answer learner questions from the supplied reading. Quote the actual source and distinguish uncertainty. Do not grade or invent source text.',reference_answers={},learning_objectives=['Explain standardized testing using cited source evidence'])
 s['questions'][0].update(id='s12-q',prompt='Discuss standardized testing using the supplied chapter.',images=[])
 p.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--serve',type=int);parser.add_argument('--folder');parser.add_argument('--resume');parser.add_argument('--retry-processing',action='store_true');parser.add_argument('--verification-dir');parser.add_argument('--student-index',type=int,choices=[1,2],default=1);parser.add_argument('--request-prefix',default='real-source');parser.add_argument('--browser',action='store_true');a=parser.parse_args()
 if a.serve:serve(Path(a.folder),a.serve,Path(a.verification_dir)if a.verification_dir else None);return 0
 folder=Path(a.resume)if a.resume else ROOT/'artifacts/stage12'/('real-e2e-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
 if not a.resume:folder.mkdir(parents=True);(folder/'data').mkdir();make_catalog(folder)
 assert folder.resolve().is_relative_to(ROOT/'artifacts/stage12')
 output=Path(a.verification_dir)if a.verification_dir else folder
 assert output.resolve().is_relative_to(ROOT/'artifacts/stage12')
 if a.verification_dir:
  assert a.resume and not a.retry_processing,'Reading verification must reuse the retained complete parse'
  output.mkdir(parents=True,exist_ok=True)
 report_path=output/'result.json'
 assert hashlib.file_digest(SOURCE.open('rb'),'sha256').hexdigest()==SHA
 if a.verification_dir and not report_path.exists():
  retained=json.loads((folder/'result.json').read_text())
  report={'status':'running','checks':[],'source_sha256':SHA,'synthetic_accounts_only':True,'real_ocr_requested':False,'reused_complete_parse':True,'ids':retained['ids'],'answers':[],'prior_result':str(folder/'result.json'),'student_index':a.student_index,'request_prefix':a.request_prefix}
 else:report=json.loads(report_path.read_text())if report_path.exists()else{'status':'running','checks':[],'source_sha256':SHA,'synthetic_accounts_only':True,'real_ocr_requested':True,'real_model_enabled':True,'ids':{},'answers':[]}
 if a.resume:save(output/('previous-attempt-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.json'),report)
 report['status']='running';report.pop('error',None);report.pop('error_type',None);report.pop('real_model',None);report['real_model_enabled']=True
 def check(label):
  if label not in report['checks']:report['checks'].append(label)
  save(report_path,report);print(json.dumps({'check':label}),flush=True)
 env=os.environ.copy();env.update(AICADEMIYA_AI_MODE='openai',AICADEMIYA_AI_PROVIDER='aicademiya-router',AICADEMIYA_AI_BASE_URL='http://127.0.0.1:18280/v1',AICADEMIYA_AI_MODEL='AIcademiya-64kx3-Qwen3.8-27B',AICADEMIYA_AI_API_KEY='',AICADEMIYA_WEB_SEARCH_ENABLED='false',TAVILY_API_KEY='',AICADEMIYA_ALLOWED_ORIGINS='',AICADEMIYA_COOKIE_SECURE='false',NO_PROXY='127.0.0.1,localhost,::1',no_proxy='127.0.0.1,localhost,::1')
 for key in ['HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy']:env.pop(key,None)
 for key in ['PYTHONPATH','PYTHONHOME','VIRTUAL_ENV']:env.pop(key,None)
 tunnel=server=None;port=free_port();base=f'http://127.0.0.1:{port}';log=(output/'server.log').open('a',encoding='utf-8');tlog=(output/'tunnel.log').open('a',encoding='utf-8')
 try:
  with socket.socket()as s:s.bind(('127.0.0.1',18280))
  tunnel=subprocess.Popen(['ssh','-N','-T','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ExitOnForwardFailure=yes','-L','127.0.0.1:18280:127.0.0.1:18280','ubuntu-gpu'],stdout=tlog,stderr=subprocess.STDOUT)
  deadline=time.monotonic()+25
  while True:
   try:
    health=httpx.get('http://127.0.0.1:18280/status',trust_env=False,timeout=2).json()
    assert health['model']=='AIcademiya-64kx3-Qwen3.8-27B' and any(w['healthy']for w in health['workers'])
    if health.get('queue')or any(w.get('busy')for w in health['workers']):raise RuntimeError('Teaching router is not idle; no model acceptance call started')
    report['model_workers_at_start']=[{'name':w['name'],'healthy':w['healthy']}for w in health['workers']]
    report['model_runtime_degraded']=not all(w['healthy']for w in health['workers']);break
   except Exception:
    if tunnel.poll()is not None or time.monotonic()>deadline:raise RuntimeError('Owned model tunnel failed')
    time.sleep(.3)
  args=[sys.executable,str(Path(__file__).resolve()),'--serve',str(port),'--folder',str(folder)]
  if a.verification_dir:args+=['--verification-dir',str(output)]
  server=subprocess.Popen(args,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT);ready(server,base)
  save(output/'live.json',{'base_url':base,'server_pid':server.pid,'tunnel_pid':tunnel.pid,'fixture_auth':True,'source':'Actual supplied PDF; no route/model interception'})
  with httpx.Client(base_url=base,trust_env=False,timeout=650)as teacher,httpx.Client(base_url=base,trust_env=False,timeout=650)as student:
   def call(c,method,url,body=None,**kwargs):
    response=c.request(method,url,**({'json':body}if body is not None else{}),**kwargs)
    if response.status_code!=200:raise RuntimeError(f'{method} {url}: {response.status_code} {response.text[:1200]}')
    return response.json()
   call(teacher,'POST','/api/auth/demo',{'role':'teacher'});call(student,'POST','/api/auth/demo',{'role':'student','student_index':a.student_index})
   assert call(teacher,'GET','/api/document-processing')['available'];check('Actual isolated app exposes configured document processing')
   mid=report['ids'].get('material')
   if not mid:
    with SOURCE.open('rb')as f:item=call(teacher,'POST','/api/sessions/s12-session/materials',files={'file':(SOURCE.name,f,'application/pdf')},data={'processing':'full_document','kind':'reading','visibility':'student'})
    mid=item['id'];report['ids']['material']=mid;check('Actual chapter upload accepted and queued; no imported parse fixture')
   ep='/api/materials/'+mid+'/document';deadline=time.monotonic()+3800;next_budget=0
   if a.retry_processing:
    prior=call(teacher,'GET',ep)
    assert prior['latest_job'] and prior['latest_job']['status']=='failed','Retry flag requires an observed failed job'
    call(teacher,'POST',ep+'/jobs',{'request_id':'explicit-recovery-'+uuid.uuid4().hex,'expected_revision':(prior['document']or{}).get('revision_id')})
    check('Explicit processing retry requested after retained failure; no automatic retry')
   while True:
    summary=call(teacher,'GET',ep);job=summary['latest_job'];save(output/'job-readback.json',job)
    if job and job['status']=='failed':raise RuntimeError('Actual SSH/CPU document job failed: '+str(job))
    if job and job['status']=='completed':break
    if time.monotonic()>deadline:raise TimeoutError('Actual document job did not complete within bounded wait')
    if time.monotonic()>next_budget:
     probe=subprocess.run([sys.executable,'tools/ocr_stage1/budget.py'],cwd=ROOT,capture_output=True,text=True,timeout=75);assert probe.returncode==0,probe.stderr
     budget=json.loads(probe.stdout);assert not budget['paused']and budget['remaining_min_percent']>=1;next_budget=time.monotonic()+60
    time.sleep(3)
   doc=summary['document'];assert doc['source_sha256']==SHA and doc['page_count']==10
   parse_root=folder/'data/uploads/documents'/job['id'];receipt=json.loads((parse_root/'receipt.json').read_text())
   report['real_ocr_pages']=sum(x['mode']=='mineru-cpu-local-vlm'for x in receipt.get('page_timings',[]))
   if(parse_root/'raw/recovery.json').exists():report['parse_recovery']=json.loads((parse_root/'raw/recovery.json').read_text())
   pages=[call(teacher,'GET',ep+'/pages/'+str(n),params={'revision_id':doc['revision_id']})for n in range(1,11)]
   assert [p['number']for p in pages]==list(range(1,11));save(output/'parsed-pages.json',pages)
   check('Retained same-source10-page parse reused; no new OCR or dataset reset' if a.verification_dir else 'Validated fresh10-page extraction recovered after transport shutdown failure; original failed attempt retained' if report.get('parse_recovery') else 'Fresh complete10-page bundle committed through actual SSH worker and app validator')
   # Source-reviewed correction layer, explicit and audited, never an OCR claim.
   if not report['ids'].get('reviewed_revision'):
    changes=[]
    verified=json.loads((ROOT/'artifacts/stage12/fresh-chapter/bundle/manifest.json').read_text())
    assert verified['source_sha256']==SHA
    verified_tables={(p['number'],b['text']) for p in verified['pages']for b in p['blocks']if b['quality']=='needs_review'}
    for p in pages:
     for b in p['blocks']:
      if b['quality']=='needs_review':
       assert (p['number'],b['text']) in verified_tables,'Fresh output differs from previously source-checked table; stop for new source review'
       change={'block_id':b['id'],'quality':'approved','reason':'Isolated QA: assistant checked this table against the unchanged original source image; not a human-gold accuracy claim.'}
       if 'Table 5.1.'in b['text']:
        left=['readily available product','easily administered to large groups','streamlined scoring and reporting procedures','a previously validated product (in many cases)'];right=['possibly inappropriate use of such tests','potential test biases','indirect testing may not elicit a good sample of performance','multiple-choice formats have the appearance of authority']
        change['text']='Table 5.1. Advantages and disadvantages of standardized tests\nAdvantages:\n'+'\n'.join('- '+x for x in left)+'\nDisadvantages:\n'+'\n'.join('- '+x for x in right)
       changes.append(change)
    assert len(changes)==5
    receipt=call(teacher,'POST',ep+'/reviews',{'request_id':'qa-source-review','expected_revision':doc['revision_id'],'changes':changes})
    confirmed=call(teacher,'GET',ep+'/reviews/qa-source-review');assert confirmed==receipt
    current=call(teacher,'GET',ep);assert current['document']['revision_id']==receipt['document']['revision_id']
    report['ids']['reviewed_revision']=receipt['document']['revision_id'];check('Explicit source review saved as new revision and independently read back; raw parse retained')
   if not report['ids'].get('version'):
    detail=call(teacher,'GET','/api/sessions/s12-session');questions=detail['questions']
    for q in questions:q['source_material_ids']=[mid];q['source_links']=[]
    call(teacher,'PATCH','/api/sessions/s12-session',{'questions':questions,'teaching_profile':{**detail['teaching_profile'],'phases':['worksheet','wrap_up']}})
    version=call(teacher,'POST','/api/teacher/courses/s12-course/versions/publish',{'label':'Isolated source acceptance'})
    report['ids']['version']=version['id'];check('Explicit synthetic course publication binds reviewed immutable document')
   vid=report['ids']['version'];published_doc=call(student,'GET',ep+'?version_id='+vid)['document'];assert published_doc['revision_id']==report['ids']['reviewed_revision']and published_doc['source_sha256']==SHA
   work=call(student,'POST','/api/sessions/s12-session/tutor/start?version_id='+vid,{'request_id':a.request_prefix+'-start'})
   if a.verification_dir:assert work['attempts']=={} and work['progress']['answered']==0,'Dedicated synthetic learner already has worksheet answers; do not reset retained work'
   questions=['According to Table 5.1, what four advantages of standardized tests are listed? Cite the source.','List the six numbered steps for developing a standardized test, in source order, with source citations.','According to the MELAB speaking rubric, how do the level4 and level2 bands differ? Cite the source; do not grade anyone.','Does the paragraph after the MELAB rubric say standardized tests exclude human judgments? Explain with an exact source citation.']
   questions.append('On printed page121, what is the final annotated bibliography entry and what does its annotation say? Quote the source; do not correct source typos.')
   for index,question in enumerate(questions):
    if any(x['index']==index for x in report['answers']):continue
    budget=json.loads(subprocess.check_output([sys.executable,'tools/ocr_stage1/budget.py'],cwd=ROOT,text=True,timeout=75));assert not budget['paused']and budget['remaining_min_percent']>=1
    work=call(student,'POST','/api/sessions/s12-session/tutor/turn?version_id='+vid,{'request_id':a.request_prefix+'-question-'+str(index),'message':question})
    message=work['messages'][-1];citations=[c for c in message.get('citations',[])if c.get('kind')=='document'];assert citations,'Real answer has no exact document citations'
    for c in citations:
     assert c['material_id']==mid and c['revision_id']==report['ids']['reviewed_revision'] and c['version_id']==vid
     response=student.get(c['url'].split('#')[0]);assert response.status_code==200 and response.headers['content-type'].startswith('application/pdf')
    if a.verification_dir:
     assert work['attempts']=={}and work['progress']['answered']==0 and work['tutor']['phase']=='worksheet'
     assert message['intent']=='ask'and all(q['answer_count']==0 for q in work['tutor']['question_states'].values())
    report['answers'].append({'index':index,'question':question,'message':message,'learning_state':{'phase':work['tutor']['phase'],'answered':work['progress']['answered'],'attempts':work['attempts']}});check('Actual local-model answer and authenticated source links '+str(index+1))
   if a.browser:
    save(report_path,report)
    browser=subprocess.run(['node','tools/stage12_real_browser.mjs','--base-url',base,'--artifact-dir',str(output/'browser'),'--ids-file',str(report_path),'--student-index',str(a.student_index),'--citations-only'],cwd=ROOT,env=env,capture_output=True,text=True,timeout=240)
    (output/'browser.log').write_text(browser.stdout+'\n'+browser.stderr,encoding='utf-8')
    assert browser.returncode==0,'Actual citation browser check failed; inspect retained browser result'
    check('Actual stored citations clicked through mobile nested chat to authenticated native PDF; no provider calls by browser')
   report['status']='passed';report['semantic_review_pending']=True;check('Real upload-to-citation protocol gates passed; parent semantic/browser review still required')
 except BaseException as e:
  report.update(status='failed',error_type=type(e).__name__,error=str(e));print(json.dumps({'status':'failed','error':str(e)}),flush=True)
 finally:
  if tunnel and tunnel.poll()is None:
   try:
    health=httpx.get('http://127.0.0.1:18280/status',trust_env=False,timeout=10).json()
    report['model_workers_at_finish']=[{'name':w['name'],'healthy':w['healthy'],'metrics':w.get('metrics')}for w in health['workers']]
   except Exception:report['model_status_readback_failed']=True
  if server:stop(server)
  if tunnel:
   tunnel.terminate()
   try:tunnel.wait(timeout=15)
   except subprocess.TimeoutExpired:tunnel.kill();tunnel.wait(timeout=10)
  log.close();tlog.close();report['server_closed']=bool(server and server.poll()is not None and listener_closed(port));report['tunnel_closed']=bool(tunnel and tunnel.poll()is not None and listener_closed(18280));report['real_model_calls']=len((output/'model-exchanges.jsonl').read_text().splitlines())if(output/'model-exchanges.jsonl').exists()else 0;save(report_path,report)
  print(json.dumps({'status':report['status'],'result':str(report_path),'checks':len(report['checks']),'server_closed':report['server_closed'],'tunnel_closed':report['tunnel_closed']}),flush=True)
 return 0 if report['status']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
