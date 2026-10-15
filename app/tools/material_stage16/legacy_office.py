"""Legacy PPT/XLS container inventory using the worker's existing DOC dependency."""
from pathlib import Path


def binary_inventory(source, fmt):
    import olefile  # Already required by the existing legacy-DOC worker path.
    if fmt not in ('ppt','xls') or not olefile.isOleFile(source):
        raise ValueError('Legacy Office requires a valid OLE compound document')
    if Path(source).stat().st_size > 64*1024*1024:
        raise ValueError('Legacy Office input exceeds64MiB')
    with olefile.OleFileIO(source) as ole:
        streams = ole.listdir(streams=True, storages=False)
        if len(streams) > 4096: raise ValueError('Legacy Office exceeds4096streams')
        rows = [{'stream':'/'.join(n), 'bytes':ole.get_size(n)} for n in streams]
        required = ('PowerPoint Document',) if fmt == 'ppt' else ('Workbook','Book')
        if not any(row['stream'] in required for row in rows):
            raise ValueError('OLE document does not match legacy Office suffix')
        if any(any(marker in row['stream'].lower() for marker in ('vba','macros','encryptioninfo','encryptedpackage')) for row in rows):
            raise ValueError('Macro-bearing or encrypted legacy Office document is unsupported')
        if any(row['bytes'] > 64*1024*1024 for row in rows) or sum(row['bytes'] for row in rows) > 100*1024*1024:
            raise ValueError('Legacy Office streams exceed bounded source bytes')
        return {'source_format':fmt, 'streams':rows, 'native_auxiliary_coverage':'derived_'+('pptx' if fmt=='ppt' else 'xlsx')+'_only',
            'warnings':['Legacy binary '+fmt.upper()+' is inventoried then converted by controlled LibreOffice. Original bytes/hash remain authoritative; converted OOXML formula/cache/text values are conversion-derived, not claimed as the original binary records.']}
