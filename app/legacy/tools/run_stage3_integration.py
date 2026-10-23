"""Owned, non-destructive stage-3 HTTP/browser acceptance. Never use production data.

Local: .venv/Scripts/python.exe tools/run_stage3_integration.py --browser
External isolated QA: --base-url URL --confirm-test-data --browser --skip-protocol
Each local group has a NEW retained SQLite root. No app routes are intercepted.
"""
from pathlib import Path
import argparse
from datetime import datetime, timezone
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


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default=os.getenv('AICADEMIYA_TEST_URL'))
    parser.add_argument('--confirm-test-data', action='store_true')
    parser.add_argument('--artifact-dir', default=os.getenv('AICADEMIYA_TEST_ARTIFACT_DIR'))
    parser.add_argument('--browser', action='store_true')
    parser.add_argument('--skip-api', action='store_true')
    parser.add_argument('--skip-protocol', action='store_true')
    args = parser.parse_args()
    if args.base_url and not args.confirm_test_data:
        parser.error('External target needs --confirm-test-data: it MUST be isolated synthetic QA with demo enabled.')
    if args.base_url and not args.skip_protocol:
        parser.error('External QA must use --skip-protocol; the fixture changes only a locally owned QA database.')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = Path(args.artifact_dir or ROOT / 'artifacts' / 'stage3' / f'integration-{stamp}-{uuid.uuid4().hex[:8]}').resolve()
    if not out.name.startswith('integration-'):
        parser.error('Artifact directory must have a unique integration-* name.')
    out.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    scratch = Path(os.getenv('HERMES_HOME', str(Path.home() / 'AppData/Local/hermes'))) / 'cache/scratch'
    scratch.mkdir(parents=True, exist_ok=True)
    env.update(TMPDIR=str(scratch), TEMP=str(scratch), TMP=str(scratch),
               AICADEMIYA_DEMO_ENABLED='true', AICADEMIYA_AI_MODE='demo',
               AICADEMIYA_AI_PROVIDER='', AICADEMIYA_AI_BASE_URL='', AICADEMIYA_AI_MODEL='',
               AICADEMIYA_AI_API_KEY='', AICADEMIYA_WEB_SEARCH_ENABLED='false',
               TAVILY_API_KEY='', NO_PROXY='127.0.0.1,localhost,::1', no_proxy='127.0.0.1,localhost,::1')
    groups = []
    commands = []
    if not args.skip_api:
        commands.append(('api', [sys.executable, str(ROOT / 'tools/stage3_api_acceptance.py')]))
    if not args.skip_protocol:
        commands.append(('protocol', [sys.executable, str(ROOT / 'tools/stage3_api_acceptance.py'), '--protocol-fixture']))
    if args.browser:
        node = shutil.which('node')
        if not node:
            parser.error('Node is required for browser acceptance.')
        commands.append(('browser', [node, str(ROOT / 'tools/stage3_browser_acceptance.mjs')]))
    for name, command in commands:
        folder = out / name
        folder.mkdir()
        data = folder / 'data'
        record = {'name': name, 'status': 'failed', 'owned_server': not bool(args.base_url)}
        process = None
        log = None
        try:
            childenv = env.copy()
            base = args.base_url or f'http://127.0.0.1:{free_port()}'
            record['base_url'] = base
            childenv.update(AICADEMIYA_TEST_URL=base, AICADEMIYA_TEST_ARTIFACT_DIR=str(folder))
            if not args.base_url:
                data.mkdir()
                record['data_dir'] = str(data)
                childenv['AICADEMIYA_DATA_DIR'] = str(data)
                log = (folder / 'server.log').open('w', encoding='utf-8')
                process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'backend.aicademiya.main:app',
                                            '--host', '127.0.0.1', '--port', base.rsplit(':', 1)[1]],
                                           cwd=ROOT, env=childenv, stdout=log, stderr=subprocess.STDOUT)
                record['server_pid'] = process.pid
                with httpx.Client(trust_env=False, timeout=2) as client:
                    deadline = time.monotonic() + 45
                    while time.monotonic() < deadline:
                        if process.poll() is not None:
                            raise RuntimeError('Owned QA server exited; see server.log')
                        try:
                            if client.get(base + '/api/health').status_code == 200:
                                break
                        except httpx.RequestError:
                            pass
                        time.sleep(.15)
                    else:
                        raise RuntimeError('Owned QA readiness timeout')
            with (folder / 'harness.log').open('w', encoding='utf-8') as harnesslog:
                completed = subprocess.run(command + ['--base-url', base, '--confirm-test-data', '--artifact-dir', str(folder)],
                                           cwd=ROOT, env=childenv, stdout=harnesslog, stderr=subprocess.STDOUT, timeout=600)
            record['exit_code'] = completed.returncode
            resultfile = folder / 'result.json'
            if resultfile.exists():
                record['acceptance'] = json.loads(resultfile.read_text(encoding='utf-8'))
            record['status'] = 'passed' if completed.returncode == 0 else 'failed'
        except Exception as exc:
            record['error'] = str(exc)
        finally:
            if process:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                record['owned_server_stopped'] = process.poll() is not None
                with socket.socket() as sock:
                    sock.settimeout(1)
                    record['owned_listener_closed'] = sock.connect_ex(('127.0.0.1', int(base.rsplit(':', 1)[1]))) != 0
            if log:
                log.close()
            db = data / 'aicademiya.sqlite3'
            if db.exists():
                with sqlite3.connect(f'file:{db.as_posix()}?mode=ro', uri=True) as conn:
                    tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
                    record['sqlite'] = {'integrity_check': conn.execute('PRAGMA integrity_check').fetchone()[0],
                                        'foreign_key_check': conn.execute('PRAGMA foreign_key_check').fetchall(),
                                        'row_counts': {table: conn.execute('SELECT count(*) FROM "' + table + '"').fetchone()[0] for table in tables}}
            groups.append(record)
            (folder / 'runner.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps({'group': name, 'status': record['status'], 'checks': len(record.get('acceptance', {}).get('checks', [])),
                              'failures': len(record.get('acceptance', {}).get('failures', [])),
                              'stopped': record.get('owned_server_stopped')}, ensure_ascii=False), flush=True)
    summary = {'status': 'passed' if groups and all(r['status'] == 'passed' for r in groups) else 'failed',
               'artifact_dir': str(out), 'real_application_http': True, 'intercepted_application_routes': 0,
               'real_model_requests': 0, 'model_evidence': 'Labelled deterministic demo / local protocol fixture only; NOT LLM quality.',
               'default_or_production_data_touched': False, 'groups': groups}
    (out / 'result.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': summary['status'], 'artifact_dir': str(out)}, ensure_ascii=False))
    return 0 if summary['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
