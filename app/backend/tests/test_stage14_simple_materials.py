"""Real full-text application commit; synthetic image bundle tests are explicit."""
import io
import json
import shutil
from pathlib import Path
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from backend.aicademiya.main import create_app
from backend.aicademiya.document_bundle import FULL_FORMATS,sha256_file
from tools.material_stage13.simple_material import text_bundle
from .test_stage12_document_api import synthetic_bundle,pdf_bytes,wait_job,endpoint
from .conftest import expect,publish


def image_bytes(fmt='PNG'):
    data=io.BytesIO();Image.new('RGB',(40,30),'white').save(data,format=fmt);return data.getvalue()


def process(source,root,cancel):
    if source.suffix in ('.txt','.md'):
        root.mkdir();text_bundle(source,root,source.suffix[1:],30)
    else:
        # Labelled test fixture validates transport/permissions, not OCR fidelity.
        pdf=root.parent/(root.name+'-synthetic.pdf');pdf.write_bytes(pdf_bytes(1));value=synthetic_bundle(pdf,root)
        shutil.copyfile(pdf,root/'preview.pdf');value.update(source_sha256=sha256_file(source),source_format=source.suffix[1:],preview_pdf='preview.pdf')
        (root/'manifest.json').write_text(json.dumps(value))


@pytest.fixture
def complete_env(tmp_path,catalog,monkeypatch):
    monkeypatch.setenv('AICADEMIYA_DOCUMENT_FORMATS',','.join(FULL_FORMATS));monkeypatch.setenv('AICADEMIYA_AI_MODE','demo')
    app=create_app(data_dir=tmp_path/'data',catalog_path=catalog,demo_enabled=True,frontend_dir=tmp_path/'dist',document_processor=process)
    with TestClient(app)as teacher:
        expect(teacher.post('/api/auth/demo',json={'role':'teacher'}));yield app,teacher


@pytest.mark.parametrize('suffix',['txt','md'])
def test_full_text_upload_preserves_all_chars_and_late_citation(complete_env,suffix):
    app,teacher=complete_env
    literal=('Exact native source paragraph 中文\r\n'*1700)+'FINAL_SOURCE_MARKER'
    original=literal.encode('utf-8')
    m=expect(teacher.post('/api/sessions/s4/materials',data={'processing':'full_document','visibility':'student'},files={'file':('source.'+suffix,original,'application/octet-stream')}))
    job=wait_job(teacher,m['id']);assert job['status']=='completed'
    summary=expect(teacher.get(endpoint(m['id'])));rid=summary['document']['revision_id']
    assert summary['document']['source_format']==suffix and summary['document']['has_rendered_pdf']
    assert teacher.get(m['download_url']).content==original
    parts=[]
    for page in summary['pages']:
        value=expect(teacher.get(endpoint(m['id'])+'/pages/'+str(page['number']),params={'revision_id':rid}));parts.extend(b['text']for b in value['blocks'])
    assert ''.join(parts)==literal and len(literal)>50000
    pdf=teacher.get(endpoint(m['id'])+'/pdf',params={'revision_id':rid});assert pdf.status_code==200 and pdf.content.startswith(b'%PDF-')
    version=publish(teacher)
    with TestClient(app)as student:
        expect(student.post('/api/auth/demo',json={'role':'student'}))
        assert student.get(endpoint(m['id'])+'/pdf',params={'revision_id':rid,'version_id':version['id']}).content==pdf.content


@pytest.mark.parametrize('suffix,fmt',[('png','PNG'),('jpg','JPEG'),('jpeg','JPEG'),('webp','WEBP')])
def test_image_full_processing_routes_and_revision_auth(complete_env,suffix,fmt):
    app,teacher=complete_env;original=image_bytes(fmt)
    m=expect(teacher.post('/api/sessions/s4/materials',data={'processing':'full_document','visibility':'student'},files={'file':('image.'+suffix,original,'application/octet-stream')}))
    job=wait_job(teacher,m['id']);assert job['status']=='completed'and job['page_count']==1
    summary=expect(teacher.get(endpoint(m['id'])));rid=summary['document']['revision_id'];url=endpoint(m['id'])+'/pdf'
    assert summary['document']['source_format']==suffix
    assert teacher.get(m['download_url']).content==original
    expect(teacher.get(url,params={'revision_id':'wrong'}),409)
    with TestClient(app)as anonymous:expect(anonymous.get(url,params={'revision_id':rid}),401)
    with TestClient(app)as other_staff:
        expect(other_staff.post('/api/auth/demo',json={'role':'admin'}));expect(other_staff.get(url,params={'revision_id':rid}),403)


def test_worker_cannot_commit_truncated_plain_text(complete_env):
    app,teacher=complete_env
    def truncated(source,root,cancel):
        process(source,root,cancel)
        p=root/'manifest.json';m=json.loads(p.read_text());m['pages'][0]['blocks'][0]['text']=m['pages'][0]['blocks'][0]['text'][:-1];p.write_text(json.dumps(m))
    app.state.document_queue.processor=truncated
    m=expect(teacher.post('/api/sessions/s4/materials',data={'processing':'full_document'},files={'file':('source.txt',b'Original exact text that must not lose its final character.','text/plain')}))
    assert wait_job(teacher,m['id'])['status']=='failed'
    assert expect(teacher.get(endpoint(m['id'])))['document']is None


def test_binary_text_and_misnamed_images_are_rejected_before_job(complete_env):
    _,teacher=complete_env
    for name,content in [('binary.txt',b'a\0b'),('not-jpeg.jpg',image_bytes('PNG'))]:
        expect(teacher.post('/api/sessions/s4/materials',data={'processing':'full_document'},files={'file':(name,content,'application/octet-stream')}),422)
