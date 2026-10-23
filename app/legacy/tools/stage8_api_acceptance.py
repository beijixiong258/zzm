"""Actual HTTP/SQLite course lifecycle checks on explicitly confirmed isolated data."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit
import argparse,json,os,sqlite3,time,traceback
import httpx
PROFILE={'schema_version':1,'background':'Synthetic QA','student_profile':'','response_strategies':'Concise hints','tone':'Specific','response_detail':'concise','phases':['worksheet','wrap_up'],'reading_focus':'','reading_question_count':1,'reference_delivery':'on_request','idle_hint_seconds':0,'presentation':'full'}
def records(path,exclude=('course_trash',)):
 if not path:return None
 with sqlite3.connect(f'file:{Path(path).as_posix()}?mode=ro',uri=True) as c:
  tables=[r[0]for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name") if r[0]not in exclude]
  return {t:sorted(json.dumps(list(r),ensure_ascii=False,default=str)for r in c.execute('SELECT * FROM "'+t+'"'))for t in tables}
def main():
 p=argparse.ArgumentParser();p.add_argument('--base-url',required=True);p.add_argument('--artifact-dir',required=True);p.add_argument('--confirm-test-data',action='store_true');a=p.parse_args();assert a.confirm_test_data and urlsplit(a.base_url).port!=18773
 out=Path(a.artifact_dir);out.mkdir(parents=True,exist_ok=True);db=os.environ.get('AICADEMIYA_QA_DB');checks=[];events=[];ids={};failures=[];clients=[httpx.Client(base_url=a.base_url,trust_env=False,timeout=90)for _ in range(4)];teacher,student,other,anon=clients
 def call(client,method,url,body=None,expected=200,**kwargs):
  r=client.request(method,url,json=body,**kwargs);events.append({'method':method,'path':url,'status':r.status_code});assert r.status_code==expected,f'{method} {url}: expected {expected}, got {r.status_code}'
  return r.json() if r.headers.get('content-type','').startswith('application/json')else r
 def check(name,condition=True):
  assert condition,name
  if not db and any(term in name for term in ('table','no-op','no writes','before account/enrollment creation')):
   name += ' [HTTP assertions only; local SQLite row equality unavailable]'
  checks.append(name)
 try:
  boot=call(anon,'GET','/api/bootstrap');check('Explicit synthetic target is Stage8, not production',boot['demo_enabled'] and call(anon,'GET','/openapi.json')['info']['version']==os.environ.get('AICADEMIYA_QA_TARGET_API','0.7.0'))
  for c,role in ((teacher,'teacher'),(student,'student'),(other,'admin')):call(c,'POST','/api/auth/demo',{'role':role})
  c=call(teacher,'POST','/api/courses',{'code':'S8-A','title':'Synthetic lifecycle target','description':'Original synthetic description'});cid=c['id'];original_invite=c['join_code'];ids['target_course']=cid
  control=call(teacher,'POST','/api/courses',{'code':'S8-B','title':'Synthetic unaffected control'});bid=control['id'];ids['control_course']=bid
  s=call(teacher,'POST',f'/api/courses/{cid}/sessions',{'title':'Synthetic lifecycle lesson','teaching_profile':PROFILE});sid=s['id'];ids['session']=sid
  q={'id':'life-q','group_id':'core','ordinal':1,'type':'open_response','prompt':'Explain one assessment principle.','options':[],'answer_slots':1,'images':[],'source_label':'Synthetic question'}
  call(teacher,'PATCH',f'/api/sessions/{sid}',{'status':'published','groups':[{'id':'core','title':'Core','kind':'core'}],'questions':[q],'reference_answers':{'life-q':'Synthetic private reference'}})
  public=call(teacher,'POST',f'/api/sessions/{sid}/materials',files={'file':('Synthetic public.txt',b'Synthetic public material kept byte for byte.','text/plain')},data={'visibility':'student','kind':'reading'})
  private=call(teacher,'POST',f'/api/sessions/{sid}/materials',files={'file':('Synthetic private.txt',b'Synthetic private material stays private.','text/plain')},data={'visibility':'teacher','kind':'reference'})
  bsession=call(teacher,'POST',f'/api/courses/{bid}/sessions',{'title':'Synthetic control lesson','teaching_profile':PROFILE})['id'];call(teacher,'PATCH',f'/api/sessions/{bsession}',{'status':'published','groups':[{'id':'core','title':'Core','kind':'core'}],'questions':[q]})
  bv=call(teacher,'POST',f'/api/teacher/courses/{bid}/versions/publish',{'label':'Control'})['id'];v1=call(teacher,'POST',f'/api/teacher/courses/{cid}/versions/publish',{'label':'Before metadata edit'})['id'];ids['version_before_edit']=v1
  for x in (c,control):call(student,'POST','/api/courses/join',{'join_code':x['join_code']})
  for ss,vv in ((sid,v1),(bsession,bv)):call(student,'POST',f'/api/sessions/{ss}/answers/life-q?version_id={vv}',{'answer':'Synthetic saved original response'})
  old_snapshot=call(teacher,'GET',f'/api/teacher/courses/{cid}/versions/{v1}');student_work=call(student,'GET',f'/api/sessions/{sid}/workspace?version_id={v1}')
  detail=call(teacher,'GET',f'/api/courses/{cid}');check('Owner details expose real impact counts and unchanged invitation identity',detail['session_count']==1 and detail['material_count']==2 and detail['enrollment_count']==1 and detail['join_code']==original_invite and detail['trashed_at'] is None)
  before=records(db,())
  for actor,expected in ((anon,401),(student,403),(other,403)):
   for method,url,body in [('GET',f'/api/courses/{cid}',None),('PATCH',f'/api/courses/{cid}',{'title':'Denied'}),('POST',f'/api/courses/{cid}/trash',{}),('POST',f'/api/courses/{cid}/restore',{})]:call(actor,method,url,body,expected)
  call(anon,'GET','/api/courses/trash',expected=401);call(student,'GET','/api/courses/trash',expected=403);check('Course ownership beats global admin privilege; denied operations do not write',not db or records(db,())==before)
  for payload in ({'title':'  '},{'code':''},{'code':'X'*51},{'title':'X'*301},{'description':'X'*10001},{'owner_id':'demo-admin'},{'join_code':'new-invite'},{'published_version_id':'fake'}):call(teacher,'PATCH',f'/api/courses/{cid}',payload,422)
  check('Metadata validation forbids blank/oversized values and relational-field edits',not db or records(db,())==before)
  changed={'code':'S8 / renamed','title':'Synthetic renamed course','description':'Line one\nLine two'};call(teacher,'PATCH',f'/api/courses/{cid}',changed)
  read=call(teacher,'GET',f'/api/courses/{cid}');check('Metadata PATCH persists exactly with independent GET',all(read[k]==v for k,v in changed.items()) and read['id']==cid and read['join_code']==original_invite and read['has_unpublished_changes'])
  student_course=next(x for x in call(student,'GET','/api/courses')if x['id']==cid);check('Saved metadata is draft-only until explicit publication',student_course['code']==c['code'] and student_course['title']==c['title'] and call(teacher,'GET',f'/api/teacher/courses/{cid}/versions/{v1}')==old_snapshot)
  v2=call(teacher,'POST',f'/api/teacher/courses/{cid}/versions/publish',{'label':'Metadata published'})['id'];ids['version_after_edit']=v2
  student_course=next(x for x in call(student,'GET','/api/courses')if x['id']==cid);check('Publication exposes new metadata without rewriting the old edition or work',student_course['title']==changed['title'] and v2!=v1 and call(teacher,'GET',f'/api/teacher/courses/{cid}/versions/{v1}')==old_snapshot and call(student,'GET',f'/api/sessions/{sid}/workspace?version_id={v1}')['attempts']==student_work['attempts'])
  preview=call(teacher,'GET',f'/api/teacher/sessions/{sid}/preview');pw=call(teacher,'POST',f'/api/teacher/sessions/{sid}/preview/reset',{'expected_revision':preview['current_revision']});pid=pw['preview']['id'];call(teacher,'POST',f'/api/sessions/{sid}/tutor/start',{'request_id':'s8-opening','preview_id':pid})
  if os.environ.get('AICADEMIYA_QA_CONTROL')=='true':
   hold=out/'hold-demo-pending';hold.write_text('explicit synthetic hold')
   try:
    with ThreadPoolExecutor(max_workers=1)as pool:
     future=pool.submit(call,teacher,'POST',f'/api/sessions/{sid}/tutor/turn',{'request_id':'s8-pending','preview_id':pid,'message':'SYNTHETIC_QA_PENDING wrong answer','web_search':False})
     deadline=time.monotonic()+12
     while not call(teacher,'GET',f'/api/teacher/sessions/{sid}/preview')['pending']:
      assert time.monotonic()<deadline;time.sleep(.03)
     pending_rows=records(db,());call(teacher,'POST',f'/api/courses/{cid}/trash',{},409);check('In-flight actual guided HTTP request blocks trash atomically, no table mutation',not db or records(db,())==pending_rows)
     hold.unlink();future.result(timeout=20)
   finally:
    if hold.exists():hold.unlink()
  call(teacher,'PATCH',f'/api/sessions/{sid}',{'active':False})
  before=records(db);public_bytes=call(teacher,'GET',public['download_url']).content;private_bytes=call(teacher,'GET',private['download_url']).content;raw_before=call(teacher,'GET',f'/api/teacher/sessions/{sid}/students/demo-student-1/workspace?version_id={v1}')
  trashed=call(teacher,'POST',f'/api/courses/{cid}/trash',{});check('Trash is a marker only; all original tables remain byte-for-byte logically equal',bool(trashed['trashed_at']) and (not db or records(db)==before))
  check('Owner trash listing shows only their course; normal lists hide it',any(x['id']==cid for x in call(teacher,'GET','/api/courses/trash')['courses']) and all(x['id']!=cid for x in call(teacher,'GET','/api/courses')) and all(x['id']!=cid for x in call(student,'GET','/api/courses')) and not any(x['id']==cid for x in call(other,'GET','/api/courses/trash')['courses']))
  again=call(teacher,'POST',f'/api/courses/{cid}/trash',{});check('Repeated trash is idempotent and keeps original timestamp',again['trashed_at']==trashed['trashed_at'] and (not db or records(db)==before))
  call(student,'POST','/api/courses/join',{'join_code':original_invite},404)
  call(anon,'POST','/api/auth/register',{'name':'Synthetic blocked signup','email':'s8-blocked@example.invalid','password':'SyntheticOnly123','join_code':original_invite},404)
  check('Trashed invitation rejects join and signup before account/enrollment creation',not db or records(db)==before)
  endpoints=[('GET',f'/api/courses/{cid}/sessions',None),('POST',f'/api/courses/{cid}/sessions',{'title':'Denied'}),('PATCH',f'/api/courses/{cid}',{'title':'Denied'}),('GET',f'/api/sessions/{sid}',None),('GET',f'/api/sessions/{sid}/workspace',None),('POST',f'/api/sessions/{sid}/tutor/start',{'request_id':'s8-opening','preview_id':pid}),('GET',f'/api/sessions/{sid}/transcript?format=txt',None),('GET',f'/api/courses/{cid}/materials',None),('GET',public['download_url'],None),('GET',private['preview_url'],None),('GET',f'/api/teacher/courses/{cid}/versions',None),('POST',f'/api/teacher/courses/{cid}/versions/publish',{}),('POST',f'/api/teacher/courses/{cid}/versions/{v1}/restore',{})]
  for method,url,body in endpoints:call(teacher,method,url,body,410)
  for method,url,body in [('GET',f'/api/sessions/{sid}/workspace?version_id={v1}',None),('POST',f'/api/sessions/{sid}/answers/life-q?version_id={v2}',{'answer':'Denied'}),('GET',public['download_url']+'?version_id='+v1,None),('POST',f'/api/sessions/{sid}/submit?version_id={v2}',{})]:call(student,method,url,body,410)
  check('Owner/student current and historical deep paths, files and mutation APIs are closed',not db or records(db)==before)
  history=call(student,'GET','/api/history');check('Other courses/history remain usable while trashed course is omitted',all(x['course']['id']!=cid for x in history) and any(x['course']['id']==bid for x in history) and call(student,'GET',f'/api/sessions/{bsession}/workspace?version_id={bv}')['attempts']['life-q']['answer']=='Synthetic saved original response')
  restored=call(teacher,'POST',f'/api/courses/{cid}/restore',{});check('Restore keeps ID/invite/content/learning/preview rows and does not publish',restored['id']==cid and restored['join_code']==original_invite and restored['trashed_at'] is None and restored['published_version_id']==v2 and (not db or records(db)==before))
  call(teacher,'POST',f'/api/courses/{cid}/restore',{});check('Repeated restore is a no-op and original session availability survives',call(teacher,'GET',f'/api/sessions/{sid}')['active'] is False and (not db or records(db)==before))
  check('Files and historical learning read back exactly after restore',call(teacher,'GET',public['download_url']).content==public_bytes and call(teacher,'GET',private['download_url']).content==private_bytes and call(teacher,'GET',f'/api/teacher/sessions/{sid}/students/demo-student-1/workspace?version_id={v1}')['messages']==raw_before['messages'] and call(teacher,'GET',f'/api/teacher/sessions/{sid}/preview')['id']==pid)
  call(student,'POST','/api/courses/join',{'join_code':original_invite});check('Original invitation works again without duplicate enrollment',call(teacher,'GET',f'/api/courses/{cid}')['enrollment_count']==1)
  final=call(teacher,'POST',f'/api/courses/{cid}/trash',{});ids['final_trashed_at']=final['trashed_at'];check('Final trash state prepared for true process restart verification',bool(final['trashed_at']))
 except Exception as e:failures.append({'error':str(e),'traceback':traceback.format_exc()})
 finally:
  for c in clients:c.close()
  report={'status':'passed'if not failures else'failed','checks':checks,'failures':failures,'ids':ids,'events':events,'real_http':True,'sqlite_inspected':bool(db),'synthetic_only':True,'model_search_evidence':'No actual model/search. Pending uses explicitly held demo adapter.'};(out/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'status':report['status'],'checks':len(checks),'failures':failures},ensure_ascii=False))
 return 0 if not failures else 1
if __name__=='__main__':raise SystemExit(main())
