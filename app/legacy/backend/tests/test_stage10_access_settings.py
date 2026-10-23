"""Persistent administrator registration gate; synthetic SQLite/API only."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import threading

import pytest
from fastapi.testclient import TestClient

from backend.aicademiya.access_control import REGISTRATION_KEY
from backend.aicademiya.main import COOKIE_NAME, create_app
from .conftest import expect

URL = '/api/admin/access-settings'
PASSWORD = 'Synthetic-password1'


def registration(invite, email='new-stage10@example.invalid'):
    return {'name': 'Synthetic learner', 'email': email, 'password': PASSWORD, 'join_code': invite}


def snapshot(conn):
    return {table: [tuple(row) for row in conn.execute(f'SELECT * FROM {table} ORDER BY rowid')]
            for table in ('users', 'enrollments', 'auth_sessions')}


def test_default_true_and_get_is_read_only(app, admin):
    with app.state.database.connect() as conn:
        before = snapshot(conn)
        settings = list(conn.execute('SELECT * FROM settings'))
    assert expect(admin.get(URL)) == {'registration_enabled': True}
    assert expect(admin.get('/api/bootstrap'))['registration_enabled'] is True
    with app.state.database.connect() as conn:
        assert snapshot(conn) == before
        assert list(conn.execute('SELECT * FROM settings')) == settings


@pytest.mark.parametrize('role', ['anonymous', 'student', 'teacher'])
def test_only_admin_reads_and_writes(app, role):
    with TestClient(app) as client:
        if role != 'anonymous':
            expect(client.post('/api/auth/demo', json={'role': role}))
        expected = 401 if role == 'anonymous' else 403
        expect(client.get(URL), expected)
        expect(client.put(URL, json={'registration_enabled': False}), expected)
        assert expect(client.get('/api/bootstrap'))['registration_enabled'] is True


@pytest.mark.parametrize('bad', [None, 0, 1, 'true', 'false', [], {}], ids=['null', 'zero', 'one', 'true-string', 'false-string', 'array', 'object'])
def test_put_requires_strict_boolean_and_no_side_effects(app, admin, bad):
    with app.state.database.connect() as conn:
        before = snapshot(conn)
    expect(admin.put(URL, json={'registration_enabled': bad}), 422)
    assert expect(admin.get(URL)) == {'registration_enabled': True}
    with app.state.database.connect() as conn:
        assert snapshot(conn) == before
        assert not conn.execute('SELECT 1 FROM settings WHERE key=?', (REGISTRATION_KEY,)).fetchone()


@pytest.mark.parametrize('payload', [{}, {'registration_enabled': False, 'role': 'admin'}, {'registration_enabled': True, 'SYNTHETIC_SECRET': 'private'}])
def test_put_missing_or_extra_fields_rejected(admin, payload):
    response = admin.put(URL, json=payload)
    expect(response, 422)
    assert 'SYNTHETIC_SECRET' not in response.text
    assert expect(admin.get(URL)) == {'registration_enabled': True}


def test_close_blocks_register_without_user_enrollment_or_cookie_and_login_unchanged(app, admin, teacher):
    invite = expect(teacher.get('/api/courses'))[0]['join_code']
    with TestClient(app) as student, TestClient(app) as new:
        existing = expect(student.post('/api/auth/register', json=registration(invite, 'existing-stage10@example.invalid')))['user']
        with app.state.database.connect() as conn:
            before = snapshot(conn)
            secret = conn.execute("SELECT value FROM meta WHERE key='kv_scope_secret'").fetchone()
        assert expect(admin.put(URL, json={'registration_enabled': False})) == {'registration_enabled': False}
        assert expect(admin.get(URL)) == {'registration_enabled': False}
        assert expect(new.get('/api/bootstrap'))['registration_enabled'] is False
        rejected = new.post('/api/auth/register', json=registration(invite))
        assert rejected.status_code == 403
        assert rejected.json() == {'detail': 'Registration is currently closed'}
        assert 'set-cookie' not in rejected.headers and PASSWORD not in rejected.text
        with app.state.database.connect() as conn:
            assert snapshot(conn) == before
            assert conn.execute("SELECT value FROM meta WHERE key='kv_scope_secret'").fetchone() == secret
        expect(student.get('/api/auth/me'))
        assert expect(new.post('/api/auth/login', json={'email': existing['email'], 'password': PASSWORD}))['user']['id'] == existing['id']
        # Course joins/provisioning are not registration: the switch is specific.
        expect(teacher.post('/api/teacher/courses/synthetic-course/students', json={'name': 'Provisioned', 'email': 'provisioned-stage10@example.invalid', 'temporary_password': PASSWORD}))
        assert expect(admin.put(URL, json={'registration_enabled': True})) == {'registration_enabled': True}
        assert expect(admin.get(URL)) == {'registration_enabled': True}
        assert expect(new.post('/api/auth/register', json=registration(invite)))['user']['role'] == 'student'


def test_open_registration_still_requires_real_invitation(app, admin):
    with TestClient(app) as client:
        expect(client.post('/api/auth/register', json=registration('not-a-real-invitation')), 404)
        with app.state.database.connect() as conn:
            assert not conn.execute('SELECT 1 FROM users WHERE email=?', ('new-stage10@example.invalid',)).fetchone()


def test_toggle_persists_restart_without_rewriting_user_rows(app, admin, tmp_path, catalog):
    with app.state.database.connect() as conn:
        before = [tuple(row) for row in conn.execute('SELECT * FROM users ORDER BY id')]
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    expect(admin.put(URL, json={'registration_enabled': False}))
    token = admin.cookies.get(COOKIE_NAME)
    restarted = create_app(data_dir=tmp_path / 'data', catalog_path=catalog, demo_enabled=True, frontend_dir=tmp_path / 'dist')
    with TestClient(restarted) as client:
        assert expect(client.get('/api/bootstrap'))['registration_enabled'] is False
        client.cookies.set(COOKIE_NAME, token)
        assert expect(client.get(URL)) == {'registration_enabled': False}
        with restarted.state.database.connect() as conn:
            assert [tuple(row) for row in conn.execute('SELECT * FROM users ORDER BY id')] == before
            assert [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")] == tables
            assert conn.execute('PRAGMA user_version').fetchone()[0] == 9
            assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert list(conn.execute('PRAGMA foreign_key_check')) == []


def test_waiting_registration_rereads_switch_after_concurrent_close(app, admin, teacher, monkeypatch):
    invite = expect(teacher.get('/api/courses'))[0]['join_code']
    with TestClient(app) as client:
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
        # Use an actual independent SQLite writer holding the same lock as PUT.
        # The register thread starts while this close is uncommitted, then must
        # observe false after it acquires BEGIN IMMEDIATE, never a stale pre-read.
        with original() as closer, ThreadPoolExecutor(max_workers=1) as pool:
            closer.execute('BEGIN IMMEDIATE')
            closer.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (REGISTRATION_KEY, 'false'))
            def attempt():
                return client.post('/api/auth/register', json=registration(invite))
            future = pool.submit(attempt)
            assert started.wait(2)
            assert not future.done()
            closer.commit()
            response = future.result(timeout=5)
        assert response.status_code == 403 and 'set-cookie' not in response.headers
        assert expect(admin.get(URL)) == {'registration_enabled': False}
        with original() as conn:
            assert not conn.execute('SELECT 1 FROM users WHERE email=?', ('new-stage10@example.invalid',)).fetchone()


def test_closed_registration_concurrency_never_creates_accounts(app, admin, teacher):
    invite = expect(teacher.get('/api/courses'))[0]['join_code']
    expect(admin.put(URL, json={'registration_enabled': False}))
    with app.state.database.connect() as conn:
        before = snapshot(conn)
    with ThreadPoolExecutor(max_workers=6) as pool:
        def attempt(index):
            # Startup is already owned by admin/teacher fixtures. Do not race
            # concurrent migrations by starting six lifespan contexts.
            client = TestClient(app)
            try:
                return client.post('/api/auth/register', json=registration(invite, f'blocked-{index}@example.invalid')).status_code
            finally:
                client.close()
        assert list(pool.map(attempt, range(6))) == [403] * 6
    with app.state.database.connect() as conn:
        assert snapshot(conn) == before


def test_cross_origin_admin_close_denied(app, admin):
    expect(admin.put(URL, json={'registration_enabled': False}, headers={'Origin': 'https://attacker.invalid'}), 403)
    assert expect(admin.get(URL)) == {'registration_enabled': True}
