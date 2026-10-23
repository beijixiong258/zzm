"""Stage-3 actual HTTP acceptance; all accounts/content synthetic, no live LLM.

The optional protocol group uses a real bounded loopback HTTP provider fixture,
not interception of application routes. It runs only on the runner's owned DB.
"""
import argparse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import threading
import time
import traceback
from urllib.parse import urlencode

import httpx

ROOT = Path(__file__).resolve().parents[1]
PROFILE = dict(schema_version=1, background='PRIVATE_STAGE3_BACKGROUND', student_profile='PRIVATE_STAGE3_STUDENT_PROFILE',
               response_strategies='Target the misconception, offer evidence-based hints and invite revision.', tone='Supportive and direct.',
               response_detail='balanced', phases=['warmup', 'worksheet', 'quiz', 'reading', 'wrap_up'],
               reading_focus='Compare reliability and validity using the public reading.', reading_question_count=2,
               reference_delivery='after_sufficient_answer', idle_hint_seconds=0, presentation='full')
FIGURES = [dict(label=x, url=f'/api/assets/s4-graph-{x.lower()}.png', alt=f'Original scatter plot {x}') for x in 'ABC']


def question(qid, ordinal, prompt, gid='core', images=None, options=None):
    return dict(id=qid, group_id=gid, ordinal=ordinal, type='image_matching' if images else 'open_response', prompt=prompt,
                options=options or [], answer_slots=1, images=images or [], source_label='Synthetic worksheet: reliability and validity',
                source_material_ids=[], source_links=[])


class Acceptance:
    def __init__(self, base, out):
        self.base, self.out = base.rstrip('/'), out
        self.events, self.checks, self.failures, self.ids = [], [], [], {}
        self.clients = [httpx.Client(base_url=self.base, trust_env=False, timeout=60) for _ in range(5)]
        self.teacher, self.student, self.second, self.admin, self.anonymous = self.clients

    def call(self, client, method, url, body=None, expected=200, **kwargs):
        response = client.request(method, url, json=body, **kwargs)
        self.events.append(dict(method=method, url=url, status=response.status_code, expected=expected))
        if response.status_code != expected:
            raise AssertionError(f'{method} {url}: expected {expected}, got {response.status_code}: {response.text[:800]}')
        return response.json() if response.headers.get('content-type', '').startswith('application/json') else response

    def check(self, name, condition, details=None):
        if condition:
            self.checks.append(name)
            print('PASS', name, flush=True)
        else:
            failure = dict(name=name, details=details)
            self.failures.append(failure)
            print('FAIL', json.dumps(failure), flush=True)
        self.save('running')

    def save(self, status):
        self.out.mkdir(parents=True, exist_ok=True)
        result = dict(status=status, checks=self.checks, failures=self.failures, requests=self.events, request_count=len(self.events),
                      ids=self.ids, real_backend=True, real_sqlite=True, synthetic_only=True, real_model=False,
                      intercepted_application_routes=0, model_evidence='Deterministic demo / explicitly labelled loopback protocol fixture, not model quality')
        (self.out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')

    def vp(self, sid, route, vid):
        return f'/api/sessions/{sid}/{route}?' + urlencode(dict(version_id=vid))

    def work(self, sid, vid, client=None):
        return self.call(client or self.student, 'GET', self.vp(sid, 'workspace', vid))

    def turn(self, sid, vid, message, rid, client=None, expected=200, **extra):
        return self.call(client or self.student, 'POST', self.vp(sid, 'tutor/turn', vid),
                         dict(message=message, request_id=rid, web_search=False, **extra), expected=expected)

    def setup(self):
        boot = self.call(self.anonymous, 'GET', '/api/bootstrap')
        assert boot['demo_enabled'] and boot['ai']['mode'] == 'demo', 'Target must be explicit demo-enabled synthetic QA.'
        self.check('Explicit deterministic demo, no provider/search fallback', boot['ai']['mode'] == 'demo')
        for client, body in [(self.teacher, {'role': 'teacher'}), (self.student, {'role': 'student', 'student_index': 1}),
                             (self.second, {'role': 'student', 'student_index': 2}), (self.admin, {'role': 'admin'})]:
            self.call(client, 'POST', '/api/auth/demo', body)
        nonce = secrets.token_hex(4)
        course = self.call(self.teacher, 'POST', '/api/courses', dict(code='S3-API-' + nonce, title='Synthetic stage-3 HTTP lab', description='QA-only teaching acceptance'))
        self.ids['course'] = course['id']
        self.student_id = self.call(self.student, 'GET', '/api/auth/me')['user']['id']
        for c in (self.student, self.second):
            self.call(c, 'POST', '/api/courses/join', {'join_code': course['join_code']})
        # Public seed figures are session-owned. Use ONLY the isolated seed copy,
        # preserving its authorized image URLs; never bypass image ownership.
        courses = self.call(self.teacher, 'GET', '/api/courses')
        seed = next(c for c in courses if c['code'] == 'EDUC7703')
        course = seed
        self.ids['course'] = course['id']
        self.sid = 'session-4'
        self.call(self.teacher, 'PATCH', f'/api/sessions/{self.sid}', dict(title='Synthetic guided assessment reasoning', teaching_profile=PROFILE))
        for c in (self.student, self.second):
            self.call(c, 'POST', '/api/courses/join', {'join_code': course['join_code']})
        material = self.call(self.teacher, 'POST', f'/api/sessions/{self.sid}/materials', files={'file': ('public-reading.txt', b'Reliability means consistent results. Validity concerns supported interpretation for a purpose. A negative scatter plot slopes down.', 'text/plain')}, data={'visibility': 'student', 'kind': 'reading'})
        self.call(self.teacher, 'POST', f'/api/sessions/{self.sid}/materials', files={'file': ('private-key.txt', b'PRIVATE_STAGE3_MATERIAL', 'text/plain')}, data={'visibility': 'teacher', 'kind': 'answer_key'})
        self.questions = [question('qa-reliability', 1, 'Explain why consistent marking supports reliability.'),
                          question('qa-graph', 2, 'Use the original scatter plots to identify a negative relationship and explain your reasoning.', images=FIGURES),
                          question('qa-validity', 3, 'Explain why validity needs evidence for a stated purpose.', options=['Supported interpretation', 'Automatic teacher confirmation'])]
        for q in self.questions:
            q['source_material_ids'] = [material['id']]
        self.call(self.teacher, 'PATCH', f'/api/sessions/{self.sid}', dict(status='published', instructions='PRIVATE_STAGE3_ADDITIONAL', learning_objectives=['Support claims about reliability and validity.'], reference_policy='after_attempt', groups=[dict(id='core', title='Assessment word bank', kind='core', description='Word bank: reliability; validity; evidence; negative correlation.')], questions=self.questions, reference_answers={q['id']: 'Synthetic instructor comparison for ' + q['id'] for q in self.questions}))
        gateprofile = {**PROFILE, 'phases': ['worksheet', 'quiz', 'wrap_up'], 'reference_delivery': 'after_sufficient_answer'}
        gate = self.call(self.teacher, 'POST', f'/api/courses/{course["id"]}/sessions', dict(title='After-submit reference gate', number=2, teaching_profile=gateprofile))
        self.gate = gate['id']
        self.call(self.teacher, 'PATCH', f'/api/sessions/{self.gate}', dict(status='published', reference_policy='after_submit', groups=[dict(id='core', title='Core', kind='core')], questions=[question('gate-q', 1, 'Explain reliability with evidence.')], reference_answers={'gate-q': 'GATED_INSTRUCTOR_REFERENCE'}))
        branch = self.call(self.teacher, 'POST', f'/api/courses/{course["id"]}/sessions', dict(title='Required reading branch', number=3, teaching_profile={**PROFILE, 'phases': ['worksheet', 'wrap_up']}))
        self.branch = branch['id']
        self.call(self.teacher, 'PATCH', f'/api/sessions/{self.branch}', dict(status='published', groups=[dict(id='core', title='Shared', kind='core'), dict(id='article-a', title='Reliability article', kind='reading'), dict(id='article-b', title='Validity article', kind='reading')], questions=[question('branch-core', 1, 'Explain a shared assessment concept.'), question('branch-a', 2, 'Relate consistent marking to the selected article.', 'article-a'), question('branch-b', 3, 'Relate supported interpretation to the other article.', 'article-b')]))
        version = self.call(self.teacher, 'POST', f'/api/teacher/courses/{course["id"]}/versions/publish', dict(label='Stage3 synthetic initial edition'))
        self.vid = version['id']
        self.ids.update(session=self.sid, gate_session=self.gate, branch_session=self.branch, version=self.vid, student=self.student_id)

    def demo(self):
        self.setup()
        d = self.call(self.teacher, 'GET', f'/api/sessions/{self.sid}')
        self.check('Teaching profile save then independent GET readback', d['teaching_profile'] == PROFILE)
        preview = self.call(self.teacher, 'POST', f'/api/sessions/{self.sid}/teaching-preview', dict(teaching_profile={**PROFILE, 'background': 'UNSAVED_PREVIEW_BACKGROUND'}, instructions='UNSAVED_PREVIEW_ADDITIONAL', reference_policy='after_submit'))
        self.check('Actual compiled preview includes all unsaved instruction sources', all(x in preview['text'] for x in ['UNSAVED_PREVIEW_BACKGROUND', 'UNSAVED_PREVIEW_ADDITIONAL', 'after_submit']) and bool(preview['sections']))
        self.check('Compiled preview does not save or publish', self.call(self.teacher, 'GET', f'/api/sessions/{self.sid}')['teaching_profile'] == PROFILE)
        self.call(self.student, 'POST', f'/api/sessions/{self.sid}/teaching-preview', {}, expected=403)
        self.call(self.admin, 'POST', f'/api/sessions/{self.sid}/teaching-preview', {}, expected=403)
        self.check('Preview restricted to actual course owner, not student or unrelated admin', True)
        w = self.work(self.sid, self.vid)
        self.check('Student/private-key projection', not any(x in json.dumps(w) for x in ['PRIVATE_STAGE3', 'teaching_profile', 'reference_answers', 'correct_index']))
        for fig in FIGURES:
            response = self.call(self.student, 'GET', fig['url'] + '?version_id=' + self.vid)
            self.check('Real original figure bytes ' + fig['label'], len(response.content) > 100 and response.headers['content-type'].startswith('image/'))
        self.call(self.student, 'POST', self.vp(self.sid, 'references/qa-reliability', self.vid), {}, expected=409)
        self.check('Reference remains locked before any attempt', True)
        w = self.call(self.student, 'POST', self.vp(self.sid, 'tutor/start', self.vid), {'request_id': 'opening'})
        self.check('Proactive opening has genuine stored timestamp and demo label', w['tutor']['phase'] == 'warmup' and 'Deterministic demo' in w['messages'][0]['content'] and bool(datetime.fromisoformat(w['messages'][0]['created_at'])))
        n = len(w['messages'])
        w = self.call(self.student, 'POST', self.vp(self.sid, 'tutor/start', self.vid), {'request_id': 'second-opening'})
        self.check('Opening resume does not duplicate', len(w['messages']) == n)
        w = self.turn(self.sid, self.vid, 'I am ready to reason about assessment.', 'warmup')
        self.check('Natural warmup advances to first configured worksheet question', w['tutor']['current_question_id'] == 'qa-reliability')
        for i in range(2):
            w = self.turn(self.sid, self.vid, 'wrong: reliability means everyone passes.', f'wrong-{i}')
            w = self.turn(self.sid, self.vid, 'Please give a hint.', f'hint-{i}', action='hint')
        state = w['tutor']['question_states']['qa-reliability']
        self.check('Multiple wrong attempts/hints remain on the same question, no reference reveal', state['answer_count'] == 2 and state['hint_count'] == 2 and state['last_outcome'] == 'needs_retry' and w['tutor']['current_question_id'] == 'qa-reliability' and not w['attempts']['qa-reliability']['reference_revealed'])
        mixed = 'Consistent marking supports reliability because evidence is stable. Why can a reliable test still lack validity?'
        w = self.turn(self.sid, self.vid, mixed, 'mixed')
        self.check('Mixed answer + follow-up saved verbatim and advances', w['attempts']['qa-reliability']['answer'] == mixed and w['tutor']['current_question_id'] == 'qa-graph' and w['messages'][-2]['metadata']['detected_intent'] == 'mixed')
        self.check('Auto reference delivery only after sufficient answer', w['attempts']['qa-reliability']['reference_revealed'] and 'Instructor reference' in w['messages'][-1]['content'])
        shown = w['messages'][-1]['metadata']['presented_question']
        self.check('Canonical graph images/source preserved in actual assistant metadata', shown['id'] == 'qa-graph' and len(shown['images']) == 3 and shown['images'][0]['url'].startswith('/api/assets/s4-graph-a.png') and shown['source_label'] == self.questions[1]['source_label'])
        w = self.turn(self.sid, self.vid, 'Why does the previous concept help?', 'prior', action='review_question', question_id='qa-reliability')
        self.check('Previous question clarification does not answer or skip current', w['tutor']['current_question_id'] == 'qa-graph' and 'qa-graph' not in w['attempts'] and w['attempts']['qa-reliability']['answer'] == mixed)
        w = self.turn(self.sid, self.vid, 'How can I read these plots?', 'pure')
        self.check('Pure follow-up does not create a saved answer', 'qa-graph' not in w['attempts'] and w['tutor']['current_question_id'] == 'qa-graph')
        w = self.turn(self.sid, self.vid, 'The downward plot is negative because its paired values move in opposite directions.', 'graph')
        w = self.turn(self.sid, self.vid, 'Validity depends on evidence supporting the interpretation for the stated purpose.', 'validity')
        self.check('Required discussion ends at quiz invitation, not automatic submission', w['tutor']['phase'] == 'quiz_offer' and w['submission']['status'] == 'in_progress' and w['progress']['answered'] == 3)
        w = self.turn(self.sid, self.vid, 'Yes', 'accept')
        self.check('Exact explicit quiz opt-in creates five persisted optional items', w['tutor']['phase'] == 'quiz' and w['tutor']['quiz']['total'] == 5 and 'correct_index' not in json.dumps(w))
        n = len(w['messages'])
        w = self.turn(self.sid, self.vid, 'Yes', 'accept')
        self.check('Same completed quiz opt-in request does not generate twice', len(w['messages']) == n)
        for i, value in enumerate(['1', 'B', 'A', '2', '1']):
            w = self.turn(self.sid, self.vid, value, 'quiz-' + str(i))
        self.check('Quiz numeric/letter answers saved independently and formative only', w['tutor']['quiz'] == dict(status='completed', answered=5, total=5, correct=3) and len(w['attempts']) == 3 and w['progress']['answered'] == 3)
        shown_reading = w['messages'][-1]['metadata']['presented_question']
        public_labels = {m['source_label'] for m in w['session']['materials'] if m.get('source_label')}
        self.check('Bounded reading grounded in actual public material', w['tutor']['phase'] == 'reading' and w['tutor']['reading']['total'] == 2 and bool(shown_reading.get('source_labels')) and set(shown_reading['source_labels']) <= public_labels)
        for i in range(2):
            w = self.turn(self.sid, self.vid, 'The public reading supports this because reliability concerns consistent results.', f'reading-{i}')
        self.check('Reading reaches configured finite count then wrap-up', w['tutor']['phase'] == 'wrap_up' and w['tutor']['reading'] == dict(answered=2, total=2))
        w = self.turn(self.sid, self.vid, 'Finish this discussion.', 'finish')
        self.check('Final summary/completion never auto-confirms or auto-submits', w['tutor']['phase'] == 'complete' and w['submission']['status'] == 'in_progress')
        # Contract promises continued questions after completion; retain a real repro if rejected.
        r = self.student.post(self.vp(self.sid, 'tutor/turn', self.vid), json=dict(message='Why is evidence important?', request_id='completed-followup', web_search=False))
        self.events.append(dict(method='POST', url=self.vp(self.sid, 'tutor/turn', self.vid), status=r.status_code, expected=200))
        self.check('Completed-phase free follow-up works as promised in student UI', r.status_code == 200, dict(status=r.status_code, body=r.text[:400], repro='Finish required/optional discussion, then send Why is evidence important? before explicit submission.'))
        text = self.call(self.student, 'GET', self.vp(self.sid, 'transcript', self.vid) + '&format=txt')
        html = self.call(self.student, 'GET', self.vp(self.sid, 'transcript', self.vid) + '&format=html')
        self.check('Raw transcript includes actual IDs, original messages, timestamps and optional responses', mixed in text.text and self.vid in text.text and self.sid in text.text and w['messages'][0]['created_at'] in text.text and '| formative=' in text.text)
        self.check('Offline transcript is attachment/sandbox and no private text', 'attachment' in html.headers['content-disposition'] and 'sandbox' in html.headers['content-security-policy'] and 'PRIVATE_STAGE3' not in html.text)
        (self.out / 'transcript.txt').write_text(text.text, encoding='utf-8')
        (self.out / 'transcript.html').write_text(html.text, encoding='utf-8')
        self.call(self.anonymous, 'GET', self.vp(self.sid, 'transcript', self.vid), expected=401)
        w = self.call(self.student, 'POST', self.vp(self.sid, 'submit', self.vid), {})
        reviewed = self.call(self.teacher, 'POST', f'/api/teacher/sessions/{self.sid}/students/{self.student_id}/review?version_id={self.vid}', dict(status='confirmed', note='Synthetic teacher explicit review.'))
        self.check('Explicit submission then owner teacher review and locked readback', w['submission']['status'] == 'submitted' and reviewed['submission']['status'] == 'confirmed' and self.work(self.sid, self.vid)['submission']['teacher_note'] == 'Synthetic teacher explicit review.')
        self.call(self.student, 'POST', self.vp(self.sid, 'tutor/turn', self.vid), dict(message='Locked', request_id='locked'), expected=409)
        self.call(self.student, 'POST', self.vp(self.gate, 'tutor/start', self.vid), {})
        g = self.turn(self.gate, self.vid, 'Because evidence supports consistent marking.', 'gate-answer')
        self.check('After-submit policy overrides sufficient-answer auto delivery', not g['attempts']['gate-q']['reference_revealed'] and 'GATED_INSTRUCTOR_REFERENCE' not in json.dumps(g))
        self.call(self.student, 'POST', self.vp(self.gate, 'references/gate-q', self.vid), {}, expected=409)
        g = self.turn(self.gate, self.vid, 'No', 'decline', action='skip_quiz')
        self.check('Optional quiz decline skips generation without blocking required submission', g['tutor']['quiz']['status'] == 'skipped' and g['tutor']['quiz']['total'] == 0)
        self.call(self.student, 'POST', self.vp(self.gate, 'submit', self.vid), {})
        ref = self.call(self.student, 'POST', self.vp(self.gate, 'references/gate-q', self.vid), {})
        self.check('Reference available only after explicit submission under after-submit', ref['reference'] == 'GATED_INSTRUCTOR_REFERENCE')
        self.call(self.student, 'POST', self.vp(self.branch, 'tutor/start', self.vid), {})
        b = self.turn(self.branch, self.vid, 'Because evidence supports the shared concept.', 'branch-core')
        self.check('Required reading path waits for actual branch selection', b['tutor']['current_question_id'] is None and b['messages'][-1]['metadata']['kind'] == 'reading_choice')
        b = self.turn(self.branch, self.vid, 'Reliability article', 'choose-branch')
        self.check('Actual chosen branch ID/order and denominator', b['selected_reading'] == 'article-a' and b['tutor']['current_question_id'] == 'branch-a' and b['progress']['total'] == 2 and 'branch-b' not in b['tutor']['question_states'])
        original = self.work(self.sid, self.vid)
        self.call(self.teacher, 'PATCH', f'/api/sessions/{self.sid}', dict(questions=[{**q, 'prompt': 'UNPUBLISHED_EDIT' if i == 0 else q['prompt']} for i, q in enumerate(self.questions)], teaching_profile={**PROFILE, 'background': 'UNPUBLISHED_PROFILE', 'presentation': 'paced'}))
        self.check('Draft changes do not leak into immutable student edition', self.work(self.sid, self.vid)['session']['questions'][0]['prompt'] == self.questions[0]['prompt'])
        newer = self.call(self.teacher, 'POST', f'/api/teacher/courses/{self.ids["course"]}/versions/publish', dict(label='Stage3 changed synthetic edition'))
        old = self.work(self.sid, self.vid)
        fresh = self.work(self.sid, newer['id'])
        self.check('Publication pins original transcript/answers and makes history read-only', old['read_only'] and old['attempts'] == original['attempts'] and old['messages'] == original['messages'])
        self.check('New edition has distinct fresh learning and private profile remains hidden', not fresh['attempts'] and not fresh['messages'] and fresh['tutor']['presentation'] == 'paced' and 'UNPUBLISHED_PROFILE' not in json.dumps(fresh))
        history = self.call(self.student, 'GET', '/api/history')
        self.check('History independently discovers original guided run', any(x['session']['id'] == self.sid and x['version']['id'] == self.vid for x in history))
        self.call(self.teacher, 'PATCH', f'/api/sessions/{self.sid}', dict(active=False, starts_at=None, ends_at=None))
        self.check('Inactive current edition retains authorized read/export', self.work(self.sid, newer['id'])['read_only'] and self.call(self.student, 'GET', self.vp(self.sid, 'transcript', self.vid)).status_code == 200)

    def protocol(self):
        self.setup()
        # Isolated local protocol-only settings; no real key, no external requests.
        self.call(self.teacher, 'PATCH', f'/api/sessions/{self.sid}', dict(teaching_profile={**PROFILE, 'phases': ['worksheet', 'wrap_up'], 'reference_delivery': 'on_request'}, questions=self.questions[:1]))
        v = self.call(self.teacher, 'POST', f'/api/teacher/courses/{self.ids["course"]}/versions/publish', {'label': 'Local HTTP protocol fixture'})['id']
        records = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                static = json.loads(request['messages'][0]['content'].split('\n')[-1])
                env = json.loads(request['messages'][1]['content'])
                failed = static['task'] == 'turn' and len(records) == 1
                records.append(dict(task=static['task'], phase=static['phase'], failure=failed))
                q = static['current_question']
                decision = dict(schema_version=1, text='[Bounded local HTTP protocol fixture; NOT real model] Synthetic formative guidance.', intent='none' if static['task'] == 'start' else 'answer', question_id=None if static['task'] == 'start' else q['id'], outcome='unknown' if static['task'] == 'start' else 'sufficient')
                self.send_response(503 if failed else 200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'choices': [{'message': {'role': 'assistant', 'content': json.dumps(decision)}}]}).encode())
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            self.call(self.admin, 'PUT', '/api/teacher/settings', dict(mode='openai', base_url=f'http://127.0.0.1:{server.server_port}/v1', model='labelled-local-protocol-fixture', api_key=''))
            self.call(self.student, 'POST', self.vp(self.sid, 'tutor/start', v), {'request_id': 'protocol-open'})
            initial = self.work(self.sid, v)
            self.turn(self.sid, v, 'Exact raw synthetic answer for retry.', 'retry-identical', expected=502)
            failed = self.work(self.sid, v)
            self.check('Actual provider socket 503 is visible, raw input retained, no fake feedback/answer/progress', failed['messages'][-1]['role'] == 'user' and failed['messages'][-1]['content'] == 'Exact raw synthetic answer for retry.' and failed['attempts'] == {} and failed['tutor']['phase'] == initial['tutor']['phase'] and failed['tutor']['pending_request_id'] is None)
            done = self.turn(self.sid, v, 'Exact raw synthetic answer for retry.', 'retry-identical')
            self.check('Same-ID recovery makes one answer revision and one original user message', len(done['messages']) == 3 and len(done['attempts']['qa-reliability']['revisions']) == 1 and len(records) == 3)
            again = self.turn(self.sid, v, 'Exact raw synthetic answer for retry.', 'retry-identical')
            self.check('Completed same-ID retry readback does not repeat provider/transition', again['messages'] == done['messages'] and len(records) == 3 and again['tutor']['last_completed_request_id'] == 'retry-identical')
            self.turn(self.sid, v, 'Changed input forbidden.', 'retry-identical', expected=409)
            self.check('Same-ID changed-payload fingerprint remains rejected', True)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            self.check('Owned HTTP protocol fixture stopped in finally', not thread.is_alive())
            (self.out / 'protocol-requests.json').write_text(json.dumps(records, indent=2), encoding='utf-8')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-url', default=os.getenv('AICADEMIYA_TEST_URL'))
    p.add_argument('--artifact-dir', default=os.getenv('AICADEMIYA_TEST_ARTIFACT_DIR'))
    p.add_argument('--confirm-test-data', action='store_true')
    p.add_argument('--protocol-fixture', action='store_true')
    args = p.parse_args()
    if not args.base_url or not args.artifact_dir or not args.confirm_test_data:
        p.error('Require --base-url, --artifact-dir and --confirm-test-data on isolated demo QA only.')
    if args.protocol_fixture and not os.getenv('AICADEMIYA_DATA_DIR'):
        p.error('Protocol fixture requires the locally owned runner data root.')
    a = Acceptance(args.base_url, Path(args.artifact_dir))
    try:
        a.protocol() if args.protocol_fixture else a.demo()
    except Exception as exc:
        a.failures.append(dict(name='Dependent API scenario interrupted', error=str(exc), traceback=traceback.format_exc()))
        print(traceback.format_exc(), flush=True)
    finally:
        for client in a.clients:
            client.close()
        a.save('failed' if a.failures else 'passed')
    print(json.dumps(dict(status='failed' if a.failures else 'passed', checks=len(a.checks), failures=len(a.failures), requests=len(a.events))))
    return 1 if a.failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
