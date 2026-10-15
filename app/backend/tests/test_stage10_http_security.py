"""Stage10 HTTP security regression evidence; synthetic isolated clients only."""
import pytest
from fastapi.testclient import TestClient

from backend.aicademiya.main import COOKIE_NAME, create_app
from .conftest import expect


def test_untrusted_host_cannot_create_its_own_csrf_allowance(app):
    with TestClient(app) as client:
        response = client.post('/api/auth/demo', json={'role': 'student'},
                               headers={'Host': 'attacker.invalid', 'Origin': 'http://attacker.invalid'})
        assert response.status_code == 400
        assert 'set-cookie' not in response.headers


@pytest.mark.parametrize('metadata', [
    {'Sec-Fetch-Site': 'cross-site'}, {'Sec-Fetch-Site': 'same-site'},
    {'Referer': 'https://attacker.invalid/form'}, {'Origin': 'null'},
])
def test_missing_origin_does_not_allow_browser_cross_origin_writes(app, metadata):
    with TestClient(app) as client:
        assert client.post('/api/auth/demo', json={'role': 'student'}, headers=metadata).status_code == 403


def test_missing_origin_nonbrowser_remains_compatible(app):
    with TestClient(app) as client:
        assert client.post('/api/auth/demo', json={'role': 'student'}).status_code == 200
        assert client.post('/api/auth/logout').status_code == 200


def test_api_security_and_private_cache_headers(app):
    with TestClient(app) as client:
        for url in ('/api/health', '/api/bootstrap', '/api/auth/me', '/api/admin/access-settings'):
            response = client.get(url)
            assert response.headers.get('x-content-type-options') == 'nosniff'
            assert response.headers.get('cache-control') == 'private, no-store'
            assert response.headers.get('referrer-policy') == 'same-origin'
            assert response.headers.get('x-frame-options') == 'SAMEORIGIN'


def test_auth_body_is_bounded_before_parsing(app):
    with TestClient(app) as client:
        response = client.post('/api/auth/login', content=b'x' * (16 * 1024 + 1),
                               headers={'content-type': 'application/json'})
        assert response.status_code == 413
        assert 'set-cookie' not in response.headers


def test_auth_validation_does_not_echo_secret_field_names(app):
    with TestClient(app) as client:
        response = client.post('/api/auth/login', json={'SYNTHETIC_PRIVATE_KEY': 'SYNTHETIC_PASSWORD'})
        assert response.status_code == 422
        assert 'SYNTHETIC_PRIVATE_KEY' not in response.text
        assert 'SYNTHETIC_PASSWORD' not in response.text


def test_login_abuse_not_bypassed_by_forwarded_ip_or_host(app):
    with TestClient(app) as client:
        for index in range(30):
            response = client.post('/api/auth/login', json={'email': f'missing-{index}@example.invalid', 'password': 'synthetic-password1'},
                                   headers={'X-Forwarded-For': f'198.51.100.{index + 1}', 'X-Forwarded-Host': f'fake-{index}.invalid'})
            assert response.status_code == 401
        blocked = client.post('/api/auth/login', json={'email': 'new-missing@example.invalid', 'password': 'synthetic-password1'},
                              headers={'X-Forwarded-For': '203.0.113.2', 'Host': '127.0.0.1'})
        assert blocked.status_code == 429
        assert int(blocked.headers['retry-after']) > 0
        assert 'set-cookie' not in blocked.headers


@pytest.mark.parametrize('host', ['192.168.32.55:18773', '127.0.0.1:18773', 'localhost:18773'])
def test_lan_http_compatible_and_cookie_not_forced_secure(app, host):
    with TestClient(app, base_url='http://' + host) as client:
        response = client.post('/api/auth/demo', json={'role': 'student'}, headers={'Origin': 'http://' + host})
        assert response.status_code == 200
        cookie = response.headers['set-cookie']
        assert 'HttpOnly' in cookie and 'SameSite=lax' in cookie and 'Secure' not in cookie


def test_cookie_https_and_explicit_secure_configuration(tmp_path, catalog, monkeypatch):
    monkeypatch.setenv('AICADEMIYA_COOKIE_SECURE', 'true')
    secure_app = create_app(data_dir=tmp_path / 'secure-data', catalog_path=catalog, demo_enabled=True)
    with TestClient(secure_app) as client:
        response = client.post('/api/auth/demo', json={'role': 'student'})
        assert 'Secure' in response.headers['set-cookie']
        assert 'Secure' in client.post('/api/auth/logout').headers['set-cookie']


def test_explicit_public_origin_and_host_configuration(tmp_path, catalog, monkeypatch):
    monkeypatch.setenv('AICADEMIYA_ALLOWED_ORIGINS', 'https://learning.example.invalid')
    public_app = create_app(data_dir=tmp_path / 'public-data', catalog_path=catalog, demo_enabled=True)
    with TestClient(public_app, base_url='https://learning.example.invalid') as client:
        response = client.post('/api/auth/demo', json={'role': 'student'}, headers={'Origin': 'https://learning.example.invalid'})
        assert response.status_code == 200
        assert 'Secure' in response.headers['set-cookie']
        assert client.post('/api/auth/logout', headers={'Origin': 'https://other.example.invalid'}).status_code == 403


def test_forwarded_proto_header_not_trusted_by_app(app):
    with TestClient(app) as client:
        response = client.post('/api/auth/demo', json={'role': 'student'}, headers={'X-Forwarded-Proto': 'https'})
        assert response.status_code == 200 and 'Secure' not in response.headers['set-cookie']


def test_cookie_token_invalid_or_expired_and_logout_revocation(app):
    with TestClient(app) as client:
        expect(client.post('/api/auth/demo', json={'role': 'student'}))
        token = client.cookies.get(COOKIE_NAME)
        expect(client.post('/api/auth/logout'))
        client.cookies.set(COOKIE_NAME, token)
        expect(client.get('/api/auth/me'), 401)
        client.cookies.clear()
        client.cookies.set(COOKIE_NAME, 'x' * 2048)
        expect(client.get('/api/auth/me'), 401)


def test_same_origin_fetch_metadata_and_json_allowed(app):
    with TestClient(app) as client:
        expect(client.post('/api/auth/demo', json={'role': 'student'}, headers={'Sec-Fetch-Site': 'same-origin'}))


def test_urlencoded_auth_not_accepted(app):
    with TestClient(app) as client:
        assert client.post('/api/auth/login', data={'email': 'synthetic@example.invalid', 'password': 'synthetic-password1'}).status_code == 415


def test_account_throttle_across_ip_client_identities(app):
    # The account bucket has no IP/Host component; server restarts intentionally reset it.
    with TestClient(app) as client:
        for _ in range(10):
            assert client.post('/api/auth/login', json={'email': ' Missing@Example.Invalid ', 'password': 'synthetic-password1'}).status_code == 401
        response = client.post('/api/auth/login', json={'email': 'missing@example.invalid', 'password': 'synthetic-password1'})
        assert response.status_code == 429 and 'set-cookie' not in response.headers


def test_api_schema_version_is_retained_for_qa(app):
    with TestClient(app) as client:
        assert client.get('/openapi.json').json()['info']['version'] == '0.11.0'
        assert client.get('/docs').status_code == 200


def test_anonymous_bootstrap_has_only_safe_existing_shape_plus_registration(app):
    with TestClient(app) as client:
        bootstrap = expect(client.get('/api/bootstrap'))
        assert set(bootstrap) == {'app_name', 'demo_enabled', 'default_locale', 'ai', 'registration_enabled'}
        assert bootstrap['registration_enabled'] is True
        assert bootstrap['ai']['base_url'] == ''
        assert 'api_key' not in bootstrap['ai']
