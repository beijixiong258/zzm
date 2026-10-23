"""Stage10 lower-level ASGI bounds, throttle, trust and revocation regressions."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import threading

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.aicademiya import auth
from backend.aicademiya.auth import PasswordVerifier, RateLimiter
from backend.aicademiya.config import SecurityConfig
from backend.aicademiya.http_security import AUTH_LIMIT, HttpSecurityMiddleware, JSON_LIMIT, UPLOAD_LIMIT, MATERIAL_UPLOAD_LIMIT
from backend.aicademiya.main import COOKIE_NAME
from .conftest import expect


def test_rate_window_expires_and_capacity_cannot_evict_active_limits():
    clock = [1000.0]
    limiter = RateLimiter(clock=lambda: clock[0], capacity=2)
    limiter.check('test', 'first', 1, 60)
    limiter.check('test', 'second', 1, 60)
    with pytest.raises(Exception) as error:
        limiter.check('test', 'third', 1, 60)
    assert error.value.status_code == 429
    with pytest.raises(Exception) as blocked:
        limiter.check('test', 'first', 1, 60)
    assert blocked.value.headers == {'Retry-After': '60'}
    clock[0] += 60
    limiter.check('test', 'first', 1, 60)
    assert all(isinstance(key[1], bytes) and len(key[1]) == 16 for key in limiter.buckets)
    clock[0] += 301
    limiter.check('test', 'third', 1, 60)
    assert len(limiter.buckets) == 1


def test_limiter_thread_safety_exact_admission_count():
    limiter = RateLimiter()
    def attempt(_):
        try:
            limiter.check('shared', 'identity', 10, 300)
            return True
        except Exception as exc:
            assert exc.status_code == 429
            return False
    with ThreadPoolExecutor(max_workers=16) as pool:
        assert sum(pool.map(attempt, range(64))) == 10


@pytest.mark.parametrize('setting,value', [
    ('AICADEMIYA_ALLOWED_ORIGINS', '*'),
    ('AICADEMIYA_ALLOWED_ORIGINS', 'https://*.example.invalid'),
    ('AICADEMIYA_ALLOWED_ORIGINS', 'https://user:password@example.invalid'),
    ('AICADEMIYA_ALLOWED_ORIGINS', 'https://example.invalid/path'),
    ('AICADEMIYA_ALLOWED_HOSTS', '*'),
    ('AICADEMIYA_ALLOWED_HOSTS', '*.example.invalid'),
    ('AICADEMIYA_ALLOWED_HOSTS', 'example.invalid/path'),
])
def test_configuration_rejects_unsafe_wildcard_or_malformed_values(monkeypatch, setting, value):
    monkeypatch.setenv(setting, value)
    with pytest.raises(ValueError):
        SecurityConfig.from_environment()


def test_password_verification_unknown_active_archived_each_do_one_hash(monkeypatch):
    verifier = PasswordVerifier()
    calls = []
    monkeypatch.setattr(auth, 'password_matches', lambda password, encoded: calls.append((password, encoded)) or True)
    assert verifier.matches('synthetic-password1', None) is False
    assert verifier.matches('synthetic-password1', {'password_hash': 'active-hash', 'archived_at': None}) is True
    assert verifier.matches('synthetic-password1', {'password_hash': 'archived-hash', 'archived_at': 'synthetic-date'}) is False
    assert calls == [('synthetic-password1', verifier.dummy), ('synthetic-password1', 'active-hash'), ('synthetic-password1', 'archived-hash')]


async def raw_asgi_request(*, path, body_parts, headers, content_type='application/json'):
    entered, sent = [], []
    config = SecurityConfig(frozenset(), frozenset({'testserver'}), False)
    async def downstream(scope, receive, send):
        entered.append(True)
        await send({'type': 'http.response.start', 'status': 204, 'headers': []})
        await send({'type': 'http.response.body', 'body': b''})
    middleware = HttpSecurityMiddleware(downstream, config=config, limiter=RateLimiter())
    remaining = iter([{'type': 'http.request', 'body': part, 'more_body': index < len(body_parts) - 1}
                      for index, part in enumerate(body_parts)])
    async def receive():
        return next(remaining, {'type': 'http.disconnect'})
    async def send(message):
        sent.append(message)
    scope = {'type': 'http', 'method': 'POST', 'path': path, 'scheme': 'http',
             'headers': [(b'host', b'testserver'), (b'content-type', content_type.encode()), *headers],
             'client': ('192.0.2.10', 12345), 'server': ('testserver', 80), 'query_string': b''}
    await middleware(scope, receive, send)
    return entered, sent


@pytest.mark.parametrize('length_headers', [[], [(b'content-length', b'1')]], ids=['chunked-no-length', 'dishonest-length'])
def test_chunked_or_dishonest_auth_body_rejected_before_route(length_headers):
    entered, sent = asyncio.run(raw_asgi_request(path='/api/auth/login', body_parts=[b'x' * AUTH_LIMIT, b'x'], headers=length_headers))
    assert not entered and sent[0]['status'] == 413
    assert (b'cache-control', b'private, no-store') in sent[0]['headers']


@pytest.mark.parametrize('headers', [
    [(b'content-length', b'-1')], [(b'content-length', b'x')],
    [(b'content-length', b'1'), (b'content-length', b'2')],
    [(b'content-length', b'9' * 5000)],
    [(b'host', b'attacker.invalid')],
    [(b'origin', b'http://testserver'), (b'origin', b'http://attacker.invalid')],
], ids=['negative', 'nonnumeric', 'duplicate-length', 'huge-digits', 'duplicate-host', 'duplicate-origin'])
def test_malformed_or_duplicate_security_headers_rejected(headers):
    entered, sent = asyncio.run(raw_asgi_request(path='/api/auth/login', body_parts=[b'{}'], headers=headers))
    assert not entered and sent[0]['status'] in (400, 403)


@pytest.mark.parametrize('path,content_type,limit', [
    ('/api/sessions/s4/answers/q1', 'application/json', JSON_LIMIT),
    ('/api/sessions/s4/materials', 'multipart/form-data', MATERIAL_UPLOAD_LIMIT),
    ('/api/auth/avatar', 'multipart/form-data', UPLOAD_LIMIT),
], ids=['json', 'full-material-multipart', 'other-multipart'])
def test_general_api_body_limits_apply_before_route(path, content_type, limit):
    entered, sent = asyncio.run(raw_asgi_request(path=path, body_parts=[b'x'], headers=[(b'content-length', str(limit + 1).encode())], content_type=content_type))
    assert not entered and sent[0]['status'] == 413


def test_login_account_throttle_uses_real_distinct_asgi_peers_not_headers(app):
    with TestClient(app):
        async def scenario():
            for index in range(11):
                transport = httpx.ASGITransport(app=app, client=(f'192.0.2.{index + 1}', 12345))
                async with httpx.AsyncClient(transport=transport, base_url='http://testserver') as client:
                    response = await client.post('/api/auth/login', json={'email': 'same-account@example.invalid', 'password': 'synthetic-password1'})
                    assert response.status_code == (401 if index < 10 else 429)
        asyncio.run(scenario())


def test_revoked_session_cannot_change_password_after_dependency_read(app, teacher, monkeypatch):
    invite = expect(teacher.get('/api/courses'))[0]['join_code']
    with TestClient(app) as client:
        user = expect(client.post('/api/auth/register', json={'name': 'Synthetic', 'email': 'revocation-stage10@example.invalid', 'password': 'Synthetic-password1', 'join_code': invite}))['user']
        started = threading.Event()
        original = app.state.database.connect
        class ConnectionProxy:
            def __init__(self, conn):
                self.conn = conn
            def __getattr__(self, name):
                return getattr(self.conn, name)
            def execute(self, sql, *args):
                if sql == 'BEGIN IMMEDIATE':
                    started.set()
                return self.conn.execute(sql, *args)
        @contextmanager
        def observed_connect():
            with original() as conn:
                yield ConnectionProxy(conn)
        monkeypatch.setattr(app.state.database, 'connect', observed_connect)
        with original() as revoker, ThreadPoolExecutor(max_workers=1) as pool:
            revoker.execute('BEGIN IMMEDIATE')
            before = tuple(revoker.execute('SELECT * FROM users WHERE id=?', (user['id'],)).fetchone())
            revoker.execute('DELETE FROM auth_sessions WHERE user_id=?', (user['id'],))
            future = pool.submit(client.post, '/api/auth/change-password', json={'current_password': 'Synthetic-password1', 'new_password': 'Synthetic-new-password2'})
            assert started.wait(2) and not future.done()
            revoker.commit()
            response = future.result(timeout=5)
        assert response.status_code == 401 and 'set-cookie' not in response.headers
        with original() as conn:
            assert tuple(conn.execute('SELECT * FROM users WHERE id=?', (user['id'],)).fetchone()) == before
            assert not conn.execute('SELECT 1 FROM auth_sessions WHERE user_id=?', (user['id'],)).fetchone()


def test_unexpected_error_is_generic_private_and_security_headers_retained(app):
    @app.get('/api/stage10-synthetic-error')
    def fail():
        raise RuntimeError('SYNTHETIC_PRIVATE_PATH_AND_PASSWORD')
    # The SPA catch-all is already registered; place this fixture route first.
    app.router.routes.insert(0, app.router.routes.pop())
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get('/api/stage10-synthetic-error')
        assert response.status_code == 500 and 'SYNTHETIC_PRIVATE' not in response.text
        assert response.headers['cache-control'] == 'private, no-store'
        assert response.headers['x-content-type-options'] == 'nosniff'
        assert response.headers['content-security-policy'] == "frame-ancestors 'self'"


def test_json_unicode_password_auth_limit_preserves_maximum_policy(app, teacher):
    invite = expect(teacher.get('/api/courses'))[0]['join_code']
    password = 'Letter1' + '界' * (512 - len('Letter1'))
    with TestClient(app) as client:
        expect(client.post('/api/auth/register', json={'name': '界' * 100, 'email': 'unicode-stage10@example.invalid', 'password': password, 'join_code': invite}))
        expect(client.post('/api/auth/login', json={'email': 'unicode-stage10@example.invalid', 'password': password}))
