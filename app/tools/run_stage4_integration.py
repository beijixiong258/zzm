"""Stage4 actual HTTP/SQLite + installed-browser acceptance; synthetic demo only.

Local: .venv/Scripts/python.exe tools/run_stage4_integration.py --browser
Staged Linux (isolated QA ONLY): --base-url URL --confirm-test-data --browser
No frontend build, production access, route interception, search or real inference.
"""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import uuid

import httpx

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'artifacts/stage4/ocr/run-20261007T043643Z-116c3ce1/inputs'


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def ready(process, base):
    with httpx.Client(trust_env=False, timeout=2) as client:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('Owned QA server exited; see server.log')
            try:
                if client.get(base + '/api/health').status_code == 200:
                    return
            except httpx.RequestError:
                pass
            time.sleep(.15)
    raise RuntimeError('Owned QA readiness timeout')


def stop(process):
    process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def listener_closed(port, timeout=3):
    deadline = time.monotonic() + timeout
    while True:
        with socket.socket() as sock:
            sock.settimeout(.5)
            closed = sock.connect_ex(('127.0.0.1', port)) != 0
        if closed or time.monotonic() >= deadline:
            return closed
        time.sleep(.1)


def sqlite_evidence(data, acceptance):
    db = data / 'aicademiya.sqlite3'
    with sqlite3.connect(f'file:{db.as_posix()}?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        report = {'integrity_check': conn.execute('PRAGMA integrity_check').fetchone()[0],
                  'foreign_key_check': [list(r) for r in conn.execute('PRAGMA foreign_key_check')],
                  'schema_version': conn.execute('PRAGMA user_version').fetchone()[0],
                  'row_counts': {t: conn.execute('SELECT count(*) FROM "' + t + '"').fetchone()[0] for t in tables}}
        ids = acceptance.get('ids', {})
        exact = ids.get('abcde', [])
        if exact:
            rows = list(conn.execute('SELECT id,session_id,file_path FROM materials WHERE id IN (' + ','.join('?' for _ in exact) + ')', exact))
            report['abcde'] = {'rows': len(rows), 'distinct_original_files': len({r['file_path'] for r in rows}),
                               'all_original_files_retained': all(Path(r['file_path']).is_file() for r in rows),
                               'b_origin_session_unchanged': next(r for r in rows if r['id'] == ids['b'])['session_id'] == ids['s1'],
                               'memberships': {r['id']: [v[0] for v in conn.execute('SELECT session_id FROM session_materials WHERE material_id=? ORDER BY session_id', (r['id'],))] for r in rows}}
            if len(rows) != 5 or report['abcde']['distinct_original_files'] != 5 or not report['abcde']['all_original_files_retained'] or not report['abcde']['b_origin_session_unchanged']:
                raise AssertionError('SQLite ABCDE same-ID/original-file preservation failed')
        if report['integrity_check'] != 'ok' or report['foreign_key_check'] or report['schema_version'] != 4:
            raise AssertionError('SQLite integrity/FK/schema4 verification failed')
        return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-url', default=os.getenv('AICADEMIYA_TEST_URL'))
    p.add_argument('--confirm-test-data', action='store_true')
    p.add_argument('--artifact-dir')
    p.add_argument('--fixture-dir', default=str(FIXTURES), help='Local labelled synthetic OCR input directory, also for remote QA')
    p.add_argument('--browser', action='store_true', help='Compatibility alias; browser group is enabled by default')
    p.add_argument('--skip-browser', action='store_true')
    p.add_argument('--skip-api', action='store_true')
    p.add_argument('--chrome-path')
    p.add_argument('--build-wait-seconds', type=int, default=0, help='Wait for parent-owned production build; NEVER build here')
    args = p.parse_args()
    if args.base_url and not args.confirm_test_data:
        p.error('External target requires --confirm-test-data: isolated synthetic demo QA, NEVER production.')
    if args.skip_api and args.skip_browser:
        p.error('At least one acceptance group is required.')
    fixtures = Path(args.fixture_dir).resolve()
    for name in ('synthetic_scan.png', 'synthetic_embedded_grouped.pptx', 'synthetic_mixed.pdf'):
        if not (fixtures / name).is_file():
            p.error('Missing labelled synthetic fixture: ' + str(fixtures / name))
    build = {}
    if not args.base_url and not args.skip_browser:
        index = ROOT / 'frontend/dist/index.html'
        sources = [f for folder in ('src', 'public') for f in (ROOT / 'frontend' / folder).rglob('*') if f.is_file()]
        newest = max(f.stat().st_mtime for f in sources)
        deadline = time.monotonic() + max(0, args.build_wait_seconds)
        while not index.is_file() or index.stat().st_mtime < newest:
            if time.monotonic() >= deadline:
                p.error('frontend/dist is absent/stale. Parent must complete npm --prefix frontend run build; harness does not rebuild.')
            time.sleep(.25)
        build = {'index_sha256': hashlib.sha256(index.read_bytes()).hexdigest(), 'index_mtime': index.stat().st_mtime,
                 'latest_source_mtime': newest, 'build_owned_by_harness': False}
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = Path(args.artifact_dir or ROOT / 'artifacts/stage4' / f'integration-{stamp}-{uuid.uuid4().hex[:8]}').resolve()
    if not out.name.startswith('integration-'):
        p.error('Use a unique integration-* artifact directory.')
    out.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    scratch = Path(os.getenv('TMPDIR', str(Path.home() / 'AppData/Local/hermes/cache/scratch')))
    scratch.mkdir(parents=True, exist_ok=True)
    env.update(TMPDIR=str(scratch), TEMP=str(scratch), TMP=str(scratch),
               AICADEMIYA_DEMO_ENABLED='true', AICADEMIYA_AI_MODE='demo', AICADEMIYA_COOKIE_SECURE='false',
               AICADEMIYA_AI_PROVIDER='', AICADEMIYA_AI_BASE_URL='', AICADEMIYA_AI_MODEL='', AICADEMIYA_AI_API_KEY='',
               AICADEMIYA_WEB_SEARCH_ENABLED='false', TAVILY_API_KEY='',
               NO_PROXY='127.0.0.1,localhost,::1', no_proxy='127.0.0.1,localhost,::1')
    if args.chrome_path:
        env['AICADEMIYA_CHROME_PATH'] = args.chrome_path
    commands = []
    if not args.skip_api:
        commands.append(('api', [sys.executable, str(ROOT / 'tools/stage4_api_acceptance.py')]))
    if not args.skip_browser:
        node = shutil.which('node')
        if not node:
            p.error('Node and frontend-local @playwright/test are required.')
        commands.append(('browser', [node, str(ROOT / 'tools/stage4_browser_acceptance.mjs')]))
    groups = []
    for name, command in commands:
        folder = out / name
        folder.mkdir()
        data = folder / 'data'
        record = {'name': name, 'status': 'failed', 'owned_server': not bool(args.base_url)}
        process = log = None
        try:
            childenv = env.copy()
            base = (args.base_url or f'http://127.0.0.1:{free_port()}').rstrip('/')
            record['base_url'] = base
            childenv.update(AICADEMIYA_TEST_URL=base, AICADEMIYA_TEST_ARTIFACT_DIR=str(folder))
            servercmd = [sys.executable, '-m', 'uvicorn', 'backend.aicademiya.main:app', '--host', '127.0.0.1', '--port', base.rsplit(':', 1)[1]]
            if not args.base_url:
                data.mkdir()
                childenv['AICADEMIYA_DATA_DIR'] = str(data)
                log = (folder / 'server.log').open('w', encoding='utf-8')
                process = subprocess.Popen(servercmd, cwd=ROOT, env=childenv, stdout=log, stderr=subprocess.STDOUT)
                record['server_pid'] = process.pid
                ready(process, base)
            else:
                # Do not let inherited local DB configuration imply remote SQLite inspection.
                childenv.pop('AICADEMIYA_DATA_DIR', None)
            with (folder / 'harness.log').open('w', encoding='utf-8') as harnesslog:
                done = subprocess.run(command + ['--base-url', base, '--confirm-test-data', '--artifact-dir', str(folder), '--fixture-dir', str(fixtures)],
                                      cwd=ROOT, env=childenv, stdout=harnesslog, stderr=subprocess.STDOUT, timeout=900)
            record['exit_code'] = done.returncode
            resultfile = folder / 'result.json'
            if resultfile.is_file():
                record['acceptance'] = json.loads(resultfile.read_text(encoding='utf-8'))
            record['status'] = 'passed' if done.returncode == 0 and record.get('acceptance', {}).get('status') == 'passed' else 'failed'
            if process and record.get('acceptance', {}).get('ids', {}).get('expected_final'):
                # Real restart is runner-owned; no direct SQL writes or route fixtures.
                stop(process)
                process = subprocess.Popen(servercmd, cwd=ROOT, env=childenv, stdout=log, stderr=subprocess.STDOUT)
                record['restart_pid'] = process.pid
                ready(process, base)
                with httpx.Client(base_url=base, trust_env=False, timeout=30) as c:
                    c.post('/api/auth/demo', json={'role': 'teacher'}).raise_for_status()
                    expected = record['acceptance']['ids']['expected_final']
                    actual = {}
                    for sid, mids in expected.items():
                        r = c.get('/api/sessions/' + sid)
                        r.raise_for_status()
                        actual[sid] = sorted(m['id'] for m in r.json()['materials'])
                        if actual[sid] != sorted(mids):
                            raise AssertionError('Restart incorrectly changed detached material membership')
                    record['restart_membership_readback'] = {'passed': True, 'sessions': actual}
        except Exception as exc:
            record.update(status='failed', error=str(exc))
        finally:
            if process:
                stop(process)
                record['owned_server_stopped'] = process.poll() is not None
                record['owned_listener_closed'] = listener_closed(int(base.rsplit(':', 1)[1]))
                if not record['owned_listener_closed']:
                    record.update(status='failed', cleanup_error='Owned loopback listener did not close after server shutdown')
            if log:
                log.close()
            if (data / 'aicademiya.sqlite3').is_file():
                try:
                    record['sqlite'] = sqlite_evidence(data, record.get('acceptance', {}))
                except Exception as exc:
                    record.update(status='failed', sqlite_error=str(exc))
            groups.append(record)
            (folder / 'runner.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps({'group': name, 'status': record['status'], 'checks': len(record.get('acceptance', {}).get('checks', [])),
                              'failures': len(record.get('acceptance', {}).get('failures', [])), 'stopped': record.get('owned_server_stopped')}, ensure_ascii=False), flush=True)
    summary = {'status': 'passed' if groups and all(g['status'] == 'passed' for g in groups) else 'failed',
               'artifact_dir': str(out), 'frontend_build': build, 'real_application_http': True,
               'real_local_sqlite_verified': not bool(args.base_url), 'intercepted_application_routes': 0,
               'real_model_requests': 0, 'web_search_requests': 0, 'synthetic_only': True,
               'model_evidence': 'Deterministic demo, NOT real-model quality. OCR is actual server-side CPU extraction.',
               'remote_note': 'Remote DB engine/integrity requires independent staged operator verification.' if args.base_url else None,
               'default_or_production_data_touched': False, 'groups': groups}
    (out / 'result.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': summary['status'], 'artifact_dir': str(out)}, ensure_ascii=False))
    return 0 if summary['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
