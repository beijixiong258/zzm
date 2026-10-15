"""Reviewed mixed-role imports: hash-only staging and atomic recoverable commit."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from fastapi import Depends, File, Form, HTTPException, UploadFile
from . import models as m
from .db import new_id, password_hash
from .course_staff import live_actor
from .roster import MAX_BYTES, parse_rows, expired


def assumption(conn, email):
    row = conn.execute('SELECT id,name,role,archived_at,purge_at FROM users WHERE email=?', (email,)).fetchone()
    return dict(row) if row else None


def visible_preview(iid, rows):
    visible = [{k: r[k] for k in ('row_number','name','email','role','action','errors','warnings')} for r in rows]
    errors = sum(bool(r['errors']) for r in rows)
    return {'import_id': iid, 'rows': visible, 'valid_count': len(rows)-errors, 'error_count': errors}


def preview_accounts(conn, user, rows, default_role, default_password):
    from .global_accounts import validate_identity
    live_actor(conn, user, admin=True)
    if conn.execute("SELECT count(*) FROM account_imports WHERE owner_id=? AND status='pending' AND expires_at>?", (user['id'], datetime.now(timezone.utc).isoformat())).fetchone()[0] >= 30:
        raise HTTPException(429, 'Too many pending account imports; commit or wait for expiry')
    staged, emails = [], set()
    for number, raw in rows:
        name, email = raw.get('name', '').strip(), raw.get('email', '').strip().lower()
        role = raw.get('role') or default_role
        errors, warnings = [], []
        if role not in ('admin','teacher','student'):
            # A non-Role token has no representation in the frozen row DTO;
            # reject the file rather than silently repairing the requested role.
            raise HTTPException(422, 'Role column must contain admin, teacher or student')
        try:
            validate_identity(name, email)
        except HTTPException:
            errors.append('Provide a name (1–100 characters) and valid email')

        if email in emails:
            errors.append('Duplicate email in this import')
        emails.add(email)
        expected = assumption(conn, email)
        action = 'skip' if expected else 'create'
        hashed = None
        if expected:
            if expected['role'] != role:
                errors.append('Existing account has a different role; change its role explicitly instead of importing')
            warnings.append('Existing account name, status and password will not be changed')
        elif not errors:
            password = raw.get('temporary_password') or default_password or ''
            try:
                m.validate_new_password(password)
                hashed = password_hash(password)
            except ValueError:
                errors.append('New accounts require 8–512 characters including an ASCII letter and digit')
        staged.append({'row_number': number, 'name': name, 'email': email, 'role': role,
                       'action': 'error' if errors else action, 'errors': errors, 'warnings': warnings,
                       'password_hash': hashed, 'expected': expected})
    iid = new_id()
    expiry = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
    conn.execute("INSERT INTO account_imports(id,owner_id,expires_at,status,payload_json) VALUES(?,?,?,'pending',?)", (iid, user['id'], expiry, json.dumps(staged)))
    return visible_preview(iid, staged)


def import_record(conn, iid, user):
    live_actor(conn, user, admin=True)
    row = conn.execute('SELECT * FROM account_imports WHERE id=? AND owner_id=?', (iid, user['id'])).fetchone()
    if not row:
        raise HTTPException(404, 'Account import not found in your scope')
    if expired(row['expires_at']):
        raise HTTPException(410, 'Account import expired; upload again')
    return row


def recover_accounts(conn, iid, user):
    row = import_record(conn, iid, user)
    return {'status': row['status'], 'preview': visible_preview(iid, json.loads(row['payload_json'])),
            'result': json.loads(row['result_json']) if row['result_json'] is not None else None}


def commit_accounts(conn, iid, user):
    row = import_record(conn, iid, user)
    if row['status'] == 'committed':
        return json.loads(row['result_json'])
    rows = json.loads(row['payload_json'])
    if any(r['errors'] or r['action'] == 'error' for r in rows):
        raise HTTPException(422, 'Import contains errors; fix and upload again')
    # Validate EVERY assumption before the first insert. The caller owns the
    # BEGIN IMMEDIATE reservation through result persistence and commit.
    for r in rows:
        if assumption(conn, r['email']) != r['expected']:
            raise HTTPException(409, 'Accounts changed since preview; upload and review again')
    result = {'created': 0, 'skipped': 0, 'user_ids': []}
    for r in rows:
        if r['action'] == 'create':
            uid = new_id()
            conn.execute('''INSERT INTO users(id,name,email,role,password_hash,must_change_password)
                VALUES(?,?,?,?,?,1)''', (uid, r['name'], r['email'], r['role'], r['password_hash']))
            result['created'] += 1
        else:
            uid = r['expected']['id']
            result['skipped'] += 1
        result['user_ids'].append(uid)
    # Recovery retains the reviewed public rows and exact result for 24 hours.
    # Remove hashes after commit: users is now the only credential store.
    for r in rows:
        r['password_hash'] = None
    expiry = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    conn.execute("UPDATE account_imports SET status='committed',result_json=?,payload_json=?,expires_at=? WHERE id=?", (json.dumps(result), json.dumps(rows), expiry, iid))
    return result


def register_account_import_routes(app, db, admin_user):
    @app.post('/api/admin/users/import/preview')
    def preview(file: UploadFile = File(...), default_role: Literal['admin','teacher','student'] = Form('student'),
                default_temporary_password: str | None = Form(None), user=Depends(admin_user)):
        with db.connect() as conn:
            live_actor(conn, user, admin=True)
        data = file.file.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise HTTPException(413, 'Account import exceeds the 2 MiB limit')
        rows = parse_rows(data, Path(file.filename or '').suffix.lower(), global_accounts=True)
        with db.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            return preview_accounts(conn, user, rows, default_role, default_temporary_password)

    @app.post('/api/admin/users/import/{import_id}/commit')
    def commit(import_id: str, payload: m.Empty, user=Depends(admin_user)):
        with db.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            return commit_accounts(conn, import_id, user)

    @app.get('/api/admin/users/import/{import_id}')
    def recovery(import_id: str, user=Depends(admin_user)):
        with db.connect() as conn:
            conn.execute('BEGIN')
            return recover_accounts(conn, import_id, user)
