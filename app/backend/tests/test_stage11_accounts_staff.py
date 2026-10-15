"""Stage11 exact account/staff contracts, boundaries and serialized transitions."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
import threading
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend.aicademiya.db import issue_session, password_matches, public_user
from backend.aicademiya.course_staff import AuthenticatedUser
from backend.aicademiya.global_accounts import change_role, set_status
from .conftest import expect, publish
from .test_stage9_account_avatars import upload
from .test_stage9_feedback import create

CID = 'synthetic-course'
BASE = '/api/admin/users'
PASSWORD = 'Synthetic-stage11-1'


def account(admin, role='teacher', suffix='staff'):
    return expect(admin.post(BASE, json={'name': 'Synthetic '+suffix, 'email': suffix+'@example.invalid',
                                       'role': role, 'temporary_password': PASSWORD}))['user']


@contextmanager
def actor_client(app, uid):
    with app.state.database.connect() as conn:
        conn.execute('UPDATE users SET must_change_password=0 WHERE id=?', (uid,))
        token = issue_session(conn, uid)
    with TestClient(app) as client:
        client.cookies.set('aicademiya_session', token)
        yield client


def assign(admin, uid, cid=CID):
    result = expect(admin.post(f'/api/courses/{cid}/staff', json={'user_id': uid}))
    assert result == expect(admin.get(f'/api/courses/{cid}/staff'))
    return result


def test_global_admin_is_not_teaching_superuser_and_index_is_light(admin, teacher, student):
    assert expect(admin.get('/api/courses')) == []
    brief = expect(admin.get('/api/admin/courses'))['courses'][0]
    assert set(brief) == {'id','code','title','owner_id','trashed_at'}
    assert brief['owner_id'] == 'demo-teacher'
    for path in (f'/api/courses/{CID}', f'/api/courses/{CID}/sessions', f'/api/courses/{CID}/materials',
                 '/api/sessions/s4', '/api/materials/s4-private/download', '/api/teacher/sessions/s4/students',
                 f'/api/teacher/courses/{CID}/versions', '/api/sessions/s4/transcript'):
        expect(admin.get(path), 403)
    expect(admin.get('/api/assets/plot.png'), 404)
    assert expect(admin.get(f'/api/courses/{CID}/staff'))['staff'][0]['is_primary']
    for client in (teacher, student):
        expect(client.get('/api/admin/courses'), 403)
        expect(client.get(BASE), 403)
        expect(client.post(BASE, json={'name':'Spoof','email':'spoof@example.invalid','role':'admin','temporary_password':PASSWORD}), 403)
    expect(student.get(f'/api/courses/{CID}/staff'), 403)
    expect(teacher.post(f'/api/courses/{CID}/staff', json={'user_id':'demo-admin'}), 403)


def test_multiple_assigned_staff_share_all_content_but_private_previews(app, admin, teacher):
    extra = account(admin)
    assign(admin, extra['id'])
    assign(admin, 'demo-admin')
    with actor_client(app, extra['id']) as coworker:
        assert expect(coworker.get('/api/courses'))[0]['id'] == CID
        for path in (f'/api/courses/{CID}', f'/api/courses/{CID}/sessions', f'/api/courses/{CID}/materials',
                     '/api/sessions/s4', '/api/materials/s4-private/download', '/api/assets/plot.png',
                     '/api/teacher/sessions/s4/students', f'/api/teacher/courses/{CID}/versions',
                     '/api/teacher/sessions/s4/preview', '/api/sessions/s4/transcript'):
            response = coworker.get(path)
            assert response.status_code == 200, (path, response.text)
        expect(coworker.patch('/api/sessions/s4', json={'instructions':'Co-managed teaching instructions'}))
        expect(coworker.patch(f'/api/courses/{CID}', json={'description':'Literal\n\nco-management'}))
        material = expect(coworker.post('/api/sessions/s4/materials', files={'file':('co.txt', b'Co-managed public source')}))
        expect(coworker.post('/api/sessions/s2/materials/attach', json={'material_id':material['id']}))
        expect(coworker.patch('/api/sessions/s4/materials/'+material['id'], json={'title':'Shared draft title'}))
        edition = publish(coworker)['id']
        expect(coworker.get(f'/api/teacher/courses/{CID}/versions/{edition}/diff'))
        expect(coworker.post(f'/api/teacher/courses/{CID}/versions/{edition}/restore', json={}))
        expect(coworker.post('/api/sessions/s4/chat', json={'intent':'ask','message':'Private coworker preview','request_id':'coworker-private'}))
        assert 'Private coworker preview' not in teacher.get('/api/sessions/s4/workspace').text
        unrelated = expect(coworker.post('/api/courses', json={'title':'Unrelated','code':'OTHER'}))['id']
        expect(teacher.get(f'/api/courses/{unrelated}/sessions'), 403)
        expect(coworker.post(f'/api/courses/{CID}/trash', json={}))
        assert CID in [c['id'] for c in expect(teacher.get('/api/courses/trash'))['courses']]
        expect(coworker.post(f'/api/courses/{CID}/restore', json={}))
    removed = expect(admin.delete(f'/api/courses/{CID}/staff/'+extra['id']))
    assert removed == expect(admin.get(f'/api/courses/{CID}/staff'))
    with actor_client(app, extra['id']) as detached:
        expect(detached.get('/api/sessions/s4'), 403)
        expect(detached.get('/api/materials/s4-private/download'), 403)
        expect(detached.get('/api/assets/plot.png'), 404)
        assert all(r['course']['id'] != CID for r in expect(detached.get('/api/history')))


def test_counts_current_roles_enrollments_and_accounts_not_editions(app, admin, teacher, student):
    assign(admin, 'demo-admin')
    extra = account(admin)
    assign(admin, extra['id'])
    edition = publish(teacher)['id']
    before = expect(student.get('/api/courses'))[0]
    assert (before['admin_count'], before['teacher_count'], before['student_count']) == (1,2,2)
    expect(admin.patch(BASE+'/demo-student-2', json={'role':'teacher'}))
    current = expect(student.get('/api/courses'))[0]
    assert (current['admin_count'], current['teacher_count'], current['student_count']) == (1,2,1)
    assert current['published_version_id'] == edition
    assign(admin, 'demo-student-2')
    assert expect(student.get('/api/courses'))[0]['teacher_count'] == 3
    expect(admin.put(BASE+'/'+extra['id']+'/status', json={'active':False}))
    assert expect(student.get('/api/courses'))[0]['teacher_count'] == 2
    expect(teacher.post(f'/api/teacher/courses/{CID}/students/archive', json={'user_ids':['demo-student-1']}))
    assert expect(student.get('/api/courses'))[0]['student_count'] == 0
    with app.state.database.connect() as conn:
        assert conn.execute('SELECT count(*) FROM enrollments WHERE course_id=?', (CID,)).fetchone()[0] == 2
        assert conn.execute('SELECT id FROM course_versions WHERE id=?', (edition,)).fetchone()[0] == edition


def test_session_counts_follow_current_draft_not_retained_history(app, teacher):
    edition = publish(teacher)['id']
    extra = expect(teacher.post(f'/api/courses/{CID}/sessions', json={'title':'Later draft session'}))['id']
    assert expect(teacher.get(f'/api/courses/{CID}'))['session_count'] == 3
    expect(teacher.post(f'/api/teacher/courses/{CID}/versions/{edition}/restore', json={}))
    assert expect(teacher.get(f'/api/courses/{CID}'))['session_count'] == 2
    assert len(expect(teacher.get(f'/api/courses/{CID}/sessions'))) == 2
    with app.state.database.connect() as conn:
        assert conn.execute('SELECT in_draft FROM sessions WHERE id=?', (extra,)).fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM sessions WHERE course_id=?', (CID,)).fetchone()[0] == 3


@pytest.mark.parametrize('role', ['admin','teacher','student'])
def test_create_filter_pagination_detail_exact_public_dto(app, admin, role):
    user = account(admin, role=role, suffix='role-'+role)
    detail = expect(admin.get(BASE+'/'+user['id']))
    assert set(detail) == {'user','active','archived_at','purge_at','assigned_course_count','owned_course_count','staff_courses'}
    assert detail['user'] == user and user['must_change_password'] and detail['staff_courses'] == []
    assert PASSWORD not in str(detail) and 'password_hash' not in str(detail)
    assert set(user) == {'id','name','email','role','must_change_password','is_demo','avatar_url'}
    page = expect(admin.get(BASE, params={'q':'role-'+role,'role':role,'active':'true','offset':0,'limit':1}))
    assert page['total'] == 1 and page['items'][0]['user'] == user
    assert page['offset'] == 0 and page['limit'] == 1
    assert expect(admin.get(BASE, params={'q':'role-'+role,'offset':1,'limit':1}))['items'] == []
    for query in ('limit=0','limit=101','offset=-1','role=owner','q='+'x'*201):
        expect(admin.get(BASE+'?'+query), 422)
    with app.state.database.connect() as conn:
        stored = conn.execute('SELECT password_hash FROM users WHERE id=?', (user['id'],)).fetchone()[0]
        assert password_matches(PASSWORD, stored)
        assert not conn.execute('SELECT 1 FROM course_staff WHERE user_id=?', (user['id'],)).fetchone()


@pytest.mark.parametrize('bad', [None, '', 'abcdefgh', '12345678', 'a1', ['CredentialLeak1'], {'CredentialLeak1':True}, 'a'*513])
def test_global_password_validation_is_generic_and_no_values(admin, bad):
    payload = {'name':'CredentialLeak1','email':'credential-leak@example.invalid','role':'teacher','temporary_password':bad}
    response = admin.post(BASE, json=payload)
    expect(response, 422)
    assert response.json() == {'detail':'Invalid request; check the required fields and values'}
    assert 'CredentialLeak1' not in response.text and 'temporary_password' not in response.text


def test_primary_transfer_removal_disable_demote_and_trash_safeguards(app, admin, teacher):
    other = account(admin)
    expect(admin.delete(f'/api/courses/{CID}/staff/demo-teacher'), 409)
    expect(admin.put(BASE+'/demo-teacher/status', json={'active':False}), 409)
    expect(admin.patch(BASE+'/demo-teacher', json={'role':'student'}), 409)
    expect(admin.put(f'/api/courses/{CID}/staff/primary', json={'user_id':other['id']}), 409)
    assign(admin, other['id'])
    expect(teacher.post(f'/api/courses/{CID}/trash', json={}))
    result = expect(admin.put(f'/api/courses/{CID}/staff/primary', json={'user_id':other['id']}))
    assert result == expect(admin.get(f'/api/courses/{CID}/staff'))
    assert len(result['staff']) == 2 and result['course']['owner_id'] == other['id']
    expect(admin.put(BASE+'/demo-teacher/status', json={'active':False}))
    assert not next(r['active'] for r in expect(admin.get(f'/api/courses/{CID}/staff'))['staff'] if r['user']['id']=='demo-teacher')
    expect(admin.put(BASE+'/'+other['id']+'/status', json={'active':False}), 409)
    expect(admin.patch(BASE+'/demo-teacher', json={'role':'student'}), 409)
    expect(admin.delete(f'/api/courses/{CID}/staff/demo-teacher'))
    expect(admin.patch(BASE+'/demo-teacher', json={'role':'student'}))
    with app.state.database.connect() as conn:
        assert conn.execute('SELECT owner_id FROM courses WHERE id=?', (CID,)).fetchone()[0] == other['id']
        assert conn.execute('SELECT 1 FROM course_trash WHERE course_id=?', (CID,)).fetchone()


def test_rolechange_revokes_target_only_preserves_learning_avatar_feedback_and_preview_privacy(app, admin, teacher, student):
    work = expect(student.post('/api/sessions/s4/chat', json={'intent':'ask','message':'Student retained history','request_id':'retained-history'}))
    vid = work['version']['id']
    avatar = expect(upload(student))['user']['avatar_url']
    feedback = expect(create(student))
    expect(teacher.post('/api/sessions/s4/chat', json={'intent':'ask','message':'Teacher private draft','request_id':'private-draft'}))
    with app.state.database.connect() as conn:
        learning = [tuple(r) for r in conn.execute('SELECT * FROM messages ORDER BY seq')]
    expect(admin.patch(BASE+'/demo-student-1', json={'role':'teacher'}))
    expect(student.get('/api/auth/me'), 401)
    assert expect(teacher.get('/api/auth/me'))['user']['id'] == 'demo-teacher'
    assert expect(admin.get('/api/auth/me'))['user']['id'] == 'demo-admin'
    with actor_client(app, 'demo-student-1') as promoted:
        assert expect(promoted.get('/api/courses')) == []
        assert expect(promoted.get('/api/history')) == []
        expect(promoted.get('/api/sessions/s4'), 403)
    # Transfer/detach explicitly before demoting the original primary manager.
    assign(admin, 'demo-admin')
    expect(admin.put(f'/api/courses/{CID}/staff/primary', json={'user_id':'demo-admin'}))
    expect(admin.delete(f'/api/courses/{CID}/staff/demo-teacher'))
    expect(admin.patch(BASE+'/demo-teacher', json={'role':'student'}))
    with actor_client(app, 'demo-teacher') as demoted:
        expect(demoted.get('/api/sessions/s4/workspace'), 403)
        assert expect(demoted.get('/api/history')) == []
        expect(admin.post(f'/api/teacher/courses/{CID}/students', json={'name':'No reset','email':'demo-teacher@example.invalid'}))
        current = expect(demoted.get('/api/sessions/s4/workspace'))
        assert 'Teacher private draft' not in str(current)
        assert all(r['version']['id'] is not None for r in expect(demoted.get('/api/history')))
    expect(admin.put(BASE+'/demo-student-1/status', json={'active':False}))
    suspended = expect(admin.get(BASE+'/demo-student-1'))
    assert suspended['purge_at'] is None and not suspended['active']
    expect(admin.put(BASE+'/demo-student-1/status', json={'active':True}))
    expect(admin.patch(BASE+'/demo-student-1', json={'role':'student'}))
    with actor_client(app, 'demo-student-1') as restored:
        assert restored.get(avatar).status_code == 200
        assert expect(restored.get('/api/feedback/'+feedback['id']))['message'] == feedback['message']
        assert 'Student retained history' in restored.get('/api/sessions/s4/workspace?version_id='+vid).text
    with app.state.database.connect() as conn:
        assert [tuple(r) for r in conn.execute('SELECT * FROM messages ORDER BY seq')] == learning


@pytest.mark.parametrize('blank', [None, ''])
def test_course_provision_existing_student_no_reset_but_new_requires_password(app, teacher, blank):
    course = expect(teacher.post('/api/courses', json={'title':'Link existing','code':'LINK'}))['id']
    payload = {'name':'Must not rename','email':'demo-student-1@example.invalid'}
    if blank is not None:
        payload['temporary_password'] = blank
    with app.state.database.connect() as conn:
        before = tuple(conn.execute("SELECT * FROM users WHERE id='demo-student-1'").fetchone())
    result = expect(teacher.post(f'/api/teacher/courses/{course}/students', json=payload))
    assert result['user']['id'] == 'demo-student-1'
    with app.state.database.connect() as conn:
        assert tuple(conn.execute("SELECT * FROM users WHERE id='demo-student-1'").fetchone()) == before
    payload['email'] = 'new-without-password@example.invalid'
    expect(teacher.post(f'/api/teacher/courses/{course}/students', json=payload), 422)
    payload['email'] = 'spoof-role@example.invalid'; payload['role']='admin'
    expect(teacher.post(f'/api/teacher/courses/{course}/students', json=payload), 422)


def test_self_and_last_usable_admin_guard_with_live_recheck(app, admin):
    expect(admin.patch(BASE+'/demo-admin', json={'role':'teacher'}), 409)
    expect(admin.put(BASE+'/demo-admin/status', json={'active':False}), 409)
    extra = account(admin, role='admin', suffix='second-admin')
    with actor_client(app, extra['id']) as other:
        expect(other.patch(BASE+'/demo-admin', json={'role':'teacher'}))
    # The old cookie cannot exploit the former administrator dependency.
    expect(admin.get(BASE), 401)
    with app.state.database.connect() as conn:
        actor = public_user(conn.execute('SELECT * FROM users WHERE id=?', (extra['id'],)).fetchone(), conn)
        target = conn.execute('SELECT * FROM users WHERE id=?', (extra['id'],)).fetchone()
        from backend.aicademiya.global_accounts import protect_last_admin
        with pytest.raises(HTTPException) as error:
            protect_last_admin(conn, target, demo_enabled=True)
        assert error.value.status_code == 409


def test_concurrent_administrators_cannot_mutually_disable_or_demote(app, admin):
    extra = account(admin, role='admin', suffix='concurrent-admin')
    with app.state.database.connect() as conn:
        conn.execute('UPDATE users SET must_change_password=0 WHERE id=?', (extra['id'],))
        token = issue_session(conn, extra['id'])
        row = conn.execute('SELECT * FROM users WHERE id=?', (extra['id'],)).fetchone()
        first = AuthenticatedUser(public_user(row, conn), hashlib.sha256(token.encode()).hexdigest())
        original = conn.execute("SELECT * FROM users WHERE id='demo-admin'").fetchone()
        original_token = admin.cookies.get('aicademiya_session')
        second = AuthenticatedUser(public_user(original, conn), hashlib.sha256(original_token.encode()).hexdigest())
    barrier = threading.Barrier(2)
    def operation(actor, target, change):
        barrier.wait(timeout=5)
        try:
            with app.state.database.connect() as conn:
                conn.execute('BEGIN IMMEDIATE')
                if change:
                    change_role(conn, actor, target, 'teacher', demo_enabled=True)
                else:
                    set_status(conn, actor, target, False, demo_enabled=True)
            return 200
        except HTTPException as exc:
            return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = [pool.submit(operation, first, 'demo-admin', True), pool.submit(operation, second, extra['id'], False)]
        outcomes = [f.result(timeout=15) for f in tasks]
    assert sorted(outcomes) == [200,403]
    with app.state.database.connect() as conn:
        assert conn.execute("SELECT count(*) FROM users WHERE role='admin' AND archived_at IS NULL").fetchone()[0] == 1


def test_primary_transfer_and_disable_race_cannot_leave_inactive_primary(app, admin):
    extra = account(admin, suffix='primary-race')
    assign(admin, extra['id'])
    barrier = threading.Barrier(2)
    def request(path, payload):
        barrier.wait(timeout=5)
        return admin.put(path, json=payload).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(request, f'/api/courses/{CID}/staff/primary', {'user_id':extra['id']}),
                pool.submit(request, BASE+'/'+extra['id']+'/status', {'active':False})]
        outcomes = [j.result(timeout=15) for j in jobs]
    assert sorted(outcomes) == [200,409]
    with app.state.database.connect() as conn:
        row = conn.execute('''SELECT u.role,u.archived_at FROM courses c JOIN users u ON u.id=c.owner_id
            JOIN course_staff cs ON cs.course_id=c.id AND cs.user_id=c.owner_id WHERE c.id=?''', (CID,)).fetchone()
        assert row['role'] in ('admin','teacher') and row['archived_at'] is None
