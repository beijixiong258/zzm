"""Stage12 real TestClient boundary with explicitly SYNTHETIC PDF/parser output.

These fixtures verify storage/API behavior, NOT OCR accuracy or real extraction.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import copy
import io
import json
from pathlib import Path
import threading
import time

from fastapi.testclient import TestClient
from PIL import Image
import pymupdf
import pytest

from backend.aicademiya.main import create_app
from backend.aicademiya.db import issue_session
from backend.aicademiya.document_bundle import sha256_file
from backend.aicademiya.document_storage import get_document_manifest
from .conftest import expect, publish

CID = 'synthetic-course'


def pdf_bytes(count=2):
    with pymupdf.open() as doc:
        for n in range(count):
            p = doc.new_page(width=100, height=120)
            p.insert_text((8, 30), f'SYNTHETIC PAGE {n+1}', fontsize=6)
        return doc.tobytes()


def synthetic_bundle(source, root, *, uncertain=False, mutate=None):
    root = Path(root)
    (root/'pages').mkdir(parents=True)
    (root/'assets').mkdir()
    (root/'raw').mkdir()
    (root/'raw'/'synthetic-receipt.txt').write_text('SYNTHETIC fixture only; no OCR performed', encoding='utf-8')
    with pymupdf.open(source) as doc:
        count = doc.page_count
    pages = []
    for number in range(1, count+1):
        name = f'pages/p{number}.png'
        Image.new('RGB', (32, 48), 'white').save(root/name)
        Image.new('RGB', (8, 8), 'blue').save(root/f'assets/p{number}.png')
        quality = 'needs_review' if uncertain and number == count else 'extracted'
        pages.append({'number': number, 'printed_label': str(number), 'rotation': 0,
                      'image': name, 'width': 32, 'height': 48,
                      'status': 'needs_review' if quality == 'needs_review' else 'text',
                      'issues': [], 'blocks': [{'id': f'p{number}-b0', 'type': 'text',
                         'bbox': [0.0,0.0,1.0,1.0], 'text': f'SYNTHETIC complete fixture text on page {number}',
                         'quality': quality, 'issues': [], 'assets': [f'assets/p{number}.png'], 'parent_id': None}]})
    value = {'schema_version': 1, 'source_sha256': sha256_file(source),
             'parser': {'name':'SYNTHETIC-test-parser','version':'1','recipe':'Fixture; no OCR'},
             'page_count': count, 'complete': True, 'warnings': [], 'pages': pages}
    if mutate:
        mutate(value)
    (root/'manifest.json').write_text(json.dumps(value), encoding='utf-8')
    return value


class Processor:
    def __init__(self):
        self.release, self.started = threading.Event(), threading.Event()
        self.release.set()
        self.calls, self.active, self.max_active = [], 0, 0
        self.fail, self.uncertain, self.mutate = False, False, None

    def hold(self):
        self.started.clear()
        self.release.clear()

    def __call__(self, source, root, cancelled):
        self.calls.append((source, root))
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.started.set()
        try:
            while not self.release.wait(.02):
                if cancelled.is_set():
                    raise RuntimeError('SYNTHETIC cancellation')
            if self.fail:
                root.mkdir(parents=True)
                (root/'raw').mkdir()
                (root/'raw'/'partial.txt').write_text('Retained SYNTHETIC partial output')
                raise RuntimeError('Secret provider argv and private paths MUST NOT appear')
            synthetic_bundle(source, root, uncertain=self.uncertain, mutate=self.mutate)
        finally:
            self.active -= 1


@pytest.fixture
def docenv(tmp_path, catalog, monkeypatch):
    monkeypatch.delenv('AICADEMIYA_DOCUMENT_WORKER_COMMAND', raising=False)
    monkeypatch.setenv('AICADEMIYA_AI_MODE', 'demo')
    processor = Processor()
    app = create_app(data_dir=tmp_path/'docs-data', catalog_path=catalog, demo_enabled=True,
                     frontend_dir=tmp_path/'no-dist', document_processor=processor)
    with TestClient(app) as teacher:
        expect(teacher.post('/api/auth/demo', json={'role':'teacher'}))
        with app.state.database.connect() as conn:
            token = issue_session(conn, 'demo-student-1')
        student = TestClient(app)
        student.cookies.set('aicademiya_session', token)
        try:
            yield app, teacher, student, processor
        finally:
            processor.release.set()
            student.close()
    assert app.state.document_queue.child is None
    assert app.state.document_queue.thread is None


def upload(client, count=2, **fields):
    return client.post('/api/sessions/s4/materials', data={'processing':'full_document', **fields},
                       files={'file':('synthetic.pdf', pdf_bytes(count), 'application/pdf')})


def endpoint(mid):
    return '/api/materials/'+mid+'/document'


def wait_job(client, mid, jid=None, status=None):
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if jid:
            job = expect(client.get(endpoint(mid)+'/jobs/'+jid))
        else:
            job = expect(client.get(endpoint(mid)))['latest_job']
        if job and (job['status'] == status if status else job['status'] in ('completed','failed')):
            return job
        time.sleep(.02)
    raise AssertionError(f'SYNTHETIC job did not reach {status or "terminal state"}: {job}')


def complete(client, count=2, **fields):
    material = expect(upload(client, count, **fields))
    assert material['status'] == 'processing'
    job = wait_job(client, material['id'])
    assert job['status'] == 'completed', job
    return material['id'], job['revision_id'], job


def page(client, mid, rid, number=1, vid=None):
    params = {'revision_id':rid}
    if vid:
        params['version_id'] = vid
    return client.get(endpoint(mid)+f'/pages/{number}', params=params)


def review_payload(rid, request='review-1', block='p2-b0', **change):
    return {'request_id':request, 'expected_revision':rid,
            'changes':[{'block_id':block, 'quality':'approved', 'reason':'SYNTHETIC explicit review', **change}]}


def test_async_truthful_progress_capability_completion_and_late317(docenv):
    app, teacher, student, processor = docenv
    assert expect(teacher.get('/api/document-processing')) == {
        'available':True,'formats':['pdf'],'max_upload_bytes':64*1024*1024,'max_pages':1000}
    processor.hold()
    material = expect(upload(teacher, 317))
    mid = material['id']
    assert material['document'] is None and material['excerpt'] == ''
    assert processor.started.wait(5)
    running = wait_job(teacher, mid, status='running')
    assert running['processed_pages'] == 0 and running['page_count'] == 317 and running['revision_id'] is None
    assert expect(teacher.get(endpoint(mid)))['pages'] == []
    expect(teacher.post(f'/api/teacher/courses/{CID}/versions/publish', json={}), 409)
    processor.release.set()
    done = wait_job(teacher, mid)
    assert done['status'] == 'completed' and done['processed_pages'] == 317
    info = expect(teacher.get(endpoint(mid)))
    assert len(info['pages']) == 317
    for n in (1,269,317):
        data = expect(page(teacher, mid, done['revision_id'], n))
        assert data['number'] == n and data['blocks'][0]['text'].endswith(f'page {n}')
        assert 'image' not in data and 'image_url' in data
        assert expect(teacher.get(endpoint(mid))) == info
    with app.state.database.connect() as conn:
        stored = conn.execute('SELECT * FROM materials WHERE id=?', (mid,)).fetchone()
        manifest, root = get_document_manifest(conn, stored)
        assert manifest['page_count'] == 317
        assert (root/'raw'/'synthetic-receipt.txt').is_file()
        assert not str(root) in json.dumps(manifest)
    edition = publish(teacher)['id']
    public = expect(student.get(endpoint(mid)))
    assert public['latest_job'] is None and public['document']['revision_id'] == done['revision_id']
    data = expect(page(student, mid, done['revision_id'], 317))
    assert 'version_id='+edition in data['image_url']
    image = student.get(data['image_url'])
    assert image.status_code == 200 and image.headers['content-type'] == 'image/png'
    assert image.headers['cache-control'] == 'private, no-store'
    assert image.headers['content-disposition'] == 'inline'
    assert image.headers['x-content-type-options'] == 'nosniff'


def test_revision_review_idempotency_exact_get_raw_audit_and_old_edition(docenv):
    app, teacher, student, processor = docenv
    processor.uncertain = True
    mid, rid, job = complete(teacher)
    old = publish(teacher)['id']
    expect(student.get('/api/sessions/s4/workspace', params={'version_id':old}))
    payload = review_payload(rid, text='SYNTHETIC corrected complete block')
    receipt = expect(teacher.post(endpoint(mid)+'/reviews', json=payload))
    newer = receipt['document']['revision_id']
    assert newer != rid
    assert receipt == expect(teacher.get(endpoint(mid)+'/reviews/review-1'))
    assert receipt == expect(teacher.post(endpoint(mid)+'/reviews', json=payload))
    corrected = expect(page(teacher, mid, newer, 2))['blocks'][0]
    assert corrected['raw_text'] == 'SYNTHETIC complete fixture text on page 2'
    assert corrected['text'] == 'SYNTHETIC corrected complete block'
    assert corrected['quality'] == 'approved' and corrected['review']['by'] == 'demo-teacher'
    assert corrected['review']['reason'] == payload['changes'][0]['reason'] and corrected['review']['at']
    expect(teacher.post(endpoint(mid)+'/reviews', json=review_payload(rid, request='stale')), 409)
    expect(teacher.post(endpoint(mid)+'/reviews', json=review_payload(rid, text='Conflicting same ID')), 409)
    expect(page(teacher, mid, rid), 409)
    assert expect(page(student, mid, rid, 2))['blocks'][0]['quality'] == 'needs_review'
    expect(page(student, mid, newer, 2), 409)
    new_edition = publish(teacher)['id']
    assert new_edition != old
    assert expect(page(student, mid, newer, 2))['blocks'][0]['text'] == corrected['text']
    assert expect(page(student, mid, rid, 2, old))['blocks'][0]['text'].endswith('page 2')
    second = expect(teacher.post(endpoint(mid)+'/reviews', json=review_payload(newer, 'review-2', text='SYNTHETIC second correction')))
    again = expect(page(teacher, mid, second['document']['revision_id'], 2))['blocks'][0]
    assert again['raw_text'] == corrected['raw_text']
    with app.state.database.connect() as conn:
        rows = conn.execute('SELECT * FROM document_revisions WHERE material_id=?', (mid,)).fetchall()
        assert len(rows) == 3 and len({r['parse_id'] for r in rows}) == 1
        roots = [json.loads(s['content_json'])['document_dir'] for s in [conn.execute('SELECT * FROM materials WHERE id=?', (mid,)).fetchone()]]
        assert len(list(Path(roots[0]).parent.iterdir())) == 1
        import sqlite3
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute('UPDATE document_revisions SET manifest_json=? WHERE id=?', ('{}', rid))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute('DELETE FROM document_revisions WHERE id=?', (rid,))
    expect(teacher.post('/api/sessions/s4/materials/'+mid+'/reprocess'), 409)


def test_job_request_recovery_active_conflicts_serial_execution_and_preview_revision(docenv):
    app, teacher, student, processor = docenv
    mid, rid, first = complete(teacher)
    baseline = expect(teacher.get('/api/teacher/sessions/s4/preview'))['current_revision']
    processor.hold()
    payload = {'request_id':'retry-original','expected_revision':rid}
    accepted = expect(teacher.post(endpoint(mid)+'/jobs', json=payload))
    assert processor.started.wait(5)
    running = wait_job(teacher, mid, accepted['id'], 'running')
    assert expect(teacher.get(endpoint(mid)+'/jobs/requests/retry-original')) == running
    assert expect(teacher.post(endpoint(mid)+'/jobs', json=payload))['id'] == accepted['id']
    expect(teacher.post(endpoint(mid)+'/jobs', json={'request_id':'other','expected_revision':rid}), 409)
    expect(teacher.post(endpoint(mid)+'/jobs', json={'request_id':'retry-original','expected_revision':None}), 409)
    expect(teacher.post(endpoint(mid)+'/reviews', json=review_payload(rid)), 409)
    assert expect(teacher.get('/api/teacher/sessions/s4/preview'))['current_revision'] == baseline
    queued_material = expect(upload(teacher))
    queued = wait_job(teacher, queued_material['id'], status='queued')
    assert queued['started_at'] is None and processor.max_active == 1
    processor.release.set()
    final = wait_job(teacher, mid, accepted['id'])
    assert final['status'] == 'completed' and final['revision_id'] != rid
    assert wait_job(teacher, queued_material['id'])['status'] == 'completed'
    assert processor.max_active == 1
    assert final == expect(teacher.get(endpoint(mid)+'/jobs/requests/retry-original'))
    assert expect(teacher.get('/api/teacher/sessions/s4/preview'))['current_revision'] != baseline
    expect(teacher.get(endpoint(mid)+'/jobs/requests/unknown'), 404)
    expect(teacher.get(endpoint(mid)+'/jobs/'+queued['id']), 404)


def test_failure_keeps_original_and_valid_revision_publication_is_attached_only(docenv):
    app, teacher, student, processor = docenv
    mid, rid, _ = complete(teacher)
    processor.fail = True
    accepted = expect(teacher.post(endpoint(mid)+'/jobs', json={'request_id':'failed-retry','expected_revision':rid}))
    failed = wait_job(teacher, mid, accepted['id'])
    assert failed['status'] == 'failed' and 'Secret' not in failed['error'] and failed['revision_id'] is None
    assert expect(teacher.get(endpoint(mid)))['document']['revision_id'] == rid
    assert page(teacher, mid, rid).status_code == 200
    publish(teacher)
    broken = expect(upload(teacher))
    assert wait_job(teacher, broken['id'])['status'] == 'failed'
    library = expect(teacher.get(f'/api/courses/{CID}/materials'))['materials']
    item = next(m for m in library if m['id'] == broken['id'])
    assert item['status'] == 'error' and item['document'] is None
    assert teacher.get('/api/materials/'+broken['id']+'/download').status_code == 200
    expect(teacher.post(f'/api/teacher/courses/{CID}/versions/publish', json={}), 409)
    expect(teacher.delete('/api/sessions/s4/materials/'+broken['id']))
    publish(teacher)
    assert page(teacher, mid, rid).status_code == 200
    assert (app.state.document_queue.uploads/'documents'/accepted['id']/'raw'/'partial.txt').is_file()


@pytest.mark.parametrize('mutation', ['source','role','session','assignment','trash','restore'], ids=['source','role','token','staff','trash','restore'])
def test_commit_rechecks_authority_source_revision_and_restore(docenv, mutation):
    app, teacher, student, processor = docenv
    mid, rid, _ = complete(teacher)
    edition = publish(teacher)['id']
    processor.hold()
    accepted = expect(teacher.post(endpoint(mid)+'/jobs', json={'request_id':'race','expected_revision':rid}))
    assert processor.started.wait(5)
    with app.state.database.connect() as conn:
        if mutation == 'source':
            path = Path(conn.execute('SELECT file_path FROM materials WHERE id=?', (mid,)).fetchone()[0])
            path.write_bytes(pdf_bytes(3))
        elif mutation == 'role':
            conn.execute("UPDATE users SET role='student' WHERE id='demo-teacher'")
        elif mutation == 'session':
            conn.execute("DELETE FROM auth_sessions WHERE user_id='demo-teacher'")
        elif mutation == 'assignment':
            conn.execute("DELETE FROM course_staff WHERE user_id='demo-teacher'")
        elif mutation == 'trash':
            conn.execute("INSERT INTO course_trash VALUES(?,?,?)", (CID, '2026-01-01T00:00:00+00:00', 'demo-teacher'))
    if mutation == 'restore':
        expect(teacher.post(f'/api/teacher/courses/{CID}/versions/{edition}/restore', json={}))
    processor.release.set()
    deadline = time.monotonic()+10
    while time.monotonic() < deadline:
        with app.state.database.connect() as conn:
            job = dict(conn.execute('SELECT * FROM document_jobs WHERE id=?', (accepted['id'],)).fetchone())
            current = json.loads(conn.execute('SELECT content_json FROM materials WHERE id=?', (mid,)).fetchone()[0])
        if job['status'] == 'failed' and processor.active == 0:
            break
        time.sleep(.02)
    assert job['status'] == 'failed' and current['document']['revision_id'] == rid
    assert processor.active == 0


def test_scope_anonymous_private_revocation_trash_and_history(docenv):
    app, teacher, student, processor = docenv
    mid, rid, _ = complete(teacher)
    private_mid, private_rid, _ = complete(teacher, visibility='teacher', kind='answer_key')
    edition = publish(teacher)['id']
    image = expect(page(teacher, mid, rid))['image_url']
    for path in ('/api/document-processing', endpoint(mid), endpoint(mid)+'/pages/1?revision_id='+rid, image):
        assert TestClient(app).get(path).status_code == 401
    for path in (endpoint(private_mid), endpoint(private_mid)+'/pages/1?revision_id='+private_rid):
        expect(student.get(path), 403)
    expect(student.post(endpoint(mid)+'/jobs', json={'request_id':'student','expected_revision':rid}), 403)
    expect(student.post(endpoint(mid)+'/reviews', json=review_payload(rid)), 403)
    expect(student.get(endpoint(mid)+'/jobs/requests/upload:'+mid), 403)
    unrelated = expect(teacher.post('/api/courses', json={'title':'SYNTHETIC unrelated','code':'OTHER'}))['id']
    with app.state.database.connect() as conn:
        conn.execute("INSERT INTO users(id,name,email,role) VALUES('other-staff','Other','other@example.invalid','teacher')")
        conn.execute('INSERT INTO course_staff VALUES(?,?)', (unrelated, 'other-staff'))
        token = issue_session(conn, 'other-staff')
    other = TestClient(app)
    other.cookies.set('aicademiya_session', token)
    try:
        for path in (endpoint(mid), endpoint(mid)+'/pages/1?revision_id='+rid, image, endpoint(mid)+'/jobs/requests/upload:'+mid):
            expect(other.get(path), 403)
        expect(other.post(endpoint(mid)+'/reviews', json=review_payload(rid)), 403)
    finally:
        other.close()
    expect(student.get('/api/sessions/s4/workspace', params={'version_id':edition}))
    corrected = expect(teacher.post(endpoint(mid)+'/reviews', json=review_payload(rid)))['document']['revision_id']
    newer = publish(teacher)['id']
    assert expect(page(student, mid, rid, vid=edition))['blocks'][0]['text'].startswith('SYNTHETIC')
    with app.state.database.connect() as conn:
        token2 = issue_session(conn, 'demo-student-2')
    newcomer = TestClient(app)
    newcomer.cookies.set('aicademiya_session', token2)
    try:
        expect(page(newcomer, mid, rid, vid=edition), 403)
        assert page(newcomer, mid, corrected).status_code == 200
    finally:
        newcomer.close()
    expect(teacher.post(f'/api/courses/{CID}/trash', json={}))
    for client in (teacher, student):
        assert client.get(endpoint(mid)).status_code in (403,410)
        assert client.get(image).status_code in (403,410)
    expect(teacher.post(f'/api/courses/{CID}/restore', json={}))
    assert expect(student.get(endpoint(mid)))['latest_job'] is None


@pytest.mark.parametrize('path', ['manifest.json','raw/synthetic-receipt.txt','../manifest.json','pages/../../manifest.json','C:/private.png','pages\\p1.png','pages/missing.png'], ids=['manifest','raw','dotdot','nested-dotdot','drive','backslash','missing'])
def test_assets_only_registered_and_required_revision(docenv, path):
    app, teacher, student, processor = docenv
    mid, rid, _ = complete(teacher)
    response = teacher.get(endpoint(mid)+'/assets/'+path, params={'revision_id':rid})
    assert response.status_code in (404,422)
    expect(teacher.get(endpoint(mid)+'/pages/1'), 422)
    expect(teacher.get(endpoint(mid)+'/assets/pages/p1.png'), 422)
    expect(page(teacher, mid, 'not-current'), 409)
    expect(page(teacher, mid, rid, 0), 404)
    expect(page(teacher, mid, rid, 3), 404)
    response = teacher.get(endpoint(mid)+'/assets/pages/p1.png', params={'revision_id':'wrong'})
    expect(response, 409)


@pytest.mark.parametrize('changes', [[], [{'block_id':'none','quality':'approved','reason':'Why'}],
    [{'block_id':'p2-b0','quality':'extracted','reason':'Why'}], [{'block_id':'p2-b0','quality':'approved','reason':' '}],
    [{'block_id':'p2-b0','quality':'approved','reason':'Why','text':None}],
    [{'block_id':'p2-b0','quality':'approved','reason':'Why'}]*2,
    [{'block_id':'p2-b0','quality':'approved','reason':'Why'}]*101], ids=['empty','unknown','quality','blank','null','duplicate','over100'])
def test_review_bounded_atomic_validation(docenv, changes):
    app, teacher, student, processor = docenv
    mid, rid, _ = complete(teacher)
    payload = review_payload(rid)
    payload['changes'] = changes
    expect(teacher.post(endpoint(mid)+'/reviews', json=payload), 422)
    assert expect(teacher.get(endpoint(mid)))['document']['revision_id'] == rid
    expect(teacher.get(endpoint(mid)+'/reviews/review-1'), 404)


def test_unconfigured_full503_preview_compatible_no_side_effect(tmp_path, catalog, monkeypatch):
    monkeypatch.delenv('AICADEMIYA_DOCUMENT_WORKER_COMMAND', raising=False)
    app = create_app(data_dir=tmp_path/'unconfigured', catalog_path=catalog, demo_enabled=True, frontend_dir=tmp_path/'dist')
    with TestClient(app) as client:
        expect(client.post('/api/auth/demo', json={'role':'teacher'}))
        assert expect(client.get('/api/document-processing'))['available'] is False
        with app.state.database.connect() as conn:
            before = conn.execute('SELECT count(*) FROM materials').fetchone()[0]
        expect(upload(client), 503)
        with app.state.database.connect() as conn:
            assert conn.execute('SELECT count(*) FROM materials').fetchone()[0] == before
            assert conn.execute('SELECT count(*) FROM document_jobs').fetchone()[0] == 0
        assert list((tmp_path/'unconfigured'/'uploads').iterdir()) == []
        material = expect(client.post('/api/sessions/s4/materials', files={'file':('legacy.txt',b'SYNTHETIC legacy preview')}))
        assert material['status'] == 'ready' and material['excerpt'] and material['document'] is None
        assert expect(client.get(endpoint(material['id']))) == {'document':None,'latest_job':None,'pages':[]}
        expect(client.post(endpoint(material['id'])+'/jobs', json={'request_id':'new','expected_revision':None}), 503)


def test_upload_bounds_pdf_only_no_fallback(docenv):
    app, teacher, student, processor = docenv
    expect(teacher.post('/api/sessions/s4/materials', data={'processing':'bad'}, files={'file':('a.txt',b'SYNTHETIC')}), 422)
    expect(teacher.post('/api/sessions/s4/materials', data={'processing':'full_document'}, files={'file':('a.txt',b'SYNTHETIC')}), 415)
    expect(teacher.post('/api/sessions/s4/materials', data={'processing':'full_document'}, files={'file':('a.pdf',b'Not a PDF')}), 422)
    expect(upload(teacher, 1001), 422)
    expect(teacher.post('/api/sessions/s4/materials', data={'processing':'full_document'}, files={'file':('a.pdf',b'x'*(64*1024*1024+1))}), 413)
    with app.state.database.connect() as conn:
        assert conn.execute('SELECT count(*) FROM document_jobs').fetchone()[0] == 0
    assert not processor.calls


def test_concurrent_enqueue_exact_once_and_review_expected_revision_conflict(docenv):
    app, teacher, student, processor = docenv
    mid, rid, _ = complete(teacher)
    processor.hold()
    payload = {'request_id':'same-concurrent','expected_revision':rid}
    clients = [TestClient(app), TestClient(app)]
    for client in clients:
        client.cookies.update(teacher.cookies)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda client: client.post(endpoint(mid)+'/jobs', json=payload), clients))
        jobs = [expect(response) for response in responses]
        assert jobs[0]['id'] == jobs[1]['id']
        assert processor.started.wait(5)
        with app.state.database.connect() as conn:
            assert conn.execute('SELECT count(*) FROM document_jobs WHERE material_id=? AND request_id=?', (mid,'same-concurrent')).fetchone()[0] == 1
        processor.release.set()
        rid = wait_job(teacher, mid, jobs[0]['id'])['revision_id']
        requests = [review_payload(rid, request='concurrent-review-'+str(i)) for i in range(2)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda pair: pair[0].post(endpoint(mid)+'/reviews', json=pair[1]), zip(clients, requests)))
        assert sorted(r.status_code for r in responses) == [200,409]
        success = next(r.json() for r in responses if r.status_code == 200)
        winner = next(requests[i]['request_id'] for i,r in enumerate(responses) if r.status_code == 200)
        assert expect(teacher.get(endpoint(mid)+'/reviews/'+winner)) == success
    finally:
        processor.release.set()
        for client in clients:
            client.close()


def test_review_unicode_codepoint_limits_nonblank_reason_and_public_whitelist(docenv):
    app, teacher, student, processor = docenv
    mid, rid, _ = complete(teacher)
    expect(teacher.post(endpoint(mid)+'/reviews', json=review_payload(rid, text='\U0001f4da'*100001)), 422)
    expect(teacher.post(endpoint(mid)+'/reviews', json=review_payload(rid, reason='x'*2001)), 422)
    receipt = expect(teacher.post(endpoint(mid)+'/reviews', json=review_payload(rid, text='\U0001f4da'*100000, reason='  Explicit Unicode review  ')))
    rid = receipt['document']['revision_id']
    assert len(expect(page(teacher, mid, rid, 2))['blocks'][0]['text']) == 100000
    with app.state.database.connect() as conn:
        row = conn.execute('SELECT * FROM materials WHERE id=?', (mid,)).fetchone()
        raw = json.loads(row['content_json'])
        raw['document']['document_dir'] = 'PRIVATE_PATH_MUST_NOT_LEAK'
        raw['document']['parser']['secret'] = 'PRIVATE_SECRET_MUST_NOT_LEAK'
        raw['operational_job'] = {'secret':'PRIVATE_JOB_MUST_NOT_LEAK'}
        conn.execute('UPDATE materials SET content_json=? WHERE id=?', (json.dumps(raw),mid))
    edition = publish(teacher)['id']
    for client in (teacher, student):
        for url in (endpoint(mid), '/api/sessions/s4'):
            response = client.get(url)
            assert response.status_code == 200
            assert 'PRIVATE_' not in response.text and 'document_dir' not in response.text
    diff = teacher.get(f'/api/teacher/courses/{CID}/versions/{edition}/diff')
    assert diff.status_code == 200 and 'PRIVATE_' not in diff.text and 'document_dir' not in diff.text


def test_reprocess_before_first_edition_legacy_keeps_old_snapshot_only(docenv):
    app, teacher, student, processor = docenv
    # Default preview remains the stored historical behavior; Stage12 neither
    # backfills nor silently reads the later complete document into old editions.
    material = expect(teacher.post('/api/sessions/s4/materials', files={'file':('synthetic.pdf',pdf_bytes())}))
    mid = material['id']
    assert material['document'] is None and material['status'] in ('ready','needs_review')
    old = publish(teacher)['id']
    expect(student.get('/api/sessions/s4/workspace', params={'version_id':old}))
    accepted = expect(teacher.post(endpoint(mid)+'/jobs', json={'request_id':'explicit-full','expected_revision':None}))
    done = wait_job(teacher, mid, accepted['id'])
    assert done['status'] == 'completed'
    old_info = expect(student.get(endpoint(mid)))
    assert old_info == {'document':None,'latest_job':None,'pages':[]}
    expect(page(student, mid, done['revision_id']), 409)
    new = publish(teacher)['id']
    assert expect(student.get(endpoint(mid)))['document']['revision_id'] == done['revision_id']
    with app.state.database.connect() as conn:
        from backend.aicademiya.versions import snapshot
        _, saved = snapshot(conn, CID, old)
        selected = next(row for s in saved['sessions'] for row in s.get('_materials',[]) if row['id']==mid)
        assert get_document_manifest(conn, selected) == (None,None)
