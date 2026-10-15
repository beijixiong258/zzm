"""Exercise an extracted Stage16 archive with synthetic data, no live provider.
Run with the project's Python, passing the extracted release and a NEW QA path.
The candidate backend/tools, not the source-tree modules, must be imported.
"""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys

p=argparse.ArgumentParser();p.add_argument('--release',required=True);p.add_argument('--output',required=True);p.add_argument('--xlsx',required=True)
a=p.parse_args();release=Path(a.release).resolve();out=Path(a.output).resolve();out.mkdir(parents=True,exist_ok=False)
for key in list(os.environ):
    if key.startswith('AICADEMIYA_') or key=='TAVILY_API_KEY':os.environ.pop(key,None)
os.environ.update(AICADEMIYA_AI_MODE='demo',AICADEMIYA_WEB_SEARCH_ENABLED='false')
sys.path.insert(0,str(release));os.chdir(release)
from fastapi.testclient import TestClient
from backend.aicademiya.main import create_app
from backend.aicademiya.document_bundle import FULL_FORMATS
assert {'doc','ppt','xls','xlsx'}<=set(FULL_FORMATS)
for name in ['backend.aicademiya.worksheet_materials','backend.aicademiya.session_lifecycle','backend.aicademiya.model_connection',
             'tools.material_stage16.workbook_material','tools.material_stage16.workbook_inventory','tools.material_stage16.legacy_office','tools.material_stage16.workbook_supplements']:
    module=importlib.import_module(name);assert Path(module.__file__).resolve().is_relative_to(release)
seed=out/'seed';seed.mkdir()
catalog={'schema_version':1,'course':{'id':'stage16-qa','code':'SYNTHETIC','title':'Stage16 archive fixture','description':'No real classroom data'},
         'sessions':[{'id':'s','course_id':'stage16-qa','number':1,'title':'Original title','subtitle':'Synthetic','status':'published','estimated_minutes':15,
            'learning_objectives':[],'instructions':'Synthetic source review','reference_policy':'after_attempt','teaching_language':'en',
            'groups':[{'id':'g','title':'Core','kind':'core'}],'questions':[],'reference_answers':{},'materials':[]}]}
(seed/'catalog.json').write_text(json.dumps(catalog),encoding='utf-8')
app=create_app(data_dir=out/'data',catalog_path=seed/'catalog.json',demo_enabled=True,frontend_dir=release/'frontend/dist')
def ok(r,status=200):
    assert r.status_code==status,(r.status_code,r.text)
    return r.json()
checks=[]
with TestClient(app)as client:
    ok(client.post('/api/auth/demo',json={'role':'teacher'}));checks.append('synthetic-auth-and-archive-boot')
    assert ok(client.get('/api/ai/connection'))['status']=='not_configured';checks.append('demo-is-not-live-endpoint-health')
    ok(client.patch('/api/sessions/s',json={'title':'Edited title','number':7}))
    assert ok(client.get('/api/sessions/s'))['title']=='Edited title';checks.append('session-edit-readback')
    raw=b'Worksheet\n1. Name the colour.\nAnswer: violet\n'
    material=ok(client.post('/api/sessions/s/materials',data={'kind':'worksheet','visibility':'teacher'},files={'file':('worksheet.txt',raw)}))
    mid=material['id'];original=client.get(material['download_url']).content;assert original==raw
    before=len(ok(client.get('/api/courses/stage16-qa/materials'))['materials'])
    preview=ok(client.post('/api/sessions/s/worksheet-import/from-material',json={'material_id':mid,'use_ai':False}))
    assert len(preview['draft']['questions'])==1 and list(preview['draft']['reference_answers'].values())==['violet']
    payload={k:preview['draft'][k]for k in ('groups','questions','reference_answers')};payload['mode']='replace'
    ok(client.post('/api/sessions/s/worksheet-import/'+preview['import_id']+'/commit',json=payload))
    assert ok(client.get('/api/sessions/s'))['questions'][0]['prompt']=='Name the colour.'
    assert len(ok(client.get('/api/courses/stage16-qa/materials'))['materials'])==before
    assert client.get(material['download_url']).content==raw;checks.append('worksheet-reuse-extraction-commit-original-identity')
    ok(client.delete('/api/sessions/s'))
    assert any(s['id']=='s'for s in ok(client.get('/api/courses/stage16-qa/sessions/trash'))['sessions'])
    ok(client.post('/api/sessions/s/restore'))
    assert ok(client.get('/api/sessions/s'))['materials'][0]['id']==mid;checks.append('session-remove-restore-shared-source')
    xlsx=Path(a.xlsx).resolve().read_bytes()
    assert hashlib.sha256(xlsx).hexdigest()=='867a73374bcbf32c2b5aac1789aa6dcf9814d1320eb89fada3560407f678b2c4'
    excel=ok(client.post('/api/sessions/s/materials',data={'kind':'reference','visibility':'teacher','processing':'preview'},files={'file':('native.xlsx',xlsx)}))
    assert excel['source_format']=='xlsx' and excel['status'] in ('ready','needs_review') and excel['excerpt']
    assert client.get(excel['download_url']).content==xlsx;checks.append('real-xlsx-preview-in-extracted-runtime')
for name,module in tuple(sys.modules.items()):
    if name.startswith('backend.') and getattr(module,'__file__',None):assert Path(module.__file__).resolve().is_relative_to(release),(name,module.__file__)
result={'status':'passed','release':str(release),'checks':checks,'app_version':app.version,'real_model':False,'deployed':False}
(out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
