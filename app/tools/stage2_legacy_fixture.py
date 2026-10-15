"""Build genuine pre-stage2 synthetic data using the immutable baseline source.

Does not import the changing working backend or touch default/user databases.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import sqlite3
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/stage2'


def main():
    baseline=json.loads((OUT/'baseline.json').read_text(encoding='utf-8'))
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    source=OUT/f'legacy-source-{stamp}';source.mkdir(parents=True)
    data=OUT/f'legacy-data-{stamp}'
    with zipfile.ZipFile(baseline['archive']) as archive:
        for entry in archive.infolist():
            if not entry.filename.startswith('backend/') or entry.is_dir():continue
            target=source/entry.filename
            if not target.resolve().is_relative_to(source.resolve()):raise RuntimeError('Invalid baseline path')
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(archive.read(entry))
    os.environ.update(EDUC_AI_MODE='demo',EDUC_AI_PROVIDER='',EDUC_AI_API_KEY='',EDUC_WEB_SEARCH_ENABLED='false',TAVILY_API_KEY='',EDUC_DATA_DIR=str(data))
    sys.path.insert(0,str(source))
    from fastapi.testclient import TestClient
    from backend.akademiya.main import create_app
    import backend.akademiya.main as original
    assert Path(original.__file__).is_relative_to(source)
    app=create_app(data_dir=data,catalog_path=ROOT/'sample_data/catalog.json',demo_enabled=True)
    def value(response):
        assert response.status_code==200,(response.status_code,response.text[:200])
        return response.json()
    with TestClient(app) as teacher, TestClient(app) as student:
        uid=app.state.database.create_teacher('Synthetic Migration Teacher','migration-teacher@example.invalid','SyntheticMigration9')
        value(teacher.post('/api/auth/login',json={'email':'migration-teacher@example.invalid','password':'SyntheticMigration9'}))
        course=value(teacher.post('/api/courses',json={'code':'MIGRATION-QA','title':'Original synthetic course','description':'Must survive stage2 migration'}))
        session=value(teacher.post(f"/api/courses/{course['id']}/sessions",json={'title':'Original synthetic lesson','number':1,'instructions':'PRIVATE MIGRATION INSTRUCTION'}))
        sid=session['id'];qid='legacy-question-1'
        question={'id':qid,'group_id':session['groups'][0]['id'],'ordinal':1,'type':'open_response',
                  'prompt':'Original wording: explain reliability.','options':[],'answer_slots':1,'images':[],
                  'source_label':'Synthetic original worksheet'}
        value(teacher.patch(f'/api/sessions/{sid}',json={'status':'published','questions':[question],
              'reference_answers':{qid:'PRIVATE MIGRATION REFERENCE'}}))
        material=value(teacher.post(f'/api/sessions/{sid}/materials',files={'file':('migration-reading.txt',b'Original synthetic material bytes.','text/plain')},data={'visibility':'student','kind':'reading'}))
        learner=value(student.post('/api/auth/register',json={'name':'Synthetic Migration Student','email':'migration-student@example.invalid',
              'password':'SyntheticStudent9','join_code':course['join_code']}))['user']
        value(student.post(f'/api/sessions/{sid}/answers/{qid}',json={'answer':'Original first answer'}))
        value(student.post(f'/api/sessions/{sid}/answers/{qid}',json={'answer':'Original revised answer'}))
        value(student.post(f'/api/sessions/{sid}/chat',json={'message':'Original follow-up question, not an answer replacement.','question_id':qid,'intent':'ask','request_id':'legacy-ask-request'}))
        value(student.post(f'/api/sessions/{sid}/references/{qid}'))
        value(student.post(f'/api/sessions/{sid}/submit',json={}))
        value(teacher.post(f"/api/teacher/sessions/{sid}/students/{learner['id']}/review",json={'status':'confirmed','note':'Original synthetic teacher review'}))
        work=value(student.get(f'/api/sessions/{sid}/workspace'))
        with app.state.database.connect() as conn:
            conn.execute("INSERT INTO settings(key,value) VALUES('ai_model','Synthetic saved model label') ON CONFLICT(key) DO UPDATE SET value=excluded.value")
            conn.execute("INSERT INTO settings(key,value) VALUES('ai_api_key','SYNTHETIC_PRIVATE_MODEL_KEY') ON CONFLICT(key) DO UPDATE SET value=excluded.value")
            conn.execute("INSERT INTO meta(key,value) VALUES('kv_scope_secret',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", ('7f'*32,))
    with sqlite3.connect(data/'educ7703.sqlite3') as conn:
        conn.row_factory=sqlite3.Row
        users=[dict(r) for r in conn.execute('SELECT * FROM users ORDER BY id')]
        fingerprints={r['key']:hashlib.sha256(r['value'].encode()).hexdigest() for r in conn.execute("SELECT key,value FROM meta WHERE key='kv_scope_secret'")}
        fingerprints.update({r['key']:hashlib.sha256(r['value'].encode()).hexdigest() for r in conn.execute('SELECT key,value FROM settings')})
        files=[{'id':r['id'],'path':r['file_path'],'sha256':hashlib.sha256(Path(r['file_path']).read_bytes()).hexdigest()} for r in conn.execute('SELECT id,file_path FROM materials WHERE file_path IS NOT NULL') if Path(r['file_path']).is_file()]
        counts={table:conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in ('users','courses','sessions','enrollments','workspaces','attempts','revisions','messages','auth_sessions','chat_requests')}
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()
    expected={'database':str(data/'educ7703.sqlite3'),'baseline_source':str(source),'course_id':course['id'],
              'session_id':sid,'question_id':qid,'teacher_id':uid,'student_id':learner['id'],'material_id':material['id'],
              'users':users,'secret_fingerprints':fingerprints,'material_files':files,'counts':counts,'workspace':work}
    (OUT/'legacy-expected.json').write_text(json.dumps(expected,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':'ready','database':expected['database'],'counts':counts,
                      'source_imported_from':str(original.__file__),'synthetic_only':True,'model_requests':0},indent=2))

if __name__=='__main__':main()
