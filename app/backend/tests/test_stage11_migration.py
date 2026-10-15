"""Genuine schema7→8 preservation, rollback, restart and backup/recovery."""
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient
from backend.aicademiya.course_staff import BACKFILL_KEY, migrate_staff
from backend.aicademiya.main import create_app
from .conftest import expect, publish
from .test_stage3_persistence import records
from .test_stage8_course_lifecycle import schema, files
from .test_stage2_backup import backup_tool, worksheet_docx, commit_payload
from .test_stage9_account_avatars import upload
from .test_stage9_feedback import create
from .test_stage11_import import preview, commit, IMPORT
from .test_stage11_accounts_staff import PASSWORD, BASE


def schema7(conn):
    conn.execute('DROP TABLE document_jobs')
    conn.execute('DROP TABLE document_revisions')
    conn.execute('DROP TABLE account_imports')
    conn.execute('DROP TABLE course_staff')
    conn.execute('DELETE FROM meta WHERE key=?', (BACKFILL_KEY,))
    conn.execute('PRAGMA user_version=7')


def original_projection(conn, original):
    current = records(conn)
    # New marker rows do not replace or normalize any original named record.
    current['meta']['rows'] = [r for r in current['meta']['rows'] if r[0] != BACKFILL_KEY]
    return {k: current[k] for k in original}


def test_genuine23_populated_tables_all_schema_rows_files_secret_preserved_once(app, teacher, student, admin, catalog):
    worksheet = expect(teacher.post('/api/sessions/s4/worksheet-import/preview', files={'file':('synthetic.docx', worksheet_docx())}))
    expect(teacher.post('/api/sessions/s4/worksheet-import/'+worksheet['import_id']+'/commit', json=commit_payload(worksheet)))
    edition = publish(teacher)['id']
    work = expect(student.get('/api/sessions/s4/workspace?version_id='+edition))
    qid = work['session']['questions'][0]['id']
    expect(student.post('/api/sessions/s4/answers/'+qid+'?version_id='+edition, json={'answer':'Retain schema7 work'}))
    expect(student.post('/api/sessions/s4/chat', json={'message':'Retain history','intent':'ask','request_id':'schema7-chat'}))
    expect(student.post('/api/sessions/s4/tutor/start', json={'request_id':'schema7-guided'}))
    info = expect(teacher.get('/api/teacher/sessions/s4/preview'))
    expect(teacher.post('/api/teacher/sessions/s4/preview/reset', json={'expected_revision':info['current_revision']}))
    expect(teacher.post('/api/sessions/s4/worksheet-import/preview', files={'file':('pending.docx', worksheet_docx())}))
    expect(upload(student)); expect(create(student))
    expect(teacher.post('/api/courses/synthetic-course/trash', json={}))
    with app.state.database.connect() as conn:
        conn.execute("INSERT OR REPLACE INTO settings VALUES('ai_api_key','SYNTHETIC_RETAIN_ONLY')")
        conn.execute("INSERT OR REPLACE INTO meta VALUES('kv_scope_secret','SYNTHETIC_RETAIN_NAMESPACE')")
        schema7(conn)
        before, before_schema = records(conn), schema(conn)
        sequence = [tuple(r) for r in conn.execute('SELECT * FROM sqlite_sequence ORDER BY name')]
        assert len(before) == 23 and all(r['rows'] for r in before.values())
    source_files = files(catalog.parent)
    for _ in range(2):
        app.state.database.initialize(catalog, demo_enabled=False)
        with app.state.database.connect() as conn:
            assert original_projection(conn, before) == before
            assert [r for r in schema(conn) if r[2] not in ('course_staff','account_imports','document_jobs','document_revisions')] == before_schema
            assert [tuple(r) for r in conn.execute('SELECT * FROM sqlite_sequence ORDER BY name')] == sequence
            assert [tuple(r) for r in conn.execute('SELECT * FROM course_staff')] == [('synthetic-course','demo-teacher')]
            assert conn.execute('SELECT count(*) FROM account_imports').fetchone()[0] == 0
            assert conn.execute('PRAGMA user_version').fetchone()[0] == 9
            assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert not conn.execute('PRAGMA foreign_key_check').fetchall()
    assert files(catalog.parent) == source_files
    assert app.version == app.openapi()['info']['version'] == '0.11.0'


@pytest.mark.parametrize('failure', ['second-table','backfill','marker','version'])
def test_savepoint_failure_rolls_back_tables_backfill_marker_version_preserves_outer(app, teacher, failure):
    with app.state.database.connect() as conn:
        schema7(conn)
    with app.state.database.connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute("INSERT INTO settings VALUES('stage11-outer','retained')")
        before, before_schema = records(conn), schema(conn)
        def authorizer(action, one, two, database, trigger):
            denied = ((failure=='second-table' and action==sqlite3.SQLITE_CREATE_TABLE and one=='account_imports')
                      or (failure=='backfill' and action==sqlite3.SQLITE_INSERT and one=='course_staff')
                      or (failure=='marker' and action==sqlite3.SQLITE_INSERT and one=='meta')
                      or (failure=='version' and action==sqlite3.SQLITE_PRAGMA and one=='user_version' and two=='8'))
            return sqlite3.SQLITE_DENY if denied else sqlite3.SQLITE_OK
        conn.set_authorizer(authorizer)
        try:
            with pytest.raises(sqlite3.DatabaseError):
                migrate_staff(conn)
        finally:
            conn.set_authorizer(None)
        assert records(conn) == before and schema(conn) == before_schema
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 7
        assert conn.in_transaction
        migrate_staff(conn)
        assert original_projection(conn, before) == before
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 8


def test_repeat_initialization_never_restores_removed_owner_or_other_assignments(app, teacher, catalog):
    with app.state.database.connect() as conn:
        conn.execute("DELETE FROM course_staff WHERE course_id='synthetic-course'")
    for demo in (False, True, False):
        app.state.database.initialize(catalog, demo_enabled=demo)
        with app.state.database.connect() as conn:
            assert not conn.execute("SELECT 1 FROM course_staff WHERE course_id='synthetic-course'").fetchone()
            assert conn.execute("SELECT owner_id FROM courses WHERE id='synthetic-course'").fetchone()[0] == 'demo-teacher'
    expect(teacher.get('/api/sessions/s4'), 403)
    assert expect(teacher.get('/api/courses')) == []


def test_new_seed_cli_and_course_creation_claims_are_memberships(tmp_path, catalog):
    from backend.aicademiya.db import Database
    db = Database(tmp_path/'claims.sqlite3')
    db.initialize(catalog, demo_enabled=False)
    admin = db.create_admin('Synthetic bootstrap','bootstrap@example.invalid',PASSWORD)
    with db.connect() as conn:
        assert [tuple(r) for r in conn.execute('SELECT * FROM course_staff')] == [('synthetic-course',admin)]
        conn.execute("INSERT INTO courses(id,code,title,description,join_code) VALUES('other-unowned','UNOWNED','Unowned synthetic','','unowned-invite')")
    teacher = db.create_teacher('Synthetic teacher','teacher@example.invalid',PASSWORD)
    with db.connect() as conn:
        assert [tuple(r) for r in conn.execute('SELECT * FROM course_staff ORDER BY course_id')] == [('other-unowned',teacher),('synthetic-course',admin)]
    db.initialize(catalog, demo_enabled=False)
    with db.connect() as conn:
        assert conn.execute('SELECT count(*) FROM course_staff').fetchone()[0] == 2


def test_backup_restore_hash_only_pending_and_committed_recovery_restart(app, admin, catalog, tmp_path):
    pending = expect(preview(admin, b'name,email,role\nPending,pending-restore@example.invalid,teacher\n', default_temporary_password=PASSWORD))
    committed = expect(preview(admin, b'name,email,role\nCommitted,committed-restore@example.invalid,admin\n', default_temporary_password=PASSWORD))
    result = expect(commit(admin, committed['import_id']))
    with app.state.database.connect() as conn:
        before = records(conn)
        original_schema = schema(conn)
    backup, restored = tmp_path/'stage11-backup', tmp_path/'stage11-restored'
    backup_tool.backup(app.state.database.path.parent, backup, catalog.parent/'materials')
    report = backup_tool.restore(backup, restored)
    assert report['records_match'] and report['files_match']
    manifest = json.loads((backup/'manifest.json').read_text(encoding='utf-8'))
    assert set(manifest['tables']) == set(before) | {'sqlite_sequence'}
    restored_app = create_app(data_dir=restored, catalog_path=catalog, demo_enabled=True, frontend_dir=tmp_path/'no-dist')
    with TestClient(restored_app) as client:
        client.cookies.update(admin.cookies)
        assert expect(client.get(IMPORT+'/'+committed['import_id']))['result'] == result
        assert expect(commit(client, committed['import_id'])) == result
        assert expect(client.get(IMPORT+'/'+pending['import_id']))['status'] == 'pending'
        pending_result = expect(commit(client, pending['import_id']))
        assert pending_result['created'] == 1
        assert expect(client.get(BASE+'/'+pending_result['user_ids'][0]))['user']['role'] == 'teacher'
    with restored_app.state.database.connect() as conn:
        assert schema(conn) == original_schema
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 9
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()
