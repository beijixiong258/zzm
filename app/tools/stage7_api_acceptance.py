"""Stage7 actual HTTP acceptance. Imports Stage6 scenario with version-only AST rebase.
Fresh synthetic SQLite only; protocol fixtures are not real model/search evidence.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import secrets
import sys
import time
import traceback

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))
import stage6_api_acceptance as s6
from stage7_qa_helpers import rebase_stage6_run, write_json

stage6_run, baseline_evidence = rebase_stage6_run(s6)


class Acceptance(s6.Acceptance):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.boundaries = []
        self.group_checks = {}
        self.secrets = ['SYNTHETIC_QA_MODEL_KEY', 'SYNTHETIC_QA_SEARCH_KEY', 'SYNTHETIC_QA_SLOW_SEARCH', 'SYNTHETIC_QA_FAIL_SEARCH']
        self.metrics_path = os.getenv('AICADEMIYA_QA_METRICS')

    def call(self, client, method, url, body=None, expected=200, **kwargs):
        r = client.request(method, url, json=body, **kwargs)
        self.events.append(dict(method=method, url=url, status=r.status_code, expected=expected))
        assert not any(secret in r.text for secret in self.secrets), 'Synthetic credential leaked in response; response omitted'
        if r.status_code != expected:
            raise AssertionError(f'{method} {url}: expected {expected}, got {r.status_code}; response omitted')
        return r.json() if r.headers.get('content-type', '').startswith('application/json') else r

    def save(self, status):
        super().save(status)
        p = self.out / 'result.json'
        value = json.loads(p.read_text(encoding='utf-8'))
        value.update(stage=7, baseline_reuse=baseline_evidence, group_checks=self.group_checks,
                     boundaries=self.boundaries, settings_protocol_fixtures=bool(self.metrics_path))
        write_json(p, value)

    def metrics(self):
        if not self.metrics_path:
            return None
        return json.loads(Path(self.metrics_path).read_text(encoding='utf-8'))

    def run(self):
        for name, scenario in [('preserved_stage6', lambda: stage6_run(self)),
                               ('material_version_library', self.material_gates),
                               ('pending_retry_protocol', self.pending_retry_gates),
                               ('global_settings', self.settings_gates)]:
            before = len(self.checks)
            try:
                scenario()
            except Exception as e:
                self.failures.append({'name': name, 'error': str(e), 'traceback': traceback.format_exc()})
                print(traceback.format_exc(), flush=True)
            finally:
                self.group_checks[name] = self.checks[before:]
                self.save('running')

    def material_gates(self):
        # Independently authenticated, fresh course. No dependence on Stage6 fixture success.
        for client, body in ((self.teacher, {'role': 'teacher'}), (self.student, {'role': 'student', 'student_index': 1}), (self.other, {'role': 'admin'})):
            self.call(client, 'POST', '/api/auth/demo', body)
        c = self.call(self.teacher, 'POST', '/api/courses', {'code': 'S7-LIB-' + secrets.token_hex(4), 'title': 'Synthetic Stage7 library and version gates'})
        cid = c['id']
        sids = [self.call(self.teacher, 'POST', f'/api/courses/{cid}/sessions', {'title': 'Synthetic library session ' + str(n), 'teaching_profile': s6.PROFILE})['id'] for n in (1, 2)]
        s1, s2 = sids
        def upload(name, text, visibility='student', kind='reading'):
            return self.call(self.teacher, 'POST', f'/api/sessions/{s1}/materials', files={'file': (name, text.encode(), 'text/plain')}, data={'visibility': visibility, 'kind': kind})
        b = upload('Synthetic Shared B.txt', 'Synthetic shared original B; public evidence only.')
        private = upload('Synthetic private.txt', 'SYNTHETIC_PRIVATE_LIBRARY_NEVER_PUBLIC', 'teacher', 'reference')
        key = upload('Synthetic key.txt', 'SYNTHETIC_KEY_LIBRARY_NEVER_PUBLIC', 'teacher', 'answer_key')
        unattached = upload('Synthetic unassigned.txt', 'Synthetic unassigned library original.')
        lib = lambda: self.call(self.teacher, 'GET', f'/api/courses/{cid}/materials')
        session = lambda sid: self.call(self.teacher, 'GET', f'/api/sessions/{sid}')
        attach = lambda mid: self.call(self.teacher, 'POST', f'/api/sessions/{s2}/materials/attach', {'material_id': mid})
        first, again = attach(b['id']), attach(b['id'])
        for m in (private, key): attach(m['id'])
        self.call(self.teacher, 'DELETE', f'/api/sessions/{s1}/materials/{unattached["id"]}')
        rows = {m['id']: m for m in lib()['materials']}
        self.check('Canonical course library preserves same-ID two-session and unassigned membership without copies', first == again and first['id'] == b['id'] and set(rows[b['id']]['session_ids']) == set(sids) and rows[unattached['id']]['session_ids'] == [] and len(rows) == 4)
        for client, status in ((self.anon, 401), (self.student, 403), (self.other, 403)):
            self.call(client, 'GET', f'/api/courses/{cid}/materials', expected=status)
            self.call(client, 'POST', f'/api/sessions/{s2}/materials/attach', {'material_id': b['id']}, expected=status)
        foreign = self.call(self.teacher, 'POST', '/api/courses', {'code': 'S7-FOREIGN-' + secrets.token_hex(4), 'title': 'Synthetic other course'})
        fsid = self.call(self.teacher, 'POST', f'/api/courses/{foreign["id"]}/sessions', {'title': 'Synthetic foreign session'})['id']
        self.call(self.teacher, 'POST', f'/api/sessions/{fsid}/materials/attach', {'material_id': b['id']}, expected=422)
        self.check('Course library owner scope and cross-course attach reject through actual HTTP', True)
        for sid in sids:
            self.call(self.teacher, 'PATCH', f'/api/sessions/{sid}', {'status': 'published', 'groups': [{'id': 'core', 'title': 'Synthetic core', 'kind': 'core'}], 'questions': [s6.question([b['id']], 'library-q')]})
        self.call(self.teacher, 'PATCH', f'/api/sessions/{s2}/materials/{key["id"]}', {'visibility': 'student'}, expected=422)
        self.call(self.teacher, 'DELETE', f'/api/sessions/{s2}/materials/{b["id"]}', expected=409)
        old = self.call(self.teacher, 'POST', f'/api/teacher/courses/{cid}/versions/publish', {'label': 'Synthetic original memberships'})['id']
        snapshot = lambda: self.call(self.teacher, 'GET', f'/api/teacher/courses/{cid}/versions/{old}')
        original = snapshot()
        self.call(self.student, 'POST', '/api/courses/join', {'join_code': c['join_code']})
        wurl = f'/api/sessions/{s2}/workspace?version_id={old}'
        w = self.call(self.student, 'GET', wurl)
        self.check('Published student materials exclude private/key and unattached library records', {m['id'] for m in w['session']['materials']} == {b['id']} and 'SYNTHETIC_PRIVATE_LIBRARY' not in json.dumps(w) and 'SYNTHETIC_KEY_LIBRARY' not in json.dumps(w))
        for m in (private, key):
            for route in ('download', 'preview'):
                self.call(self.student, 'GET', f'/api/materials/{m["id"]}/{route}?version_id={old}', expected=403)
        self.call(self.anon, 'GET', b['download_url'], expected=401)
        self.call(self.other, 'GET', b['download_url'], expected=403)
        self.check('Private originals, previews, referenced detach and answer-key visibility retain HTTP gates', True)
        rawbytes = self.call(self.teacher, 'GET', b['download_url']).content
        self.call(self.student, 'POST', f'/api/sessions/{s2}/answers/library-q?version_id={old}', {'answer': 'Synthetic protected raw library response'})
        raw = self.call(self.student, 'GET', wurl)
        self.call(self.teacher, 'PATCH', f'/api/sessions/{s1}/materials/{b["id"]}', {'title': 'Synthetic shared B renamed'})
        self.check('Shared metadata saves independently into both draft sessions', all(next(m for m in session(sid)['materials'] if m['id'] == b['id'])['title'] == 'Synthetic shared B renamed' for sid in sids))
        for sid in sids:
            self.call(self.teacher, 'PATCH', f'/api/sessions/{sid}', {'questions': []})
            self.call(self.teacher, 'DELETE', f'/api/sessions/{sid}/materials/{b["id"]}')
        rows = {m['id']: m for m in lib()['materials']}
        self.check('Last detach preserves unassigned original and historical authorized download', rows[b['id']]['session_ids'] == [] and self.call(self.teacher, 'GET', b['download_url']).content == rawbytes and self.call(self.student, 'GET', b['download_url'] + '?version_id=' + old).content == rawbytes)
        new = self.call(self.teacher, 'POST', f'/api/teacher/courses/{cid}/versions/publish', {'label': 'Synthetic detached next edition'})['id']
        pinned = self.call(self.student, 'GET', wurl)
        second = httpx.Client(base_url=str(self.student.base_url), trust_env=False)
        try:
            self.call(second, 'POST', '/api/auth/demo', {'role': 'student', 'student_index': 2})
            self.call(second, 'POST', '/api/courses/join', {'join_code': c['join_code']})
            self.call(second, 'GET', b['download_url'] + '?version_id=' + old, expected=403)
        finally:
            second.close()
        self.check('Immutable old version and saved raw student history survive draft edits/detach/new edition', snapshot() == original and pinned['read_only'] and pinned['attempts'] == raw['attempts'] and pinned['messages'] == raw['messages'] and {m['id'] for m in pinned['session']['materials']} == {b['id']})
        restored = self.call(self.teacher, 'POST', f'/api/teacher/courses/{cid}/versions/{old}/restore', {'label': 'Synthetic Stage7 restore'})['id']
        rows = {m['id']: m for m in lib()['materials']}
        self.check('Restore produces new edition and restores exact canonical memberships/title without rewriting history', restored not in (old, new) and set(rows[b['id']]['session_ids']) == set(sids) and rows[b['id']]['title'] == b['title'] and snapshot() == original)
        self.ids['stage7_library'] = {'course': cid, 'sessions': sids, 'shared_material': b['id'], 'old_version': old, 'new_version': new, 'restored_version': restored}

    def pending_retry_gates(self):
        if not self.metrics_path:
            self.boundaries.append('External QA has no local demo delay/fail-once controls: pending/reset and accepted-failure retry protocol not claimed.')
            return
        c = self.call(self.teacher, 'POST', '/api/courses', {'code': 'S7-PENDING-' + secrets.token_hex(4), 'title': 'Synthetic Stage7 pending and retry lab'})
        sid = self.call(self.teacher, 'POST', f'/api/courses/{c["id"]}/sessions', {'title': 'Synthetic protocol workbench', 'teaching_profile': s6.PROFILE})['id']
        self.call(self.teacher, 'PATCH', f'/api/sessions/{sid}', {'groups': [{'id': 'core', 'title': 'Synthetic core', 'kind': 'core'}], 'questions': [s6.question(qid='retry-q')]})
        info = lambda: self.call(self.teacher, 'GET', f'/api/teacher/sessions/{sid}/preview')
        work = lambda: self.call(self.teacher, 'GET', f'/api/sessions/{sid}/workspace')
        p = info()
        w = self.call(self.teacher, 'POST', f'/api/teacher/sessions/{sid}/preview/reset', {'expected_revision': p['current_revision']})
        pid = w['preview']['id']
        self.call(self.teacher, 'POST', f'/api/sessions/{sid}/tutor/start', {'preview_id': pid, 'request_id': 's7-pending-opening'})
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.call, self.teacher, 'POST', f'/api/sessions/{sid}/tutor/turn', {'preview_id': pid, 'request_id': 's7-pending-turn', 'message': 'SYNTHETIC_QA_PENDING wrong answer', 'web_search': False})
            deadline = time.monotonic() + 10
            while not info()['pending']:
                assert time.monotonic() < deadline, 'Synthetic delayed request never became pending'
                time.sleep(.03)
            self.call(self.teacher, 'POST', f'/api/teacher/sessions/{sid}/preview/reset', {'expected_revision': p['current_revision']}, expected=409)
            future.result(timeout=20)
        self.check('Actual pending tutor HTTP state rejects concurrent preview reset409 until completion', not info()['pending'] and work()['preview']['id'] == pid)
        retry = {'preview_id': pid, 'request_id': 's7-fail-once-durable-id', 'message': 'SYNTHETIC_QA_RETRY wrong answer', 'web_search': False}
        before_failure = work()
        self.call(self.teacher, 'POST', f'/api/sessions/{sid}/tutor/turn', retry, expected=502)
        failed = work()
        self.check('Accepted raw tutor input survives labelled demo failure without inventing classified answer', len([m for m in failed['messages'] if m['role'] == 'user' and m['content'] == retry['message']]) == 1 and failed['attempts'] == before_failure['attempts'])
        self.call(self.teacher, 'POST', f'/api/sessions/{sid}/tutor/turn', retry)
        done = work()
        self.call(self.teacher, 'POST', f'/api/sessions/{sid}/tutor/turn', retry)
        again = work()
        self.check('Same unchanged request ID retry and completed replay do not duplicate raw message/revision', len([m for m in done['messages'] if m['role'] == 'user' and m['content'] == retry['message']]) == 1 and done['messages'] == again['messages'] and done['attempts'] == again['attempts'] and done['tutor']['last_completed_request_id'] == retry['request_id'])
        self.ids['stage7_pending_retry'] = {'session': sid, 'preview': pid, 'retry_request_id': retry['request_id']}

    def settings_gates(self):
        self.call(self.other, 'POST', '/api/auth/demo', {'role': 'admin'})
        model, search = '/api/teacher/settings', '/api/teacher/search-settings'
        before = s6.records(self.db) if self.db else None
        for client, expected in ((self.anon, 401), (self.teacher, 403), (self.student, 403)):
            for endpoint in (model, search):
                self.call(client, 'GET', endpoint, expected=expected)
                self.call(client, 'PUT', endpoint, {'mode': 'demo'} if endpoint == model else {'enabled': True}, expected=expected)
                self.call(client, 'POST', endpoint + '/test', {}, expected=expected)
        self.check('Settings admin-only GET/PUT/test enforced for anonymous, teacher and student', True)
        if before is not None:
            self.check('Denied global Settings requests leave every SQLite table unchanged', s6.records(self.db) == before)
        initial_metrics = self.metrics()
        state = self.call(self.other, 'GET', model)
        self.call(self.other, 'GET', search)
        boot = self.call(self.anon, 'GET', '/api/bootstrap')
        self.check('Settings projections have safe connection states and never infer configured means connected', state['ai']['connection']['status'] in ('not_configured', 'not_checked') and boot['ai']['connection']['message'] is None)
        if not self.metrics_path:
            self.boundaries.append('External QA: provider-transport controls unavailable. Explicit connection success/failure/stale probes are NOT run or claimed; compose settings suite on isolated controlled host.')
            return
        save_model = lambda name, **extra: self.call(self.other, 'PUT', model, {'mode': 'openai', 'base_url': 'http://127.0.0.1:9/v1', 'model': name, **extra})
        save_model('Synthetic protocol model', api_key=self.secrets[0])
        state = self.call(self.other, 'GET', model)
        self.call(self.other, 'PUT', search, {'enabled': True, 'api_key': self.secrets[1]})
        search_state = self.call(self.other, 'GET', search)
        now = self.metrics()
        self.check('Admin model/search projections expose only frozen safe DTO fields, never secret fragments/fingerprints', set(state) == {'ai', 'api_key_set'} and set(state['ai']) <= {'mode', 'configured', 'base_url', 'model', 'last_error', 'connection', 'web_search'} and set(search_state) == {'provider', 'enabled', 'configured', 'api_key_set', 'api_key_source', 'connection'} and set(state['ai']['connection']) == {'status', 'checked_at', 'message'} and set(search_state['connection']) == {'status', 'checked_at', 'message'})
        self.check('Model/search save and independent GET readback do not automatically probe or leak keys', state['api_key_set'] and state['ai']['connection']['status'] == 'not_checked' and search_state['configured'] and search_state['api_key_source'] == 'saved' and search_state['connection']['status'] == 'not_checked' and now['model_protocol_calls'] == initial_metrics['model_protocol_calls'] and now['search_protocol_calls'] == initial_metrics['search_protocol_calls'])
        checked = self.call(self.other, 'POST', model + '/test', {})
        search_checked = self.call(self.other, 'POST', search + '/test', {})
        self.check('Explicit bounded model/search protocol tests persist dated successful connection state', checked['ok'] and checked['connection']['status'] == 'connected' and checked['connection']['checked_at'] and search_checked['result_count'] == 1 and search_checked['connection']['status'] == 'connected' and self.call(self.other, 'GET', model)['ai']['connection'] == checked['connection'] and self.call(self.other, 'GET', search)['connection'] == search_checked['connection'])
        public = self.call(self.anon, 'GET', '/api/bootstrap')['ai']
        self.check('Public connection check projects generic state without private diagnostics/key material', public['connection']['status'] == 'connected' and public['connection']['message'] is None and public['web_search'].get('connection', {'message': None})['message'] is None and 'binding' not in json.dumps(public))
        save_model('SYNTHETIC_QA_FAIL')
        failed = self.call(self.other, 'POST', model + '/test', {})
        self.call(self.other, 'PUT', search, {'api_key': 'SYNTHETIC_QA_FAIL_SEARCH'})
        self.call(self.other, 'POST', search + '/test', {}, expected=502)
        self.check('Explicit protocol provider failures persist safe dated error, never fabricated success', not failed['ok'] and failed['connection']['status'] == 'error' and self.call(self.other, 'GET', model)['ai']['connection']['status'] == 'error' and self.call(self.other, 'GET', search)['connection']['status'] == 'error')
        self.call(self.other, 'PUT', search, {'api_key': self.secrets[1]})
        search_state = self.call(self.other, 'PUT', search, {'api_key': '   '})
        self.call(self.other, 'PUT', search, {'api_key': self.secrets[1], 'clear_api_key': True}, expected=422)
        self.check('Blank search key preserves saved key and conflicting clear fails without credential echo', search_state['configured'] and search_state['api_key_source'] == 'saved' and search_state['connection']['status'] == 'not_checked')
        # Two real concurrent HTTP requests; delayed transport only, not route interception.
        def stale_check(endpoint, kind, initial_save, changed_save):
            initial_save()
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(self.call, self.other, 'POST', endpoint + '/test', {}, 409)
                deadline = time.monotonic() + 10
                while not self.metrics()['active_' + kind + '_protocol_calls']:
                    assert time.monotonic() < deadline, 'Delayed protocol fixture never became active'
                    time.sleep(.03)
                changed_save()
                future.result(timeout=20)
        stale_check(model, 'model', lambda: save_model('SYNTHETIC_QA_SLOW'), lambda: save_model('Synthetic changed while checking'))
        self.check('Concurrent saved model change rejects stale probe409 and leaves current state not_checked', self.call(self.other, 'GET', model)['ai']['connection']['status'] == 'not_checked')
        stale_check(search, 'search', lambda: self.call(self.other, 'PUT', search, {'api_key': 'SYNTHETIC_QA_SLOW_SEARCH'}), lambda: self.call(self.other, 'PUT', search, {'api_key': self.secrets[1]}))
        self.check('Concurrent saved search change rejects stale probe409 and leaves current state not_checked', self.call(self.other, 'GET', search)['connection']['status'] == 'not_checked')
        cleared = self.call(self.other, 'PUT', search, {'clear_api_key': True, 'enabled': False})
        self.call(self.other, 'POST', search + '/test', {}, expected=409)
        self.check('Explicit clear/disabled search persists empty override and rejects probe without fallback', not cleared['enabled'] and not cleared['configured'] and cleared['api_key_source'] == 'none' and self.call(self.other, 'GET', search) == cleared)
        self.call(self.other, 'PUT', model, {'mode': 'demo', 'base_url': '', 'model': '', 'api_key': ''})
        demo_test = self.call(self.other, 'POST', model + '/test', {})
        self.check('Isolated deterministic demo test never labels itself real connected service', demo_test['mode'] == 'demo' and demo_test['connection']['status'] == 'not_configured' and 'no model connectivity was tested' in demo_test['message'])
        m = self.metrics()
        self.check('Protocol fixture boundaries prohibit real inference/search and classroom-private probe context', m['model_calls'] == 0 and m['search_calls'] == 0 and all(not row['private_course_or_student_context'] for row in m['provider_request_boundaries']))


def production_gates(base, out):
    """Actual HTTP against owned create_app(demo_enabled=False), synthetic accounts.
    Fixture credentials are generated in parent env, never stored in artifacts.
    """
    checks, events = [], []
    password = os.environ['AICADEMIYA_QA_LOGIN_PASSWORD']
    with httpx.Client(base_url=base, trust_env=False, timeout=120) as c:
        def call(method, url, data=None, expected=200):
            r = c.request(method, url, json=data)
            events.append({'method': method, 'url': url, 'status': r.status_code, 'expected': expected})
            assert password not in r.text, 'Synthetic account credential response leak'
            assert r.status_code == expected, f'{method} {url}: expected {expected}, got {r.status_code}'
            return r.json()
        boot = call('GET', '/api/bootstrap')
        assert not boot['demo_enabled'] and boot['ai']['mode'] == 'openai' and not boot['ai']['configured']
        call('POST', '/api/auth/demo', {'role': 'admin'}, 403)
        checks.append('Production-disabled HTTP bootstrap normalizes legacy saved/environment demo and rejects demo authentication')
        call('POST', '/api/auth/login', {'email': 'synthetic-stage7-admin@example.invalid', 'password': password})
        call('PUT', '/api/teacher/settings', {'mode': 'demo', 'base_url': '', 'model': ''}, 422)
        assert call('GET', '/api/teacher/settings')['ai']['mode'] == 'openai'
        checks.append('Production-disabled admin HTTP cannot save explicit demo mode')
        course = call('POST', '/api/courses', {'code': 'S7-PRODUCTION-GATE-' + secrets.token_hex(4), 'title': 'Synthetic demo-disabled course'})
        sid = call('POST', f'/api/courses/{course["id"]}/sessions', {'title': 'Synthetic production-mode test', 'teaching_profile': s6.PROFILE})['id']
        call('PATCH', f'/api/sessions/{sid}', {'groups': [{'id': 'core', 'kind': 'core', 'title': 'Synthetic core'}], 'questions': [s6.question(qid='prod-q')]})
        p = call('GET', f'/api/teacher/sessions/{sid}/preview')
        w = call('POST', f'/api/teacher/sessions/{sid}/preview/reset', {'expected_revision': p['current_revision']})
        pid = w['preview']['id']
        failure = call('POST', f'/api/sessions/{sid}/tutor/start', {'request_id': 'synthetic-production-no-fallback', 'preview_id': pid}, 502)
        w = call('GET', f'/api/sessions/{sid}/workspace')
        assert not w['messages'] and 'configured' in failure['detail'].lower()
        checks.append('Unconfigured normal-runtime tutor returns real HTTP502 and stores no deterministic demo fallback message')
    write_json(Path(out) / 'result.json', {'status': 'passed', 'checks': checks, 'failures': [], 'requests': events,
               'request_count': len(events), 'real_backend_http': True, 'synthetic_only': True,
               'real_model': False, 'intercepted_application_routes': 0,
               'evidence': 'Local synthetic create_app(demo_enabled=False); NOT a production-server claim.'})
    return len(checks)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-url', required=True)
    p.add_argument('--artifact-dir', required=True)
    p.add_argument('--fixture-dir', required=True)
    p.add_argument('--confirm-test-data', action='store_true')
    p.add_argument('--production-gate', action='store_true')
    args = p.parse_args()
    if not args.confirm_test_data:
        p.error('Explicit isolated synthetic QA confirmation required; NEVER production')
    if args.production_gate:
        try:
            count = production_gates(args.base_url, args.artifact_dir)
            print(json.dumps({'status': 'passed', 'checks': count}))
            return 0
        except Exception as e:
            write_json(Path(args.artifact_dir) / 'result.json', {'status': 'failed', 'checks': [], 'failures': [{'name': 'production-disabled HTTP gate', 'error': str(e), 'traceback': traceback.format_exc()}]})
            print(traceback.format_exc())
            return 1
    a = Acceptance(args.base_url, args.artifact_dir, args.fixture_dir, os.getenv('AICADEMIYA_QA_DB'))
    try:
        a.run()
    except Exception as e:
        a.failures.append({'name': 'API setup interrupted', 'error': str(e), 'traceback': traceback.format_exc()})
    finally:
        for client in a.clients: client.close()
        a.save('failed' if a.failures else 'passed')
    print(json.dumps({'status': 'failed' if a.failures else 'passed', 'checks': len(a.checks), 'failures': len(a.failures)}))
    return 1 if a.failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
