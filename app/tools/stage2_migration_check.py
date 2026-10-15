"""Independently migrate genuine baseline fixture and verify learning-data preservation.

Run after backend handoff. Creates a sibling test DB, never opens default data for writes.
"""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/stage2'
sys.path.insert(0,str(ROOT))


def main():
    expected=json.loads((OUT/'legacy-expected.json').read_text(encoding='utf-8'))
    source=Path(expected['database'])
    assert source.is_relative_to(OUT)
    target=source.with_name('migrated-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.sqlite3')
    with sqlite3.connect(f'file:{source.as_posix()}?mode=ro',uri=True) as old, sqlite3.connect(target) as new:
        auth_before=old.execute('SELECT token_hash,user_id,expires_at FROM auth_sessions ORDER BY token_hash').fetchall()
        old.backup(new)
    os.environ.update(AICADEMIYA_AI_MODE='demo',AICADEMIYA_AI_PROVIDER='',AICADEMIYA_WEB_SEARCH_ENABLED='false',TAVILY_API_KEY='')
    from fastapi.testclient import TestClient
    from backend.aicademiya.main import create_app
    app=create_app(data_dir=source.parent,db_path=target,catalog_path=ROOT/'sample_data/catalog.json',demo_enabled=True)
    checks=[]
    def ok(name, condition):
        assert condition,name
        checks.append(name)
    def value(response):
        assert response.status_code==200,(response.status_code,response.text[:500])
        return response.json()
    with TestClient(app) as teacher, TestClient(app) as student, TestClient(app) as admin:
        with app.state.database.connect() as conn:
            ok('foreign keys intact',not conn.execute('PRAGMA foreign_key_check').fetchall())
            for old_user in expected['users']:
                current=conn.execute('SELECT * FROM users WHERE id=?',(old_user['id'],)).fetchone()
                ok('legacy user preserved: '+old_user['id'],current is not None and all(current[k]==v for k,v in old_user.items()))
            auth_after=[tuple(r) for r in conn.execute('SELECT token_hash,user_id,expires_at FROM auth_sessions ORDER BY token_hash')]
            ok('old login sessions preserved',all(row in auth_after for row in auth_before))
            for key,digest in expected['secret_fingerprints'].items():
                table='meta' if key=='kv_scope_secret' else 'settings'
                row=conn.execute(f'SELECT value FROM {table} WHERE key=?',(key,)).fetchone()
                ok('saved private setting preserved: '+key,row is not None and hashlib.sha256(row[0].encode()).hexdigest()==digest)
        value(teacher.post('/api/auth/login',json={'email':'migration-teacher@example.invalid','password':'SyntheticMigration9'}))
        value(student.post('/api/auth/login',json={'email':'migration-student@example.invalid','password':'SyntheticStudent9'}))
        value(admin.post('/api/auth/demo',json={'role':'admin'}))
        ok('teacher no longer configures platform model',teacher.get('/api/teacher/settings').status_code==403)
        ok('admin model settings accessible',admin.get('/api/teacher/settings').status_code==200)
        sid=expected['session_id'];qid=expected['question_id']
        current=value(student.get(f'/api/sessions/{sid}/workspace'))
        old=expected['workspace']
        ok('original question wording preserved',current['session']['questions'][0]['prompt']==old['session']['questions'][0]['prompt'])
        ok('legacy course has baseline published version',current['version']['id'] is not None and current['version']['number']==1)
        ok('answer/revisions/reveal marker preserved',current['attempts']==old['attempts'])
        ok('submission/review preserved',current['submission']==old['submission'])
        ok('raw message count preserved',len(current['messages'])==len(old['messages']))
        for before,after in zip(old['messages'],current['messages']):
            ok('raw message preserved: '+before['id'],all(after.get(k)==v for k,v in before.items()))
        ref=value(student.get(f'/api/sessions/{sid}/references/{qid}',params={'version_id':current['version']['id']}))
        ok('previously revealed reference readable without mutation',ref['reference']=='PRIVATE MIGRATION REFERENCE')
        material=next(m for m in current['session']['materials'] if m['id']==expected['material_id'])
        response=student.get(material['download_url'])
        ok('original material bytes accessible',response.status_code==200 and response.content==b'Original synthetic material bytes.')
        for item in expected['material_files']:
            ok('original material file unchanged: '+item['id'],Path(item['path']).is_file() and hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()==item['sha256'])
        export=value(student.get(f'/api/sessions/{sid}/export',params={'version_id':current['version']['id']}))
        ok('versioned export retains legacy answer',export['attempts'][qid]['answer']=='Original revised answer')
        # A second application initialization must not reseed/rewrite/migrate repeatedly.
    reopened=create_app(data_dir=source.parent,db_path=target,catalog_path=ROOT/'sample_data/catalog.json',demo_enabled=True)
    with TestClient(reopened) as student:
        value(student.post('/api/auth/login',json={'email':'migration-student@example.invalid','password':'SyntheticStudent9'}))
        again=value(student.get(f'/api/sessions/{expected["session_id"]}/workspace'))
        ok('repeat initialization preserves learning run',again['attempts']==expected['workspace']['attempts'] and again['version']['number']==1)
    result={'status':'passed','checks':checks,'database':str(target),'baseline_source':expected['baseline_source'],'real_user_data_touched':False}
    (OUT/'migration-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':'passed','checks':len(checks),'database':str(target),'real_user_data_touched':False},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
