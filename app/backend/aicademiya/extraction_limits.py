"""Bounds shared by uploaded Office extraction; no extraction/network side effects."""
from pathlib import Path
from contextlib import nullcontext
import struct
import zipfile
import zlib

MAX_OFFICE_ENTRIES = 4096
MAX_EXPANDED_BYTES = 100 * 1024 * 1024


def _open_source(source):
    return nullcontext(source) if hasattr(source, "read") else Path(source).open("rb")


def office_guard(path, *, max_expanded=MAX_EXPANDED_BYTES):
    # Read the bounded end record before ZipFile constructs every ZipInfo.
    # Uploads are <=25 MiB: ZIP64/multi-disk packages are unnecessary here.
    with _open_source(path) as file:
        file.seek(0, 2)
        size = file.tell()
        file.seek(max(0, size - 65557))
        tail = file.read(65557)
    offset = tail.rfind(b'PK\x05\x06')
    if offset < 0 or len(tail) - offset < 22:
        raise ValueError('Office archive has no valid end record')
    _, disk, directory_disk, disk_entries, entries, directory_size, directory_offset, comment = struct.unpack_from('<4s4H2LH', tail, offset)
    if len(tail) - offset != 22 + comment or disk or directory_disk or disk_entries != entries:
        raise ValueError('Office archive end record is invalid or multi-disk')
    if entries == 65535 or directory_size == 0xffffffff or directory_offset == 0xffffffff:
        raise ValueError('Office archive ZIP64 entries are not supported')
    if entries > MAX_OFFICE_ENTRIES:
        raise ValueError(f'Office archive exceeds the {MAX_OFFICE_ENTRIES}-entry limit')
    end_offset = size - len(tail) + offset
    if directory_offset + directory_size != end_offset:
        raise ValueError('Office archive directory bounds are invalid')
    # A forged EOCD entry count must not send unlimited central-directory
    # records into ZipFile. Walk fixed headers and skip bounded variable fields.
    with _open_source(path) as file:
        file.seek(directory_offset)
        consumed = count = 0
        while consumed < directory_size:
            header = file.read(46)
            if len(header) != 46 or header[:4] != b'PK\x01\x02':
                raise ValueError('Office archive directory entry is invalid')
            name_size, extra_size, comment_size = struct.unpack_from('<3H', header, 28)
            record_size = 46 + name_size + extra_size + comment_size
            consumed += record_size
            count += 1
            if count > MAX_OFFICE_ENTRIES or consumed > directory_size:
                raise ValueError('Office archive directory entries exceed the limit or bounds')
            file.seek(record_size - 46, 1)
        if count != entries:
            raise ValueError('Office archive directory entry count is invalid')
    with zipfile.ZipFile(path) as archive:
        items = archive.infolist()
        if len(items) != entries or len(items) > MAX_OFFICE_ENTRIES:
            raise ValueError('Office archive entry count is invalid or exceeds the limit')
        if sum(item.file_size for item in items) > max_expanded:
            raise ValueError('Expanded Office document exceeds the 100 MiB extraction size limit')
        # Office readers select members in memory, never extract filesystem paths.
        # Duplicate names make selection ambiguous and can evade package checks.
        if len({item.filename for item in items}) != len(items):
            raise ValueError('Office archive has duplicate entries')
        # Headers are attacker-controlled: ZipExtFile.read() may decompress a
        # huge chunk then truncate it to forged file_size (and validate prefix
        # CRC). Check real deflate output with max_length BEFORE Office readers.
        with _open_source(path) as file:
            for item in items:
                _verify_member(file, item, directory_offset)


def _verify_member(file, item, directory_offset):
    if item.flag_bits & 1 or item.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
        raise ValueError('Office archive uses encrypted or unsupported compression')
    file.seek(item.header_offset)
    header = file.read(30)
    if len(header) != 30 or header[:4] != b'PK\x03\x04':
        raise ValueError('Office archive local member header is invalid')
    name_size, extra_size = struct.unpack_from('<HH', header, 26)
    start = item.header_offset + 30 + name_size + extra_size
    if start < 0 or start + item.compress_size > directory_offset:
        raise ValueError('Office archive compressed member bounds are invalid')
    file.seek(start)
    remaining = item.compress_size
    decoder = zlib.decompressobj(-15) if item.compress_type == zipfile.ZIP_DEFLATED else None
    count = crc = 0
    while remaining:
        data = file.read(min(65536, remaining))
        if not data:
            raise ValueError('Office archive compressed member is truncated')
        remaining -= len(data)
        while data:
            if decoder:
                output = decoder.decompress(data, min(65536, item.file_size - count + 1))
                data = decoder.unconsumed_tail
            else:
                output, data = data, b''
            count += len(output)
            if count > item.file_size:
                raise ValueError('Office archive expanded member exceeds its declared size')
            crc = zlib.crc32(output, crc)
        if decoder and decoder.eof and (decoder.unused_data or remaining):
            raise ValueError('Office archive compressed member has trailing data')
    if decoder and not decoder.eof:
        raise ValueError('Office archive compressed member did not complete')
    if count != item.file_size or crc != item.CRC:
        raise ValueError('Office archive expanded size or checksum is invalid')
