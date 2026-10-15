"""Real SQLite/API source reuse; model responses below are labelled fixtures."""
import json
from pathlib import Path
import pytest
from .conftest import expect, publish
from .test_stage2_authoring import worksheet_docx

EP = '/api/sessions/s4/worksheet-import/from-material'
TEXT = b'Synthetic worksheet\n1. Name the source colour.\n2. State its identifier.\n'


def upload(teacher, text=TEXT, name='worksheet.txt', kind='worksheet', visibility='student'):
    return expect(teacher.post('/api/sessions/s4/materials', data={'kind':kind,'visibility':visibility}, files={'file':(name,text)}))


def preview(teacher, mid, **kwargs):
    return expect(teacher.post(EP, json={'material_id':mid,'use_ai':False,**kwargs}))


def commit(teacher, p):
    return teacher.post('/api/sessions/s4/worksheet-import/'+p['import_id']+'/commit',json={**{k:p['draft'][k]for k in ('groups','questions','reference_answers')},'mode':'replace'})


def test_reuse_detached_course_original_not_insert_copy_or_publish(teacher,student,app):
    m=upload(teacher);old=publish(teacher)['id']
    expect(teacher.delete('/api/sessions/s4/materials/'+m['id']))
    with app.state.database.connect() as conn:
        path=conn.execute('SELECT file_path FROM materials WHERE id=?',(m['id'],)).fetchone()[0]
        count=conn.execute('SELECT count(*) FROM materials').fetchone()[0]
    p=preview(teacher,m['id']);assert p['material']['id']==m['id'];assert len(p['draft']['questions'])==2
    assert p['draft']['reference_answers']=={}
    result=expect(commit(teacher,p));assert len(result['questions'])==2
    assert result['questions'][0]['source_material_ids']==[m['id']]
    read=expect(teacher.get('/api/sessions/s4'));assert read['questions']==result['questions']
    with app.state.database.connect() as conn:
        assert conn.execute('SELECT count(*) FROM materials').fetchone()[0]==count
        assert conn.execute('SELECT file_path FROM materials WHERE id=?',(m['id'],)).fetchone()[0]==path
    assert Path(path).read_bytes()==TEXT
    assert expect(student.get('/api/sessions/s4',params={'version_id':old}))['questions']!=result['questions']
    expect(commit(teacher,p),404)


def test_inline_answers_keep_original_private_at_commit(teacher,student):
    m=upload(teacher,b'Synthetic worksheet\n1. Name the colour.\nAnswer: violet\n')
    p=preview(teacher,m['id']);assert list(p['draft']['reference_answers'].values())==['violet']
    expect(commit(teacher,p));published=publish(teacher)['id']
    expect(student.get(m['download_url'],params={'version_id':published}),403)
    student_detail=expect(student.get('/api/sessions/s4',params={'version_id':published}))
    assert 'violet' not in json.dumps(student_detail)


def test_preview_and_committed_figures_keep_original_identity(teacher,student):
    m=upload(teacher,worksheet_docx(),'figure.docx',visibility='teacher')
    p=preview(teacher,m['id']);assert p['assets']
    a=p['assets'][0];assert teacher.get(a['url']).status_code==200
    expect(student.get(a['url']),403)
    q=p['draft']['questions'][0];q['images']=[{'asset_key':a['key'],'label':'Source figure','alt':'Reviewed synthetic figure'}]
    result=expect(commit(teacher,p));assert result['questions'][0]['images'][0]['url'].startswith('/api/materials/'+m['id']+'/assets/')
    assert teacher.get(result['questions'][0]['images'][0]['url']).status_code==200
    published=publish(teacher)['id']
    assert student.get(result['questions'][0]['images'][0]['url'],params={'version_id':published}).status_code==200
    expect(student.get(m['download_url'],params={'version_id':published}),403)


@pytest.mark.parametrize('change',['metadata','bytes','detach_other_scope'])
def test_stale_preview_cannot_overwrite_source(teacher,app,change):
    m=upload(teacher);p=preview(teacher,m['id'])
    if change=='metadata':expect(teacher.patch('/api/sessions/s4/materials/'+m['id'],json={'title':'Changed title'}))
    elif change=='bytes':
        with app.state.database.connect()as conn:path=conn.execute('SELECT file_path FROM materials WHERE id=?',(m['id'],)).fetchone()[0]
        Path(path).write_bytes(b'Changed synthetic bytes')
    else:
        # Moving course ownership is never inferred from a client material ID.
        with app.state.database.connect()as conn:conn.execute('UPDATE materials SET archived=1 WHERE id=?',(m['id'],))
    expect(commit(teacher,p),404 if change=='detach_other_scope' else 409)


def install_model_fixture(monkeypatch,app,refs):
    calls=[]
    monkeypatch.setattr(app.state.tutor,'settings',lambda conn:{'mode':'openai','model':'explicit-fixture'})
    monkeypatch.setattr(app.state.tutor,'uses_aicademiya_router',lambda settings:False)
    def complete(settings,messages,**kwargs):
        calls.append((messages,kwargs))
        return json.dumps({'title':'Synthetic fixture','groups':[{'id':'g','title':'Questions','kind':'core'}],
          'questions':[{'id':'a','group_id':'g','type':'open_response','prompt':'Name the source colour.','options':[],'answer_slots':1,'images':[]},
                       {'id':'b','group_id':'g','type':'open_response','prompt':'State its identifier.','options':[],'answer_slots':1,'images':[]}],
          'reference_answers':refs})
    monkeypatch.setattr(app.state.tutor,'complete',complete)
    return calls


def test_ai_uses_only_selected_sources_and_matches_separate_private_key(teacher,student,app,monkeypatch):
    m=upload(teacher);key=upload(teacher,b'Answer key\n1. violet\n','answers.txt','answer_key','teacher')
    calls=install_model_fixture(monkeypatch,app,{'a':'violet'})
    p=preview(teacher,m['id'],answer_material_id=key['id'],use_ai=True)
    assert p['method']=='ai_materials';assert list(p['draft']['reference_answers'].values())==['violet']
    assert len(calls)==1 and calls[0][1]['max_tokens']==8192
    sent=json.loads(calls[0][0][1]['content']);assert 'violet'in sent['supplied_answer_key']and'TEACHER_MATERIAL_DO_NOT_LEAK'not in json.dumps(sent)
    assert all(q['source_material_ids']==[m['id']]for q in p['draft']['questions'])
    expect(commit(teacher,p));vid=publish(teacher)['id']
    assert 'violet'not in json.dumps(expect(student.get('/api/sessions/s4',params={'version_id':vid})))


def test_no_supplied_answers_cannot_turn_into_generation(teacher,app,monkeypatch):
    m=upload(teacher);install_model_fixture(monkeypatch,app,{'a':'invented answer'})
    p=preview(teacher,m['id'],use_ai=True);assert p['draft']['reference_answers']=={}
    assert any('left blank'in w for w in p['warnings'])


def test_student_unassigned_admin_and_answer_key_source_denied(teacher,student,admin):
    m=upload(teacher);payload={'material_id':m['id'],'use_ai':False}
    expect(student.post(EP,json=payload),403);expect(admin.post(EP,json=payload),403)
    key=upload(teacher,b'private key','key.txt','answer_key','teacher')
    expect(teacher.post(EP,json={'material_id':key['id'],'use_ai':False}),422)
    expect(teacher.post(EP,json={**payload,'answer_material_id':m['id']}),422)
