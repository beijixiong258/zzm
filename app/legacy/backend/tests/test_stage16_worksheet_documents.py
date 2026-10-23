"""Stage16 saved-revision, review privacy and relocated-pending-import gates.
Synthetic document processor fixtures are protocol tests, not real OCR.
"""
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from backend.aicademiya.main import create_app
from .conftest import expect, publish
from .test_stage12_document_api import docenv, complete, endpoint, review_payload
from .test_stage16_worksheet_materials import preview, commit, upload, install_model_fixture
from .test_stage2_backup import backup_tool, worksheet_docx


def question_blocks(manifest):
    for page in manifest['pages']:
        block=page['blocks'][0]
        block['text']=f"{page['number']}. Give evidence for item {page['number']}."
        page['blocks'].append({**block,'id':f"p{page['number']}-b1",'type':'image','text':'',
            'bbox':[.1,.1,.5,.5]})


def test_complete_revision_used_and_recorded_not_reextracted(docenv):
    app,teacher,student,processor=docenv
    processor.mutate=question_blocks
    mid,rid,_=complete(teacher,kind='worksheet',visibility='teacher')
    p=preview(teacher,mid);assert p['method']=='saved_document';assert len(p['draft']['questions'])==2
    assert len(p['assets'])==1  # Identical synthetic crop bytes are one asset; whole pages excluded.
    result=expect(commit(teacher,p));assert len(result['questions'])==2
    with app.state.database.connect()as conn:
        raw=json.loads(conn.execute('SELECT content_json FROM sessions WHERE id=?',('s4',)).fetchone()[0])
        evidence=raw['worksheet_import_sources'][-1]
        assert evidence['materials']==[{'material_id':mid,'revision_id':rid}]
        assert evidence['question_ids']==[q['id']for q in result['questions']]
    assert 'worksheet_import_sources'not in result
    vid=publish(teacher)['id']
    assert 'worksheet_import_sources'not in expect(student.get('/api/sessions/s4',params={'version_id':vid}))


def test_changed_document_revision_rejects_stale_import(docenv):
    app,teacher,student,processor=docenv;processor.mutate=question_blocks
    mid,rid,_=complete(teacher,kind='worksheet')
    p=preview(teacher,mid)
    expect(teacher.post(endpoint(mid)+'/reviews',json=review_payload(rid,text='2. Reviewed replacement question.')))
    expect(commit(teacher,p),409)


def test_private_inline_source_stays_private_even_if_teacher_clears_references(teacher,student):
    m=upload(teacher,b'Worksheet\n1. Name the colour.\nAnswer: violet\n')
    p=preview(teacher,m['id']);p['draft']['reference_answers']={}
    expect(commit(teacher,p));vid=publish(teacher)['id']
    expect(student.get(m['download_url'],params={'version_id':vid}),403)


def test_key_does_not_license_unsupplied_answer_generation(teacher,app,monkeypatch):
    m=upload(teacher);key=upload(teacher,b'Answer key\n1. violet\n','key.txt','answer_key','teacher')
    install_model_fixture(monkeypatch,app,{'a':'violet','b':'invented replacement'})
    p=preview(teacher,m['id'],answer_material_id=key['id'],use_ai=True)
    assert list(p['draft']['reference_answers'].values())==['violet']
    assert any('did not occur' in w for w in p['warnings'])


def test_pending_reused_source_import_survives_relocation(app,teacher,tmp_path,catalog):
    m=upload(teacher,worksheet_docx(),'restore-worksheet.docx',visibility='teacher')
    p=preview(teacher,m['id']);assert p['assets']
    first=p['assets'][0]
    p['draft']['questions'][0]['images']=[{'asset_key':first['key'],'label':'A','alt':'Synthetic source figure'}]
    root=app.state.database.path.parent
    saved=tmp_path/'stage16-backup';restored=tmp_path/'stage16-restored'
    backup_tool.backup(root,saved,materials_root=catalog.parent)
    backup_tool.restore(saved,restored)
    old_uploads=root/'uploads';held=root/'uploads-held-unavailable'
    old_uploads.rename(held)
    try:
        other=create_app(data_dir=restored,catalog_path=catalog,demo_enabled=True,frontend_dir=tmp_path/'no-ui')
        with TestClient(other)as client:
            expect(client.post('/api/auth/demo',json={'role':'teacher'}))
            assert client.get(first['url']).status_code==200
            count=len(expect(client.get('/api/courses/synthetic-course/materials'))['materials'])
            result=expect(commit(client,p));assert result['questions']
            assert len(expect(client.get('/api/courses/synthetic-course/materials'))['materials'])==count
            assert client.get(m['download_url']).content==worksheet_docx_bytes(restored,m['id'])
    finally:
        held.rename(old_uploads)


def worksheet_docx_bytes(root,mid):
    import sqlite3
    with sqlite3.connect(root/'aicademiya.sqlite3')as conn:
        path=conn.execute('SELECT file_path FROM materials WHERE id=?',(mid,)).fetchone()[0]
    assert Path(path).is_relative_to(root)
    return Path(path).read_bytes()
