"""Run Stage6 built-frontend/real HTTP/fresh SQLite acceptance (explicit demo).
Local: .venv/Scripts/python.exe tools/run_stage6_integration.py
Staged isolated QA: --base-url URL --confirm-test-data
Owns random-port FastAPI and browser subprocess only; never builds or touches production.
"""
import argparse
import hashlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import uuid

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from stage6_api_acceptance import make_fixtures
from run_stage4_integration import free_port, ready, stop, listener_closed


def serve(port, metrics):
    """Local instrumentation only: forbid actual model/search, perturb labelled demo.
    No application HTTP routes are intercepted/replaced. Faults are NOT LLM evidence.
    """
    import uvicorn
    sys.path.insert(0, str(ROOT))
    from backend.aicademiya.main import app
    from backend.aicademiya import guided_director
    from backend.aicademiya.ai import ModelFailure
    counts = {'model_calls': 0, 'search_calls': 0, 'demo_calls': 0, 'synthetic_faults': [],
              'evidence': 'Local no-model guard and explicit demo-only delay/fail-once instrumentation; no app route interception.'}
    target = Path(metrics)
    def save():
        target.write_text(json.dumps(counts, indent=2), encoding='utf-8')
    def forbidden(kind):
        def call(*a, **kw):
            counts[kind] += 1
            save()
            raise AssertionError('Stage6 acceptance forbids real model/search calls')
        return call
    app.state.tutor.complete = forbidden('model_calls')
    app.state.tutor.search_context = forbidden('search_calls')
    original = guided_director.demo_result
    failed = set()
    def demo(*a, **kw):
        counts['demo_calls'] += 1
        payload = a[2] if len(a) > 2 else kw.get('payload', {})
        text = payload.get('message', '')
        detail = a[5] if len(a) > 5 else kw.get('detail', {})
        fault_key = (detail.get('id'), text)
        if 'SYNTHETIC_QA_PENDING' in text:
            counts['synthetic_faults'].append({'kind': 'demo_delay', 'session': detail.get('id'), 'marker': 'SYNTHETIC_QA_PENDING'})
            save()
            time.sleep(2)
        if 'SYNTHETIC_QA_RETRY' in text and fault_key not in failed:
            failed.add(fault_key)
            counts['synthetic_faults'].append({'kind': 'demo_fail_once', 'session': detail.get('id'), 'marker': 'SYNTHETIC_QA_RETRY'})
            save()
            raise ModelFailure('Explicit synthetic demo fail-once fixture, not real model failure')
        save()
        return original(*a, **kw)
    guided_director.demo_result = demo
    save()
    uvicorn.run(app, host='127.0.0.1', port=port, log_level='info')


def sqlite_evidence(data):
    db = data / 'aicademiya.sqlite3'
    with sqlite3.connect(f'file:{db.as_posix()}?mode=ro', uri=True) as c:
        c.row_factory = sqlite3.Row
        tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        report = {'path': str(db), 'integrity_check': c.execute('PRAGMA integrity_check').fetchone()[0],
                  'foreign_key_check': [list(r) for r in c.execute('PRAGMA foreign_key_check')],
                  'schema_version': c.execute('PRAGMA user_version').fetchone()[0],
                  'row_counts': {t: c.execute('SELECT count(*) FROM "' + t + '"').fetchone()[0] for t in tables},
                  'teacher_previews': [dict(r) for r in c.execute('SELECT * FROM teacher_previews')],
                  'message_modes': [dict(r) for r in c.execute('SELECT mode,count(*) AS count FROM messages GROUP BY mode')]}
        if report['integrity_check'] != 'ok' or report['foreign_key_check'] or report['schema_version'] != 5:
            raise AssertionError('SQLite integrity/FK/schema5 verification failed')
        if any(r['mode'] != 'demo' for r in report['message_modes']):
            raise AssertionError('Unexpected non-demo message mode')
        return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-url', default=os.getenv('AICADEMIYA_TEST_URL'))
    p.add_argument('--confirm-test-data', action='store_true')
    p.add_argument('--artifact-dir')
    p.add_argument('--fixture-dir', help='Optional local synthetic instruction fixtures, uploaded from client even to Linux QA')
    p.add_argument('--skip-browser', action='store_true')
    p.add_argument('--skip-api', action='store_true')
    p.add_argument('--browser', action='store_true', help='Compatibility alias: browser enabled by default')
    p.add_argument('--chrome-path')
    p.add_argument('--allow-stale-build', action='store_true', help='Explicit parent-approved pre-final dist only; records hash and stale-source boundary. Default requires current dist.')
    p.add_argument('--serve', type=int, help=argparse.SUPPRESS)
    p.add_argument('--metrics', help=argparse.SUPPRESS)
    args = p.parse_args()
    if args.serve:
        data = os.getenv('AICADEMIYA_DATA_DIR')
        db = os.getenv('AICADEMIYA_QA_DB')
        if not data or not db or Path(db).resolve() != (Path(data) / 'aicademiya.sqlite3').resolve() or os.getenv('AICADEMIYA_AI_MODE') != 'demo' or not args.metrics:
            p.error('Internal server requires explicit isolated QA data/DB, demo mode and metrics; never use default data.')
        serve(args.serve, args.metrics)
        return 0
    if args.base_url and not args.confirm_test_data:
        p.error('External target requires --confirm-test-data: fresh isolated synthetic demo QA only. NEVER production.')
    if args.skip_api and args.skip_browser:
        p.error('At least one group is required')
    build = {}
    if not args.base_url and not args.skip_browser:
        index = ROOT / 'frontend/dist/index.html'
        newest = max(f.stat().st_mtime for folder in ('src', 'public') for f in (ROOT / 'frontend' / folder).rglob('*') if f.is_file())
        if not index.is_file() or (index.stat().st_mtime < newest and not args.allow_stale_build):
            p.error('Parent-owned frontend/dist is missing/stale. Harness never builds. Use --allow-stale-build ONLY for explicitly parent-approved pre-final evidence.')
        build = {'index_sha256': hashlib.sha256(index.read_bytes()).hexdigest(), 'index_mtime': index.stat().st_mtime, 'latest_source_mtime': newest, 'source_newer_than_dist': index.stat().st_mtime < newest, 'explicit_pre_final_permission': args.allow_stale_build, 'harness_rebuilt_frontend': False}
    out = Path(args.artifact_dir or ROOT / 'artifacts/stage6' / ('integration-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])).resolve()
    allowed = (ROOT / 'artifacts/stage6').resolve()
    if out.parent != allowed or not out.name.startswith('integration-'):
        p.error('Use a NEW artifacts/stage6/integration-* directory')
    out.mkdir(parents=True, exist_ok=False)
    fixtures = Path(args.fixture_dir).resolve() if args.fixture_dir else out / 'fixtures'
    manifest = make_fixtures(fixtures) if not args.fixture_dir else {f.name: {'bytes': f.stat().st_size} for f in fixtures.iterdir() if f.is_file()}
    (out / 'fixtures.json').write_text(json.dumps({'synthetic_only': True, 'missing_archive_S6_not_used_or_invented': True, 'files': manifest}, indent=2), encoding='utf-8')
    env = os.environ.copy()
    scratch = Path(os.getenv('TMPDIR', str(Path.home() / 'AppData/Local/hermes/cache/scratch')))
    scratch.mkdir(parents=True, exist_ok=True)
    env.update(TMPDIR=str(scratch), TEMP=str(scratch), TMP=str(scratch), AICADEMIYA_DEMO_ENABLED='true',
               AICADEMIYA_AI_MODE='demo', AICADEMIYA_COOKIE_SECURE='false', AICADEMIYA_AI_PROVIDER='',
               AICADEMIYA_AI_BASE_URL='', AICADEMIYA_AI_MODEL='', AICADEMIYA_AI_API_KEY='',
               AICADEMIYA_WEB_SEARCH_ENABLED='false', TAVILY_API_KEY='',
               NO_PROXY='127.0.0.1,localhost,::1', no_proxy='127.0.0.1,localhost,::1')
    if args.chrome_path:
        env['AICADEMIYA_CHROME_PATH'] = args.chrome_path
    groups = []
    commands = []
    if not args.skip_api:
        commands.append(('api', [sys.executable, str(ROOT / 'tools/stage6_api_acceptance.py')]))
    if not args.skip_browser:
        node = shutil.which('node')
        if not node:
            p.error('Node with frontend-local Playwright required')
        commands.append(('browser', [node, str(ROOT / 'tools/stage6_browser_acceptance.mjs')]))
    for name, command in commands:
        folder = out / name
        folder.mkdir()
        data = folder / 'data'
        rec = {'name': name, 'status': 'failed', 'owned_server': not bool(args.base_url)}
        proc = log = None
        try:
            base = (args.base_url or f'http://127.0.0.1:{free_port()}').rstrip('/')
            rec['base_url'] = base
            childenv = env.copy()
            childenv['AICADEMIYA_QA_PYTHON'] = sys.executable
            if not args.base_url:
                data.mkdir()
                childenv.update(AICADEMIYA_DATA_DIR=str(data), AICADEMIYA_QA_DB=str(data / 'aicademiya.sqlite3'), AICADEMIYA_QA_CONTROL='true')
                port = int(base.rsplit(':', 1)[1])
                log = (folder / 'server.log').open('w', encoding='utf-8')
                proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--serve', str(port), '--metrics', str(folder / 'no-model-metrics.json')], cwd=ROOT, env=childenv, stdout=log, stderr=subprocess.STDOUT)
                rec['server_pid'] = proc.pid
                ready(proc, base)
            else:
                for k in ('AICADEMIYA_DATA_DIR', 'AICADEMIYA_QA_DB', 'AICADEMIYA_QA_CONTROL'):
                    childenv.pop(k, None)
            with (folder / 'harness.log').open('w', encoding='utf-8') as hlog:
                done = subprocess.run(command + ['--base-url', base, '--confirm-test-data', '--artifact-dir', str(folder), '--fixture-dir', str(fixtures)], cwd=ROOT, env=childenv, stdout=hlog, stderr=subprocess.STDOUT, timeout=900)
            rec['exit_code'] = done.returncode
            if (folder / 'result.json').is_file():
                rec['acceptance'] = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
            rec['status'] = 'passed' if done.returncode == 0 and rec.get('acceptance', {}).get('status') == 'passed' else 'failed'
        except Exception as e:
            rec['error'] = str(e)
        finally:
            if proc:
                stop(proc)
                rec['owned_server_stopped'] = proc.poll() is not None
                rec['owned_listener_closed'] = listener_closed(port)
                if not rec['owned_listener_closed']:
                    rec.update(status='failed', cleanup_error='Owned listener still open')
            if log:
                log.close()
            if (data / 'aicademiya.sqlite3').is_file():
                try:
                    rec['sqlite'] = sqlite_evidence(data)
                except Exception as e:
                    rec.update(status='failed', sqlite_error=str(e))
            metrics = folder / 'no-model-metrics.json'
            if metrics.is_file():
                rec['no_model_guard'] = json.loads(metrics.read_text(encoding='utf-8'))
                if rec['no_model_guard']['model_calls'] or rec['no_model_guard']['search_calls']:
                    rec.update(status='failed', model_guard_error='Attempted forbidden actual model/search')
            groups.append(rec)
            (folder / 'runner.json').write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps({'group': name, 'status': rec['status'], 'checks': len(rec.get('acceptance', {}).get('checks', [])), 'errors': rec.get('acceptance', {}).get('failures', [])}, ensure_ascii=False), flush=True)
    summary = {'status': 'passed' if groups and all(g['status'] == 'passed' for g in groups) else 'failed',
               'artifact_dir': str(out), 'groups': groups, 'frontend_build': build, 'real_application_http': True, 'intercepted_application_routes': 0,
               'local_sqlite_verified': not bool(args.base_url) and bool(groups) and all(g.get('sqlite', {}).get('integrity_check') == 'ok' and g.get('sqlite', {}).get('schema_version') == 5 and not g.get('sqlite', {}).get('foreign_key_check') for g in groups), 'synthetic_only': True, 'real_model_requests': 0,
               'evidence_boundary': 'Deterministic demo and separate labelled demo fault controls, NOT real-model teaching quality. Native file extraction is real.',
               'remote_note': 'Remote SQLite/cleanup/no-model counter require independent operator verification; client uploads local synthetic fixtures.' if args.base_url else None}
    (out / 'result.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# Stage6 integration handoff', '', f"- Result: **{summary['status']}**", '- Built frontend → actual FastAPI HTTP; no intercepted app routes; isolated synthetic demo only.', '- Missing original S6 DOCX was not read or invented; fixtures explicitly named Synthetic Instructions.', '- Actual-model quality and staged/production preservation are parent-owned, not proven here.']
    if build.get('source_newer_than_dist'):
        lines += ['- Known parent-approved pre-final dist difference: source-review count/capacity label and preview footer spacing are already fixed in source but not rebuilt here. Parent final build/strict rerun must verify those changes.', f"- Tested dist index SHA256: `{build['index_sha256']}`; harness never rebuilt frontend."]
    for g in groups:
        a = g.get('acceptance', {})
        lines += [f"- {g['name']}: {g['status']}; {len(a.get('checks', []))} checks; {len(a.get('failures', []))} failures. Evidence: `{g['name']}/result.json`, `runner.json`, `harness.log`."]
        for failure in a.get('failures', []):
            lines += [f"  - Blocker: {failure.get('name')}: {failure.get('error')}"]
        for shot in a.get('screenshots', []):
            lines += [f"  - Screenshot: `{shot}`"]
        lines += [f"  - Cleanup: server stopped={g.get('owned_server_stopped', 'external—not owned')}, listener closed={g.get('owned_listener_closed', 'external—not owned')}; browser cleanup={a.get('cleanup', 'N/A')}."]
    lines += ['', '## Evidence boundary', '- No-write opening is checked after the existing workspace GET initializes its empty operational row; browser/result.json notes record that initialization explicitly. This is not proof that the very first workspace GET writes nothing.', '- Pure teaching/source/import endpoints have strict all-table equality evidence; Save/Reset/Publish happen only in explicitly synthetic exercises.', '- Local pending/retry tests use separately labelled demo delay/fail-once hooks, not a real provider or intercepted HTTP response.', '', '## Run', '`./.venv/Scripts/python.exe tools/run_stage6_integration.py`', '`./.venv/Scripts/python.exe tools/run_stage6_integration.py --base-url ISOLATED_QA_URL --confirm-test-data`', '', '- External mode never claims local SQLite inspection. Remote DB and process state must be verified by staged operator.', '- Local DB is retained under each group/data for read-only evidence; only owned browser/server are closed.']
    (out / 'HANDOFF.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({'status': summary['status'], 'artifact_dir': str(out)}))
    return 0 if summary['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
