"""Native auxiliary text + immutable sharing/auth/model-read contract tests.

Rendering/model responses are not exercised by the synthetic bundle fixture.
"""
import copy
import io
import json
import zipfile
from pathlib import Path
import pytest
from docx import Document
from fastapi.testclient import TestClient
from backend.aicademiya.main import create_app
from backend.aicademiya.document_bundle import BundleError,validate_manifest
from backend.aicademiya.document_supplements import index_supplements
from backend.aicademiya.reading_context import catalogue,execute_plan,validate_citations
from backend.aicademiya.guided_reading import SourceFeedback,source_citations
from .test_stage13_material_documents import office_bundle
from .test_stage12_document_api import endpoint,wait_job
from .conftest import expect,publish

SECRET='SYNTHETIC staff source note: preserve the original wording.'


def docx_notes(text=SECRET):
    stream=io.BytesIO();d=Document();d.add_paragraph('SYNTHETIC public body, separate from staff-only source notes.');d.save(stream)
    result=io.BytesIO()
    with zipfile.ZipFile(stream)as source,zipfile.ZipFile(result,'w',zipfile.ZIP_DEFLATED)as target:
        for item in source.infolist():target.writestr(item,source.read(item.filename))
        target.writestr('word/comments.xml','<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:comment w:id="42"><w:p><w:r><w:t>'+text+'</w:t></w:r></w:p><w:p><w:r><w:t>Second </w:t></w:r><w:r><w:t>run stays adjacent.</w:t></w:r></w:p></w:comment></w:comments>')
        target.writestr('word/footnotes.xml','<w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:footnote w:id="1"><w:p><w:r><w:t>Native footnote source.</w:t></w:r></w:p></w:footnote></w:footnotes>')
    return result.getvalue()


def test_native_notes_are_not_lost_between_runs_or_at_chunk_boundary(tmp_path):
    literal='NATIVE_NOTE_'*2300;source=tmp_path/'source.docx';source.write_bytes(docx_notes(literal))
    notes=index_supplements(source,tmp_path,{'page_count':2})
    comments=[s for s in notes if s['kind']=='comment'];assert len(comments)>1
    assert ''.join(s['text']for s in comments)==literal+'\nSecond run stays adjacent.'
    assert comments[0]['char_start']==0 and comments[-1]['char_end']==len(literal+'\nSecond run stays adjacent.')
    assert all(a['char_end']==b['char_start']for a,b in zip(comments,comments[1:]))
    assert all(s['page_hint']is None and s['visibility']=='teacher'for s in notes)
    assert {s['source_part']for s in notes}=={'word/comments.xml','word/footnotes.xml'}


def with_supplement(visibility='teacher'):
    from .test_stage12_reading_context import document
    d=document();d['manifest']['pages']=d['manifest']['pages'][:1]
    d['manifest']['supplements']=[{'id':'s1','kind':'comment','source_part':'word/comments.xml','source_node':'42',
        'page_hint':None,'char_start':0,'char_end':len(SECRET),'text':SECRET,'quality':'extracted','visibility':visibility,'derivation':'original_office_xml'}]
    return d


def test_private_supplement_not_in_student_directory_search_or_sequential_reads():
    d=with_supplement();assert 'word/comments'not in json.dumps(catalogue([d]))
    r=execute_plan([d],{'requests':[{'material_id':'m1','query':'staff source note'}]})
    assert SECRET not in json.dumps(r)
    with pytest.raises(ValueError):execute_plan([d],{'requests':[{'material_id':'m1','supplement_ids':['s1']}]})
    sequential=execute_plan([d],{'requests':[{'material_id':'m1','mode':'sequential'}]},char_budget=20000)
    assert SECRET not in json.dumps(sequential)


def test_authorized_native_note_has_part_locator_not_invented_pdf_page():
    d=with_supplement();directory=catalogue([d],include_staff_supplements=True)
    assert directory[0]['supplements'][0]['id']=='s1'
    evidence=execute_plan([d],{'requests':[{'material_id':'m1','supplement_ids':['s1']}]},include_staff_supplements=True)
    b=evidence['blocks'][0];assert b['page']is None and b['source_part']=='word/comments.xml'and b['visibility']=='teacher'
    with pytest.raises(ValueError):validate_citations([{'ref':b['ref'],'quote':SECRET}],evidence)
    response=SourceFeedback(text='SYNTHETIC staff source response',document_citations=[{'ref':b['ref'],'quote':SECRET}])
    citation=source_citations(response,evidence,{'_version_id':'edition'},allow_private=True)[0]
    assert citation['kind']=='document_supplement'and citation['page']is None
    assert citation['url']=='/api/materials/m1/document/supplements/s1/text?version_id=edition&revision_id=revision-old'


def test_explicitly_shared_note_can_be_read_but_private_file_stays_private():
    d=with_supplement('student');r=execute_plan([d],{'requests':[{'material_id':'m1','supplement_ids':['s1']}]})
    assert r['blocks'][0]['visibility']=='student'
    d['visibility']='teacher'
    with pytest.raises(ValueError):execute_plan([d],{'requests':[{'material_id':'m1','supplement_ids':['s1']}]})
    r=execute_plan([d],{'requests':[{'material_id':'m1','supplement_ids':['s1']}]},private=True)
    assert r['blocks'][0]['visibility']=='teacher'


def test_staff_cursor_cannot_skip_student_body_after_visibility_scope_change():
    d=with_supplement();staff=execute_plan([d],{'requests':[{'material_id':'m1','mode':'sequential'}]},include_staff_supplements=True,char_budget=20000)
    student=execute_plan([d],{'requests':[{'material_id':'m1','mode':'sequential'}]},progress=staff['_progress_updates'],char_budget=20)
    assert student['blocks'][0]['page']==1 and student['blocks'][0]['char_start']==0
    assert SECRET not in json.dumps(student)


@pytest.fixture
def notesenv(tmp_path,catalog,monkeypatch):
    monkeypatch.setenv('AICADEMIYA_DOCUMENT_FORMATS','pdf,docx');monkeypatch.setenv('AICADEMIYA_AI_MODE','demo')
    app=create_app(data_dir=tmp_path/'data',catalog_path=catalog,demo_enabled=True,frontend_dir=tmp_path/'dist',document_processor=lambda s,r,c:office_bundle(s,r))
    with TestClient(app)as teacher,TestClient(app)as student:
        expect(teacher.post('/api/auth/demo',json={'role':'teacher'}));expect(student.post('/api/auth/demo',json={'role':'student'}))
        m=expect(teacher.post('/api/sessions/s4/materials',data={'processing':'full_document','visibility':'student'},files={'file':('source.docx',docx_notes(),'application/octet-stream')}))
        assert wait_job(teacher,m['id'])['status']=='completed'
        yield app,teacher,student,m['id']


def test_full_http_native_notes_private_default_and_immutable_explicit_sharing(notesenv):
    app,teacher,student,mid=notesenv;before=expect(teacher.get(endpoint(mid)));rid=before['document']['revision_id']
    assert len(before['supplements'])==2 and all(s['visibility']=='teacher'for s in before['supplements'])
    note=next(s for s in before['supplements']if s['kind']=='comment');path=endpoint(mid)+'/supplements/'+note['id']+'/text'
    text=teacher.get(path,params={'revision_id':rid});assert text.status_code==200 and SECRET in text.text and text.headers['content-type'].startswith('text/plain')
    old=publish(teacher)['id'];old_student=expect(student.get(endpoint(mid),params={'version_id':old}));assert old_student['supplements']==[]
    expect(student.get(path,params={'revision_id':rid,'version_id':old}),404)
    with TestClient(app)as anonymous:expect(anonymous.get(path,params={'revision_id':rid}),401)
    with TestClient(app)as outsider:
        expect(outsider.post('/api/auth/demo',json={'role':'admin'}));expect(outsider.get(path,params={'revision_id':rid}),403)
    payload={'request_id':'share-native-notes','expected_revision':rid,'visible_to_students':True,'reason':'SYNTHETIC explicit sharing decision'}
    expect(student.post(endpoint(mid)+'/supplements/sharing',json=payload),403)
    outcome=expect(teacher.post(endpoint(mid)+'/supplements/sharing',json=payload));new=outcome['document']['revision_id'];assert new!=rid
    assert expect(teacher.post(endpoint(mid)+'/supplements/sharing',json=payload))==outcome
    assert expect(teacher.get(endpoint(mid)+'/reviews/share-native-notes'))==outcome
    expect(teacher.post(endpoint(mid)+'/supplements/sharing',json={**payload,'visible_to_students':False}),409)
    draft=expect(teacher.get(endpoint(mid)));assert draft['document']['revision_id']==new and all(s['visibility']=='student'for s in draft['supplements'])
    expect(student.get(path,params={'revision_id':rid,'version_id':old}),404)
    version=publish(teacher)['id'];visible=expect(student.get(endpoint(mid),params={'version_id':version}));assert len(visible['supplements'])==2
    assert student.get(path,params={'revision_id':new,'version_id':version}).text==text.text
    expect(student.get(path,params={'revision_id':rid,'version_id':version}),409)
    hidden=expect(teacher.post(endpoint(mid)+'/supplements/sharing',json={'request_id':'hide-native-notes','expected_revision':new,'visible_to_students':False,'reason':'SYNTHETIC restrict draft notes'}))
    assert hidden['document']['revision_id']!=new
    assert student.get(path,params={'revision_id':new,'version_id':version}).text==text.text


def test_worker_cannot_forge_student_shared_auxiliary(notesenv):
    app,teacher,student,mid=notesenv
    with app.state.database.connect()as conn:
        value=json.loads(conn.execute('select manifest_json from document_revisions where material_id=?',(mid,)).fetchone()[0])
    value['supplements'][0]['visibility']='student'
    with pytest.raises(BundleError):validate_manifest(value)
