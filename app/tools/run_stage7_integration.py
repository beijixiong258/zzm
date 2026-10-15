"""Stage7 merged acceptance: built UI -> actual FastAPI HTTP -> isolated SQLite.
Never rebuilds frontend/dist, intercepts app routes, uses sample_data, or touches production.
Default final browser lane requires current dist; a blocked browser never prevents API execution.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import traceback
import uuid
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from run_stage4_integration import free_port, ready, stop, listener_closed
from stage6_api_acceptance import make_fixtures
from stage7_qa_helpers import ProtocolFixtures, build_evidence, catalog_fixture, sqlite_evidence, write_json


def serve(port, folder, production_gate=False):
    import uvicorn
    sys.path.insert(0, str(ROOT))
    from backend.aicademiya.main import create_app
    catalog = folder / 'catalog.json'
    data = folder / 'data'
    if production_gate:
        # Explicit old-record fixture, only in owned empty synthetic DB before HTTP startup.
        from backend.aicademiya.db import Database
        db = Database(data / 'aicademiya.sqlite3')
        db.initialize(catalog, demo_enabled=False)
        db.create_admin('Synthetic Stage7 administrator', 'synthetic-stage7-admin@example.invalid', os.environ['AICADEMIYA_QA_LOGIN_PASSWORD'])
        with db.connect() as c:
            c.execute("INSERT INTO settings(key,value) VALUES('ai_mode','demo')")
        write_json(folder / 'legacy-fixture-boundary.json', {'synthetic_only': True, 'prepared_before_http_startup': True, 'fixture': 'Legacy saved ai_mode=demo; generated non-demo admin, no password export', 'sample_data_copied': False})
    fixture = ProtocolFixtures(folder / 'no-model-metrics.json')
    app = create_app(data_dir=data, catalog_path=catalog, demo_enabled=not production_gate,
                     ai_transport=httpx.MockTransport(fixture.model))
    if not production_gate:
        fixture.instrument(app)
    else:
        app.state.tutor.search_context = fixture.forbidden('search_calls')
        app.state.tutor.search.transport = httpx.MockTransport(fixture.search)
    uvicorn.run(app, host='127.0.0.1', port=port, log_level='info')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-url', help='Explicit fresh isolated QA only (e.g. future staged Linux), never production')
    p.add_argument('--confirm-test-data', action='store_true')
    p.add_argument('--artifact-dir')
    p.add_argument('--skip-browser', action='store_true')
    p.add_argument('--skip-api', action='store_true')
    p.add_argument('--chrome-path')
    p.add_argument('--allow-stale-build', action='store_true', help='Explicit PRE-FINAL evidence only; never a final pass')
    p.add_argument('--pre-final-legacy-labels', action='store_true', help='Stage6-labelled browser only; requires --allow-stale-build; new UI gates remain pending')
    p.add_argument('--compose-settings', action='store_true', help='Run parent-owned 15-check Settings browser/SQLite/restart suite as separate group')
    p.add_argument('--settings-evidence', help='Attach previous parent suite result as historical evidence, NOT a current merged acceptance pass')
    p.add_argument('--serve', type=int, help=argparse.SUPPRESS)
    p.add_argument('--serve-folder', help=argparse.SUPPRESS)
    p.add_argument('--production-gate-server', action='store_true', help=argparse.SUPPRESS)
    args = p.parse_args()
    if args.serve:
        folder = Path(args.serve_folder).resolve()
        allowed = (ROOT / 'artifacts/stage7/qa-handoff').resolve()
        if not folder.is_relative_to(allowed) or not (folder / 'catalog.json').is_file():
            p.error('Owned synthetic serve folder/catalog required')
        if Path(os.environ.get('AICADEMIYA_QA_DB', '')).resolve() != (folder / 'data/aicademiya.sqlite3').resolve():
            p.error('Explicit isolated data/DB required; no default application data')
        serve(args.serve, folder, args.production_gate_server)
        return 0
    if args.base_url:
        if not args.confirm_test_data: p.error('External QA requires --confirm-test-data')
        target = urlsplit(args.base_url)
        if target.scheme not in ('http', 'https') or not target.hostname or target.port == 18773 or target.username or target.password:
            p.error('Valid credential-free isolated QA URL required; production port18773 prohibited')
        if args.compose_settings: p.error('Parent Settings runner is local-only; compose separately on staged host')
    if args.skip_browser and args.skip_api: p.error('At least one group required')
    if args.pre_final_legacy_labels and not args.allow_stale_build: p.error('Legacy labels require explicit --allow-stale-build; never final')
    if args.compose_settings and args.allow_stale_build: p.error('Settings composition requires strict current dist, not pre-final stale evidence')
    out = Path(args.artifact_dir or ROOT / 'artifacts/stage7/qa-handoff' / ('run-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])).resolve()
    allowed = (ROOT / 'artifacts/stage7/qa-handoff').resolve()
    if out.parent != allowed or not out.name.startswith('run-'): p.error('Use a NEW artifacts/stage7/qa-handoff/run-* directory; failed history must not be overwritten')
    out.mkdir(parents=True, exist_ok=False)
    fixtures = out / 'fixtures'
    write_json(out / 'fixtures.json', {'synthetic_only': True, 'sample_data_copied': False, 'missing_archive_S6_not_invented': True, 'files': make_fixtures(fixtures)})
    build = build_evidence(args.allow_stale_build)
    write_json(out / 'frontend-build.json', build)
    env = os.environ.copy()
    scratch = Path(os.environ.get('TMPDIR', str(Path.home() / 'AppData/Local/hermes/cache/scratch')))
    scratch.mkdir(parents=True, exist_ok=True)
    env.update(TMPDIR=str(scratch), TEMP=str(scratch), TMP=str(scratch),
               AICADEMIYA_DEMO_ENABLED='true', AICADEMIYA_AI_MODE='demo', AICADEMIYA_COOKIE_SECURE='false',
               AICADEMIYA_AI_PROVIDER='', AICADEMIYA_AI_BASE_URL='', AICADEMIYA_AI_MODEL='', AICADEMIYA_AI_API_KEY='',
               AICADEMIYA_WEB_SEARCH_ENABLED='false', TAVILY_API_KEY='',
               NO_PROXY='127.0.0.1,localhost,::1', no_proxy='127.0.0.1,localhost,::1')
    for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'):
        env.pop(key, None)
    if args.chrome_path: env['AICADEMIYA_CHROME_PATH'] = args.chrome_path
    groups = []
    commands = []
    if not args.skip_api:
        commands.append(('api', [sys.executable, str(ROOT / 'tools/stage7_api_acceptance.py')]))
        if not args.base_url:
            commands.append(('production-demo-http-gate', [sys.executable, str(ROOT / 'tools/stage7_api_acceptance.py'), '--production-gate']))
        else:
            groups.append({'name': 'production-demo-http-gate', 'status': 'pending', 'reason': 'External target does not permit this runner to create owned demo-disabled app; operator must run local/isolated gate.'})
    else:
        groups.append({'name': 'api', 'status': 'skipped', 'reason': 'Explicit --skip-api'})
    if args.skip_browser:
        groups.append({'name': 'browser', 'status': 'skipped', 'reason': 'Explicit --skip-browser; browser coverage unverified'})
    elif build['status'] != 'ready':
        groups.append({'name': 'browser', 'status': 'blocked', 'reason': build['reason'], 'checks': []})
    else:
        node = shutil.which('node')
        if not node:
            groups.append({'name': 'browser', 'status': 'blocked', 'reason': 'Node/frontend-local Playwright unavailable', 'checks': []})
        else:
            cmd = [node, str(ROOT / 'tools/stage7_browser_acceptance.mjs')]
            if args.pre_final_legacy_labels: cmd += ['--pre-final-legacy-labels']
            if args.allow_stale_build: cmd += ['--allow-stale-build']
            commands.append(('browser', cmd))
    for name, command in commands:
        folder = out / name
        folder.mkdir()
        catalog_fixture(folder / 'catalog.json')
        data = folder / 'data'
        rec = {'name': name, 'status': 'failed', 'owned_server': not bool(args.base_url)}
        proc = log = None
        production = name == 'production-demo-http-gate'
        try:
            base = (args.base_url or f'http://127.0.0.1:{free_port()}').rstrip('/')
            rec['base_url'] = base
            childenv = env.copy()
            childenv.update(AICADEMIYA_QA_PYTHON=sys.executable)
            if not args.base_url:
                data.mkdir()
                childenv.update(AICADEMIYA_DATA_DIR=str(data), AICADEMIYA_QA_DB=str(data / 'aicademiya.sqlite3'),
                                AICADEMIYA_QA_CONTROL='true', AICADEMIYA_QA_METRICS=str(folder / 'no-model-metrics.json'))
                if production:
                    childenv['AICADEMIYA_QA_LOGIN_PASSWORD'] = 'Synthetic-QA-' + secrets.token_urlsafe(24) + 'Aa1'
                    childenv['AICADEMIYA_DEMO_ENABLED'] = 'false'
                port = int(urlsplit(base).port)
                servercmd = [sys.executable, str(Path(__file__).resolve()), '--serve', str(port), '--serve-folder', str(folder)]
                if production: servercmd += ['--production-gate-server']
                log = (folder / 'server.log').open('w', encoding='utf-8')
                proc = subprocess.Popen(servercmd, cwd=ROOT, env=childenv, stdout=log, stderr=subprocess.STDOUT)
                rec['server_pid'] = proc.pid
                ready(proc, base)
            else:
                for key in ('AICADEMIYA_DATA_DIR', 'AICADEMIYA_QA_DB', 'AICADEMIYA_QA_CONTROL', 'AICADEMIYA_QA_METRICS', 'AICADEMIYA_QA_LOGIN_PASSWORD'): childenv.pop(key, None)
            with (folder / 'harness.log').open('w', encoding='utf-8') as hlog:
                done = subprocess.run(command + ['--base-url', base, '--confirm-test-data', '--artifact-dir', str(folder), '--fixture-dir', str(fixtures)], cwd=ROOT, env=childenv, stdout=hlog, stderr=subprocess.STDOUT, timeout=900)
            rec['exit_code'] = done.returncode
            if (folder / 'result.json').is_file(): rec['acceptance'] = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
            rec['status'] = 'passed' if done.returncode == 0 and rec.get('acceptance', {}).get('status') == 'passed' else 'failed'
        except Exception as e:
            rec.update(error=str(e), traceback=traceback.format_exc())
        finally:
            if proc:
                stop(proc)
                rec['owned_server_stopped'] = proc.poll() is not None
                rec['owned_listener_closed'] = listener_closed(port)
                if not rec['owned_listener_closed']: rec.update(status='failed', cleanup_error='Owned listener still open')
            if log: log.close()
            if (data / 'aicademiya.sqlite3').is_file():
                try: rec['sqlite'] = sqlite_evidence(data, require_demo=not production)
                except Exception as e: rec.update(status='failed', sqlite_error=str(e))
            metrics = folder / 'no-model-metrics.json'
            if metrics.is_file():
                rec['no_model_guard'] = json.loads(metrics.read_text(encoding='utf-8'))
                if rec['no_model_guard']['model_calls'] or rec['no_model_guard']['search_calls']: rec.update(status='failed', model_guard_error='Forbidden real model/search attempted')
                if production and rec['no_model_guard']['demo_calls']: rec.update(status='failed', model_guard_error='Demo executed in normal-runtime fixture')
            groups.append(rec)
            write_json(folder / 'runner.json', rec)
            print(json.dumps({'group': name, 'status': rec['status'], 'checks': len(rec.get('acceptance', {}).get('checks', [])), 'failures': rec.get('acceptance', {}).get('failures', []), 'error': rec.get('error')}, ensure_ascii=False), flush=True)
    if args.compose_settings:
        rec = {'name': 'composed-parent-settings-browser-api-restart', 'status': 'blocked'}
        if build['status'] != 'ready': rec['reason'] = 'Strict current dist gate blocks Settings composition'
        else:
            try:
                done = subprocess.run([sys.executable, str(ROOT / 'tools/run_stage7_settings_integration.py')], cwd=ROOT, env=env, capture_output=True, text=True, timeout=500)
                (out / 'composed-settings.log').write_text(done.stdout + '\n' + done.stderr, encoding='utf-8')
                last = json.loads(done.stdout.strip().splitlines()[-1])
                rec.update(result_handle=last['result'], acceptance=json.loads(Path(last['result']).read_text(encoding='utf-8')))
                rec['status'] = 'passed' if done.returncode == 0 and rec['acceptance']['status'] == 'passed' else 'failed'
            except Exception as e: rec.update(status='failed', error=str(e))
        groups.append(rec)
    else:
        groups.append({'name': 'composed-parent-settings-browser-api-restart', 'status': 'pending', 'reason': 'Run --compose-settings for current merged state. Historical settings evidence cannot satisfy final gate.'})
    history = None
    if args.settings_evidence:
        path = Path(args.settings_evidence).resolve()
        history = {'handle': str(path), 'historical_only_not_current_final_gate': True, 'result': json.loads(path.read_text(encoding='utf-8'))}
    build_after = build_evidence(args.allow_stale_build)
    build_stable = build.get('source_manifest_sha256') == build_after.get('source_manifest_sha256') and build.get('dist_manifest') == build_after.get('dist_manifest')
    write_json(out / 'frontend-build-after.json', build_after)
    if not build_stable and not args.skip_browser:
        groups.append({'name': 'source-dist-stability', 'status': 'pending', 'reason': 'Source or dist changed while acceptance ran; parent must strict-rerun final merged state.'})
    statuses = [g['status'] for g in groups]
    direct_checks = sum(len(g.get('acceptance', {}).get('checks', [])) for g in groups)
    composed_checks = sum(len(phase.get('browser', {}).get('checks', [])) for g in groups if g['name'] == 'composed-parent-settings-browser-api-restart' for phase in g.get('acceptance', {}).get('groups', []))
    final = build_stable and not args.allow_stale_build and not args.pre_final_legacy_labels and not args.skip_api and not args.skip_browser and args.compose_settings and all(s == 'passed' for s in statuses)
    status = 'failed' if 'failed' in statuses else ('passed' if final else 'partial')
    summary = {'stage': 7, 'status': status, 'final_acceptance': final, 'artifact_dir': str(out), 'groups': groups,
               'verified_check_count': direct_checks + composed_checks, 'direct_check_count': direct_checks,
               'composed_settings_browser_check_count': composed_checks, 'source_dist_stable_during_run': build_stable,
               'frontend_build': build, 'historical_settings_evidence': history, 'real_application_http': True,
               'intercepted_application_routes': 0, 'synthetic_only': True, 'real_model_requests': 0,
               'local_sqlite_verified': not bool(args.base_url) and all(g.get('sqlite', {}).get('integrity_check') == 'ok' for g in groups if g.get('owned_server')),
               'evidence_boundary': 'Actual HTTP/native extraction/SQLite; deterministic demo and labelled provider transport fixtures only. No real model teaching-quality/search-result claim.',
               'remote_note': 'External mode requires operator SQLite/schema/FK/no-model/process evidence and separate normal-runtime gate; never claims local DB or external cleanup.' if args.base_url else None}
    write_json(out / 'result.json', summary)
    lines = ['# Stage7 run evidence', '', f'- Status: **{status}**; final acceptance: **{final}**.', f'- Real checked assertions: {summary["verified_check_count"]}. No passed count includes pending/blocked/skipped gates.', '- Source/dist guard: `frontend-build.json`; no frontend rebuild by harness.', '- Actual app HTTP and isolated generated SQLite. No intercepted app routes, real inference/search or sample_data copies.']
    for g in groups:
        a = g.get('acceptance', {})
        lines += [f'- {g["name"]}: {g["status"]}; {len(a.get("checks", []))} direct checks. {g.get("reason", "")}', f'  - Evidence: `{g.get("result_handle", g["name"] + "/result.json")}`; cleanup server={g.get("owned_server_stopped", "not owned")}, listener={g.get("owned_listener_closed", "not owned")}.']
        for f in a.get('failures', []): lines += [f'  - Failure: {f.get("name")}: {f.get("error")}']
    lines += ['', 'Retained DBs are read-only evidence after server shutdown. Failed runs remain in unique folders. Parent owns final source merges, current dist build, full unit/package/Linux/deployment/preservation gates.']
    (out / 'HANDOFF.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({'status': status, 'final_acceptance': final, 'checked': summary['verified_check_count'], 'result': str(out / 'result.json')}), flush=True)
    return 0 if status != 'failed' and ('blocked' not in statuses or args.skip_browser) else 1


if __name__ == '__main__':
    raise SystemExit(main())
