"""Owned Stage16 HTTP fixture: isolated SQLite + localhost GET /v1/models only."""
from __future__ import annotations
import argparse
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def prepare(folder: Path):
    from docx import Document
    seed = folder / 'seed'
    (seed / 'materials').mkdir(parents=True)
    (seed / 'materials' / 'reading.txt').write_text('Synthetic shared historical reading.\n', encoding='utf-8')
    q = {'id': 's16-q', 'group_id': 'core', 'ordinal': 1, 'type': 'open_response',
         'prompt': 'Explain the synthetic fixture.', 'options': [], 'answer_slots': 1,
         'images': [], 'source_label': 'Synthetic fixture', 'hint': 'Use evidence.'}
    sessions = []
    for sid, number, title in [('s16-session', 1, 'Synthetic Stage16 session'), ('s16-other', 2, 'Synthetic shared session')]:
        sessions.append({'id': sid, 'course_id': 's16-course', 'number': number, 'title': title,
                         'subtitle': 'Synthetic only: no real teaching account or course data.', 'status': 'published',
                         'estimated_minutes': 30, 'learning_objectives': ['Verify real browser operations'],
                         'instructions': 'Synthetic instructions.', 'reference_policy': 'after_attempt',
                         'teaching_language': 'en', 'groups': [{'id': 'core', 'title': 'Core', 'kind': 'core'}],
                         'questions': [{**q, 'id': 's16-q' if sid == 's16-session' else 's16-other-q'}],
                         'reference_answers': {}, 'materials': ([{'id': 's16-shared', 'title': 'Synthetic shared reading',
                         'kind': 'reading', 'visibility': 'student', 'source_label': 'Synthetic only', 'status': 'ready',
                         'excerpt': 'Synthetic shared historical reading.', 'file_path': 'materials/reading.txt'}]
                         if sid == 's16-session' else [])})
    (seed / 'catalog.json').write_text(json.dumps({'schema_version': 1, 'course': {'id': 's16-course',
        'code': 'TEST16', 'title': 'Synthetic Stage16 course', 'description': 'No real classroom content.'},
        'sessions': sessions}), encoding='utf-8')
    files = folder / 'inputs' / 'Stage16Folder'
    (files / 'nested').mkdir(parents=True)
    d = Document()
    for text in ['Synthetic worksheet', '1. Name the source colour.', '2. State its identifier.']:
        d.add_paragraph(text)
    d.save(files / 'worksheet.docx')
    (files / 'nested' / 'key.txt').write_text('Synthetic supplied key\n1. violet\n2. fixture-16\n', encoding='utf-8')
    (files / 'nested' / 'reading.txt').write_text(('Synthetic public reading: examples are fixture data.\n' * 11000), encoding='utf-8')
    (files / 'remove-me.txt').write_text('This selected file is removed before upload.\n', encoding='utf-8')
    return seed / 'catalog.json', files


class ModelFixture:
    def __init__(self, port):
        self.port, self.server, self.thread = port, None, None
        self.requests, self.blocked = [], []

    def start(self):
        if self.server:
            return
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                owner.requests.append({'method': 'GET', 'path': self.path, 'at': time.time()})
                data = json.dumps({'object': 'list', 'data': [{'id': 'stage16-protocol-fixture', 'object': 'model'}]}).encode()
                self.send_response(200 if self.path == '/v1/models' else 404)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            def do_POST(self):
                owner.blocked.append({'method': 'POST', 'path': self.path, 'at': time.time()})
                self.send_error(405, 'Protocol fixture has no generation')
        class Server(ThreadingHTTPServer):
            allow_reuse_address = True
        self.server = Server(('127.0.0.1', self.port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=3)
            self.server = None


def serve(folder: Path, port: int, model_port: int):
    import httpx
    import uvicorn
    from backend.aicademiya.main import create_app
    fixture = ModelFixture(model_port)
    fixture.start()
    class LocalGetOnly(httpx.BaseTransport):
        def __init__(self):
            self.delegate = httpx.HTTPTransport()
        def handle_request(self, request):
            if request.url.host != '127.0.0.1' or request.url.port != model_port or request.method != 'GET' or request.url.path != '/v1/models':
                fixture.blocked.append({'method': request.method, 'path': request.url.path, 'at': time.time()})
                raise httpx.ConnectError('QA transport blocks all non-fixture requests', request=request)
            return self.delegate.handle_request(request)
        def close(self):
            self.delegate.close()
    app = create_app(data_dir=folder / 'data', catalog_path=folder / 'seed' / 'catalog.json',
                     demo_enabled=True, frontend_dir=folder / 'no-dist', ai_transport=LocalGetOnly(),
                     document_worker_command=[])
    delay = {'milliseconds': 0}
    @app.middleware('http')
    async def connection_delay(request, call_next):
        if request.url.path == '/api/ai/connection' and delay['milliseconds']:
            await asyncio.sleep(delay['milliseconds'] / 1000)
        return await call_next(request)
    @app.get('/__qa/metrics')
    def metrics():
        return {'model_protocol_requests': fixture.requests, 'blocked_model_requests': fixture.blocked,
                'fixture_listening': fixture.server is not None, 'connection_delay_ms': delay['milliseconds']}
    @app.post('/__qa/model/{state}')
    def model_state(state: str):
        if state == 'off':
            fixture.close()
        elif state == 'on':
            fixture.start()
        return {'fixture_listening': fixture.server is not None}
    @app.post('/__qa/connection-delay/{milliseconds}')
    def connection_delay_control(milliseconds: int):
        delay['milliseconds'] = max(0, min(milliseconds, 10000))
        return delay
    # Product's SPA GET catch-all precedes dynamically appended fixture routes.
    qa_routes = [r for r in app.router.routes if getattr(r, 'path', '').startswith('/__qa/')]
    app.router.routes = qa_routes + [r for r in app.router.routes if r not in qa_routes]
    try:
        uvicorn.run(app, host='127.0.0.1', port=port, log_level='warning')
    finally:
        fixture.close()
        (folder / 'fixture-final.json').write_text(json.dumps(metrics(), indent=2), encoding='utf-8')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--folder', required=True)
    p.add_argument('--port', type=int, required=True)
    p.add_argument('--model-port', type=int, required=True)
    args = p.parse_args()
    f = Path(args.folder).resolve()
    assert f.is_relative_to(ROOT / 'artifacts' / 'stage16' / 'browser')
    serve(f, args.port, args.model_port)
