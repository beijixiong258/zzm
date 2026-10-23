"""Roster XLSX must share the pre-decompression guard, not trust declared sizes."""
import io
import struct
import zipfile
import zlib
import pytest
from fastapi import HTTPException
from backend.aicademiya.roster import parse_rows


def test_forged_xlsx_size_rejected_before_workbook_reader(monkeypatch):
    out = io.BytesIO()
    payload = b'HEAD' + b'A' * 10000
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('xl/sharedStrings.xml', payload)
    data = bytearray(out.getvalue())
    central = data.index(b'PK\x01\x02')
    crc = zlib.crc32(payload[:4])
    struct.pack_into('<L', data, 14, crc)
    struct.pack_into('<L', data, 22, 4)
    struct.pack_into('<L', data, central + 16, crc)
    struct.pack_into('<L', data, central + 24, 4)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert z.read('xl/sharedStrings.xml') == b'HEAD'
    reached = []
    def reader(*args, **kwargs):
        reached.append(True)
        raise ValueError('Synthetic reader reached')
    monkeypatch.setattr('openpyxl.load_workbook', reader)
    with pytest.raises(HTTPException) as error:
        parse_rows(bytes(data), '.xlsx')
    assert error.value.status_code == 422
    assert reached == [], 'Unverified deflate stream reached the workbook parser'


def test_normal_xlsx_import_still_works():
    from openpyxl import Workbook
    book = Workbook()
    book.active.append(['name', 'email'])
    book.active.append(['Synthetic learner', 'synthetic@example.invalid'])
    out = io.BytesIO()
    book.save(out)
    book.close()
    rows = parse_rows(out.getvalue(), '.xlsx')
    assert len(rows) == 1 and rows[0][1]['email'] == 'synthetic@example.invalid'
