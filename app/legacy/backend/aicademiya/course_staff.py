"""Explicit course staff, live authorization and primary-manager continuity."""
from fastapi import Depends, HTTPException
from .db import now, public_user

STAFF_ROLES = ('admin', 'teacher')
BACKFILL_KEY = 'stage11_staff_backfilled'


class AuthenticatedUser(dict):
    """Public keys only; the session identity never enters a JSON projection."""
    def __init__(self, public, token_hash):
        super().__init__(public)
        self.token_hash = token_hash


def migrate_staff(conn):
    conn.execute('SAVEPOINT stage11_staff')
    try:
        conn.execute('''CREATE TABLE IF NOT EXISTS course_staff (
            course_id TEXT NOT NULL REFERENCES courses(id),
            user_id TEXT NOT NULL REFERENCES users(id),
            PRIMARY KEY(course_id,user_id))''')
        conn.execute('''CREATE TABLE IF NOT EXISTS account_imports (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL REFERENCES users(id),
            expires_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('pending','committed')),
            payload_json TEXT NOT NULL,
            result_json TEXT)''')
        if not conn.execute('SELECT 1 FROM meta WHERE key=?', (BACKFILL_KEY,)).fetchone():
            # Do not rewrite owner, curriculum, learning, account or original schemas.
            conn.execute('''INSERT OR IGNORE INTO course_staff(course_id,user_id)
                SELECT c.id,c.owner_id FROM courses c JOIN users u ON u.id=c.owner_id
                WHERE u.role IN ('admin','teacher')''')
            conn.execute('INSERT INTO meta(key,value) VALUES(?,?)', (BACKFILL_KEY, now()))
        conn.execute('PRAGMA user_version=8')
        conn.execute('RELEASE stage11_staff')
    except Exception:
        conn.execute('ROLLBACK TO stage11_staff')
        conn.execute('RELEASE stage11_staff')
        raise


def live_actor(conn, user, *, admin=False, staff=False):
    row = conn.execute('SELECT * FROM users WHERE id=?', (user['id'],)).fetchone()
    if not row or row['archived_at'] or row['role'] != user['role']:
        raise HTTPException(403, 'Account permissions changed; sign in again')
    digest = getattr(user, 'token_hash', None)
    if digest and not conn.execute('SELECT 1 FROM auth_sessions WHERE token_hash=? AND user_id=? AND expires_at>?', (digest, row['id'], now())).fetchone():
        raise HTTPException(401, 'Session expired or unavailable; sign in again')
    if row['must_change_password']:
        raise HTTPException(403, 'Password change required')
    if admin and row['role'] != 'admin':
        raise HTTPException(403, 'Administrator access required')
    if staff and row['role'] not in STAFF_ROLES:
        raise HTTPException(403, 'Teacher access required')
    return row


def assigned(conn, cid, uid):
    return bool(conn.execute('''SELECT 1 FROM course_staff cs JOIN users u ON u.id=cs.user_id
        WHERE cs.course_id=? AND cs.user_id=? AND u.archived_at IS NULL
        AND u.role IN ('admin','teacher')''', (cid, uid)).fetchone())


def require_assigned(conn, cid, user):
    live_actor(conn, user, staff=True)
    if not assigned(conn, cid, user['id']):
        raise HTTPException(403, 'You are not assigned staff for this course')


def establish_assignment(conn, cid, uid):
    # Only explicit creation/bootstrap/assignment paths call this; never auth fallback.
    conn.execute('INSERT OR IGNORE INTO course_staff(course_id,user_id) VALUES(?,?)', (cid, uid))


def course_brief(conn, cid):
    row = conn.execute('SELECT id,code,title,owner_id FROM courses WHERE id=?', (cid,)).fetchone()
    if not row:
        raise HTTPException(404, 'Course not found')
    trash = conn.execute('SELECT trashed_at FROM course_trash WHERE course_id=?', (cid,)).fetchone()
    return {**dict(row), 'trashed_at': trash[0] if trash else None}


def staff_response(conn, cid):
    course = course_brief(conn, cid)
    rows = conn.execute('''SELECT u.* FROM users u JOIN course_staff cs ON cs.user_id=u.id
        WHERE cs.course_id=? ORDER BY u.name,u.email,u.id''', (cid,)).fetchall()
    return {'course': course, 'staff': [
        {'user': public_user(r, conn), 'is_primary': r['id'] == course['owner_id'],
         'active': not bool(r['archived_at'])} for r in rows]}


def ensure_can_remove_manager(conn, uid, *, cid=None):
    courses = conn.execute('''SELECT c.id,c.owner_id FROM courses c
        WHERE (c.owner_id=? OR EXISTS(SELECT 1 FROM course_staff cs WHERE cs.course_id=c.id AND cs.user_id=?))''', (uid, uid)).fetchall()
    for course in courses:
        if cid is not None and course['id'] != cid:
            continue
        if course['owner_id'] == uid:
            raise HTTPException(409, 'Transfer primary manager through course staff assignments before removing or disabling this account')
        if not conn.execute('''SELECT 1 FROM course_staff cs JOIN users u ON u.id=cs.user_id
            WHERE cs.course_id=? AND u.id<>? AND u.archived_at IS NULL
            AND u.role IN ('admin','teacher')''', (course['id'], uid)).fetchone():
            raise HTTPException(409, 'Course must retain active assigned staff; assign another manager first')


def register_staff_routes(app, db, current_user, admin_user):
    from . import models as m

    @app.get('/api/admin/courses')
    def course_index(user=Depends(admin_user)):
        with db.connect() as conn:
            conn.execute('BEGIN')
            live_actor(conn, user, admin=True)
            return {'courses': [course_brief(conn, r['id']) for r in conn.execute('SELECT id FROM courses ORDER BY code,title,id').fetchall()]}

    @app.get('/api/courses/{course_id}/staff')
    def get_staff(course_id: str, user=Depends(current_user)):
        with db.connect() as conn:
            conn.execute('BEGIN')
            actor = live_actor(conn, user, staff=True)
            course_brief(conn, course_id)
            if actor['role'] != 'admin':
                require_assigned(conn, course_id, user)
            return staff_response(conn, course_id)

    @app.post('/api/courses/{course_id}/staff')
    def add_staff(course_id: str, payload: m.StaffAssignment, user=Depends(admin_user)):
        with db.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            live_actor(conn, user, admin=True)
            course_brief(conn, course_id)
            target = conn.execute('SELECT * FROM users WHERE id=?', (payload.user_id,)).fetchone()
            if not target or target['archived_at'] or target['role'] not in STAFF_ROLES:
                raise HTTPException(422, 'Assign an active Admin or Teacher account')
            establish_assignment(conn, course_id, payload.user_id)
            return staff_response(conn, course_id)

    @app.delete('/api/courses/{course_id}/staff/{user_id}')
    def remove_staff(course_id: str, user_id: str, user=Depends(admin_user)):
        with db.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            live_actor(conn, user, admin=True)
            course_brief(conn, course_id)
            if conn.execute('SELECT 1 FROM course_staff WHERE course_id=? AND user_id=?', (course_id, user_id)).fetchone():
                ensure_can_remove_manager(conn, user_id, cid=course_id)
                conn.execute('DELETE FROM course_staff WHERE course_id=? AND user_id=?', (course_id, user_id))
            return staff_response(conn, course_id)

    @app.put('/api/courses/{course_id}/staff/primary')
    def transfer_primary(course_id: str, payload: m.StaffAssignment, user=Depends(admin_user)):
        with db.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            live_actor(conn, user, admin=True)
            course_brief(conn, course_id)
            if not assigned(conn, course_id, payload.user_id):
                raise HTTPException(409, 'Primary manager must already be active assigned staff')
            conn.execute('UPDATE courses SET owner_id=? WHERE id=?', (payload.user_id, course_id))
            return staff_response(conn, course_id)
