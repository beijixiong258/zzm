"""CPU-only: real loopback HTTP fake fixtures, never a GPU/model test.

Generated full prepared bundles and literal fixture outputs are labelled. The
server deliberately implements only the counter/completion protocol, not a model.
"""
from __future__ import annotations

import ast
import base64
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

import pymupdf
import pytest
from PIL import Image

from backend.aicademiya.document_bundle import validate_bundle as app_validate
from tools.document_stage12.parser_helpers import dump, sha256, validate_bundle
from tools.material_stage15 import page_worker as worker

LABEL = 'cpu_http_fake_fixture_not_real_model_or_gpu'
BODY = '| Role | Text |\n| --- | --- |\n| T → Ss | O/0, I/l: ____ |\n'


def completion(body=BODY, finish='stop', content=None):
    return {'id': 'synthetic-http-fixture', 'model': LABEL,
            'choices': [{'finish_reason': finish, 'message': {'role': 'assistant',
              'content': content if content is not None else json.dumps({
                  'body_text': body, 'images': [{'description': 'Fixture table, unverified', 'bbox': [0, 0, 1000, 1000]}],
                  'uncertainty': '无'}, ensure_ascii=False)}}],
            'usage': {'prompt_tokens': 700, 'completion_tokens': 120, 'total_tokens': 820,
                      'prompt_tokens_details': {'cached_tokens': 0}}}


@pytest.fixture
def prepared(tmp_path):
    root = tmp_path / 'native-prepared'
    (root / 'pages').mkdir(parents=True)
    (root / 'assets').mkdir()
    (root / 'raw').mkdir()
    original = root / 'raw/source.pdf'
    with pymupdf.open() as pdf:
        for n in range(1, 4):
            page = pdf.new_page(width=100, height=80)
            page.insert_text((10, 20), 'Synthetic CPU fixture %d' % n, fontsize=6)
        pdf.save(original)
    (root / 'preview.pdf').write_bytes(original.read_bytes())
    (root / 'raw/native-evidence.bin').write_bytes(b'Literal original evidence\x00\xff\r\n')
    pages = []
    for n in range(1, 4):
        with Image.new('RGB', (100, 80), (n * 40, 20, 30)) as image:
            image.save(root / ('pages/p%04d.png' % n))
        asset = 'assets/p%d-b1.png' % n
        (root / asset).write_bytes((root / ('pages/p%04d.png' % n)).read_bytes())
        pages.append({'number': n, 'printed_label': str(n + 10), 'rotation': 0,
            'image': 'pages/p%04d.png' % n, 'width': 100, 'height': 80, 'status': 'needs_review',
            'issues': ['synthetic_native_fixture'], 'blocks': [
                {'id': 'p%d-b0' % n, 'type': 'text', 'bbox': [0, 0, 1, 1],
                 'text': 'Native\tO/0 I/l %d\r\n' % n, 'quality': 'extracted',
                 'issues': ['source_transcription_native'], 'assets': [], 'parent_id': None},
                {'id': 'p%d-b1' % n, 'type': 'image', 'bbox': [0, 0, 1, 1], 'text': '',
                 'quality': 'needs_review', 'issues': ['source_image_occurrence'], 'assets': [asset], 'parent_id': None}]})
    manifest = {'schema_version': 1, 'source_sha256': sha256(original), 'source_format': 'pdf',
                'preview_pdf': 'preview.pdf', 'parser': {'name': LABEL, 'version': '1', 'recipe': 'native-only-fixture'},
                'page_count': 3, 'complete': True, 'pages': pages, 'warnings': ['Synthetic fixture only'],
                'coverage': {'version': 1, 'expected_pages': 3, 'rendered_pages': 3, 'page_set_complete': True,
                             'semantic_accuracy_approved': False},
                'supplements': [{'id': 's1', 'kind': 'speaker_notes', 'source_part': 'raw/notes.xml',
                    'source_node': 'fixture-note', 'page_hint': 3, 'char_start': 0, 'char_end': 8,
                    'text': 'NOTE O/0', 'quality': 'extracted', 'visibility': 'teacher', 'derivation': 'original_office_xml'}]}
    (root / 'raw/notes.xml').write_bytes(b'<note>NOTE O/0</note>\r\n')
    dump(root / 'manifest.json', manifest)
    native = {'status': 'complete', 'engine': 'native', 'source_sha256': manifest['source_sha256'],
              'source_format': 'pdf', 'fixture_kind': LABEL,
              'page_timings': [{'page': n, 'model_calls': 0, 'model_processed': False,
                  'raster_sha256': sha256(root / ('pages/p%04d.png' % n))} for n in range(1, 4)]}
    # Deliberately non-pretty native receipt to verify original bytes, not JSON equality.
    (root / 'receipt.json').write_bytes(json.dumps(native, separators=(',', ':')).encode() + b'\r\n')
    validate_bundle(root)
    app_validate(root, manifest['source_sha256'], 3)
    return root


@contextmanager
def fake_http(*, count=None, replies=None, after_count=None, delay=0):
    state = {'fixture_kind': LABEL, 'requests': [], 'responses': [], 'completion_index': 0}
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        def log_message(self, *args):
            pass
        def do_POST(self):
            raw = self.rfile.read(int(self.headers['Content-Length']))
            payload = json.loads(raw)
            state['requests'].append({'path': self.path, 'payload': payload, 'raw': raw})
            if self.path == worker.COUNT_PATH:
                answer = count if count is not None else {'input_tokens': 700}
            elif self.path == worker.COMPLETION_PATH:
                index = state['completion_index']
                state['completion_index'] += 1
                answer = replies[index] if replies is not None else completion(body=BODY + 'Page %d\n' % (index + 1))
            else:
                answer = (404, b'unknown fake route')
            if delay:
                time.sleep(delay)
            if isinstance(answer, tuple):
                status, raw_answer = answer
            else:
                status, raw_answer = 200, worker.json_bytes(answer)
            state['responses'].append(raw_answer)
            if self.path == worker.COUNT_PATH and after_count:
                after_count()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw_answer)))
            self.send_header('X-Fixture-Kind', LABEL)
            self.end_headers()
            try:
                self.wfile.write(raw_answer)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield 'http://127.0.0.1:%d' % server.server_port, state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        assert not thread.is_alive()


def load(path):
    return json.loads(path.read_bytes())


def run(prepared, tmp_path, url, **kwargs):
    return worker.run_worker(prepared, tmp_path / 'output', vlm_url=url, model='fixture-vision',
                             pages='1,2', source=prepared / 'raw/source.pdf', **kwargs)


def assert_preserved(prepared, output, selected=(1, 2)):
    before, after = load(prepared / 'manifest.json'), load(output / 'manifest.json')
    assert after['source_sha256'] == before['source_sha256']
    assert after['source_format'] == before['source_format']
    assert after['supplements'] == before['supplements']
    for old, new in zip(before['pages'], after['pages']):
        assert new['blocks'][:len(old['blocks'])] == old['blocks']
        assert all(new[key] == old[key] for key in ('number', 'printed_label', 'rotation', 'image', 'width', 'height'))
        if old['number'] not in selected:
            assert new == old
    for path in prepared.rglob('*'):
        if path.is_file() and path.name not in ('manifest.json', 'receipt.json'):
            assert (output / path.relative_to(prepared)).read_bytes() == path.read_bytes()
    assert (output / 'raw/stage15-native-receipt.json').read_bytes() == (prepared / 'receipt.json').read_bytes()
    assert (output / 'raw/stage15-prepared-manifest.json').read_bytes() == (prepared / 'manifest.json').read_bytes()
    assert validate_bundle(output)['valid']
    assert app_validate(output, before['source_sha256'], before['page_count'])['complete']


@pytest.mark.skipif(sys.platform != 'linux', reason='Actual POSIX SIGTERM lifecycle check')
def test_cli_sigterm_during_actual_http_preserves_cancel(prepared, tmp_path):
    entered, release = threading.Event(), threading.Event()
    def hold_count():
        entered.set()
        assert release.wait(20)
    output = tmp_path / 'signal-output'
    with fake_http(after_count=hold_count) as (url, state):
        child = subprocess.Popen([sys.executable, str(Path(worker.__file__)),
            '--prepared-dir', str(prepared), '--output', str(output),
            '--vlm-url', url, '--model', 'fixture-vision', '--pages', '1,2',
            '--deadline-seconds', '30'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            assert entered.wait(15), 'Worker did not enter the actual count HTTP fixture'
            child.send_signal(signal.SIGTERM)
            stdout, _ = child.communicate(timeout=15)
            (tmp_path / 'sigterm.log').write_bytes(stdout)
            assert child.returncode == 130
            receipt = load(output / 'receipt.json')
            assert receipt['status'] == 'cancelled' and receipt['model_calls'] == 0
            assert receipt['fresh_completed_transcription'] is False
            assert [r['path'] for r in state['requests']] == [worker.COUNT_PATH]
            assert_preserved(prepared, output)
        finally:
            release.set()
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)


def test_verified_live_probe_prompt_schema_literal():
    tree = ast.parse((worker.APP / 'tools/teaching_stage15/run_markdown_probe.py').read_text(encoding='utf-8'))
    constants = {}
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and statement.targets[0].id in ('BOX', 'SCHEMA', 'PROMPT'):
            expression = ast.Expression(statement.value)
            constants[statement.targets[0].id] = eval(compile(expression, '<verified-probe-constants>', 'eval'), {'__builtins__': {}}, constants)
    assert worker.PROMPT == constants['PROMPT']
    assert worker.SCHEMA == constants['SCHEMA']


def test_fresh_two_page_success(prepared, tmp_path):
    initial = {p.relative_to(prepared).as_posix(): sha256(p) for p in prepared.rglob('*') if p.is_file()}
    with fake_http() as (url, state):
        receipt = run(prepared, tmp_path, url)
    assert receipt['status'] == 'complete'
    assert receipt['model_calls'] == receipt['input_count_calls'] == 2
    assert receipt['visual_pages_completed'] == receipt['recognized_text_pages'] == 2
    assert receipt['fresh_completed_transcription'] and not receipt['imported_evidence']
    assert receipt['visual_transcription_complete'] and receipt['visual_failed_pages'] == []
    assert [r['path'] for r in state['requests']] == [worker.COUNT_PATH, worker.COMPLETION_PATH] * 2
    for index in range(2):
        count, generation = state['requests'][index * 2:index * 2 + 2]
        assert count['raw'] == generation['raw']
        payload = generation['payload']
        assert payload['cache_prompt'] is False and payload['stream'] is False
        assert payload['temperature'] == 0 and payload['chat_template_kwargs'] == {'enable_thinking': False}
        assert payload['max_tokens'] + receipt['page_timings'][index]['input_tokens'] <= 8192
        image_url = payload['messages'][1]['content'][1]['image_url']['url']
        assert base64.b64decode(image_url.split(',')[1]) == (prepared / ('pages/p%04d.png' % (index + 1))).read_bytes()
        folder = tmp_path / ('output/raw/stage15-worker/p%04d' % (index + 1))
        assert (folder / 'completion-response.bin').read_bytes() == state['responses'][index * 2 + 1]
        assert receipt['page_timings'][index]['usage'] == completion()['usage']
        assert load(folder / 'completion-http.json')['response_complete']
    assert all(not row['model_processed'] and row['model_calls'] == 0 for row in receipt['page_timings'][2:])
    assert_preserved(prepared, tmp_path / 'output')
    assert load(tmp_path / 'output/stage15-receipt.json')['model_calls'] == 0
    result = load(tmp_path / 'output/manifest.json')
    assert 'native+live-page-markdown' in result['parser']['recipe']
    assert 'import' not in result['parser']['recipe']
    assert result['pages'][0]['blocks'][2]['text'] == BODY + 'Page 1\n'
    assert result['pages'][0]['blocks'][2]['quality'] == 'extracted'
    assert {p.relative_to(prepared).as_posix(): sha256(p) for p in prepared.rglob('*') if p.is_file()} == initial


@pytest.mark.parametrize('failed', [(500, b'{"error":"synthetic failure"}'), completion(finish='length'),
    completion(content='bad JSON'), completion(content=json.dumps({'body_text': '', 'images': [], 'uncertainty': 'Unreadable fixture'})),
    completion(body='')],
    ids=['http500', 'length', 'bad-content-json', 'unreadable', 'image-descriptions-only'])
def test_one_page_failure_other_success(prepared, tmp_path, failed):
    with fake_http(replies=[failed, completion()]) as (url, state):
        receipt = run(prepared, tmp_path, url)
    assert len(state['requests']) == 4 and receipt['model_calls'] == 2
    assert receipt['visual_pages_completed'] == 1 and receipt['visual_pages_failed'] == 1
    assert not receipt['fresh_completed_transcription']
    assert receipt['completion_kind'] == 'representation_complete'
    assert not receipt['visual_transcription_complete'] and receipt['visual_failed_pages'] == [1]
    result = load(tmp_path / 'output/manifest.json')
    assert result['pages'][0]['blocks'] == load(prepared / 'manifest.json')['pages'][0]['blocks']
    assert result['pages'][0]['status'] == 'needs_review'
    assert any('visual transcription incomplete' in issue for issue in result['pages'][0]['issues'])
    assert any('visual transcription incomplete' in warning for warning in result['warnings'])
    assert_preserved(prepared, tmp_path / 'output')


def test_all_failed_retains_source_only(prepared, tmp_path):
    with fake_http(replies=[completion(finish='length'), completion(content='broken')]) as (url, state):
        receipt = run(prepared, tmp_path, url)
    assert receipt['model_calls'] == 2 and receipt['visual_pages_completed'] == receipt['recognized_text_pages'] == 0
    assert receipt['representation_complete'] and receipt['status'] == 'complete'
    assert not receipt['visual_transcription_complete'] and receipt['visual_failed_pages'] == [1, 2]
    assert not receipt['fresh_completed_transcription']
    assert not (tmp_path / 'output/stage15-receipt.json').exists()
    assert_preserved(prepared, tmp_path / 'output')


@pytest.mark.parametrize('count', [(404, b'counter not implemented'), {'input_tokens': True}, {'tokens': 700},
                                 {'input_tokens': 4097}], ids=['unavailable', 'bool', 'not-full-counter', 'ctx-overflow'])
def test_counter_failure_never_generates(prepared, tmp_path, count):
    with fake_http(count=count) as (url, state):
        receipt = run(prepared, tmp_path, url)
    assert len(state['requests']) == 2 and all(r['path'] == worker.COUNT_PATH for r in state['requests'])
    assert receipt['model_calls'] == receipt['visual_pages_completed'] == 0
    assert receipt['input_count_calls'] == 2
    assert_preserved(prepared, tmp_path / 'output')


def test_default_all_pages_exact_once_context_boundary(prepared, tmp_path):
    answers = [completion() for _ in range(3)]
    for answer in answers:
        answer['usage'].update(prompt_tokens=4096, total_tokens=4216)
    with fake_http(count={'input_tokens': 4096}, replies=answers) as (url, state):
        receipt = worker.run_worker(prepared, tmp_path / 'output', vlm_url=url, model='fixture')
    assert receipt['selected_pages'] == [1, 2, 3]
    assert receipt['model_calls'] == receipt['visual_pages_completed'] == 3
    assert len(state['requests']) == 6
    assert receipt['visual_transcription_complete']
    assert_preserved(prepared, tmp_path / 'output', (1, 2, 3))


def test_usage_mismatch_not_promoted(prepared, tmp_path):
    wrong = completion()
    wrong['usage']['prompt_tokens'] = 701
    with fake_http(replies=[wrong, completion()]) as (url, state):
        receipt = run(prepared, tmp_path, url)
    assert receipt['model_calls'] == 2 and receipt['visual_failed_pages'] == [1]
    assert receipt['page_timings'][0]['usage']['prompt_tokens'] == 701
    assert receipt['page_timings'][0]['input_tokens'] == 700
    assert 'differs' in receipt['page_timings'][0]['error']
    assert not receipt['page_timings'][0]['model_processed']
    assert_preserved(prepared, tmp_path / 'output')


def test_cli_deadline_nonzero_propagated(prepared, tmp_path):
    with fake_http(delay=.4) as (url, state):
        proc = subprocess.run([sys.executable, str(Path(worker.__file__)), '--prepared-dir', str(prepared),
            '--output', str(tmp_path / 'output'), '--vlm-url', url, '--model', 'fixture', '--pages', '1,2',
            '--deadline-seconds', '.1'], cwd=tmp_path, capture_output=True, text=True, encoding='utf-8', timeout=20)
    (tmp_path / 'cli.stdout.log').write_text(proc.stdout, encoding='utf-8')
    (tmp_path / 'cli.stderr.log').write_text(proc.stderr, encoding='utf-8')
    assert proc.returncode == 2
    final = json.loads(proc.stdout)
    assert final['status'] == 'failed' and final['error_type'] == 'TimeoutError'
    if (tmp_path / 'output/receipt.json').exists():
        receipt = load(tmp_path / 'output/receipt.json')
        assert receipt['model_calls'] == 0 and not receipt['visual_transcription_complete']
    assert all(row['path'] == worker.COUNT_PATH for row in state['requests'])


def test_explicit_no_pages_zero_requests(prepared, tmp_path):
    with fake_http() as (url, state):
        receipt = worker.run_worker(prepared, tmp_path / 'output', vlm_url=url, model='fixture', pages='')
    assert state['requests'] == [] and receipt['model_calls'] == receipt['input_count_calls'] == 0
    assert receipt['completion_kind'] == 'representation_complete' and not receipt['fresh_completed_transcription']
    assert_preserved(prepared, tmp_path / 'output', ())


@pytest.mark.parametrize('pages', ['0', '4', '1,1', '01', '1, 2', '-1', '1,'],
                         ids=['zero', 'outside', 'duplicate', 'zero-prefix', 'spaces', 'negative', 'trailing-comma'])
def test_invalid_page_numbers_before_request(prepared, tmp_path, pages):
    with fake_http() as (url, state):
        with pytest.raises(ValueError):
            worker.run_worker(prepared, tmp_path / 'output', vlm_url=url, model='fixture', pages=pages)
    assert not state['requests'] and not (tmp_path / 'output').exists()


def test_source_and_raster_binding_reject(prepared, tmp_path):
    with fake_http() as (url, state):
        wrong_source = tmp_path / 'wrong.pdf'
        wrong_source.write_bytes(b'wrong original')
        with pytest.raises(ValueError, match='source SHA'):
            worker.run_worker(prepared, tmp_path / 'output', vlm_url=url, model='fixture', source=wrong_source)
        native = load(prepared / 'receipt.json')
        native['page_timings'][0]['raster_sha256'] = '0' * 64
        dump(prepared / 'receipt.json', native)
        with pytest.raises(ValueError, match='raster SHA'):
            worker.run_worker(prepared, tmp_path / 'output', vlm_url=url, model='fixture')
    assert not state['requests'] and not (tmp_path / 'output').exists()


def test_receipt_wrong_source_refuses_archived_import(prepared, tmp_path):
    native = load(prepared / 'receipt.json')
    native['source_sha256'] = '0' * 64
    dump(prepared / 'receipt.json', native)
    with fake_http() as (url, state):
        with pytest.raises(ValueError, match='binding invalid'):
            run(prepared, tmp_path, url)
    assert not state['requests']


def test_output_overwrite_and_rotation_refused(prepared, tmp_path):
    out = tmp_path / 'output'
    out.mkdir()
    (out / 'sentinel').write_bytes(b'preserve')
    with fake_http() as (url, state):
        with pytest.raises(ValueError, match='overwrite'):
            run(prepared, tmp_path, url)
        assert (out / 'sentinel').read_bytes() == b'preserve'
        manifest = load(prepared / 'manifest.json')
        manifest['pages'][0]['rotation'] = 90
        dump(prepared / 'manifest.json', manifest)
        with pytest.raises(ValueError, match='rotation unsupported'):
            worker.run_worker(prepared, tmp_path / 'rotated-output', vlm_url=url, model='fixture', pages='1')
    assert not state['requests']


def test_big_image_skipped_not_resized(prepared, tmp_path):
    raster = prepared / 'pages/p0001.png'
    original_pixels = Image.open(raster).tobytes()
    with raster.open('ab') as stream:
        stream.write(b'\x00' * worker.MAX_IMAGE_BYTES)
    native = load(prepared / 'receipt.json')
    native['page_timings'][0]['raster_sha256'] = sha256(raster)
    dump(prepared / 'receipt.json', native)
    with fake_http() as (url, state):
        receipt = run(prepared, tmp_path, url)
    assert receipt['model_calls'] == 1 and len(state['requests']) == 2
    assert receipt['page_timings'][0]['model_calls'] == receipt['page_timings'][0]['input_count_calls'] == 0
    assert '4 MiB' in receipt['page_timings'][0]['error']
    assert Image.open(tmp_path / 'output/pages/p0001.png').tobytes() == original_pixels
    assert_preserved(prepared, tmp_path / 'output')


@pytest.mark.parametrize('fmt,ext', [('JPEG','jpg'), ('WEBP','webp')], ids=['jpeg','webp'])
def test_non_png_prepared_raster_explicit_no_transcode(prepared, tmp_path, fmt, ext):
    manifest = load(prepared / 'manifest.json')
    raster = prepared / ('pages/p0001.' + ext)
    with Image.new('RGB', (100, 80), 'red') as image:
        image.save(raster, format=fmt)
    manifest['pages'][0]['image'] = raster.relative_to(prepared).as_posix()
    dump(prepared / 'manifest.json', manifest)
    native = load(prepared / 'receipt.json')
    native['page_timings'][0]['raster_sha256'] = sha256(raster)
    dump(prepared / 'receipt.json', native)
    with fake_http() as (url, state):
        receipt = run(prepared, tmp_path, url)
    assert len(state['requests']) == 2 and receipt['page_timings'][0]['input_count_calls'] == 0
    assert 'not transcoded' in receipt['page_timings'][0]['error']
    assert_preserved(prepared, tmp_path / 'output')


def test_bounded_response_prefix_retained(prepared, tmp_path, monkeypatch):
    monkeypatch.setattr(worker, 'MAX_RESPONSE_BYTES', 256)
    with fake_http(replies=[(200, b'x' * 2000), (200, b'x' * 2000)]) as (url, state):
        receipt = run(prepared, tmp_path, url)
    assert receipt['model_calls'] == 2 and receipt['visual_pages_completed'] == 0
    folder = tmp_path / 'output/raw/stage15-worker/p0001'
    assert (folder / 'completion-response.bin').stat().st_size == 257
    assert not load(folder / 'completion-http.json')['response_complete']


def test_deadline_propagates_not_page_failure(prepared, tmp_path, monkeypatch):
    # Expire only after the actual count request. A .1s wall timer can expire
    # during WSL filesystem preflight, before any output/HTTP phase exists.
    budgets = []
    class ObservedBudget(worker.Budget):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            budgets.append(self)
    monkeypatch.setattr(worker, 'Budget', ObservedBudget)
    def expire_after_count():
        budgets[0].until = time.monotonic() - 1
    with fake_http(after_count=expire_after_count) as (url, state):
        with pytest.raises(TimeoutError):
            run(prepared, tmp_path, url, deadline_seconds=30)
    receipt = load(tmp_path / 'output/receipt.json')
    assert receipt['status'] == 'failed' and receipt['error_type'] == 'TimeoutError'
    assert receipt['model_calls'] == 0 and len(state['requests']) == 1
    assert not receipt['fresh_completed_transcription']
    assert_preserved(prepared, tmp_path / 'output')


def test_cancel_propagates_no_successor_request(prepared, tmp_path):
    cancelled = threading.Event()
    with fake_http(after_count=cancelled.set) as (url, state):
        with pytest.raises(worker.WorkerCancelled):
            run(prepared, tmp_path, url, cancel=cancelled.is_set)
    receipt = load(tmp_path / 'output/receipt.json')
    assert receipt['status'] == 'cancelled' and receipt['model_calls'] == 0
    assert len(state['requests']) == 1
    assert_preserved(prepared, tmp_path / 'output')


def test_resource_error_aborts_no_next_page(prepared, tmp_path):
    with fake_http(replies=[(503, b'{"error":"synthetic resource unavailable"}')]) as (url, state):
        with pytest.raises(worker.ResourceFailure):
            run(prepared, tmp_path, url)
    assert len(state['requests']) == 2
    receipt = load(tmp_path / 'output/receipt.json')
    assert receipt['status'] == 'failed' and receipt['model_calls'] == 1
    assert not receipt['fresh_completed_transcription']
    assert_preserved(prepared, tmp_path / 'output')


def test_release_tools_only_without_backend_import(prepared, tmp_path):
    import shutil
    release = tmp_path / 'release-tools-only'
    for name in ('document_stage12', 'material_stage13', 'material_stage15'):
        target = release / 'tools' / name
        target.mkdir(parents=True)
        for source in (worker.APP / 'tools' / name).glob('*.py'):
            shutil.copyfile(source, target / source.name)
    assert not (release / 'backend').exists()
    launcher = release / 'block_backend_import.py'
    launcher.write_text("import sys,runpy\nclass NoBackend:\n    def find_spec(self,name,*args):\n        if name.split('.')[0] in ('backend','fastapi'):\n            raise AssertionError('Production worker imported '+name)\nsys.meta_path.insert(0,NoBackend())\nrunpy.run_path(sys.argv[0].replace('block_backend_import.py','tools/material_stage15/page_worker.py'),run_name='__main__')\n", encoding='utf-8')
    with fake_http() as (url, state):
        proc = subprocess.run([sys.executable, str(launcher), '--prepared-dir', str(prepared),
            '--output', str(tmp_path / 'output'), '--vlm-url', url, '--model', 'fixture', '--pages', '1,2',
            '--deadline-seconds', '20'], cwd=tmp_path, capture_output=True, text=True, encoding='utf-8', timeout=30)
    (tmp_path / 'release-cli.stdout.log').write_text(proc.stdout, encoding='utf-8')
    (tmp_path / 'release-cli.stderr.log').write_text(proc.stderr, encoding='utf-8')
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert json.loads(proc.stdout)['model_calls'] == 2
    assert len(state['requests']) == 4
    assert_preserved(prepared, tmp_path / 'output')


def test_direct_script_cli_fresh_subprocess(prepared, tmp_path):
    with fake_http() as (url, state):
        proc = subprocess.run([sys.executable, str(Path(worker.__file__)), '--prepared-dir', str(prepared),
            '--output', str(tmp_path / 'output'), '--vlm-url', url, '--model', 'fixture', '--pages', '1,2',
            '--deadline-seconds', '20', '--ctx-size', '8192', '--source', str(prepared / 'raw/source.pdf')],
            cwd=tmp_path, capture_output=True, text=True, encoding='utf-8', timeout=30)
    (tmp_path / 'cli.stdout.log').write_text(proc.stdout, encoding='utf-8')
    (tmp_path / 'cli.stderr.log').write_text(proc.stderr, encoding='utf-8')
    assert proc.returncode == 0, proc.stderr + proc.stdout
    receipt = json.loads(proc.stdout)
    assert receipt['model_calls'] == 2 and receipt['fresh_completed_transcription']
    assert len(state['requests']) == 4
    assert_preserved(prepared, tmp_path / 'output')
