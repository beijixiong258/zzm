"""Fresh production bootstrap: owned seed content, no demo identities."""
from fastapi.testclient import TestClient
from backend.aicademiya.main import create_app


def test_first_local_admin_owns_unassigned_seed_and_next_admin_does_not(tmp_path, catalog, monkeypatch):
    monkeypatch.setenv('AICADEMIYA_AI_MODE', 'demo')
    app = create_app(data_dir=tmp_path / 'fresh', catalog_path=catalog, demo_enabled=False)
    with TestClient(app) as client:
        db = app.state.database
        with db.connect() as conn:
            assert conn.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0
        owner = db.create_admin('Initial Owner', 'owner@example.invalid', 'SyntheticAdmin9')
        login = client.post('/api/auth/login', json={'email':'owner@example.invalid','password':'SyntheticAdmin9'})
        assert login.status_code == 200
        courses = client.get('/api/courses').json()
        assert [c['id'] for c in courses] == ['synthetic-course']
        assert client.get('/api/sessions/s4').status_code == 200
        db.create_admin('Other Admin', 'other@example.invalid', 'SyntheticOther9')
        with db.connect() as conn:
            assert conn.execute('SELECT owner_id FROM courses WHERE id=?', ('synthetic-course',)).fetchone()[0] == owner
            assert conn.execute('SELECT label FROM course_versions WHERE course_id=?', ('synthetic-course',)).fetchone()[0] == 'Initial edition'
            assert conn.execute('SELECT COUNT(*) FROM users WHERE is_demo=1').fetchone()[0] == 0


def test_local_admin_creation_does_not_take_existing_teachers_course(tmp_path, catalog, monkeypatch):
    monkeypatch.setenv('AICADEMIYA_AI_MODE', 'demo')
    app = create_app(data_dir=tmp_path / 'owned', catalog_path=catalog, demo_enabled=False)
    with TestClient(app) as client:
        db = app.state.database
        teacher = db.create_teacher('Existing Teacher', 'teacher@example.invalid', 'SyntheticTeacher9')
        db.create_admin('New Admin', 'admin@example.invalid', 'SyntheticAdmin9')
        login = client.post('/api/auth/login', json={'email':'admin@example.invalid','password':'SyntheticAdmin9'})
        assert login.status_code == 200
        assert client.get('/api/courses').json() == []
        assert client.get('/api/sessions/s4').status_code == 403
        with db.connect() as conn:
            assert conn.execute('SELECT owner_id FROM courses WHERE id=?', ('synthetic-course',)).fetchone()[0] == teacher
