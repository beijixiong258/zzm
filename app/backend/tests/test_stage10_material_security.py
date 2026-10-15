"""Stage10 helper authorization/history compatibility; isolated synthetic DB."""
import json
from pathlib import Path
import struct
import zipfile
import pytest
from fastapi import HTTPException
from backend.aicademiya.material_security import resolve_catalog_asset
from backend.aicademiya.extraction_limits import office_guard
from .conftest import demo_client, expect, publish


def user(client):
    return expect(client.get('/api/auth/me'))['user']


def test_catalog_figure_helper_preserves_current_history_owner_and_archive(app, catalog, teacher, student, admin):
    root = catalog.parent / 'assets'
    owner, learner, other_owner = user(teacher), user(student), user(admin)
    old = expect(teacher.get('/api/teacher/courses/synthetic-course/versions'))['current_version_id']
    expect(student.get('/api/sessions/s4/workspace?version_id=' + old))
    with app.state.database.connect() as conn:
        assert resolve_catalog_asset(conn, root, 'plot.png', owner).read_bytes().startswith(b'\x89PNG')
        assert resolve_catalog_asset(conn, root, 'plot.png', learner, old).is_file()
        with pytest.raises(HTTPException) as error:
            resolve_catalog_asset(conn, root, 'plot.png', other_owner)
        assert error.value.status_code == 404
    # New draft removes the old reference; a saved old student run keeps it.
    detail = expect(teacher.get('/api/sessions/s4'))
    questions = detail['questions']
    for question in questions:
        question['images'] = []
    expect(teacher.patch('/api/sessions/s4', json={'questions': questions}))
    new = publish(teacher)['id']
    with demo_client(app, 'student', 2) as new_learner:
        fresh = user(new_learner)
        with app.state.database.connect() as conn:
            assert resolve_catalog_asset(conn, root, 'plot.png', learner).is_file()
            with pytest.raises(HTTPException):
                resolve_catalog_asset(conn, root, 'plot.png', learner, new)
            with pytest.raises(HTTPException):
                resolve_catalog_asset(conn, root, 'plot.png', fresh)
            conn.execute("UPDATE enrollments SET archived_at='2026-10-01T00:00:00+00:00',purge_at='2099-01-01T00:00:00+00:00' WHERE user_id=?", (learner['id'],))
            assert resolve_catalog_asset(conn, root, 'plot.png', learner, old).is_file()
    # Trash is still an absolute access closure, including saved diagrams.
    expect(teacher.post('/api/courses/synthetic-course/trash', json={}))
    with app.state.database.connect() as conn:
        for identity in (owner, learner):
            with pytest.raises(HTTPException):
                resolve_catalog_asset(conn, root, 'plot.png', identity, old)


@pytest.mark.parametrize('value', ['../materials/key.txt', '/absolute.png', 'C:/Windows/file.png', '..\\file.png', 'missing.png', 'plot.svg/../plot.png'])
def test_catalog_asset_helper_traversal(app, catalog, teacher, value):
    with app.state.database.connect() as conn:
        with pytest.raises(HTTPException) as error:
            resolve_catalog_asset(conn, catalog.parent / 'assets', value, user(teacher))
        assert error.value.status_code == 404


def test_catalog_draft_only_reference_is_teacher_only(app, catalog, teacher, student):
    root = catalog.parent / 'assets'
    (root / 'draft-only.png').write_bytes(b'SYNTHETIC_DRAFT_FIGURE')
    with app.state.database.connect() as conn:
        detail = json.loads(conn.execute("SELECT content_json FROM sessions WHERE id='s4'").fetchone()[0])
        detail['questions'][0]['images'] = [{'url': '/api/assets/draft-only.png'}]
        conn.execute("UPDATE sessions SET content_json=? WHERE id='s4'", (json.dumps(detail),))
    with app.state.database.connect() as conn:
        assert resolve_catalog_asset(conn, root, 'draft-only.png', user(teacher)).read_bytes() == b'SYNTHETIC_DRAFT_FIGURE'
        with pytest.raises(HTTPException):
            resolve_catalog_asset(conn, root, 'draft-only.png', user(student))


def test_synthetic_http_hook_uses_auth_course_gate_and_private_cache(app, catalog, teacher, student, admin):
    # Exercise the handed-off route hook on the ISOLATED app only. Production
    # main.py is not modified here; its two direct route-gate repros stay strict.
    from fastapi import Depends
    from fastapi.responses import FileResponse
    from fastapi.testclient import TestClient
    download = next(route for route in app.router.routes if getattr(route, 'path', '') == '/api/materials/{material_id}/download')
    current_user = download.dependant.dependencies[0].call
    app.router.routes[:] = [route for route in app.router.routes if getattr(route, 'path', '') != '/api/assets/{asset_path:path}']
    @app.get('/api/assets/{asset_path:path}')
    def figure(asset_path: str, version_id: str | None = None, identity=Depends(current_user)):
        with app.state.database.connect() as conn:
            path = resolve_catalog_asset(conn, catalog.parent / 'assets', asset_path, identity, version_id)
        return FileResponse(path, headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'private, no-store'})
    # Added after the SPA catchall: move it before the catchall in this harness.
    app.router.routes.insert(0, app.router.routes.pop())
    for client in (teacher, student):
        response = client.get('/api/assets/plot.png')
        assert response.status_code == 200 and response.content.startswith(b'\x89PNG')
        assert response.headers['cache-control'] == 'private, no-store'
        assert response.headers['x-content-type-options'] == 'nosniff'
    assert admin.get('/api/assets/plot.png').status_code == 404
    with TestClient(app) as anonymous:
        assert anonymous.get('/api/assets/plot.png').status_code == 401
    with demo_client(app, 'student', 2) as other:
        uid = user(other)['id']
        with app.state.database.connect() as conn:
            conn.execute('DELETE FROM enrollments WHERE user_id=?', (uid,))
        assert other.get('/api/assets/plot.png').status_code == 404


def test_forged_office_count_is_refused_before_zipinfo_allocation(tmp_path, monkeypatch):
    path = tmp_path / 'forged.docx'
    with zipfile.ZipFile(path, 'w') as archive:
        for number in range(20):
            archive.writestr(f'part{number}.xml', '<x/>')
    data = bytearray(path.read_bytes())
    end = data.rfind(b'PK\x05\x06')
    struct.pack_into('<HH', data, end + 8, 1, 1)
    path.write_bytes(data)
    calls = []
    monkeypatch.setattr(zipfile, 'ZipFile', lambda *a, **kw: calls.append(1))
    with pytest.raises(ValueError, match='entry count'):
        office_guard(path)
    assert calls == []


def test_forged_office_expanded_size_cannot_bypass_declared_budget(tmp_path):
    path = tmp_path / 'forged-size.docx'
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('word/document.xml', b'<x/>' + b'A' * 10000)
    data = bytearray(path.read_bytes())
    central = data.index(b'PK\x01\x02')
    # ZipExtFile truncates output to its forged size after decompression. Its CRC
    # then validates only this prefix, so metadata-only preflight is insufficient.
    import zlib
    crc = zlib.crc32(b'<x/>') & 0xffffffff
    struct.pack_into('<I', data, 14, crc)
    struct.pack_into('<I', data, 22, 4)
    struct.pack_into('<I', data, central + 16, crc)
    struct.pack_into('<I', data, central + 24, 4)
    path.write_bytes(data)
    with zipfile.ZipFile(path) as archive:
        assert archive.read('word/document.xml') == b'<x/>'
    with pytest.raises(ValueError, match='(?i)(expanded|declared|size)'):
        office_guard(path, max_expanded=100)


def test_office_expansion_and_duplicate_bounds(tmp_path):
    duplicate = tmp_path / 'duplicate.docx'
    with zipfile.ZipFile(duplicate, 'w') as archive:
        archive.writestr('part.xml', 'x')
        with pytest.warns(UserWarning):
            archive.writestr('part.xml', 'y')
    with pytest.raises(ValueError, match='duplicate'):
        office_guard(duplicate)
    expanded = tmp_path / 'expanded.docx'
    with zipfile.ZipFile(expanded, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('part.xml', 'x' * 1024)
    with pytest.raises(ValueError, match='Expanded Office'):
        office_guard(expanded, max_expanded=100)
