"""Administrator registration switch in the existing SQLite settings table."""
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, StrictBool

from .auth import session_user

REGISTRATION_KEY = 'registration_enabled'


class AccessSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    registration_enabled: StrictBool


def registration_enabled(conn):
    row = conn.execute('SELECT value FROM settings WHERE key=?', (REGISTRATION_KEY,)).fetchone()
    # Existing installations are unchanged; malformed stored overrides fail closed.
    return row is None or row[0] == 'true'


def require_registration(conn):
    if not registration_enabled(conn):
        raise HTTPException(403, 'Registration is currently closed')


def register_access_settings_routes(application, database, admin_user, cookie_name, demo_enabled):
    @application.get('/api/admin/access-settings')
    def get_access_settings(user=Depends(admin_user)):
        with database.connect() as conn:
            conn.execute('BEGIN')
            from .course_staff import live_actor
            live_actor(conn, user, admin=True)
            return {'registration_enabled': registration_enabled(conn)}

    @application.put('/api/admin/access-settings')
    def put_access_settings(payload: AccessSettings, request: Request,
                            user=Depends(admin_user)):
        with database.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            # Re-check live authorization while holding the same write lock as
            # register, archive, promote, and password/session revocation writes.
            row = session_user(conn, request.cookies.get(cookie_name), demo_enabled=demo_enabled)
            if row['role'] != 'admin' or row['must_change_password']:
                raise HTTPException(403, 'Administrator access required')
            value = 'true' if payload.registration_enabled else 'false'
            conn.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (REGISTRATION_KEY, value))
            return {'registration_enabled': registration_enabled(conn)}
