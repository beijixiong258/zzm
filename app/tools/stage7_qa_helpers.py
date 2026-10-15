"""Stage7 owned QA helpers; application routes and production are never patched.
Provider responses here are labelled protocol fixtures, not AI/search evidence.
"""
import ast
import hashlib
import inspect
import json
import os
from pathlib import Path
import textwrap
import threading
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def catalog_fixture(path):
    write_json(path, {'schema_version': 1, 'course': {
        'id': 'synthetic-stage7-seed', 'code': 'S7-SYNTHETIC',
        'title': 'Synthetic Stage7 isolated acceptance seed',
        'description': 'Generated QA data, no sample_data copies or real teaching content.'}, 'sessions': []})


def rebase_stage6_run(module):
    """Import all Stage6 assertions unchanged except its strict API-version constant.

    AST checks fail closed if the maintained baseline changes. This is a version
    rebase, never a replacement of the scenario, condition, or coverage.
    """
    source = textwrap.dedent(inspect.getsource(module.Acceptance.run))
    tree = ast.parse(source)
    target = os.environ.get('AICADEMIYA_QA_TARGET_API', '0.6.0')
    if target not in ('0.6.0', '0.7.0', '0.8.0', '0.9.0', '0.10.0'):
        raise ValueError('Unsupported explicit QA API target')
    replacements = {
        '0.5.0': target,
        'Explicit demo-enabled target and API 0.5.0': 'Explicit demo-enabled target and API ' + target,
    }
    changed = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in replacements:
            changed.append(node.value)
            node.value = replacements[node.value]
    if sorted(changed) != sorted(replacements):
        raise RuntimeError('Stage6 version rebase boundary changed; review baseline before proceeding')
    namespace = {}
    exec(compile(tree, str(Path(module.__file__).resolve()) + ':stage7-version-rebase', 'exec'), module.__dict__, namespace)
    evidence = {'module': str(Path(module.__file__).resolve()),
                'sha256': hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest(),
                'changed_constants_only': replacements, 'all_scenario_assertions_retained': True}
    return namespace['run'], evidence


class ProtocolFixtures:
    def __init__(self, target):
        self.target = Path(target)
        self.lock = threading.Lock()
        self.counts = {'model_calls': 0, 'search_calls': 0, 'demo_calls': 0,
                       'model_protocol_calls': 0, 'search_protocol_calls': 0,
                       'active_model_protocol_calls': 0, 'active_search_protocol_calls': 0,
                       'synthetic_faults': [], 'provider_request_boundaries': [],
                       'evidence': 'No application-route interception. Demo delay/fail-once and provider MockTransport responses are explicit synthetic fixtures, NOT real model/search evidence.'}
        self.save()

    def save(self):
        temporary = self.target.with_suffix('.json.tmp')
        write_json(temporary, self.counts)
        os.replace(temporary, self.target)

    def forbidden(self, kind):
        def call(*a, **kw):
            with self.lock:
                self.counts[kind] += 1
                self.save()
            raise AssertionError('Stage7 acceptance forbids real model/search requests')
        return call

    def model(self, request):
        body = json.loads(request.content)
        assert request.url.host == '127.0.0.1' and request.url.port == 9
        assert body['max_tokens'] == 32 and body['stream'] is False
        assert body['messages'] == [{'role': 'user', 'content': 'Reply with OK only; this is an AIcademiya connectivity test.'}]
        with self.lock:
            self.counts['model_protocol_calls'] += 1
            self.counts['active_model_protocol_calls'] += 1
            self.counts['provider_request_boundaries'].append({'kind': 'model_connection_probe', 'synthetic': True, 'max_tokens': 32, 'endpoint': 'loopback-port9-transport-only', 'private_course_or_student_context': False})
            self.save()
        try:
            if body['model'] == 'SYNTHETIC_QA_SLOW':
                time.sleep(2)
            if body['model'] == 'SYNTHETIC_QA_FAIL':
                return httpx.Response(503, json={'error': 'Explicit synthetic protocol rejection'})
            return httpx.Response(200, json={'choices': [{'message': {'role': 'assistant', 'content': 'OK — explicit protocol fixture; no model ran'}}]})
        finally:
            with self.lock:
                self.counts['active_model_protocol_calls'] -= 1
                self.save()

    def search(self, request):
        body = json.loads(request.content)
        assert str(request.url) == 'https://api.tavily.com/search'
        assert body['search_depth'] == 'basic' and body['max_results'] == 5 and body['auto_parameters'] is False
        assert body['query'] == 'public education formative assessment research'
        with self.lock:
            self.counts['search_protocol_calls'] += 1
            self.counts['active_search_protocol_calls'] += 1
            self.counts['provider_request_boundaries'].append({'kind': 'search_connection_probe', 'synthetic': True, 'search_depth': 'basic', 'max_results': 5, 'auto_parameters': False, 'fixed_public_query': True, 'private_course_or_student_context': False})
            self.save()
        try:
            credential = request.headers.get('Authorization', '').removeprefix('Bearer ')
            if credential == 'SYNTHETIC_QA_SLOW_SEARCH':
                time.sleep(2)
            if credential == 'SYNTHETIC_QA_FAIL_SEARCH':
                return httpx.Response(503, json={'error': 'Explicit synthetic protocol rejection'})
            return httpx.Response(200, json={'results': [{'title': 'Explicit synthetic protocol result', 'url': 'https://example.invalid/stage7-synthetic', 'content': 'A generated public-topic fixture, not an actual search result.'}], 'usage': {'credits': 0}})
        finally:
            with self.lock:
                self.counts['active_search_protocol_calls'] -= 1
                self.save()

    def instrument(self, app):
        from backend.aicademiya import guided_director
        from backend.aicademiya.ai import ModelFailure
        original_complete = app.state.tutor.complete
        forbidden_model = self.forbidden('model_calls')
        def complete(settings, messages, **kwargs):
            if kwargs.get('max_tokens') == 32:
                return original_complete(settings, messages, **kwargs)
            return forbidden_model(settings, messages, **kwargs)
        app.state.tutor.complete = complete
        app.state.tutor.search_context = self.forbidden('search_calls')
        app.state.tutor.search.transport = httpx.MockTransport(self.search)
        original_demo = guided_director.demo_result
        failed = set()
        def demo(*args, **kw):
            payload = args[2] if len(args) > 2 else kw.get('payload', {})
            detail = args[5] if len(args) > 5 else kw.get('detail', {})
            text = payload.get('message', '')
            identity = (detail.get('id'), text)
            with self.lock:
                self.counts['demo_calls'] += 1
                self.save()
            if 'SYNTHETIC_QA_PENDING' in text:
                with self.lock:
                    self.counts['synthetic_faults'].append({'kind': 'demo_delay', 'session': detail.get('id'), 'marker': 'SYNTHETIC_QA_PENDING'})
                    self.save()
                hold = self.target.parent / 'hold-demo-pending'
                if hold.exists():
                    deadline = time.monotonic() + 30
                    while hold.exists():
                        if time.monotonic() >= deadline:
                            raise AssertionError('Owned browser did not release synthetic pending fixture')
                        time.sleep(.02)
                else:
                    time.sleep(2)
            if 'SYNTHETIC_QA_RETRY'  in text and identity not in failed:
                failed.add(identity)
                with self.lock:
                    self.counts['synthetic_faults'].append({'kind': 'demo_fail_once', 'session': detail.get('id'), 'marker': 'SYNTHETIC_QA_RETRY'})
                    self.save()
                raise ModelFailure('Explicit synthetic demo fail-once fixture, not a real provider failure')
            return original_demo(*args, **kw)
        guided_director.demo_result = demo


def sqlite_evidence(data, require_demo=True):
    import sqlite3
    db = Path(data) / 'aicademiya.sqlite3'
    with sqlite3.connect(f'file:{db.as_posix()}?mode=ro', uri=True) as c:
        c.row_factory = sqlite3.Row
        tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        evidence = {'path': str(db), 'integrity_check': c.execute('PRAGMA integrity_check').fetchone()[0],
                    'foreign_key_check': [list(r) for r in c.execute('PRAGMA foreign_key_check')],
                    'schema_version': c.execute('PRAGMA user_version').fetchone()[0],
                    'row_counts': {t: c.execute('SELECT count(*) FROM "' + t + '"').fetchone()[0] for t in tables},
                    'message_modes': [dict(r) for r in c.execute('SELECT mode,count(*) AS count FROM messages GROUP BY mode')],
                    'teacher_previews': [dict(r) for r in c.execute('SELECT * FROM teacher_previews')],
                    'material_memberships': [dict(r) for r in c.execute('SELECT material_id,session_id FROM session_materials ORDER BY material_id,session_id')],
                    'settings_values_exported': False, 'password_hashes_exported': False}
    assert evidence['integrity_check'] == 'ok' and not evidence['foreign_key_check'] and evidence['schema_version'] == int(os.environ.get('AICADEMIYA_QA_TARGET_SCHEMA','5')), 'SQLite integrity/FK/explicit target schema verification failed'
    assert all(r['mode'] == 'demo' for r in evidence['message_modes']) if require_demo else all(r['mode'] != 'demo' for r in evidence['message_modes']), 'Unexpected message mode'
    return evidence


def build_evidence(allow_stale=False):
    frontend = ROOT / 'frontend'
    index = frontend / 'dist/index.html'
    files = [f for folder in ('src', 'public') for f in (frontend / folder).rglob('*') if f.is_file()]
    files += [frontend / 'package.json', frontend / 'package-lock.json']
    files += [f for f in frontend.glob('*config*') if f.is_file()]
    newest = max(f.stat().st_mtime for f in files if f.is_file())
    result = {'harness_rebuilt_frontend': False, 'strict_current_dist_required': not allow_stale,
              'explicit_allow_stale_build': allow_stale, 'final_evidence': False,
              'latest_source_mtime': newest, 'index_exists': index.is_file()}
    if not index.is_file():
        result.update(status='blocked', reason='Parent-owned frontend/dist/index.html is missing')
        return result
    result.update(index_sha256=hashlib.sha256(index.read_bytes()).hexdigest(), index_mtime=index.stat().st_mtime,
                  source_newer_than_dist=index.stat().st_mtime < newest,
                  newer_source_files=[str(f.relative_to(ROOT)) for f in files if f.is_file() and f.stat().st_mtime > index.stat().st_mtime])
    distfiles = [f for f in (frontend / 'dist').rglob('*') if f.is_file()]
    result['dist_manifest'] = {str(f.relative_to(frontend / 'dist')): hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(distfiles)}
    result['source_manifest_sha256'] = hashlib.sha256(json.dumps({str(f.relative_to(frontend)): hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(set(files)) if f.is_file()}, sort_keys=True).encode()).hexdigest()
    if result['source_newer_than_dist'] and not allow_stale:
        result.update(status='blocked', reason='Parent-owned dist predates source. Final browser gate requires parent build; harness never rebuilds.')
    else:
        result.update(status='ready', final_evidence=not allow_stale)
    return result
