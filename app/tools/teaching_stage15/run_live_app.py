"""Isolated actual app routes + real GPU vision teaching through an owned tunnel.
Imports byte-verified archived REAL extraction results (not a fake processor or
fresh OCR claim). Synthetic accounts/course only; every model reply is live HTTP.
"""
from pathlib import Path
import argparse,base64,hashlib,json,os,shutil,sys,time,uuid
APP=Path(__file__).resolve().parents[2];sys.path[:0]=[str(APP),str(APP/'tools')]

def main():
 cli=argparse.ArgumentParser();cli.add_argument('--output',required=True);cli.add_argument('--resume');cli.add_argument('--tasks',default='prose,table,image,summary,generation');cli.add_argument('--installed-router',action='store_true');a=cli.parse_args();out=Path(a.output).resolve();out.mkdir(exist_ok=False)
 selected_tasks=set(a.tasks.split(','));qa_base=Path(a.resume).resolve()if a.resume else out
 os.environ.update(AICADEMIYA_DATA_DIR=str(out/'import-data'),AICADEMIYA_DEMO_ENABLED='true',AICADEMIYA_AI_MODE='openai',AICADEMIYA_AI_PROVIDER='aicademiya-router',AICADEMIYA_AI_BASE_URL='http://127.0.0.1:18280/v1',AICADEMIYA_AI_MODEL='AIcademiya-64kx3-Qwen3.8-27B',AICADEMIYA_AI_API_KEY='',AICADEMIYA_DOCUMENT_FORMATS='png,pdf',AICADEMIYA_WEB_SEARCH_ENABLED='false',TAVILY_API_KEY='')
 from fastapi.testclient import TestClient
 import httpx
 from backend.aicademiya.main import create_app
 from backend.aicademiya.document_bundle import sha256_file,validate_bundle
 from backend.aicademiya.authoring import selected_tutor_materials
 from backend.aicademiya.version_context import session_access
 from backend.aicademiya.guided_state import load_state
 from backend.aicademiya.guided_director import direct
 from run_stage12_real_reading import make_catalog
 fixture=qa_base/'fixture'
 if not a.resume:fixture.mkdir();make_catalog(fixture)
 old=APP/'artifacts/stage15/material-adapter/real10/bundles';new=APP/'artifacts/stage15/integrated-inputs'
 source=Path('C:/Users/17193/Desktop/AIcademiya-27B图文实测-20261012-113346/minimal-final/input')
 specs=[('s15-lesson.png','01-native-page126',new),('s15-method-trait.png','04-scan-page9',new),('s15-rubric.png','07-sample14',new),('s15-jumbled.png','05-sample23',old)]
 sources={};by_sha={}
 for name,stem,bundle_base in specs:
  image=source/(stem+'.png');bundle=bundle_base/stem;m=json.loads((bundle/'manifest.json').read_text());digest=sha256_file(image);assert digest==m['source_sha256'];validate_bundle(bundle,digest,1)
  sources[name]={'file':image,'bundle':bundle,'sha256':digest};by_sha[digest]=sources[name]
 report={'status':'running','scope':'Actual ASGI application routes and live GPU model; synthetic accounts, archived actual source-extraction import','not_production_router_acceptance':not a.installed_router,'fresh_ocr_calls':0,'ids':{},'turns':[],'provider_calls':[]}
 if a.resume:
  previous=json.loads((qa_base/'result.json').read_text());report.update(ids=previous['ids'],version_id=previous['version_id'],resumed_data=str(qa_base),prior_results_preserved=True)
 def save():(out/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 class ArchiveImporter:
  def __call__(self,input_file,destination,cancelled):
   if cancelled.is_set():raise RuntimeError('Import cancelled')
   bound=by_sha.get(sha256_file(input_file))
   if bound is None:raise ValueError('No exact archived real extraction for this input')
   shutil.copytree(bound['bundle'],destination);validate_bundle(destination,bound['sha256'],1)
 class Recorder(httpx.BaseTransport):
  def __init__(self):self.real=httpx.HTTPTransport(retries=0,trust_env=False)
  def handle_request(self,request):
   body=json.loads(request.content);row={'request':body,'real_HTTP':True,'image_sha256':[]};began=time.monotonic()
   for m in body['messages']:
    if isinstance(m.get('content'),list):
     for p in m['content']:
      if p.get('type')=='image_url':
       blob=base64.b64decode(p['image_url']['url'].split(',',1)[1],validate=True);digest=hashlib.sha256(blob).hexdigest();assert digest in by_sha;row['image_sha256'].append(digest)
   try:
    response=self.real.handle_request(request);response.read();row['status_code']=response.status_code;row['router_headers']={k:response.headers.get(k)for k in ('X-AIcademiya-Worker','X-Queue-Seconds','X-KV-Restored')}
    if a.installed_router and response.status_code==200:
     assert row['router_headers']['X-AIcademiya-Worker']in ('v100','t10a','t10b'),'Actual installed-router worker header missing'
     if row['image_sha256']:assert row['router_headers']['X-AIcademiya-Worker']=='t10b'and row['router_headers']['X-KV-Restored']=='false'
    try:row['response']=response.json()
    except ValueError:row['response_text']=response.text[:4000]
    return response
   except BaseException as e:row['error_type']=type(e).__name__;raise
   finally:
    row['seconds']=time.monotonic()-began
    with(out/'model-exchanges.jsonl').open('a',encoding='utf-8')as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    report['provider_calls'].append({'index':len(report['provider_calls'])+1,'status_code':row.get('status_code'),'images':row['image_sha256'],'seconds':row['seconds'],'router_headers':row.get('router_headers'),'finish_reason':(row.get('response',{}).get('choices')or[{}])[0].get('finish_reason')});save()
  def close(self):pass # Short-lived Tutor clients share this recording transport.
 transport=Recorder();app=create_app(data_dir=qa_base/'data',catalog_path=fixture/'catalog.json',frontend_dir=APP/'frontend/dist',demo_enabled=True,document_processor=ArchiveImporter(),ai_transport=transport)
 def call(c,method,path,body=None,**kw):
  r=c.request(method,path,**({'json':body}if body is not None else{}),**kw)
  if r.status_code!=200:raise RuntimeError(f'{method} {path}: {r.status_code} {r.text[:2000]}')
  return r.json()
 student=TestClient(app)
 try:
  with TestClient(app)as teacher:
   call(teacher,'POST','/api/auth/demo',{'role':'teacher'});user=call(student,'POST','/api/auth/demo',{'role':'student'})['user']
   assert call(teacher,'GET','/api/bootstrap')['ai']['mode']=='openai'
   for name,info in sources.items():
    if a.resume:
     summary=call(teacher,'GET','/api/materials/'+report['ids'][name]+'/document');assert summary['document']['source_sha256']==info['sha256'];info['revision_id']=summary['document']['revision_id'];continue
    with info['file'].open('rb')as f:material=call(teacher,'POST','/api/sessions/s12-session/materials',files={'file':(name,f,'image/png')},data={'processing':'full_document','kind':'reading','visibility':'student'})
    mid=material['id'];report['ids'][name]=mid;save();deadline=time.monotonic()+60
    while True:
     summary=call(teacher,'GET','/api/materials/'+mid+'/document');job=summary['latest_job']
     if job and job['status']=='failed':raise RuntimeError('Archived-source application import failed: '+str(job))
     if job and job['status']=='completed':break
     if time.monotonic()>deadline:raise TimeoutError('Source import completion')
     time.sleep(.05)
    assert summary['document']['source_sha256']==info['sha256'];info['revision_id']=summary['document']['revision_id']
   if not a.resume:
    detail=call(teacher,'GET','/api/sessions/s12-session');questions=detail['questions']
    for q in questions:q['source_material_ids']=list(report['ids'].values());q['source_links']=[]
    call(teacher,'PATCH','/api/sessions/s12-session',{'questions':questions,'teaching_language':'en','teaching_profile':{**detail['teaching_profile'],'phases':['worksheet','wrap_up']}})
    version=call(teacher,'POST','/api/teacher/courses/s12-course/versions/publish',{'label':'Isolated Stage15 actual vision teaching references'})['id'];report['version_id']=version;save()
    work=call(student,'POST','/api/sessions/s12-session/tutor/start',{'request_id':'stage15-start'},params={'version_id':version})
   else:
    version=report['version_id'];work=call(student,'GET','/api/sessions/s12-session/workspace',params={'version_id':version})
   cases=[('prose','s15-lesson.png','What prior learning and teaching materials are listed in s15-lesson.png? Answer from that source, not general teaching advice. Cite the source.'),
    ('table','s15-method-trait.png','Using the original table image in s15-method-trait.png, how are Grammar, Discourse and Sociolinguistic traits assessed by Multiple-choice? State the exact item count for each trait and cite the original image.'),
    ('image','s15-jumbled.png','Look at the original image in s15-jumbled.png. Explain what the learner is asked to do in the first exercise. Do not solve the jumbled words or provide any answer. Cite the original image.'),
    ('summary','s15-rubric.png','Summarize the differences between Excellent, Good, Marginal/Fair and Poor/Weak speakers in s15-rubric.png, covering all four bands and retaining the band labels. Base this on the supplied rubric and cite the source.')]
   for kind,name,message in cases:
    if kind not in selected_tasks:continue
    before=len(report['provider_calls']);request={'request_id':out.name+'-'+kind,'message':message};work=call(student,'POST','/api/sessions/s12-session/tutor/turn',request,params={'version_id':version});last=work['messages'][-1]
    assert work['attempts']=={}and work['progress']['answered']==0
    if a.resume and kind=='image':assert not any(w in last['content'].casefold()for w in ('trousers','jeans','shoes','jacket')),'Instruction-only reply named a pictured target object'
    citations=[c for c in last['citations']if c.get('material_id')==report['ids'][name]];assert citations,'No source citation for requested material'
    for c in citations:
     assert c['revision_id']==sources[name]['revision_id']and c['version_id']==version
     assert student.get(c['url'].split('#')[0]).status_code==200
    sent=[h for row in report['provider_calls'][before:]for h in row['images']]
    if kind in ('table','image'):assert sources[name]['sha256']in sent,'Requested original image did not enter the real model HTTP request'
    calls=len(report['provider_calls']);again=call(student,'POST','/api/sessions/s12-session/tutor/turn',request,params={'version_id':version});assert len(report['provider_calls'])==calls and again['messages'][-1]==last
    report['turns'].append({'kind':kind,'source':name,'request':message,'message':last,'image_sha256_sent':sent,'source_citations_valid':True,'quality_review':'pending_parent_source_comparison'});save()
   # Exercise the same source-grounded generation function used by the app.
   # This does not forge student progression or create formal grades.
   if 'generation'in selected_tasks:
    with app.state.database.connect()as conn:
     detail=session_access(conn,'s12-session',user,version_id=version);state=load_state(conn,detail,user);public,private=selected_tutor_materials(conn,detail,None);settings=app.state.tutor.settings(conn)
    state={**state,'phase':'quiz','quiz_items':[]};before=len(report['provider_calls'])
    generated,citations=direct(app.state.tutor,settings,work,detail,state,{'message':'Create five practice questions about the methods and traits in s15-method-trait.png. Inspect its original table image and cite the source.'},None,public,task='quiz_generate',private_materials=private)
    assert len(generated.items)==5 and citations
    assert 'correct answer'not in generated.text.casefold()and all(i.prompt not in generated.text for i in generated.items),'Private generated exercise content leaked into the public introduction'
    assert sources['s15-method-trait.png']['sha256']in[h for row in report['provider_calls'][before:]for h in row['images']]
    report['generation']={'scope':'actual app generator function, not a fabricated student transition','result':generated.model_dump(),'citations':citations,'quality_review':'pending_parent_source_comparison'}
   report.update(status='real_app_model_exercised_requires_source_review',synthetic_accounts_only=True,provider_transport_mocked=False);save()
 except BaseException as e:report.update(status='failed',error_type=type(e).__name__,error=str(e));save();raise
 finally:student.close();transport.real.close();report['app_queue_closed']=app.state.document_queue.thread is None;save();print(json.dumps({'status':report['status'],'result':str(out/'result.json'),'provider_calls':len(report['provider_calls']),'turns':len(report['turns']),'error':report.get('error')},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
