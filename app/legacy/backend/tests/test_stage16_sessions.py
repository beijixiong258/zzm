"""Reversible session removal: real synthetic API/SQLite, no model/network."""
from pathlib import Path
from .conftest import expect,publish

def test_session_remove_restore_preserves_shared_material_and_learning(app,teacher,student):
 material=expect(teacher.post('/api/sessions/s4/materials',files={'file':('shared.txt',b'SYNTHETIC shared course original')}))
 expect(teacher.post('/api/sessions/s2/materials/attach',json={'material_id':material['id']}));old=publish(teacher)['id']
 expect(student.get('/api/sessions/s4/workspace',params={'version_id':old}));expect(student.post('/api/sessions/s4/answers/q1',params={'version_id':old},json={'answer':'Synthetic answer kept through deletion.'}))
 with app.state.database.connect()as c:
  before={t:[tuple(x)for x in c.execute('select * from '+t)]for t in ('attempts','revisions','messages','course_versions')};original=Path(c.execute('select file_path from materials where id=?',(material['id'],)).fetchone()[0])
 first=expect(teacher.delete('/api/sessions/s4'));assert first['removed'];assert expect(teacher.delete('/api/sessions/s4'))==first
 assert 's4'not in [x['id']for x in expect(teacher.get('/api/courses/synthetic-course/sessions'))]
 assert 's4'in [x['id']for x in expect(student.get('/api/courses/synthetic-course/sessions'))], 'Published edition must not be silently edited'
 assert expect(teacher.get('/api/courses/synthetic-course/sessions/trash'))['sessions'][0]['id']=='s4'
 expect(teacher.get('/api/sessions/s4'),404)
 with app.state.database.connect()as c:
  assert all([tuple(x)for x in c.execute('select * from '+t)]==rows for t,rows in before.items())
 assert original.read_bytes()==b'SYNTHETIC shared course original'
 library=expect(teacher.get('/api/courses/synthetic-course/materials'))['materials'];assert next(x for x in library if x['id']==material['id'])['session_ids']==['s2']
 new=publish(teacher)['id'];assert old!=new
 assert all(s['id']!='s4'for s in expect(student.get('/api/courses/synthetic-course/sessions')))
 historic=expect(student.get('/api/sessions/s4/workspace',params={'version_id':old}));assert historic['attempts']['q1']['answer']=='Synthetic answer kept through deletion.'
 expect(teacher.post('/api/sessions/s4/restore'));restored=expect(teacher.get('/api/sessions/s4'));assert material['id']in [m['id']for m in restored['materials']]
 assert expect(teacher.get('/api/courses/synthetic-course/sessions/trash'))['sessions']==[]
 with app.state.database.connect()as c:assert c.execute("select published_version_id from courses where id='synthetic-course'").fetchone()[0]==new

def test_session_edit_title_number_description_with_independent_readback(teacher):
 patch={'title':'Renamed session','number':9,'subtitle':'Editable session description.'}
 saved=expect(teacher.patch('/api/sessions/s4',json=patch));assert all(saved[k]==v for k,v in patch.items())
 read=expect(teacher.get('/api/sessions/s4'));assert all(read[k]==v for k,v in patch.items())
 for value in (0,10000,1.5):expect(teacher.patch('/api/sessions/s4',json={'number':value}),422)

def test_students_and_unassigned_admin_cannot_change_session_lifecycle(teacher,student,admin):
 for client in (student,admin):
  expect(client.delete('/api/sessions/s4'),403)
  expect(client.post('/api/sessions/s4/restore'),403)
  expect(client.get('/api/courses/synthetic-course/sessions/trash'),403)
 assert expect(teacher.get('/api/sessions/s4'))['id']=='s4'
