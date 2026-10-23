"""Stage16 material metadata API, synthetic originals; no model calls."""
from .conftest import expect,publish

def uploaded(teacher):
 return expect(teacher.post('/api/sessions/s4/materials',data={'kind':'reading','visibility':'student'},files={'file':('source.txt',b'SYNTHETIC source kept unchanged')}))

def test_type_edit_preserves_original_id_membership_and_old_edition(teacher,student,app):
 m=uploaded(teacher);old=publish(teacher)['id'];expect(student.get('/api/sessions/s4/workspace',params={'version_id':old}));ep='/api/sessions/s4/materials/'+m['id']
 changed=expect(teacher.patch(ep,json={'kind':'worksheet'}));assert changed['id']==m['id']and changed['kind']=='worksheet'
 current=expect(teacher.get('/api/sessions/s4'));assert next(x for x in current['materials']if x['id']==m['id'])['kind']=='worksheet'
 historical=expect(student.get('/api/sessions/s4',params={'version_id':old}));assert next(x for x in historical['materials']if x['id']==m['id'])['kind']=='reading'
 assert teacher.get(m['download_url']).content==b'SYNTHETIC source kept unchanged'
 with app.state.database.connect()as c:assert c.execute('select count(*)from materials where id=?',(m['id'],)).fetchone()[0]==1

def test_answer_key_conversion_forces_private_and_rejects_public_explicitly(teacher,student):
 m=uploaded(teacher);ep='/api/sessions/s4/materials/'+m['id']
 expect(teacher.patch(ep,json={'kind':'answer_key','visibility':'student'}),422)
 changed=expect(teacher.patch(ep,json={'kind':'answer_key'}));assert changed['kind']=='answer_key'and changed['visibility']=='teacher'
 new=publish(teacher)['id'];expect(student.get(m['download_url'],params={'version_id':new}),403)
 expect(teacher.patch(ep,json={'kind':'reading','visibility':'student'}),422)
 assert expect(teacher.patch(ep,json={'kind':'reading'}))['visibility']=='teacher'

def test_kind_validation_and_student_write_denial(teacher,student):
 m=uploaded(teacher);ep='/api/sessions/s4/materials/'+m['id']
 for value in ('link','executable','',None):expect(teacher.patch(ep,json={'kind':value}),422)
 expect(student.patch(ep,json={'kind':'worksheet'}),403)
 assert next(x for x in expect(teacher.get('/api/sessions/s4'))['materials']if x['id']==m['id'])['kind']=='reading'
