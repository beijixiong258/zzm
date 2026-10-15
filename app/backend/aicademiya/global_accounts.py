"""Administrator-only global accounts; no implicit teaching privileges."""
from typing import Literal
from fastapi import Depends, HTTPException, Query
from . import models as m
from .db import new_id, now, password_hash, public_user
from .course_staff import live_actor, ensure_can_remove_manager, course_brief


def validate_identity(name, email):
    name, email = name.strip(), email.strip().lower()
    if not 1 <= len(name) <= 100 or not 3 <= len(email) <= 254 or '@' not in email or any(c.isspace() for c in email):
        raise HTTPException(422, 'Provide a name (1–100 characters) and valid email')
    return name, email


def target_user(conn, uid):
    row = conn.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    if not row:
        raise HTTPException(404, 'Account not found')
    return row


def account_projection(conn, row, *, detail=False):
    uid = row['id']
    result = {'user': public_user(row, conn), 'active': not bool(row['archived_at']),
              'archived_at': row['archived_at'], 'purge_at': row['purge_at'],
              'assigned_course_count': conn.execute('SELECT count(*) FROM course_staff WHERE user_id=?', (uid,)).fetchone()[0],
              'owned_course_count': conn.execute('SELECT count(*) FROM courses WHERE owner_id=?', (uid,)).fetchone()[0]}
    if detail:
        result['staff_courses'] = [course_brief(conn, r[0]) for r in conn.execute('''SELECT c.id FROM courses c JOIN course_staff cs ON cs.course_id=c.id
            WHERE cs.user_id=? ORDER BY c.code,c.title,c.id''', (uid,)).fetchall()]
    return result


def protect_last_admin(conn, target, *, demo_enabled):
    if target['role'] != 'admin' or target['archived_at']:
        return
    usable = conn.execute('''SELECT 1 FROM users WHERE role='admin' AND archived_at IS NULL AND id<>?
        AND (is_demo=0 OR ?) AND (password_hash IS NOT NULL OR (is_demo=1 AND ?))''',
        (target['id'], int(demo_enabled), int(demo_enabled))).fetchone()
    if not usable:
        raise HTTPException(409, 'At least one usable active administrator must remain')


def change_role(conn, actor, uid, role, *, demo_enabled):
    live_actor(conn, actor, admin=True)
    target = target_user(conn, uid)
    if uid == actor['id']:
        raise HTTPException(409, 'You cannot change your own global role')
    if target['role'] == role:
        return target
    if target['role'] == 'admin':
        protect_last_admin(conn, target, demo_enabled=demo_enabled)
    if role == 'student' and (conn.execute('SELECT 1 FROM course_staff WHERE user_id=?', (uid,)).fetchone()
                              or conn.execute('SELECT 1 FROM courses WHERE owner_id=?', (uid,)).fetchone()):
        raise HTTPException(409, 'Transfer primary management and remove all course staff assignments before changing to Student')
    conn.execute('UPDATE users SET role=? WHERE id=?', (role, uid))
    conn.execute('DELETE FROM auth_sessions WHERE user_id=?', (uid,))
    return target_user(conn, uid)


def set_status(conn, actor, uid, active, *, demo_enabled):
    live_actor(conn, actor, admin=True)
    target = target_user(conn, uid)
    if not active and uid == actor['id']:
        raise HTTPException(409, 'You cannot disable your own account')
    if active == (not bool(target['archived_at'])):
        return target
    if not active:
        protect_last_admin(conn, target, demo_enabled=demo_enabled)
        ensure_can_remove_manager(conn, uid)
        # Reversible suspension has no automatic purge. Old retention deadlines
        # are left intact by no-op requests and cleared only by explicit restore.
        conn.execute('UPDATE users SET archived_at=?,purge_at=NULL WHERE id=?', (now(), uid))
        conn.execute('DELETE FROM auth_sessions WHERE user_id=?', (uid,))
    else:
        conn.execute('UPDATE users SET archived_at=NULL,purge_at=NULL WHERE id=?', (uid,))
    return target_user(conn, uid)


def register_global_account_routes(app, db, admin_user, *, demo_enabled):
    # Literal import paths must precede the dynamic account ID routes.
    from .account_import import register_account_import_routes
    register_account_import_routes(app, db, admin_user)

    @app.get('/api/admin/users')
    def list_accounts(q: str = Query('', max_length=200), role: Literal['admin','teacher','student'] | None = None,
                      active: bool | None = None, offset: int = Query(0, ge=0),
                      limit: int = Query(50, ge=1, le=100), user=Depends(admin_user)):
        with db.connect() as conn:
            conn.execute('BEGIN')
            live_actor(conn, user, admin=True)
            conditions, params = [], []
            if q:
                # Literal substring search, not caller-controlled LIKE wildcards.
                conditions.append('(instr(lower(name),lower(?))>0 OR instr(lower(email),lower(?))>0)')
                params.extend([q, q])
            if role is not None:
                conditions.append('role=?')
                params.append(role)
            if active is not None:
                conditions.append('archived_at IS NULL' if active else 'archived_at IS NOT NULL')
            where = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
            total = conn.execute('SELECT count(*) FROM users' + where, params).fetchone()[0]
            rows = conn.execute('SELECT * FROM users' + where + ' ORDER BY name,email,id LIMIT ? OFFSET ?', (*params, limit, offset)).fetchall()
            return {'items': [account_projection(conn, r) for r in rows], 'total': total, 'offset': offset, 'limit': limit}

    @app.post('/api/admin/users')
    def create_account(payload: m.GlobalAccountCreate, user=Depends(admin_user)):
        name, email = validate_identity(payload.name, payload.email)
        hashed = password_hash(payload.temporary_password)
        with db.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            live_actor(conn, user, admin=True)
            uid = new_id()
            conn.execute('''INSERT INTO users(id,name,email,role,password_hash,must_change_password)
                VALUES(?,?,?,?,?,1)''', (uid, name, email, payload.role, hashed))
            return {'user': public_user(target_user(conn, uid), conn)}

    @app.get('/api/admin/users/{user_id}')
    def get_account(user_id: str, user=Depends(admin_user)):
        with db.connect() as conn:
            conn.execute('BEGIN')
            live_actor(conn, user, admin=True)
            return account_projection(conn, target_user(conn, user_id), detail=True)

    @app.patch('/api/admin/users/{user_id}')
    def role_change(user_id: str, payload: m.GlobalRoleChange, user=Depends(admin_user)):
        with db.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = change_role(conn, user, user_id, payload.role, demo_enabled=demo_enabled)
            return {'user': public_user(row, conn)}

    @app.put('/api/admin/users/{user_id}/status')
    def status_change(user_id: str, payload: m.AccountStatus, user=Depends(admin_user)):
        with db.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = set_status(conn, user, user_id, payload.active, demo_enabled=demo_enabled)
            return account_projection(conn, row)
