"""Real XLSX XML/comments through queue/API commit; rendered bundle is a labelled fixture."""
from pathlib import Path
import hashlib,json
from fastapi.testclient import TestClient
from backend.aicademiya.main import create_app
from tools.material_stage16.fixtures import workbook
from tools.material_stage16.workbook_inventory import read_workbook
from .test_stage13_material_documents import office_bundle
from .conftest import expect,publish
from .test_stage12_document_api import wait_job,endpoint


def test_xlsx_comments_are_indexed_at_queue_commit_not_only_by_direct_helper(tmp_path,catalog,monkeypatch):
    monkeypatch.setenv('AICADEMIYA_DOCUMENT_FORMATS','xlsx')
    monkeypatch.setenv('AICADEMIYA_AI_MODE','demo')
    source=tmp_path/'worksheet.xlsx';workbook(source,media=False)
    def processor(source,root,cancelled):
        assert not cancelled.is_set()
        office_bundle(source,root)
        native=read_workbook(source)
        native['original_source_sha256']=hashlib.sha256(Path(source).read_bytes()).hexdigest()
        (root/'raw/office-inventory.json').write_text(json.dumps(native))
    app=create_app(data_dir=tmp_path/'data',catalog_path=catalog,demo_enabled=True,frontend_dir=tmp_path/'dist',document_processor=processor)
    with TestClient(app)as teacher,TestClient(app)as student:
        expect(teacher.post('/api/auth/demo',json={'role':'teacher'}));expect(student.post('/api/auth/demo',json={'role':'student'}))
        m=expect(teacher.post('/api/sessions/s4/materials',data={'processing':'full_document','visibility':'student'},files={'file':('source.xlsx',source.read_bytes())}))
        job=wait_job(teacher,m['id']);assert job['status']=='completed',job
        info=expect(teacher.get(endpoint(m['id'])));notes=info['supplements'];assert len(notes)==1
        assert notes[0]['kind']=='comment'and notes[0]['visibility']=='teacher'and notes[0]['page_hint']is None
        assert 'sheet:1; cell:B1'==notes[0]['source_node']
        vid=publish(teacher)['id'];assert expect(student.get(endpoint(m['id']),params={'version_id':vid}))['supplements']==[]
        assert teacher.get(m['download_url']).content==source.read_bytes()
