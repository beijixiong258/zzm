"""Stage11 revocation during accepted work and stale-dependency boundary tests."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import threading
import pytest
from fastapi import HTTPException
from backend.aicademiya.course_staff import AuthenticatedUser
from backend.aicademiya.db import public_user
from .conftest import expect, publish
from .test_stage11_accounts_staff import account, assign, actor_client, CID, BASE, PASSWORD


def cached_actor(app, client, uid):
    with app.state.database.connect() as conn:
        row = conn.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
        return AuthenticatedUser(public_user(row, conn), hashlib.sha256(client.cookies.get('aicademiya_session').encode()).hexdigest())


def dependency(app, name):
    return next(d.call for route in app.routes if hasattr(route, 'dependant')
                for d in route.dependant.dependencies if getattr(d.call, '__name__', '') == name)


def test_revoked_admin_session_aba_cannot_pass_stale_dependency_under_write_lock(app, admin):
    stale = cached_actor(app, admin, 'demo-admin')
    extra = account(admin, role='admin', suffix='live-rechecker')
    target = account(admin, role='student', suffix='unchanged-target')
    with actor_client(app, extra['id']) as other:
        expect(other.patch(BASE+'/demo-admin', json={'role':'teacher'}))
        expect(other.patch(BASE+'/demo-admin', json={'role':'admin'}))
    app.dependency_overrides[dependency(app, 'admin_user')] = lambda: stale
    try:
        expect(admin.patch(BASE+'/'+target['id'], json={'role':'teacher'}), 401)
        expect(admin.post(BASE, json={'name':'Must not create','email':'blocked-aba@example.invalid','role':'admin','temporary_password':PASSWORD}), 401)
        expect(admin.post(f'/api/courses/{CID}/staff', json={'user_id':extra['id']}), 401)
    finally:
        app.dependency_overrides.clear()
    with app.state.database.connect() as conn:
        assert conn.execute('SELECT role FROM users WHERE id=?', (target['id'],)).fetchone()[0] == 'student'
        assert not conn.execute("SELECT 1 FROM users WHERE email='blocked-aba@example.invalid'").fetchone()


@pytest.mark.parametrize('path,method,payload', [
    ('/api/sessions/s4','PATCH',{'instructions':'Must not save'}),
    (f'/api/courses/{CID}','PATCH',{'title':'Must not save'}),
    (f'/api/courses/{CID}/trash','POST',{}),
    (f'/api/teacher/courses/{CID}/students/archive','POST',{'user_ids':['demo-student-1']}),
    (f'/api/teacher/courses/{CID}/versions/publish','POST',{}),
    ('/api/sessions/s4/materials/s4-public','PATCH',{'title':'Must not save'}),
    ('/api/sessions/s4/materials/attach','POST',{'material_id':'s2-public'}),
    ('/api/teacher/sessions/s4/preview/reset','POST',{'expected_revision':'wrong-revision'}),
], ids=['session','course','trash','roster','publication','material','library','preview'])
def test_old_routes_recheck_removed_assignment_with_cached_staff_dependency(app, admin, teacher, path, method, payload):
    extra = account(admin)
    assign(admin, extra['id'])
    with actor_client(app, extra['id']) as coworker:
        stale = cached_actor(app, coworker, extra['id'])
        expect(admin.delete(f'/api/courses/{CID}/staff/'+extra['id']))
        app.dependency_overrides[dependency(app, 'teacher_user')] = lambda: stale
        try:
            expect(coworker.request(method, path, json=payload), 403)
        finally:
            app.dependency_overrides.clear()
    assert expect(teacher.get('/api/sessions/s4'))['instructions'] != 'Must not save'


@pytest.mark.parametrize('kind', ['chat','guided'])
@pytest.mark.parametrize('revoke', ['assignment','role','disable'])
def test_async_commit_rechecks_staff_after_inference_no_assistant_or_answer(app, admin, teacher, kind, revoke, monkeypatch):
    extra = account(admin, suffix='async-'+kind+'-'+revoke)
    assign(admin, extra['id'])
    entered, release = threading.Event(), threading.Event()
    if kind == 'chat':
        original = app.state.tutor.feedback
        def held(*args, **kwargs):
            entered.set(); assert release.wait(15)
            return original(*args, **kwargs)
        monkeypatch.setattr(app.state.tutor, 'feedback', held)
        path = '/api/sessions/s4/chat'
        payload = {'message':'Retained accepted raw input','intent':'ask','request_id':'async-revoked'}
        table = 'chat_requests'
    else:
        import backend.aicademiya.guided_routes as routes
        original = routes.run_lesson
        def held(*args, **kwargs):
            entered.set(); assert release.wait(15)
            return original(*args, **kwargs)
        monkeypatch.setattr(routes, 'run_lesson', held)
        path = '/api/sessions/s4/tutor/start'
        payload = {'request_id':'async-revoked'}
        table = 'tutor_requests'
    with actor_client(app, extra['id']) as coworker:
        with ThreadPoolExecutor(max_workers=1) as pool:
            job = pool.submit(coworker.post, path, json=payload)
            try:
                assert entered.wait(10) and not job.done()
                if revoke == 'assignment':
                    expect(admin.delete(f'/api/courses/{CID}/staff/'+extra['id']))
                elif revoke == 'role':
                    expect(admin.patch(BASE+'/'+extra['id'], json={'role':'admin'}))
                else:
                    expect(admin.put(BASE+'/'+extra['id']+'/status', json={'active':False}))
            finally:
                release.set()
            response = job.result(timeout=15)
            assert response.status_code in (401,403), response.text
    with app.state.database.connect() as conn:
        assert not conn.execute("SELECT 1 FROM messages WHERE user_id=? AND role='assistant'", (extra['id'],)).fetchone()
        assert not conn.execute('SELECT 1 FROM attempts WHERE user_id=?', (extra['id'],)).fetchone()
        assert conn.execute(f'SELECT status FROM {table} WHERE user_id=?', (extra['id'],)).fetchone()[0] == 'failed'
        if kind == 'chat':
            assert conn.execute("SELECT content FROM messages WHERE user_id=? AND role='user'", (extra['id'],)).fetchone()[0] == 'Retained accepted raw input'


def test_teacher_scoped_students_and_removal_does_not_disable_or_affect_other_course(app, teacher, student, admin):
    unrelated = expect(admin.post('/api/courses', json={'title':'Admin unrelated','code':'UNRELATED'}))['id']
    expect(admin.post(f'/api/teacher/courses/{unrelated}/students', json={'name':'Existing student','email':'demo-student-1@example.invalid'}))
    expect(teacher.get(f'/api/teacher/courses/{unrelated}/students'), 403)
    expect(teacher.post(f'/api/teacher/courses/{unrelated}/students/archive', json={'user_ids':['demo-student-1']}), 403)
    expect(teacher.post(f'/api/teacher/courses/{CID}/students/archive', json={'user_ids':['demo-student-1']}))
    assert expect(student.get('/api/auth/me'))['user']['role'] == 'student'
    with app.state.database.connect() as conn:
        assert conn.execute("SELECT archived_at FROM users WHERE id='demo-student-1'").fetchone()[0] is None
        assert conn.execute('SELECT archived_at FROM enrollments WHERE course_id=? AND user_id=?', (unrelated,'demo-student-1')).fetchone()[0] is None
    expect(teacher.post(f'/api/teacher/courses/{CID}/students/restore', json={'user_ids':['demo-student-1']}))
    expect(admin.patch(BASE+'/demo-student-2', json={'role':'teacher'}))
    roster = expect(teacher.get(f'/api/teacher/courses/{CID}/students'))
    assert [r['user']['id'] for r in roster] == ['demo-student-1']
