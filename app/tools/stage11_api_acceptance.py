"""Stage11 actual HTTP accounts/staff/roster/role/retention acceptance, synthetic only."""
from pathlib import Path
from io import BytesIO, StringIO
import argparse,csv,json,secrets,os,sqlite3,traceback
from urllib.parse import urlsplit
import httpx
from openpyxl import Workbook

def main():
 p=argparse.ArgumentParser();p.add_argument('--base-url',required=True);p.add_argument('--artifact-dir',required=True);p.add_argument('--confirm-test-data',action='store_true');a=p.parse_args();assert a.confirm_test_data and urlsplit(a.base_url).port!=18773
 out=Path(a.artifact_dir);out.mkdir(parents=True,exist_ok=True);checks=[];events=[];failures=[];ids={};clients=[]
 def client():
  c=httpx.Client(base_url=a.base_url,trust_env=False,timeout=45);clients.append(c);return c
 admin,teacher,student,other,anon=[client()for _ in range(5)]
 def call(c,method,path,body=None,expected=200,**kw):
  r=c.request(method,path,**({'json':body}if body is not None else{}),**kw);events.append({'method':method,'path':path,'status':r.status_code});allowed=expected if isinstance(expected,tuple)else(expected,);assert r.status_code in allowed,f'{method} {path}: {r.status_code} expected{allowed}'
  return r.json()if r.headers.get('content-type','').startswith('application/json')else r
 def check(label,condition=True):assert condition,label;checks.append(label)
 def demo(c,role,index=1):return call(c,'POST','/api/auth/demo',{'role':role,'student_index':index})['user']
 token=secrets.token_hex(5);temporary=secrets.token_urlsafe(24)+'A1';newpassword=secrets.token_urlsafe(24)+'B2'
 def create(role,name):
  body={'name':name,'email':role+'-'+secrets.token_hex(6)+'@example.invalid','role':role,'temporary_password':temporary};u=call(admin,'POST','/api/admin/users',body)['user'];saved=call(admin,'GET','/api/admin/users/'+u['id']);assert saved['user']==u and u['role']==role and u['must_change_password'];return u
 def activate(u):
  c=client();v=call(c,'POST','/api/auth/login',{'email':u['email'],'password':temporary})['user'];assert v['must_change_password'];call(c,'POST','/api/auth/change-password',{'current_password':temporary,'new_password':newpassword});assert not call(c,'GET','/api/auth/me')['user']['must_change_password'];return c
 def counts(c,cid):return next(x for x in call(c,'GET','/api/courses')if x['id']==cid)
 try:
  boot=call(anon,'GET','/api/bootstrap');target=os.environ.get('AICADEMIYA_QA_TARGET_API','0.9.0');assert target in ('0.9.0','0.10.0');assert boot['demo_enabled'];assert call(anon,'GET','/openapi.json')['info']['version']==target;check('Explicit isolated API'+target+' runtime, no production writes')
  au=demo(admin,'admin');tu=demo(teacher,'teacher');su=demo(student,'student');ou=demo(other,'student',2)
  for c,status in [(anon,401),(teacher,403),(student,403)]:
   call(c,'GET','/api/admin/users',expected=status);call(c,'POST','/api/admin/users',{'name':'Denied','email':'denied@example.invalid','role':'admin','temporary_password':temporary},status)
  cid=call(teacher,'GET','/api/courses')[0]['id'];session=call(teacher,'GET',f'/api/courses/{cid}/sessions')[0];sid=session['id'];detail=call(teacher,'GET',f'/api/sessions/{sid}');qid=detail['questions'][0]['id'];figure=detail['questions'][0]['images'][0]['url']
  call(anon,'GET',figure,expected=401);call(admin,'GET',f'/api/courses/{cid}/sessions',expected=403)
  light=call(admin,'GET','/api/admin/courses')['courses'];assert cid in {x['id']for x in light};assert not {'description','join_code','materials'}&set(light[0]);check('Global administrators see assignment metadata, not unassigned teaching content; old figure authentication retained')
  teacher2=create('teacher','Synthetic Second Teacher');admin2=create('admin','Synthetic Second Admin');learner=create('student','Synthetic Global Student');tc=activate(teacher2);ac=activate(admin2);lc=activate(learner)
  call(tc,'GET',f'/api/courses/{cid}/sessions',expected=403);check('Create each global role with forced password change; staff role alone grants no course permission')
  for u in (teacher2,admin2):call(admin,'POST',f'/api/courses/{cid}/staff',{'user_id':u['id']})
  staff=call(admin,'GET',f'/api/courses/{cid}/staff');assert {tu['id'],teacher2['id'],admin2['id']}=={x['user']['id']for x in staff['staff']};c=counts(tc,cid);assert(c['admin_count'],c['teacher_count'],c['student_count'])==(1,2,2)
  call(tc,'GET',f'/api/courses/{cid}/sessions');call(ac,'GET',f'/api/sessions/{sid}');call(tc,'GET',figure);call(tc,'POST',f'/api/courses/{cid}/staff',{'user_id':au['id']},403);call(student,'GET',f'/api/courses/{cid}/staff',expected=403);check('Two Teachers and an Admin co-manage the assigned course; exact operational counts and colleague privilege boundary hold')
  second=call(teacher,'POST','/api/courses',{'code':'EDUC1145','title':'Synthetic separate course','description':'Separate\ncourse scope.'});cid2=second['id'];call(tc,'GET',f'/api/teacher/courses/{cid2}/students',expected=403)
  for course_id in (cid,cid2):call(teacher,'POST',f'/api/teacher/courses/{course_id}/students',{'name':'Do not overwrite name','email':learner['email'],'temporary_password':''})
  assert call(admin,'GET','/api/admin/users/'+learner['id'])['user']['name']==learner['name'];call(lc,'GET','/api/auth/me');check('Known Student joins two courses without password/name reset; co-teacher has no unrelated-course roster access')
  before=counts(teacher,cid)['student_count'];call(tc,'POST',f'/api/teacher/courses/{cid}/students/archive',{'user_ids':[learner['id']]});assert counts(teacher,cid)['student_count']==before-1;assert learner['id'] in {x['user']['id']for x in call(teacher,'GET',f'/api/teacher/courses/{cid2}/students')};assert call(lc,'GET','/api/auth/me')['user']['id']==learner['id'];call(tc,'POST',f'/api/teacher/courses/{cid}/students/restore',{'user_ids':[learner['id']]});assert counts(teacher,cid)['student_count']==before;check('Teacher course removal/restoration updates only that enrollment, preserves other course and global login')
  work=call(other,'GET',f'/api/sessions/{sid}/workspace');vid=work['version']['id'];answer='Synthetic preserved learner answer';call(other,'POST',f'/api/sessions/{sid}/answers/{qid}?version_id={vid}',{'answer':answer});base_students=counts(teacher,cid)['student_count']
  call(admin,'PATCH','/api/admin/users/'+ou['id'],{'role':'teacher'});call(other,'GET','/api/auth/me',expected=401);demo(other,'student',2);call(other,'GET',f'/api/sessions/{sid}',expected=403);assert counts(teacher,cid)['student_count']==base_students-1
  call(admin,'PATCH','/api/admin/users/'+ou['id'],{'role':'student'});demo(other,'student',2);assert call(other,'GET',f'/api/sessions/{sid}/workspace?version_id={vid}')['attempts'][qid]['answer']==answer;check('Global role changes revoke only target sessions, do not turn enrollment into staff privilege, and preserve actual saved learner answer')
  for method,url,body in [('PATCH','/api/admin/users/'+au['id'],{'role':'student'}),('PUT','/api/admin/users/'+au['id']+'/status',{'active':False}),('DELETE',f'/api/courses/{cid}/staff/'+tu['id'],None),('PATCH','/api/admin/users/'+tu['id'],{'role':'student'}),('PUT','/api/admin/users/'+tu['id']+'/status',{'active':False})]:call(admin,method,url,body,409)
  call(admin,'PUT',f'/api/courses/{cid}/staff/primary',{'user_id':teacher2['id']});assert call(admin,'GET',f'/api/courses/{cid}/staff')['course']['owner_id']==teacher2['id'];call(admin,'DELETE',f'/api/courses/{cid}/staff/'+tu['id']);call(teacher,'GET',f'/api/sessions/{sid}',expected=403);call(admin,'POST',f'/api/courses/{cid}/staff',{'user_id':tu['id']});call(admin,'PUT',f'/api/courses/{cid}/staff/primary',{'user_id':tu['id']});check('Self/primary safety guards reject unsafe actions; explicit primary transfer/removal enforces revocation and can be restored')
  call(admin,'PUT','/api/admin/users/'+learner['id']+'/status',{'active':False});call(lc,'GET','/api/auth/me',expected=401);disabled=call(admin,'GET','/api/admin/users/'+learner['id']);assert not disabled['active'] and disabled['purge_at'] is None;call(admin,'PUT','/api/admin/users/'+learner['id']+'/status',{'active':True});call(lc,'POST','/api/auth/login',{'email':learner['email'],'password':newpassword});assert counts(teacher,cid)['student_count']==before;check('Global disable is reversible, revokes sessions, adds no purge deadline and retains the original password/enrollments')
  # Real mixed-role CSV parser, default/explicit roles, exact recovery and duplicate commit.
  mixed=[['Synthetic CSV Admin',f'csv-admin-{token}@example.invalid','admin'],['Synthetic CSV Teacher',f'csv-teacher-{token}@example.invalid','teacher'],['Synthetic CSV Student',f'csv-student-{token}@example.invalid','student'],['Name not overwritten',teacher2['email'],'teacher']]
  stream=StringIO();writer=csv.writer(stream);writer.writerow(['name','email','role']);writer.writerows(mixed)
  preview=call(admin,'POST','/api/admin/users/import/preview',files={'file':('Synthetic.csv',stream.getvalue().encode(),'text/csv')},data={'default_role':'student','default_temporary_password':temporary});assert preview['valid_count']==4 and preview['error_count']==0;assert temporary not in json.dumps(preview) and 'password_hash' not in json.dumps(preview);iid=preview['import_id'];call(ac,'GET','/api/admin/users/import/'+iid,expected=404)
  result=call(admin,'POST',f'/api/admin/users/import/{iid}/commit',{});assert result['created']==3 and result['skipped']==1 and len(set(result['user_ids']))==4;assert call(admin,'POST',f'/api/admin/users/import/{iid}/commit',{})==result;recovered=call(admin,'GET','/api/admin/users/import/'+iid);assert recovered['status']=='committed' and recovered['result']==result
  saved=[call(admin,'GET','/api/admin/users/'+uid)['user']for uid in result['user_ids']];assert[(u['email'],u['role'])for u in saved]==[(r[1],r[2])for r in mixed];assert saved[-1]['name']==teacher2['name'];check('Actual mixed Admin/Teacher/Student CSV is hash-safe reviewed create/skip, atomic and recoverable/idempotent by exact admin-owned import ID')
  wb=Workbook();ws=wb.active;ws.append(['name','email','role']);ws.append(['Synthetic XLSX Teacher',f'xlsx-{token}@example.invalid','teacher']);buf=BytesIO();wb.save(buf);wb.close();px=call(admin,'POST','/api/admin/users/import/preview',files={'file':('Synthetic.xlsx',buf.getvalue(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},data={'default_role':'student','default_temporary_password':temporary});rx=call(admin,'POST',f"/api/admin/users/import/{px['import_id']}/commit",{});assert call(admin,'GET','/api/admin/users/'+rx['user_ids'][0])['user']['role']=='teacher';check('Actual XLSX parser respects per-row role over selected default')
  bad='name,email,role\nConflict,'+learner['email']+',admin\nShould not create,blocked-'+token+'@example.invalid,student\n';pv=call(admin,'POST','/api/admin/users/import/preview',files={'file':('Synthetic-bad.csv',bad.encode(),'text/csv')},data={'default_temporary_password':temporary});assert pv['error_count']==1;call(admin,'POST',f"/api/admin/users/import/{pv['import_id']}/commit",{},422);assert call(admin,'GET','/api/admin/users',params={'q':'blocked-'+token})['total']==0;assert call(admin,'GET','/api/admin/users/'+learner['id'])['user']['role']=='student';check('Existing different-role import blocks the entire commit, creates no other row and cannot silently promote/reset')
  stale='name,email,role\nStale,'+teacher2['email']+',teacher\n';pv=call(admin,'POST','/api/admin/users/import/preview',files={'file':('Synthetic-stale.csv',stale.encode(),'text/csv')});call(admin,'PATCH','/api/admin/users/'+teacher2['id'],{'role':'admin'});call(admin,'POST',f"/api/admin/users/import/{pv['import_id']}/commit",{},409);assert counts(teacher,cid)['admin_count']==2 and counts(teacher,cid)['teacher_count']==1;call(admin,'PATCH','/api/admin/users/'+teacher2['id'],{'role':'teacher'});check('Stale preview detects concurrent role change, and per-course counts update live rather than from published snapshots')
  total=call(admin,'GET','/api/admin/users')['total'];seen=[]
  for offset in range(0,total,2):
   page=call(admin,'GET','/api/admin/users',params={'offset':offset,'limit':2});assert page['total']==total;seen.extend(r['user']['id']for r in page['items'])
  assert len(seen)==len(set(seen))==total
  for role in ('admin','teacher','student'):
   page=call(admin,'GET','/api/admin/users',params={'role':role});assert page['total']==len(page['items']) and all(x['user']['role']==role for x in page['items'])
  check('True stable global pagination enumerates every distinct account; role filters return matching totals')
  call(student,'POST','/api/admin/users/import/preview',files={'file':('Denied.csv',b'name,email','text/csv')},expected=403);call(teacher,'PATCH','/api/admin/users/'+learner['id'],{'role':'admin'},403);call(admin,'PATCH','/api/admin/users/'+learner['id'],{'role':'student','password':temporary},422);check('Teacher/student cannot invoke global import or role changes, and extra credential fields are rejected')
  ids={'course':cid,'second_course':cid2,'primary':tu['id'],'staff_user_ids':sorted(x['user']['id']for x in call(admin,'GET',f'/api/courses/{cid}/staff')['staff']),'counts':{k:counts(teacher,cid)[k]for k in ['admin_count','teacher_count','student_count']},'import_id':iid,'import_result':result,'learner_user':ou['id'],'learner_session':sid,'learner_version':vid,'learner_question':qid,'learner_answer':answer,'global_total':total}
  if os.getenv('AICADEMIYA_QA_DB'):
   with sqlite3.connect('file:'+Path(os.environ['AICADEMIYA_QA_DB']).as_posix()+'?mode=ro',uri=True)as db:
    row=db.execute('SELECT payload_json,result_json FROM account_imports WHERE id=?',(iid,)).fetchone();assert temporary not in row[0] and all(x.get('password_hash') is None for x in json.loads(row[0]));assert json.loads(row[1])==result
   check('SQLite committed import stores exact result and removes staging credential hashes')
 except Exception as e:failures.append({'error':str(e),'traceback':traceback.format_exc()})
 finally:
  for c in clients:c.close()
  r={'status':'passed'if not failures else'failed','checks':checks,'events':events,'failures':failures,'ids':ids,'real_http':True,'synthetic_only':True,'real_model_or_search_calls':0};(out/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'status':r['status'],'checks':len(checks),'failures':failures,'result':str(out/'result.json')}))
 return 1 if failures else 0
if __name__=='__main__':raise SystemExit(main())
