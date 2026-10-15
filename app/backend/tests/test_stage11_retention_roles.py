"""Role transitions must not make legacy retention fail on former-staff references."""
from datetime import datetime, timezone
import pytest
from backend.aicademiya.roster import maintenance

AT = datetime(2026,10,8,tzinfo=timezone.utc)

def former(conn):
    # Isolated post-transition state; no production account or raw credential.
    conn.execute("INSERT INTO users(id,name,email,role,archived_at,purge_at) VALUES('former-staff','Former staff','former@example.invalid','student','2000-01-01T00:00:00+00:00','2000-02-01T00:00:00+00:00')")

def test_expired_account_import_does_not_block_former_admin_retention(app,teacher):
    with app.state.database.connect() as c:
        former(c)
        c.execute("INSERT INTO account_imports VALUES('old-import','former-staff','2000-01-01T00:00:00+00:00','pending','[]',NULL)")
        result=maintenance(c,at=AT)
        assert 'former-staff' in result['accounts']
        assert c.execute("SELECT 1 FROM users WHERE id='former-staff'").fetchone() is None
        assert c.execute("SELECT 1 FROM account_imports WHERE id='old-import'").fetchone() is None
        assert not c.execute('PRAGMA foreign_key_check').fetchall()

@pytest.mark.parametrize('reference',['preview','trash'])
def test_durable_staff_references_retain_disabled_identity_without_blocking_other_retention(app,teacher,reference):
    with app.state.database.connect() as c:
        former(c)
        c.execute("INSERT INTO users(id,name,email,role,archived_at,purge_at) VALUES('ordinary-old','Ordinary old','ordinary@example.invalid','student','2000-01-01T00:00:00+00:00','2000-02-01T00:00:00+00:00')")
        if reference=='preview':
            c.execute("INSERT INTO teacher_previews(session_id,user_id,preview_id,revision,bound_at) VALUES('s4','former-staff','retained-preview','retained-revision','2000-01-01T00:00:00+00:00')")
        else:
            c.execute("INSERT INTO course_trash VALUES('synthetic-course','2000-01-01T00:00:00+00:00','former-staff')")
        result=maintenance(c,at=AT)
        assert 'former-staff' not in result['accounts']
        assert c.execute("SELECT archived_at FROM users WHERE id='former-staff'").fetchone()[0]
        assert c.execute("SELECT 1 FROM users WHERE id='ordinary-old'").fetchone() is None
        table='teacher_previews' if reference=='preview' else'course_trash'
        assert c.execute('SELECT count(*) FROM '+table).fetchone()[0]==1
        assert not c.execute('PRAGMA foreign_key_check').fetchall()

def test_unexpired_admin_import_protects_identity_and_dry_run_is_read_only(app,teacher):
    with app.state.database.connect() as c:
        former(c)
        c.execute("INSERT INTO account_imports VALUES('active-import','former-staff','2099-01-01T00:00:00+00:00','pending','[]',NULL)")
        before=c.total_changes
        dry=maintenance(c,at=AT,dry_run=True)
        assert 'former-staff' not in dry['accounts'] and c.total_changes==before
        result=maintenance(c,at=AT)
        assert 'former-staff' not in result['accounts']
        assert c.execute("SELECT 1 FROM users WHERE id='former-staff'").fetchone()
        assert not c.execute('PRAGMA foreign_key_check').fetchall()
