"""Stage10 isolated security repros; synthetic files/HTTP, no external traffic."""
import gzip
import io
import socket
import struct
import zlib
import zipfile

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.aicademiya import link_materials as links
from backend.aicademiya import worksheet_import as worksheets
from backend.aicademiya import material_extraction as extraction
from .conftest import demo_client, expect, publish


def png(width, height):
    # Valid grayscale PNG without constructing a full raw raster in memory.
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    compressor = zlib.compressobj()
    compressed = bytearray()
    for _ in range(height):
        compressed.extend(compressor.compress(b'\0' * (width + 1)))
    compressed.extend(compressor.flush())
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 0, 0, 0, 0)) + chunk(b'IDAT', bytes(compressed)) + chunk(b'IEND', b'')


def public_dns(monkeypatch):
    monkeypatch.setattr(links.socket, 'getaddrinfo', lambda host, port, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', port))])


def test_encoded_response_is_rejected_before_httpx_decompression(monkeypatch):
    import httpx._decoders
    public_dns(monkeypatch)
    seen = []
    decoded = []
    original = httpx._decoders.GZipDecoder.decode
    def decode(self, data):
        output = original(self, data)
        decoded.append(len(output))
        return output
    monkeypatch.setattr(httpx._decoders.GZipDecoder, 'decode', decode)
    monkeypatch.setattr(links, 'MAX_BYTES', 1000)
    def handler(request):
        seen.append(request.headers.get('accept-encoding'))
        return httpx.Response(200, stream=httpx.ByteStream(gzip.compress(b'A' * 5000)), headers={'content-type': 'text/plain', 'content-encoding': 'gzip'})
    result = links.extract_link('https://example.org/encoded', transport=httpx.MockTransport(handler))
    assert result['status'] == 'error' and not result['excerpt']
    assert decoded == [], f'Expanded allocation occurred before limit check: {decoded}'
    assert seen == ['identity']
    assert 'encoding' in result['warning'].lower()


def test_worksheet_line_budget_is_enforced_before_all_blocks_exist(tmp_path, monkeypatch):
    path = tmp_path / 'many-lines.txt'
    path.write_text('Q\n' * 2500, encoding='utf-8')
    monkeypatch.setattr(worksheets, 'MAX_TEXT', 1000)
    count = []
    original = worksheets._Block
    def block(*args, **kwargs):
        count.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(worksheets, '_Block', block)
    result = worksheets.preview_worksheet(path, assets_dir=tmp_path / 'figures')
    assert result['method'] == 'error' and not result['questions']
    assert len(count) <= 100, f'All {len(count)} blocks allocated before source-size validation'
    assert any('limit' in warning.lower() or 'exceeds' in warning.lower() for warning in result['warnings'])


def test_large_worksheet_figure_is_rejected_before_pixel_decoder(tmp_path, monkeypatch):
    import pymupdf
    calls = []
    original = pymupdf.Pixmap
    def pixmap(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(pymupdf, 'Pixmap', pixmap)
    warnings = []
    assets = worksheets._Assets(tmp_path / 'figures', warnings)
    assert assets.save(png(4100, 4000), 'Synthetic oversized raster') is None
    assert calls == [], 'Pixmap decoded the oversized raster before its pixel limit'
    assert warnings and not assets.assets
    assert not (tmp_path / 'figures').exists()


def test_office_member_count_is_bounded_before_parser(tmp_path):
    path = tmp_path / 'many-members.docx'
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for index in range(5000):
            archive.writestr(f'synthetic/{index}.xml', '<x/>')
    with pytest.raises(ValueError, match='(?i)(entries|members|parts|entry)'):
        extraction._office_guard(path)
    with pytest.raises(ValueError, match='(?i)(entries|members|parts|entry)'):
        worksheets._office_guard(path)


def test_original_material_private_course_and_traversal_guards(app, teacher, student, admin):
    item = expect(teacher.post('/api/sessions/s4/materials', files={'file': ('../../secret.txt', b'SYNTHETIC_PRIVATE_KEY')}, data={'kind': 'answer_key', 'visibility': 'teacher'}))
    assert item['title'] == 'secret.txt'
    publish(teacher)
    for client in (student, admin):
        for url in (item['preview_url'], item['download_url']):
            assert client.get(url).status_code == 403
    assert teacher.get(item['download_url']).content == b'SYNTHETIC_PRIVATE_KEY'
    with TestClient(app) as anonymous:
        assert anonymous.get(item['download_url']).status_code == 401
        assert anonymous.get('/api/assets/%2e%2e%2fmaterials%2fkey.txt').status_code in (401, 403, 404)
        assert anonymous.get('/api/assets/C:%5cWindows%5cwin.ini').status_code in (401, 403, 404)
    for url in ('/api/materials/s4-private/assets/..%5ckey.txt', '/api/materials/s4-private/assets/key.txt', '/api/materials/s4-private/assets/%2e%2e'):
        assert student.get(url).status_code in (403, 404)


def test_seed_question_figure_is_not_anonymous(app, teacher, student):
    # Main-route hook belongs to the parent/auth lane, not this helper lane.
    assert teacher.get('/api/assets/plot.png').status_code == 200
    assert student.get('/api/assets/plot.png').status_code == 200
    with TestClient(app) as anonymous:
        assert anonymous.get('/api/assets/plot.png').status_code == 401


def test_seed_question_figure_cannot_cross_course_enrollment(app, teacher):
    with demo_client(app, 'student', 2) as other:
        uid = expect(other.get('/api/auth/me'))['user']['id']
        with app.state.database.connect() as conn:
            conn.execute('DELETE FROM enrollments WHERE user_id=?', (uid,))
        assert other.get('/api/sessions/s4').status_code == 403
        assert other.get('/api/assets/plot.png').status_code in (403, 404)
