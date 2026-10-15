"""Stage4 actual FastAPI HTTP acceptance. Synthetic accounts/files, demo only.

No TestClient, API interception, DB mutation, inference provider or web search.
Run via run_stage4_integration.py, or explicitly on isolated staged QA.
"""
import argparse
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import secrets
import traceback

import httpx

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'artifacts/stage4/ocr/run-20261007T043643Z-116c3ce1/inputs'
PROFILE = dict(schema_version=1, background='Synthetic teacher-only design', student_profile='Synthetic learners',
               response_strategies='Invite evidence and revision.', tone='Supportive.', response_detail='balanced',
               phases=['worksheet', 'quiz', 'reading', 'wrap_up'], reading_focus='Use attached public reading only.',
               reading_question_count=1, reference_delivery='on_request', idle_hint_seconds=0, presentation='full')


def question(mid, qid='source-q'):
    return dict(id=qid, group_id='core', ordinal=1, type='open_response', prompt='Explain why consistent marking supports reliability.',
                options=[], answer_slots=1, images=[], source_label='Synthetic selected B', source_material_ids=[mid], source_links=[])


class Acceptance:
    def __init__(self, base, out, fixtures):
        self.base, self.out, self.fixtures = base.rstrip('/'), out, fixtures
        self.checks, self.failures, self.events, self.ids, self.ocr = [], [], [], {}, []
        self.clients = [httpx.Client(base_url=self.base, trust_env=False, timeout=120) for _ in range(5)]
        self.teacher, self.student, self.second, self.admin, self.anonymous = self.clients

    def call(self, client, method, url, body=None, expected=200, **kw):
        r = client.request(method, url, json=body, **kw)
        self.events.append(dict(method=method, url=url, status=r.status_code, expected=expected))
        if r.status_code != expected:
            # Log status only: never dump auth/cookies/private server responses.
            raise AssertionError(f'{method} {url}: expected {expected}, got {r.status_code}')
        return r.json() if r.headers.get('content-type', '').startswith('application/json') else r

    def check(self, name, condition, details=None):
        if not condition:
            raise AssertionError(name + (': ' + json.dumps(details) if details else ''))
        self.checks.append(name)
        print('PASS', name, flush=True)
        self.save('running')

    def save(self, status):
        self.out.mkdir(parents=True, exist_ok=True)
        result = dict(status=status, checks=self.checks, failures=self.failures, requests=self.events, request_count=len(self.events),
                      ids=self.ids, ocr=self.ocr, real_backend_http=True, real_model=False, synthetic_only=True,
                      intercepted_application_routes=0, model_evidence='Explicit deterministic demo. Actual CPU OCR, NOT LLM evidence.')
        (self.out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')

    def upload(self, sid, name, data=None, **meta):
        content = data if data is not None else ('Synthetic reading ' + name + ': reliability means consistent marking.').encode()
        return self.call(self.teacher, 'POST', f'/api/sessions/{sid}/materials', files={'file': (name, content, mimetypes.guess_type(name)[0] or 'application/octet-stream')}, data={'visibility': 'student', 'kind': 'reading', **meta})

    def session(self, sid):
        return self.call(self.teacher, 'GET', f'/api/sessions/{sid}')

    def mids(self, sid):
        return {m['id'] for m in self.session(sid)['materials']}

    def library(self):
        return {m['id']: m for m in self.call(self.teacher, 'GET', f'/api/courses/{self.cid}/materials')['materials']}

    def attach(self, sid, mid):
        return self.call(self.teacher, 'POST', f'/api/sessions/{sid}/materials/attach', {'material_id': mid})

    def detach(self, sid, mid):
        return self.call(self.teacher, 'DELETE', f'/api/sessions/{sid}/materials/{mid}')

    def publish(self, label):
        return self.call(self.teacher, 'POST', f'/api/teacher/courses/{self.cid}/versions/publish', {'label': label})['id']

    def snapshot(self, vid):
        return self.call(self.teacher, 'GET', f'/api/teacher/courses/{self.cid}/versions/{vid}')

    def work(self, sid, vid):
        return self.call(self.student, 'GET', f'/api/sessions/{sid}/workspace?version_id={vid}')

    def turn(self, sid, vid, message, rid, **kw):
        return self.call(self.student, 'POST', f'/api/sessions/{sid}/tutor/turn?version_id={vid}', dict(message=message, request_id=rid, web_search=False, **kw))

    def run(self):
        boot = self.call(self.anonymous, 'GET', '/api/bootstrap')
        self.check('Explicit demo-enabled target; no real model/search', boot['demo_enabled'] and boot['ai']['mode'] == 'demo')
        for client, body in ((self.teacher, {'role': 'teacher'}), (self.student, {'role': 'student', 'student_index': 1}),
                             (self.second, {'role': 'student', 'student_index': 2}), (self.admin, {'role': 'admin'})):
            self.call(client, 'POST', '/api/auth/demo', body)
        course = self.call(self.teacher, 'POST', '/api/courses', {'code': 'S4-API-' + secrets.token_hex(4), 'title': 'Synthetic stage4 material HTTP lab', 'description': 'Acceptance QA only.'})
        self.cid = course['id']
        for client in (self.student, self.second):
            self.call(client, 'POST', '/api/courses/join', {'join_code': course['join_code']})
        s1, s2 = [self.call(self.teacher, 'POST', f'/api/courses/{self.cid}/sessions', {'title': 'Synthetic ' + name, 'number': i+1, 'teaching_profile': PROFILE})['id'] for i, name in enumerate(('S1', 'S2'))]
        self.ids.update(course=self.cid, s1=s1, s2=s2)
        a, b, c = [self.upload(s1, x+'.txt') for x in 'ABC']
        self.check('HTTP S1 ABC; S2 explicitly empty; course library exactly three', self.mids(s1) == {a['id'], b['id'], c['id']} and not self.mids(s2) and len(self.library()) == 3)
        d, e = [self.upload(s2, x+'.txt') for x in 'DE']
        attached = self.attach(s2, b['id'])
        again = self.attach(s2, b['id'])
        self.ids.update(b=b['id'], abcde=[x['id'] for x in (a,b,c,d,e)])
        self.check('HTTP exact ABC/BDE, course five, repeated attach same ID/URL', self.mids(s1) == {a['id'],b['id'],c['id']} and self.mids(s2) == {b['id'],d['id'],e['id']} and len(self.library()) == 5 and attached == again and attached['id'] == b['id'] and attached['download_url'] == b['download_url'])
        self.check('Library tracks B linked twice without file copies', set(self.library()[b['id']]['session_ids']) == {s1,s2})
        foreign = self.call(self.teacher, 'POST', '/api/courses', {'code': 'S4-OTHER-' + secrets.token_hex(3), 'title': 'Synthetic different course'})
        foreign_sid = self.call(self.teacher, 'POST', f'/api/courses/{foreign["id"]}/sessions', {'title': 'Cross course'})['id']
        self.call(self.teacher, 'POST', f'/api/sessions/{foreign_sid}/materials/attach', {'material_id': b['id']}, expected=422)
        for client, status in ((self.anonymous,401),(self.student,403),(self.admin,403)):
            self.call(client, 'GET', f'/api/courses/{self.cid}/materials', expected=status)
            self.call(client, 'POST', f'/api/sessions/{s2}/materials/attach', {'material_id': b['id']}, expected=status)
        self.check('Ownership, anonymous/student/unrelated staff and cross-course guards are actual HTTP rejects', True)
        private = self.upload(s1, 'private-synthetic.txt', b'SYNTHETIC_PRIVATE_READING_ONLY', visibility='teacher')
        key = self.upload(s1, 'synthetic-key.txt', b'SYNTHETIC_NEVER_AGGREGATE_KEY', visibility='teacher', kind='answer_key')
        self.attach(s2, private['id']); self.attach(s2, key['id'])
        self.call(self.teacher, 'PATCH', f'/api/sessions/{s2}/materials/{key["id"]}', {'visibility':'student'}, expected=422)
        for client in (self.student,self.admin):
            self.call(client, 'POST', f'/api/sessions/{s2}/materials/{private["id"]}/reprocess', expected=403)
        for sid in (s1,s2):
            self.call(self.teacher, 'PATCH', f'/api/sessions/{sid}', {'status':'published','groups':[{'id':'core','title':'Synthetic reasoning','kind':'core'}], 'questions':[question(b['id'])]})
        self.call(self.teacher, 'DELETE', f'/api/sessions/{s2}/materials/{b["id"]}', expected=409)
        old = self.publish('Synthetic ABC/BDE original edition')
        original = self.snapshot(old)
        w = self.work(s2, old)  # Only S2 gets learning history, not material origin S1.
        public_ids = {m['id'] for m in w['session']['materials']}
        self.check('Published S2 sources limited to BDE; private/key and unrelated AC hidden', public_ids == {b['id'],d['id'],e['id']} and 'SYNTHETIC_PRIVATE' not in json.dumps(w) and 'SYNTHETIC_NEVER' not in json.dumps(w))
        for mid in (private['id'],key['id']):
            for route in ('preview','download'):
                self.call(self.student,'GET',f'/api/materials/{mid}/{route}?version_id={old}',expected=403)
        self.check('Attachment does not publish teacher-only/key originals or permit student reprocess', True)
        self.call(self.student, 'POST', f'/api/sessions/{s2}/tutor/start?version_id={old}', {'request_id':'s4-start'})
        w = self.turn(s2,old,'Consistent marking supports reliability because evidence is stable.','s4-answer')
        self.check('Actual selected-source worksheet enters demo quiz invitation', w['tutor']['phase']=='quiz_offer' and w['attempts']['source-q']['answer'].endswith('stable.'))
        w = self.turn(s2,old,'No','s4-skip',action='skip_quiz')
        p = w['messages'][-1]['metadata']['presented_question']
        self.check('Demo reading source label belongs to attached published BDE, never course-wide AC/private/key', w['tutor']['phase']=='reading' and set(p['source_labels']) <= {m['source_label'] for m in w['session']['materials']} and p['source_labels'])
        # No direct file/DB mutation; shared metadata changes and detached membership use real API.
        self.call(self.teacher,'PATCH',f'/api/sessions/{s1}/materials/{b["id"]}',{'title':'Shared B renamed'})
        self.check('Shared B title is independently visible in both draft sessions', all(next(m for m in self.session(s)['materials'] if m['id']==b['id'])['title']=='Shared B renamed' for s in (s1,s2)))
        self.call(self.teacher,'PATCH',f'/api/sessions/{s1}',{'questions':[]})
        self.detach(s1,b['id'])
        self.check('Detach B from origin retains S2, course library, original download', b['id'] not in self.mids(s1) and b['id'] in self.mids(s2) and self.call(self.teacher,'GET',b['download_url']).content == self.call(self.student,'GET',b['download_url']+'?version_id='+old).content)
        self.call(self.teacher,'PATCH',f'/api/sessions/{s2}',{'questions':[]})
        self.detach(s2,b['id'])
        self.check('Detach last B membership preserves unassigned library original and denies reprocess', self.library()[b['id']]['session_ids']==[] and self.call(self.teacher,'GET',b['download_url']).content.startswith(b'Synthetic reading B'))
        self.call(self.teacher,'POST',f'/api/sessions/{s2}/materials/{b["id"]}/reprocess',expected=404)
        new = self.publish('Synthetic detached next edition')
        history = self.work(s2,old)
        self.check('Immutable original snapshot and student history survive shared edits/detach/new publication', self.snapshot(old)==original and history['read_only'] and {m['id'] for m in history['session']['materials']}==public_ids)
        self.call(self.second,'GET',b['download_url']+'?version_id='+old,expected=403)
        self.check('Historical shared B download checks S2 saved history despite origin S1; unseen student forbidden', self.call(self.student,'GET',b['download_url']+'?version_id='+old).content.startswith(b'Synthetic reading B'))
        restored = self.call(self.teacher,'POST',f'/api/teacher/courses/{self.cid}/versions/{old}/restore',{'label':'Synthetic restore'})['id']
        self.check('Restore exact ABC/BDE memberships with original B shared title, immutable old snapshot', restored not in (old,new) and self.mids(s1)=={a['id'],b['id'],c['id'],private['id'],key['id']} and self.mids(s2)=={b['id'],d['id'],e['id'],private['id'],key['id']} and self.library()[b['id']]['title']=='B.txt' and self.snapshot(old)==original)
        # Restore retains sources, so clear S1 refs before detach for restart proof.
        self.call(self.teacher,'PATCH',f'/api/sessions/{s1}',{'questions':[]})
        self.detach(s1,b['id'])
        for filename in ('synthetic_scan.png','synthetic_embedded_grouped.pptx','synthetic_mixed.pdf'):
            data = (self.fixtures/filename).read_bytes()
            item = self.upload(s2,filename,data)
            before = self.snapshot(old)
            result = self.call(self.teacher,'POST',f'/api/sessions/{s2}/materials/{item["id"]}/reprocess')
            report = result.get('extraction_report',{})
            readback = next(m for m in self.session(s2)['materials'] if m['id']==item['id'])
            originalbytes = self.call(self.teacher,'GET',result['download_url']).content
            self.ocr.append({'filename':filename,'material_id':result['id'],'status':result['status'],'report':report,
                             'input_sha256':hashlib.sha256(data).hexdigest(),'original_retained':originalbytes==data,
                             'ocr_expected_text_present':'SYNTHETIC CPU OCR MATERIAL' in result['excerpt'],
                             'native_expected_text_present': 'Native' in result['excerpt'] if filename.endswith('.pdf') else None})
            self.check('Actual HTTP upload + reprocess CPU OCR '+filename, result['id']==item['id'] and result['status']=='needs_review' and report.get('ocr_units',0)>0 and report.get('visual_review_required') and report.get('units_processed')==report.get('units_total') and report.get('excerpt_chars')==len(result['excerpt']) and 'SYNTHETIC CPU OCR MATERIAL' in result['excerpt'] and originalbytes==data and readback==result and self.snapshot(old)==before)
            if filename.endswith('.pdf'):
                self.ids['pdf']=item['id']
                preview=self.call(self.teacher,'GET',item['preview_url'])
                self.check('PDF exact MIME, inline, nosniff; no CSP sandbox; original bytes', preview.headers.get('content-type')=='application/pdf' and preview.headers.get('x-content-type-options')=='nosniff' and preview.headers.get('content-disposition','').startswith('inline') and 'sandbox' not in preview.headers.get('content-security-policy','') and preview.content==data)
                self.call(self.anonymous,'GET',item['preview_url'],expected=401)
                self.call(self.admin,'GET',item['preview_url'],expected=403)
                self.call(self.student,'GET',item['preview_url'],expected=404)  # Not present in any student published snapshot.
                self.check('New unpublished PDF preview is authorized owner-only, no public URL bypass', True)
        pdf_version = self.publish('Synthetic OCR PDF access edition')
        student_pdf = self.call(self.student, 'GET', f'/api/materials/{self.ids["pdf"]}/preview?version_id={pdf_version}')
        self.check('Published PDF permits authorized student original while anonymous/staff auth rejects persist',
                   student_pdf.headers.get('content-type') == 'application/pdf' and student_pdf.content == (self.fixtures/'synthetic_mixed.pdf').read_bytes())
        self.call(self.anonymous, 'GET', f'/api/materials/{self.ids["pdf"]}/preview?version_id={pdf_version}', expected=401)
        self.call(self.admin, 'GET', f'/api/materials/{self.ids["pdf"]}/preview?version_id={pdf_version}', expected=403)
        invalid=self.teacher.post(f'/api/sessions/{s2}/materials',files={'file':('invalid-synthetic.exe',b'Synthetic invalid extension','application/octet-stream')})
        self.events.append({'method':'POST','url':f'/api/sessions/{s2}/materials','status':invalid.status_code,'expected':415})
        self.check('Invalid extension produces real server 415 (not fabricated failure)',invalid.status_code==415)
        self.ids['expected_final']={sid:sorted(self.mids(sid)) for sid in (s1,s2)}
        self.ids.update(old_version=old,restored_version=restored)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-url',default=os.getenv('AICADEMIYA_TEST_URL'))
    p.add_argument('--artifact-dir',default=os.getenv('AICADEMIYA_TEST_ARTIFACT_DIR'))
    p.add_argument('--fixture-dir',default=str(FIXTURES))
    p.add_argument('--confirm-test-data',action='store_true')
    args=p.parse_args()
    if not args.base_url or not args.artifact_dir or not args.confirm_test_data:
        p.error('Require isolated QA --base-url, --artifact-dir and --confirm-test-data.')
    a=Acceptance(args.base_url,Path(args.artifact_dir),Path(args.fixture_dir))
    try:
        a.run()
    except Exception as exc:
        a.failures.append({'name':'Dependent API scenario interrupted','error':str(exc),'traceback':traceback.format_exc()})
        print(traceback.format_exc(),flush=True)
    finally:
        for c in a.clients:c.close()
        a.save('failed' if a.failures else 'passed')
    print(json.dumps({'status':'failed' if a.failures else 'passed','checks':len(a.checks),'failures':len(a.failures),'requests':len(a.events)}))
    return 1 if a.failures else 0


if __name__=='__main__':
    raise SystemExit(main())
