"""Real isolated HTTP + SQLite/restart security acceptance, no provider calls."""
from contextlib import contextmanager
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx

from backend.aicademiya.main import create_app

PASSWORD = 'Synthetic-stage10-password1'
ROOT = Path(__file__).resolve().parents[2]


@contextmanager
def isolated_server(data_dir, catalog, dist):
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    # No secrets in argv: all accounts/passwords were created in synthetic SQLite.
    code = ('import sys,uvicorn; from backend.aicademiya.main import create_app; '
            'app=create_app(data_dir=sys.argv[1],catalog_path=sys.argv[2],frontend_dir=sys.argv[3],demo_enabled=True); '
            'uvicorn.run(app,host="127.0.0.1",port=int(sys.argv[4]),proxy_headers=False,log_level="warning")')
    env = dict(os.environ, AICADEMIYA_DATA_DIR=str(data_dir), AICADEMIYA_AI_MODE='demo', AICADEMIYA_DEMO_ENABLED='true',
               AICADEMIYA_ALLOWED_ORIGINS='', AICADEMIYA_ALLOWED_HOSTS='', AICADEMIYA_COOKIE_SECURE='false',
               AICADEMIYA_WEB_SEARCH_ENABLED='false', AICADEMIYA_AI_API_KEY='', TAVILY_API_KEY='')
    log = data_dir.parent / ('http-' + str(port) + '.log')
    with log.open('wb') as output:
        process = subprocess.Popen([sys.executable, '-c', code, str(data_dir), str(catalog), str(dist), str(port)], cwd=ROOT, env=env, stdout=output, stderr=output)
        url = f'http://127.0.0.1:{port}'
        try:
            end = time.monotonic() + 15
            with httpx.Client(timeout=1, trust_env=False) as client:
                while time.monotonic() < end and process.poll() is None:
                    try:
                        if client.get(url + '/api/health').status_code == 200:
                            break
                    except httpx.RequestError:
                        pass
                    time.sleep(0.05)
                else:
                    raise AssertionError('Isolated HTTP server failed; retained log: ' + str(log))
            yield url
        finally:
            if os.name == 'nt':
                # Exact owned tree, before the Windows venv launcher exits.
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
            elif process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
            end = time.monotonic() + 3
            while time.monotonic() < end:
                with socket.socket() as check:
                    check.settimeout(0.1)
                    if check.connect_ex(('127.0.0.1', port)) != 0:
                        break
                time.sleep(0.05)
            else:
                raise AssertionError('Owned isolated HTTP listener still open')


def test_real_http_admin_toggle_preservation_and_restart(tmp_path, catalog):
    data, dist = tmp_path / 'http-data', tmp_path / 'http-dist'
    dist.mkdir()
    (dist / 'index.html').write_text('<!doctype html><title>Explicit synthetic HTTP fixture</title>', encoding='utf-8')
    fixture = create_app(data_dir=data, catalog_path=catalog, demo_enabled=True, frontend_dir=dist)
    fixture.state.database.initialize(catalog, True)
    fixture.state.database.create_admin('Synthetic administrator', 'admin-stage10@example.invalid', PASSWORD)
    with fixture.state.database.connect() as conn:
        invite = conn.execute("SELECT join_code FROM courses WHERE id='synthetic-course'").fetchone()[0]
    with isolated_server(data, catalog, dist) as url:
        with httpx.Client(base_url=url, timeout=5, trust_env=False) as admin, httpx.Client(base_url=url, timeout=5, trust_env=False) as learner:
            login = admin.post('/api/auth/login', json={'email': 'admin-stage10@example.invalid', 'password': PASSWORD}, headers={'Origin': url})
            assert login.status_code == 200
            assert 'HttpOnly' in login.headers['set-cookie'] and 'Secure' not in login.headers['set-cookie']
            invalid = admin.put('/api/admin/access-settings', json={'registration_enabled': 'false'})
            assert invalid.status_code == 422 and 'set-cookie' not in invalid.headers
            assert admin.get('/api/admin/access-settings').json() == {'registration_enabled': True}
            registered = learner.post('/api/auth/register', json={'name': 'Synthetic learner', 'email': 'learner-stage10@example.invalid', 'password': PASSWORD, 'join_code': invite})
            assert registered.status_code == 200
            with fixture.state.database.connect() as conn:
                before = {table: [tuple(r) for r in conn.execute(f'SELECT * FROM {table} ORDER BY rowid')]
                          for table in ('users', 'enrollments', 'auth_sessions')}
            assert admin.put('/api/admin/access-settings', json={'registration_enabled': False}).json() == {'registration_enabled': False}
            assert admin.get('/api/admin/access-settings').json() == {'registration_enabled': False}
            assert learner.get('/api/bootstrap').json()['registration_enabled'] is False
            rejected = learner.post('/api/auth/register', json={'name': 'Blocked', 'email': 'blocked-http@example.invalid', 'password': PASSWORD, 'join_code': invite})
            assert rejected.status_code == 403 and 'set-cookie' not in rejected.headers
            assert learner.get('/api/auth/me').status_code == 200
            with fixture.state.database.connect() as conn:
                after = {table: [tuple(r) for r in conn.execute(f'SELECT * FROM {table} ORDER BY rowid')] for table in before}
                assert after == before and conn.execute('PRAGMA user_version').fetchone()[0] == 9
            for path in ('/', '/api/bootstrap', '/api/auth/me'):
                response = learner.get(path)
                assert response.headers['x-content-type-options'] == 'nosniff'
                assert response.headers['content-security-policy'] == "frame-ancestors 'self'"
                assert response.headers['x-frame-options'] == 'SAMEORIGIN'
                assert response.headers['cache-control'] == ('no-cache' if path == '/' else 'private, no-store')
            forged = learner.post('/api/auth/logout', headers={'Host': 'attacker.invalid', 'Origin': 'http://attacker.invalid'})
            assert forged.status_code == 400 and 'set-cookie' not in forged.headers
            missing_origin = learner.post('/api/auth/logout', headers={'Sec-Fetch-Site': 'cross-site'})
            assert missing_origin.status_code == 403 and learner.get('/api/auth/me').status_code == 200
            chunked = learner.post('/api/auth/login', content=iter([b'x' * 8192, b'x' * 8193]), headers={'Content-Type': 'application/json'})
            assert chunked.status_code == 413
            assert admin.get('/openapi.json').json()['info']['version'] == '0.11.0'
    # Actual new OS process, same synthetic DB. Login remains usable while closed.
    with isolated_server(data, catalog, dist) as url:
        with httpx.Client(base_url=url, timeout=5, trust_env=False) as client:
            assert client.get('/api/bootstrap').json()['registration_enabled'] is False
            assert client.post('/api/auth/login', json={'email': 'admin-stage10@example.invalid', 'password': PASSWORD}).status_code == 200
            assert client.get('/api/admin/access-settings').json() == {'registration_enabled': False}
            assert client.put('/api/admin/access-settings', json={'registration_enabled': True}).json() == {'registration_enabled': True}
            assert client.get('/api/admin/access-settings').json() == {'registration_enabled': True}
            assert client.get('/api/bootstrap').json()['registration_enabled'] is True
            assert client.post('/api/auth/login', json={'email': 'learner-stage10@example.invalid', 'password': PASSWORD}).status_code == 200
    with fixture.state.database.connect() as conn:
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert list(conn.execute('PRAGMA foreign_key_check')) == []
