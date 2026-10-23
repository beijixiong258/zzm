"""Durability/CLI/upgrade/real backup restore into new synthetic directories."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

from fastapi.testclient import TestClient
import pytest

from backend.aicademiya.main import create_app
from backend.aicademiya.db import issue_session
from backend.aicademiya.document_storage import enqueue_job, migrate_documents
from backend.aicademiya.document_jobs import configured_command
from backend.aicademiya.course_staff import AuthenticatedUser
from .conftest import expect, publish
from .test_stage12_document_api import (docenv, Processor, complete, endpoint, page, pdf_bytes,
                                       review_payload, upload, wait_job)
from .test_stage3_persistence import records
from .test_stage8_course_lifecycle import schema, files
from .test_stage2_backup import backup_tool, worksheet_docx, commit_payload
from .test_stage9_account_avatars import upload as avatar_upload
from .test_stage9_feedback import create as feedback_create


def cli_command(extra=''):
    # Real shell=False child command; output unmistakably SYNTHETIC.
    code = "import argparse; from pathlib import Path; from backend.tests.test_stage12_document_api import synthetic_bundle; "
    code += "p=argparse.ArgumentParser(); p.add_argument('--input'); p.add_argument('--output'); a=p.parse_args(); "
    code += "assert not Path(a.output).exists(); "
    code += extra or "synthetic_bundle(Path(a.input),Path(a.output))"
    return [sys.executable, '-c', code]


def process_running(pid):
    if os.name == 'nt':
        import ctypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE only
        if not handle:
            if ctypes.get_last_error() == 87:  # Invalid PID, not access denied.
                return False
            raise OSError('Cannot verify owned process status')
        try:
            return kernel.WaitForSingleObject(handle, 0) == 258
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        status = Path('/proc')/str(pid)/'stat'
        return not status.exists() or status.read_text().split(') ',1)[1][0] != 'Z'
    except ProcessLookupError:
        return False


def test_real_synthetic_cli_boundary_shell_false_env_and_readback(tmp_path, catalog, monkeypatch):
    monkeypatch.setenv('AICADEMIYA_DOCUMENT_WORKER_COMMAND', json.dumps(cli_command()))
    from backend.aicademiya import document_jobs
    original = document_jobs.subprocess.Popen
    launches = []
    def record(*args, **kwargs):
        launches.append((args, kwargs))
        return original(*args, **kwargs)
    monkeypatch.setattr(document_jobs.subprocess, 'Popen', record)
    app = create_app(data_dir=tmp_path/'cli-data', catalog_path=catalog, demo_enabled=True, frontend_dir=tmp_path/'dist')
    with TestClient(app) as teacher:
        expect(teacher.post('/api/auth/demo', json={'role':'teacher'}))
        mid, rid, job = complete(teacher)
        assert expect(page(teacher, mid, rid))['blocks'][0]['text'].startswith('SYNTHETIC')
        assert launches and launches[0][1]['shell'] is False
        args = launches[0][0][0]
        assert args[-4] == '--input' and args[-2] == '--output'
        assert Path(args[-1]).name == job['id']
        assert job == expect(teacher.get(endpoint(mid)+'/jobs/requests/upload:'+mid))
    assert app.state.document_queue.thread is None and app.state.document_queue.child is None


def test_real_worker_timeout_terminates_owned_tree_no_stderr_path_leak(tmp_path, catalog, monkeypatch):
    monkeypatch.delenv('AICADEMIYA_DOCUMENT_WORKER_COMMAND', raising=False)
    extra = "import os, subprocess, time; root=Path(a.output); root.mkdir(parents=True); "
    extra += "child=subprocess.Popen([__import__('sys').executable,'-c','import time; time.sleep(120)']); "
    extra += "(root/'owned-pids.json').write_text(__import__('json').dumps([os.getpid(),child.pid])); "
    extra += "print('SYNTHETIC_SECRET /private/provider --password',flush=True); time.sleep(120)"
    app = create_app(data_dir=tmp_path/'timeout-data', catalog_path=catalog, demo_enabled=True, frontend_dir=tmp_path/'dist',
                     document_worker_command=cli_command(extra), document_worker_timeout=3)
    with TestClient(app) as teacher:
        expect(teacher.post('/api/auth/demo', json={'role':'teacher'}))
        material = expect(upload(teacher))
        job = wait_job(teacher, material['id'])
        assert job['status'] == 'failed' and 'SECRET' not in job['error'] and '/private' not in job['error']
        pidfile = tmp_path/'timeout-data'/'uploads'/'documents'/job['id']/'owned-pids.json'
        assert pidfile.is_file(), 'The real synthetic child must run before the timeout assertion'
        pids = json.loads(pidfile.read_text())
        deadline = time.monotonic()+10
        while time.monotonic() < deadline and any(process_running(pid) for pid in pids):
            time.sleep(.05)
        assert not any(process_running(pid) for pid in pids)
        assert app.state.document_queue.child is None
    assert app.state.document_queue.thread is None


@pytest.mark.parametrize('command', ['', 'not json', '"shell string"', '[42]', '[]'], ids=['absent','invalidjson','string','number','empty'])
def test_invalid_worker_configuration_is_unavailable(monkeypatch, command):
    monkeypatch.setenv('AICADEMIYA_DOCUMENT_WORKER_COMMAND', command)
    assert configured_command() is None


def test_restart_running_failed_queued_retained_then_executed_once(docenv, tmp_path, catalog, monkeypatch):
    app, teacher, student, processor = docenv
    mid, rid, _ = complete(teacher)
    second_mid, _, _ = complete(teacher)
    app.state.document_queue.close()
    with app.state.database.connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        token = issue_session(conn, 'demo-teacher')
        actor = AuthenticatedUser({'id':'demo-teacher','role':'teacher'}, hashlib.sha256(token.encode()).hexdigest())
        accepted = enqueue_job(conn, mid, actor, 'interrupted', rid)
        second_rid = json.loads(conn.execute('SELECT content_json FROM materials WHERE id=?', (second_mid,)).fetchone()[0])['document']['revision_id']
        queued = enqueue_job(conn, second_mid, actor, 'retained-queued', second_rid)
        conn.execute("UPDATE document_jobs SET status='running',started_at='2026-01-01T00:00:00+00:00' WHERE id=?", (accepted['id'],))
    monkeypatch.delenv('AICADEMIYA_DOCUMENT_WORKER_COMMAND', raising=False)
    dormant = create_app(data_dir=app.state.database.path.parent, catalog_path=catalog, demo_enabled=True, frontend_dir=tmp_path/'dist')
    with TestClient(dormant) as client:
        client.cookies.set('aicademiya_session', token)
        interrupted = expect(client.get(endpoint(mid)+'/jobs/requests/interrupted'))
        assert interrupted['status'] == 'failed' and interrupted['finished_at']
        retained = expect(client.get(endpoint(second_mid)+'/jobs/requests/retained-queued'))
        assert retained['status'] == 'queued' and retained['started_at'] is None
        assert expect(client.get(endpoint(mid)))['document']['revision_id'] == rid
    resumed_processor = Processor()
    resumed = create_app(data_dir=app.state.database.path.parent, catalog_path=catalog, demo_enabled=True,
                         frontend_dir=tmp_path/'dist', document_processor=resumed_processor)
    with TestClient(resumed) as client:
        client.cookies.set('aicademiya_session', token)
        completed = wait_job(client, second_mid, queued['id'])
        assert completed['status'] == 'completed' and len(resumed_processor.calls) == 1
        assert expect(client.get(endpoint(mid)+'/jobs/'+accepted['id'])) == interrupted
    assert resumed.state.document_queue.thread is None


def test_install_failure_rolls_back_revision_material_and_completed_job_atomically(docenv, monkeypatch):
    app, teacher, student, processor = docenv
    mid, rid, _ = complete(teacher)
    from backend.aicademiya import document_jobs
    original = document_jobs.install_document
    def fail_after_writes(*args):
        original(*args)
        raise sqlite3.OperationalError('SYNTHETIC commit-boundary failure')
    monkeypatch.setattr(document_jobs, 'install_document', fail_after_writes)
    accepted = expect(teacher.post(endpoint(mid)+'/jobs', json={'request_id':'rollback-install','expected_revision':rid}))
    outcome = wait_job(teacher, mid, accepted['id'])
    assert outcome['status'] == 'failed' and outcome['processed_pages'] == 0 and outcome['revision_id'] is None
    assert expect(teacher.get(endpoint(mid)))['document']['revision_id'] == rid
    with app.state.database.connect() as conn:
        assert conn.execute('SELECT count(*) FROM document_revisions WHERE material_id=?', (mid,)).fetchone()[0] == 1


def populate_old25(app, teacher, student):
    worksheet = expect(teacher.post('/api/sessions/s4/worksheet-import/preview', files={'file':('synthetic.docx',worksheet_docx())}))
    expect(teacher.post('/api/sessions/s4/worksheet-import/'+worksheet['import_id']+'/commit', json=commit_payload(worksheet)))
    edition = publish(teacher)['id']
    workspace = expect(student.get('/api/sessions/s4/workspace', params={'version_id':edition}))
    qid = workspace['session']['questions'][0]['id']
    expect(student.post('/api/sessions/s4/answers/'+qid, params={'version_id':edition}, json={'answer':'SYNTHETIC persisted answer'}))
    expect(student.post('/api/sessions/s4/chat', params={'version_id':edition}, json={'message':'SYNTHETIC persisted chat','intent':'ask','request_id':'retained-chat'}))
    expect(student.post('/api/sessions/s4/tutor/start', params={'version_id':edition}, json={'request_id':'retained-tutor'}))
    preview = expect(teacher.get('/api/teacher/sessions/s4/preview'))
    expect(teacher.post('/api/teacher/sessions/s4/preview/reset', json={'expected_revision':preview['current_revision']}))
    expect(teacher.post('/api/sessions/s4/worksheet-import/preview', files={'file':('pending.docx',worksheet_docx())}))
    expect(avatar_upload(student)); expect(feedback_create(student))
    with app.state.database.connect() as conn:
        token = issue_session(conn, 'demo-admin')
    admin = TestClient(app)
    admin.cookies.set('aicademiya_session', token)
    try:
        expect(admin.post('/api/admin/users/import/preview', data={'default_temporary_password':'SYNTHETIC-safe-1'},
                          files={'file':('synthetic.csv',b'name,email,role\nPending,pending@example.invalid,teacher\n')}))
    finally:
        admin.close()
    expect(teacher.post('/api/courses/synthetic-course/trash', json={}))
    with app.state.database.connect() as conn:
        conn.execute("INSERT OR REPLACE INTO settings VALUES('retain-only-key','SYNTHETIC_PRIVATE')")
        conn.execute("INSERT OR REPLACE INTO meta VALUES('kv_scope_secret','SYNTHETIC_SCOPE_PRESERVE')")


def remove_empty_documents(conn):
    assert conn.execute('SELECT count(*) FROM document_jobs').fetchone()[0] == 0
    assert conn.execute('SELECT count(*) FROM document_revisions').fetchone()[0] == 0
    conn.execute('DROP TABLE document_jobs')
    conn.execute('DROP TABLE document_revisions')
    conn.execute('PRAGMA user_version=8')


def test_genuine25_populated_schemas_named_records_preserved_schema9_no_autoextract(docenv, catalog):
    app, teacher, student, processor = docenv
    populate_old25(app, teacher, student)
    app.state.document_queue.close()
    with app.state.database.connect() as conn:
        remove_empty_documents(conn)
        before, before_schema = records(conn), schema(conn)
        sequence = [tuple(r) for r in conn.execute('SELECT * FROM sqlite_sequence ORDER BY name')]
        assert len(before) == 25 and all(item['rows'] for item in before.values())
    for _ in range(2):
        app.state.database.initialize(catalog, demo_enabled=False)
        with app.state.database.connect() as conn:
            current = records(conn)
            assert {k: current[k] for k in before} == before
            assert [item for item in schema(conn) if item[2] not in ('document_jobs','document_revisions')] == before_schema
            assert [tuple(r) for r in conn.execute('SELECT * FROM sqlite_sequence ORDER BY name')] == sequence
            assert len(current) == 27
            assert current['document_jobs']['rows'] == current['document_revisions']['rows'] == []
            assert conn.execute('PRAGMA user_version').fetchone()[0] == 9
            assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert not conn.execute('PRAGMA foreign_key_check').fetchall()
    assert not processor.calls and app.version == app.openapi()['info']['version'] == '0.11.0'


@pytest.mark.parametrize('failure', ['second-table','trigger','schema-version'], ids=['second-table','trigger','user-version'])
def test_additive_migration_savepoint_atomic_failure_preserves_outer(docenv, failure):
    app, teacher, student, processor = docenv
    app.state.document_queue.close()
    with app.state.database.connect() as conn:
        remove_empty_documents(conn)
    with app.state.database.connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute("INSERT INTO settings VALUES('stage12-outer','retained')")
        before, before_schema = records(conn), schema(conn)
        def authorizer(action, one, two, dbname, trigger):
            denied = ((failure == 'second-table' and action == sqlite3.SQLITE_CREATE_TABLE and one == 'document_revisions')
                or (failure == 'trigger' and action == sqlite3.SQLITE_CREATE_TRIGGER and one == 'immutable_document_update')
                or (failure == 'schema-version' and action == sqlite3.SQLITE_PRAGMA and one == 'user_version' and two == '9'))
            return sqlite3.SQLITE_DENY if denied else sqlite3.SQLITE_OK
        conn.set_authorizer(authorizer)
        try:
            with pytest.raises(sqlite3.DatabaseError):
                migrate_documents(conn)
        finally:
            conn.set_authorizer(None)
        assert records(conn) == before and schema(conn) == before_schema
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 8 and conn.in_transaction
        migrate_documents(conn)
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 9
        assert {k: records(conn)[k] for k in before} == before


def test_actual_backup_cli_restore_original_unavailable_current_old_assets_and_review_receipts(docenv, catalog, tmp_path, monkeypatch):
    app, teacher, student, processor = docenv
    mid, old_rid, _ = complete(teacher)
    old_edition = publish(teacher)['id']
    expect(student.get('/api/sessions/s4/workspace', params={'version_id':old_edition}))
    reparse = expect(teacher.post(endpoint(mid)+'/jobs', json={'request_id':'fresh-parse','expected_revision':old_rid}))
    newer = wait_job(teacher, mid, reparse['id'])['revision_id']
    receipt = expect(teacher.post(endpoint(mid)+'/reviews', json=review_payload(newer, text='SYNTHETIC restored reviewed text')))
    rid = receipt['document']['revision_id']
    current_edition = publish(teacher)['id']
    # Arbitrary source-like metadata is NOT a path binding and remains byte-exact.
    with app.state.database.connect() as conn:
        conn.execute("INSERT INTO settings VALUES('literal-path','C:/synthetic/not-a-binding')")
        before = records(conn)
        before_schema = schema(conn)
    root = app.state.database.path.parent
    original_bytes = teacher.get('/api/materials/'+mid+'/download').content
    backup, restored = tmp_path/'private-backup', tmp_path/'new-restore'
    args = [sys.executable, str(Path(__file__).resolve().parents[2]/'tools'/'backup_data.py')]
    result = subprocess.run([*args,'backup','--data-dir',str(root),'--destination',str(backup),
                             '--materials-root',str(catalog.parent/'materials')], capture_output=True, text=True, check=True)
    report = json.loads(result.stdout)
    assert report['integrity'] == 'ok'
    restore_result = subprocess.run([*args,'restore','--source',str(backup),'--destination',str(restored)],
                                    capture_output=True, text=True, check=True)
    restored_report = json.loads(restore_result.stdout)
    assert restored_report['records_match'] and restored_report['files_match']
    bindings = json.loads((backup/'manifest.json').read_text())['path_bindings']
    assert sum('document_dir' in key for key in bindings) >= 3
    # Close the ONLY owned queue and hide synthetic roots, never source originals.
    app.state.document_queue.close()
    hidden, hidden_seed = root.with_name('source-unavailable'), catalog.parent.with_name('seed-unavailable')
    root.rename(hidden)
    catalog.parent.rename(hidden_seed)
    try:
        assert not root.exists() and not catalog.exists()
        clone = create_app(data_dir=restored, catalog_path=catalog, demo_enabled=True, frontend_dir=tmp_path/'dist')
        with TestClient(clone) as client:
            client.cookies.update(teacher.cookies)
            assert expect(client.get(endpoint(mid)))['document']['revision_id'] == rid
            assert expect(client.get(endpoint(mid)+'/reviews/review-1')) == receipt
            assert expect(client.get(endpoint(mid)+'/jobs/requests/fresh-parse'))['revision_id'] == newer
            assert expect(page(client, mid, rid, 2))['blocks'][0]['text'] == 'SYNTHETIC restored reviewed text'
            old_page = expect(page(client, mid, old_rid, 2, old_edition))
            assert old_page['blocks'][0]['text'].endswith('page 2')
            assert client.get(old_page['image_url']).status_code == 200
            assert client.get(old_page['blocks'][0]['assets'][0]).status_code == 200
            current_page = expect(page(client, mid, rid, 2))
            assert client.get(current_page['image_url']).status_code == 200
            assert client.get('/api/materials/'+mid+'/download', params={'version_id':old_edition}).content == original_bytes
            with clone.state.database.connect() as conn:
                assert schema(conn) == before_schema
                for table in before:
                    if table not in ('materials','course_versions'):
                        assert records(conn)[table] == before[table]
                found_roots = []
                for row in conn.execute('SELECT content_json FROM materials'):
                    value = json.loads(row[0])
                    if value.get('document_dir'):
                        found_roots.append(Path(value['document_dir']))
                for row in conn.execute('SELECT snapshot_json FROM course_versions'):
                    for session in json.loads(row[0])['sessions']:
                        for material in session.get('_materials',[]):
                            value = json.loads(material['content_json'])
                            if value.get('document_dir'):
                                found_roots.append(Path(value['document_dir']))
                assert len(set(found_roots)) == 2 and all(p.is_relative_to(restored) for p in found_roots)
                assert all((p/'raw'/'synthetic-receipt.txt').is_file() for p in found_roots)
    finally:
        hidden.rename(root)
        hidden_seed.rename(catalog.parent)
