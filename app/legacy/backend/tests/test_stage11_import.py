"""Global reviewed CSV/XLSX import secrecy, resources, atomicity and recovery."""
from concurrent.futures import ThreadPoolExecutor
import io
import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
import pytest
from backend.aicademiya.account_import import commit_accounts
from backend.aicademiya.db import public_user, password_matches
from backend.aicademiya.roster import MAX_BYTES, maintenance, parse_rows
from .conftest import expect
from .test_stage11_accounts_staff import account, actor_client, PASSWORD, BASE

IMPORT = BASE+'/import'


def preview(admin, text, *, suffix='.csv', **form):
    return admin.post(IMPORT+'/preview', files={'file':('synthetic'+suffix, text)}, data=form)


def commit(admin, iid):
    return admin.post(IMPORT+'/'+iid+'/commit', json={})


def xlsx(rows):
    from openpyxl import Workbook
    book = Workbook()
    for row in rows:
        book.active.append(row)
    output = io.BytesIO(); book.save(output); book.close()
    return output.getvalue()


@pytest.mark.parametrize('kind', ['csv','xlsx'])
def test_mixed_roles_hash_only_preview_commit_recovery_and_no_assignment(app, admin, kind):
    rows = [['name','email','role','temporary_password'], ['Admin imported','mixed-admin@example.invalid','admin',PASSWORD],
            ['Teacher imported','mixed-teacher@example.invalid','teacher',PASSWORD], ['Student imported','mixed-student@example.invalid','student',PASSWORD],
            ['Skip existing','demo-student-1@example.invalid','student','Do-not-reset2']]
    if kind == 'xlsx':
        content = xlsx(rows)
    else:
        import csv
        text = io.StringIO(); csv.writer(text).writerows(rows); content=text.getvalue().encode()
    reviewed = expect(preview(admin, content, suffix='.'+kind))
    assert reviewed['valid_count'] == 4 and reviewed['error_count'] == 0
    assert [r['role'] for r in reviewed['rows']] == ['admin','teacher','student','student']
    assert [r['action'] for r in reviewed['rows']] == ['create','create','create','skip']
    assert PASSWORD not in str(reviewed) and 'password_hash' not in str(reviewed)
    iid = reviewed['import_id']
    with app.state.database.connect() as conn:
        encoded = conn.execute('SELECT payload_json FROM account_imports WHERE id=?', (iid,)).fetchone()[0]
        assert PASSWORD not in encoded and 'Do-not-reset2' not in encoded
        staged = json.loads(encoded)
        assert all(r['password_hash'].startswith('scrypt$') for r in staged[:3])
        old = tuple(conn.execute("SELECT * FROM users WHERE id='demo-student-1'").fetchone())
    assert expect(admin.get(IMPORT+'/'+iid)) == {'status':'pending','preview':reviewed,'result':None}
    result = expect(commit(admin, iid))
    assert result['created'] == 3 and result['skipped'] == 1 and len(result['user_ids']) == 4
    assert result['user_ids'][-1] == 'demo-student-1'
    assert expect(commit(admin, iid)) == result
    assert expect(admin.get(IMPORT+'/'+iid)) == {'status':'committed','preview':reviewed,'result':result}
    for uid, role in zip(result['user_ids'][:3], ('admin','teacher','student')):
        user = expect(admin.get(BASE+'/'+uid))['user']
        assert user['role'] == role and user['must_change_password']
    with app.state.database.connect() as conn:
        assert tuple(conn.execute("SELECT * FROM users WHERE id='demo-student-1'").fetchone()) == old
        assert conn.execute('SELECT count(*) FROM course_staff WHERE user_id IN (?,?,?)', result['user_ids'][:3]).fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM enrollments WHERE user_id IN (?,?,?)', result['user_ids'][:3]).fetchone()[0] == 0
        for uid in result['user_ids'][:3]:
            assert password_matches(PASSWORD, conn.execute('SELECT password_hash FROM users WHERE id=?', (uid,)).fetchone()[0])
        assert all(r['password_hash'] is None for r in json.loads(conn.execute('SELECT payload_json FROM account_imports WHERE id=?', (iid,)).fetchone()[0]))


def test_defaults_column_override_and_password_literal_spaces(admin, app):
    spaced = '  Synthetic literal1  '
    content = ('name,email,role,temporary_password\nDefault,default@example.invalid,,\nOverride,override@example.invalid,admin,'+spaced+'\n').encode()
    reviewed = expect(preview(admin, content, default_role='teacher', default_temporary_password=PASSWORD))
    assert [r['role'] for r in reviewed['rows']] == ['teacher','admin']
    result = expect(commit(admin, reviewed['import_id']))
    with app.state.database.connect() as conn:
        hashed = conn.execute('SELECT password_hash FROM users WHERE id=?', (result['user_ids'][1],)).fetchone()[0]
        assert password_matches(spaced, hashed) and not password_matches(spaced.strip(), hashed)


def test_duplicate_emails_and_disabled_existing_skip_are_explicit(admin, app):
    reviewed = expect(preview(admin, b'name,email,role\nOne,duplicate-global@example.invalid,teacher\nTwo,DUPLICATE-GLOBAL@example.invalid,teacher\n', default_temporary_password=PASSWORD))
    assert reviewed['valid_count'] == 1 and reviewed['error_count'] == 1
    expect(commit(admin, reviewed['import_id']), 422)
    expect(admin.put(BASE+'/demo-student-2/status', json={'active':False}))
    reviewed = expect(preview(admin, b'name,email\nMust not change,demo-student-2@example.invalid\n'))
    assert reviewed['rows'][0]['action'] == 'skip'
    result = expect(commit(admin, reviewed['import_id']))
    assert result == {'created':0,'skipped':1,'user_ids':['demo-student-2']}
    assert not expect(admin.get(BASE+'/demo-student-2'))['active']
    with app.state.database.connect() as conn:
        assert not conn.execute("SELECT 1 FROM users WHERE email='duplicate-global@example.invalid'").fetchone()


@pytest.mark.parametrize('bad_row', [
    'Different,demo-student-1@example.invalid,admin,Synthetic-import1',

    'Bad password,bad-password@example.invalid,student,no-digit-password',
    'No password,no-password@example.invalid,teacher,',
    ',missing-name@example.invalid,admin,Synthetic-import1',
])
def test_any_error_blocks_every_creation_without_credential_echo(admin, app, bad_row):
    content = ('name,email,role,temporary_password\nValid,valid-first@example.invalid,student,Synthetic-import1\n'+bad_row+'\n').encode()
    reviewed = expect(preview(admin, content))
    assert reviewed['valid_count'] == 1 and reviewed['error_count'] == 1
    assert 'Synthetic-import1' not in str(reviewed) and 'no-digit-password' not in str(reviewed)
    expect(commit(admin, reviewed['import_id']), 422)
    with app.state.database.connect() as conn:
        assert not conn.execute("SELECT 1 FROM users WHERE email='valid-first@example.invalid'").fetchone()


@pytest.mark.parametrize('change', ['create','role','disable','name','delete'])
def test_stale_review_is_atomic_and_does_not_create_earlier_valid_rows(admin, app, change):
    text = 'name,email,role,temporary_password\nFirst,stale-first@example.invalid,student,Synthetic-stale1\nExisting,demo-student-2@example.invalid,student,\n'
    if change == 'create':
        text = text.replace('demo-student-2@example.invalid','stale-new@example.invalid')
    reviewed = expect(preview(admin, text.encode(), default_temporary_password=PASSWORD))
    assert reviewed['error_count'] == 0
    if change == 'create':
        account(admin, role='student', suffix='stale-new')
    elif change == 'role':
        expect(admin.patch(BASE+'/demo-student-2', json={'role':'teacher'}))
    elif change == 'disable':
        expect(admin.put(BASE+'/demo-student-2/status', json={'active':False}))
    else:
        with app.state.database.connect() as conn:
            if change == 'name':
                conn.execute("UPDATE users SET name='Changed since review' WHERE id='demo-student-2'")
            else:
                conn.execute("DELETE FROM enrollments WHERE user_id='demo-student-2'")
                conn.execute("DELETE FROM users WHERE id='demo-student-2'")
    expect(commit(admin, reviewed['import_id']), 409)
    with app.state.database.connect() as conn:
        assert not conn.execute("SELECT 1 FROM users WHERE email='stale-first@example.invalid'").fetchone()
        assert conn.execute('SELECT status FROM account_imports WHERE id=?', (reviewed['import_id'],)).fetchone()[0] == 'pending'


def test_scope_expiry_permissions_csrf_and_pending_capacity(app, admin, teacher):
    text = b'name,email\nNew,new-capacity@example.invalid\n'
    reviewed = expect(preview(admin, text, default_temporary_password=PASSWORD))
    iid = reviewed['import_id']
    expect(preview(teacher, text), 403)
    expect(teacher.get(IMPORT+'/'+iid), 403)
    expect(commit(teacher, iid), 403)
    expect(admin.post(IMPORT+'/'+iid+'/commit', json={}, headers={'Origin':'https://attacker.invalid'}), 403)
    expect(admin.post(IMPORT+'/'+iid+'/commit', json={'role':'admin'}), 422)
    other = account(admin, role='admin', suffix='other-review-owner')
    with actor_client(app, other['id']) as outsider:
        expect(outsider.get(IMPORT+'/'+iid), 404)
        expect(commit(outsider, iid), 404)
    with app.state.database.connect() as conn:
        conn.execute("UPDATE account_imports SET expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (iid,))
    expect(admin.get(IMPORT+'/'+iid), 410)
    expect(commit(admin, iid), 410)
    with app.state.database.connect() as conn:
        maintenance(conn)
        assert not conn.execute('SELECT 1 FROM account_imports WHERE id=?', (iid,)).fetchone()
        expiry = (datetime.now(timezone.utc)+timedelta(minutes=30)).isoformat()
        for i in range(30):
            conn.execute("INSERT INTO account_imports VALUES(?,?,?,'pending','[]',NULL)", ('capacity-'+str(i),'demo-admin',expiry))
    expect(preview(admin, text, default_temporary_password=PASSWORD), 429)


@pytest.mark.parametrize('data,suffix,status', [
    (b'name,email,role,role\nX,x@example.invalid,student,student\n','.csv',422),
    (b'name,email,unknown\nX,x@example.invalid,x\n','.csv',422),
    (b'name,email\nX,x@example.invalid,secret-extra1\n','.csv',422),
    (b'\xff','.csv',422),
    (b'name,email\n','.csv',422),
    (b'not a zip','.xlsx',422),
    (b'name,email\nX,x@example.invalid\n','.txt',415),
    (b'x'*(MAX_BYTES+1),'.csv',413),
], ids=['duplicate-header','unknown-header','extra-column','encoding','empty','bad-zip','extension','2mib'])
def test_parser_resources_are_safe(admin, data, suffix, status):
    response = preview(admin, data, suffix=suffix)
    expect(response, status)
    assert 'secret-extra1' not in response.text


def test_row_formula_and_actual_xlsx_expansion_guards(admin):
    expect(preview(admin, b'name,email,role,temporary_password\nBad,invalid-role@example.invalid,owner,Synthetic-import1\n'), 422)
    expect(preview(admin, ('name,email\n'+'X,x@example.invalid\n'*1001).encode()), 413)
    expect(preview(admin, xlsx([['name','email','role'],['X','x@example.invalid','=1+1']]), suffix='.xlsx'), 422)
    import struct, zipfile, zlib
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('xl/worksheets/sheet1.xml', b'<x/>'+b'A'*10000)
    data = bytearray(output.getvalue())
    central = data.index(b'PK\x01\x02')
    crc = zlib.crc32(b'<x/>') & 0xffffffff
    for position, value in ((14,crc),(22,4),(central+16,crc),(central+24,4)):
        struct.pack_into('<I', data, position, value)
    expect(preview(admin, bytes(data), suffix='.xlsx'), 422)
    assert expect(admin.get(BASE, params={'q':'x@example.invalid'}))['total'] == 0


def test_failed_insert_rolls_back_whole_batch_and_result_then_can_recover(admin, app):
    reviewed = expect(preview(admin, b'name,email\nOne,atomic-one@example.invalid\nTwo,atomic-two@example.invalid\n', default_temporary_password=PASSWORD))
    iid = reviewed['import_id']
    with app.state.database.connect() as conn:
        conn.execute("CREATE TRIGGER stage11_failure BEFORE INSERT ON users WHEN NEW.email='atomic-two@example.invalid' BEGIN SELECT RAISE(ABORT,'Synthetic failure'); END")
    expect(commit(admin, iid), 409)
    with app.state.database.connect() as conn:
        assert not conn.execute("SELECT 1 FROM users WHERE email='atomic-one@example.invalid'").fetchone()
        assert conn.execute('SELECT result_json FROM account_imports WHERE id=?', (iid,)).fetchone()[0] is None
        conn.execute('DROP TRIGGER stage11_failure')
    result = expect(commit(admin, iid))
    assert result['created'] == 2 and expect(commit(admin, iid)) == result


def test_concurrent_commit_returns_identical_exact_ids_once(admin, app):
    reviewed = expect(preview(admin, b'name,email\nOnce,concurrent-once@example.invalid\n', default_temporary_password=PASSWORD))
    barrier = threading.Barrier(2)
    def work():
        barrier.wait(timeout=5)
        with app.state.database.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            actor = public_user(conn.execute("SELECT * FROM users WHERE id='demo-admin'").fetchone(), conn)
            return commit_accounts(conn, reviewed['import_id'], actor)
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(work) for _ in range(2)]
        results = [j.result(timeout=15) for j in jobs]
    assert results[0] == results[1] and results[0]['created'] == 1
    with app.state.database.connect() as conn:
        assert conn.execute("SELECT count(*) FROM users WHERE email='concurrent-once@example.invalid'").fetchone()[0] == 1
