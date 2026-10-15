"""Authenticated seed diagram resolution through existing edition/course gates."""
import json
from pathlib import Path
from fastapi import HTTPException
from .version_context import is_staff, session_access


def resolve_catalog_asset(conn, root, asset_path, user, version_id=None):
    """Only an authorized question reference permits a trusted catalog figure.

    Unlike a material original, the same seed figure may occur in several
    editions/courses. Try every authorized reference, preserving historical
    access for a learner with a saved run without granting draft-only access.
    """
    root = Path(root).resolve()
    relative = Path(asset_path)
    if relative.is_absolute() or '..' in relative.parts or '\\' in asset_path or ':' in asset_path:
        raise HTTPException(404, 'Question figure not found')
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or path.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp', '.svg'} or not path.is_file():
        raise HTTPException(404, 'Question figure not found')
    if version_id is not None and not version_id:
        raise HTTPException(422, 'version_id must not be blank')
    wanted = '/api/assets/' + asset_path
    if is_staff(user):
        course_filter = 'EXISTS (SELECT 1 FROM course_staff cs WHERE cs.course_id=c.id AND cs.user_id=?)'
    else:
        course_filter = 'EXISTS (SELECT 1 FROM enrollments e WHERE e.course_id=c.id AND e.user_id=?)'
    if is_staff(user) and version_id is None:
        for row in conn.execute('SELECT s.id,s.content_json FROM sessions s JOIN courses c ON c.id=s.course_id WHERE ' + course_filter, (user['id'],)):
            if _references(json.loads(row['content_json']), wanted) and _authorized_reference(conn, row['id'], user, None, wanted):
                return path
    query = 'SELECT v.id,v.snapshot_json FROM course_versions v JOIN courses c ON c.id=v.course_id WHERE ' + course_filter
    params = (user['id'],)
    if version_id is not None:
        query += ' AND v.id=?'
        params += (version_id,)
    for row in conn.execute(query, params):
        for saved in json.loads(row['snapshot_json']).get('sessions', []):
            if _references(saved, wanted) and _authorized_reference(conn, saved['id'], user, row['id'], wanted):
                return path
    raise HTTPException(404, 'Question figure not found in an authorized edition')


def _authorized_reference(conn, sid, user, vid, wanted):
    try:
        detail = session_access(conn, sid, user, vid)
    except HTTPException as exc:
        if exc.status_code in (403, 404, 410):
            return False
        raise
    return _references(detail, wanted)


def _references(detail, wanted):
    return any(image.get('url', '').split('?', 1)[0] == wanted
               for question in detail.get('questions', []) for image in question.get('images', []))
