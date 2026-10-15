"""Strict lossless decoding shared by upload validation and full text parsing."""

def decode_text(data):
    if data.startswith((b'\xff\xfe\x00\x00',b'\x00\x00\xfe\xff')):
        encoding='utf-32'
    elif data.startswith((b'\xff\xfe',b'\xfe\xff')):
        encoding='utf-16'
    elif data.startswith(b'\xef\xbb\xbf'):
        encoding='utf-8-sig'
    else:
        try:
            data.decode('utf-8');encoding='utf-8'
        except UnicodeDecodeError:
            encoding='gb18030'
    try:
        text=data.decode(encoding,errors='strict')
    except UnicodeError:
        raise ValueError('Text source must use valid UTF-8, BOM-marked UTF-16/32 or GB18030')from None
    if any(ord(c)<32 and c not in '\t\n\r'for c in text):
        raise ValueError('Binary/control content is not a plain-text source')
    return text,encoding
