"""Bounded native Office inventory. No model calls or workbook solving."""
from __future__ import annotations
import io
import json
import posixpath
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath
import xml.etree.ElementTree as ET
if __package__:
    from .archive_guard import office_guard
else:
    from archive_guard import office_guard

XML_LIMIT = 16 * 1024 * 1024
IMAGE_PIXELS = 16_000_000
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
P = '{http://schemas.openxmlformats.org/presentationml/2006/main}'
A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def xml_part(archive, name):
    info = archive.getinfo(name)
    if info.file_size > XML_LIMIT:
        raise ValueError('Office XML part exceeds16MiB')
    data = archive.read(name)
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('Office XML entities are unsupported')
    return ET.fromstring(data)


def rels(archive, name):
    filename = posixpath.join(posixpath.dirname(name), '_rels', posixpath.basename(name)+'.rels')
    if filename not in archive.namelist():
        return {}
    result = {}
    for rel in xml_part(archive, filename):
        target = rel.get('Target','')
        external = rel.get('TargetMode') == 'External'
        typ = rel.get('Type','')
        if external and not typ.endswith('/hyperlink'):
            raise ValueError('External Office linked content is unsupported')
        resolved = target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join(posixpath.dirname(name),target))
        if not external and (resolved.startswith('../') or ':' in resolved or '\\' in resolved):
            raise ValueError('Unsafe Office relationship')
        result[rel.get('Id')] = {'target':resolved, 'external':external, 'type':typ}
    return result


def preflight(source, fmt):
    """Before Office readers/LibreOffice: real deflate bounds, names, rasters."""
    office_guard(source)
    from PIL import Image
    images = []
    with zipfile.ZipFile(source) as archive:
        names = archive.namelist()
        required = {'pptx':'ppt/presentation.xml', 'docx':'word/document.xml', 'xlsx':'xl/workbook.xml'}[fmt]
        if required not in names or '[Content_Types].xml' not in names:
            raise ValueError('Office package does not match original suffix')
        for info in archive.infolist():
            name = info.filename
            path = PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or ':' in name or '\\' in name or stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError('Unsafe Office archive member')
            if info.file_size > 64*1024*1024:
                raise ValueError('Office part exceeds64MiB')
            if name.endswith(('.xml','.rels')):
                xml_part(archive,name)
            if name.endswith('.rels'):
                for rel in xml_part(archive,name):
                    if rel.get('TargetMode')=='External' and not rel.get('Type','').endswith('/hyperlink'):
                        raise ValueError('External Office linked content is unsupported')
            if name.lower().endswith(('vbaproject.bin',)):
                raise ValueError('Macro-bearing Office document is unsupported')
            if '/media/' not in name or name.endswith('/'):
                continue
            data = archive.read(name)
            row = {'part':name, 'bytes':len(data), 'raster_pixels':None, 'format':'non_raster_or_unsupported'}
            if name.lower().endswith(('.png','.jpg','.jpeg','.gif','.bmp','.tif','.tiff','.webp')):
                with Image.open(io.BytesIO(data)) as image:
                    pixels = image.width * image.height
                    if pixels > IMAGE_PIXELS:
                        raise ValueError('Office embedded raster exceeds16million source pixels')
                    row.update(raster_pixels=pixels,format=image.format,frames=getattr(image,'n_frames',1))
            images.append(row)
    return images


def inventory(source, fmt, raw):
    """Preserve auxiliary XML/media and precise Office-part native provenance.

    Page locators are supplied later by the rendered PDF; Office XML coordinates
    and source-part references are not guessed to be PDF block relationships.
    """
    if fmt == 'xlsx':
        from tools.material_stage16.workbook_inventory import inventory as workbook_inventory
        return workbook_inventory(source, raw)
    media = preflight(source, fmt)
    raw = Path(raw); raw.mkdir(parents=True,exist_ok=True)
    result = {'source_format':fmt, 'native_units':[], 'notes':[], 'media':media,
              'image_references':[], 'auxiliary_parts':[], 'warnings':[]}
    with zipfile.ZipFile(source) as archive:
        names = archive.namelist()
        for ordinal,row in enumerate(media):
            suffix = Path(row['part']).suffix.lower()
            if not re.fullmatch(r'\.[a-z0-9]{1,8}', suffix): suffix='.bin'
            ref = f'office-media/m{ordinal:04}{suffix}'
            (raw/'office-media').mkdir(exist_ok=True)
            (raw/ref).write_bytes(archive.read(row['part']))
            row['raw_asset'] = 'raw/'+ref
        if fmt=='pptx':
            presentation = xml_part(archive,'ppt/presentation.xml')
            mapping = rels(archive,'ppt/presentation.xml')
            parts = [mapping[s.get(R+'id')]['target'] for s in presentation.findall('.//'+P+'sldId')]
            result['slides_expected'] = len(parts)
        else:
            parts = ['word/document.xml']
            parts += sorted(n for n in names if re.fullmatch(r'word/(header|footer)\d+\.xml',n))
        for ordinal,name in enumerate(parts,1):
            tree = xml_part(archive,name)
            mapping = rels(archive,name)
            units=[]
            for i,element in enumerate(tree.iter()):
                if element.tag in (A+'p', W+'p'):
                    text=''.join(t.text or '' for t in element.iter() if t.tag in (A+'t',W+'t'))
                    if text:
                        units.append({'ordinal':len(units),'text':text})
                if element.tag == A+'blip':
                    rid=element.get(R+'embed') or element.get(R+'link')
                    target=mapping.get(rid)
                    result['image_references'].append({'part':name,'unit':ordinal,'xml_node':i,
                        'relationship_id':rid,'media_part':target['target'] if target else None})
            result['native_units'].append({'unit':ordinal,'part':name,'paragraphs':units,
                'hidden':fmt=='pptx' and tree.get('show')=='0'})
            if fmt=='pptx':
                notes=[r['target'] for r in mapping.values() if r['type'].endswith('/notesSlide')]
                for note in notes:
                    note_tree=xml_part(archive,note)
                    text='\n'.join(''.join(t.text or '' for t in e.iter(A+'t')) for e in note_tree.iter(A+'p'))
                    result['notes'].append({'slide':ordinal,'part':note,'text':text})
        # Keep parts whose text is not necessarily present in the rendered PDF.
        # Also retain masters/layouts/relationships so unrendered content is not
        # silently represented as student-reading coverage.
        aux=[n for n in names if n.endswith(('.xml','.rels'))]
        (raw/'office-parts').mkdir(exist_ok=True)
        for ordinal,name in enumerate(aux):
            ref=f'office-parts/part{ordinal:04}.xml'
            (raw/ref).write_bytes(archive.read(name))
            result['auxiliary_parts'].append({'part':name,'raw_asset':'raw/'+ref})
            if fmt=='docx' and re.fullmatch(r'word/(comments|footnotes|endnotes)\.xml',name):
                tree=xml_part(archive,name)
                result['notes'].append({'part':name,'text':'\n'.join(t.text or '' for t in tree.iter(W+'t'))})
        if fmt=='pptx':
            result['warnings'].append('Hidden slides are included in the rendered slide set. Speaker notes, masters/layouts and off-slide objects are retained as native inventory; supported supplementary text is indexed separately by the application with its own visibility policy.')
        else:
            result['warnings'].append('Comments, footnotes/endnotes, headers/footers and embedded objects are retained where available; only rendered page content enters reading blocks.')
    result['native_text_chars'] = sum(len(p['text']) for u in result['native_units'] for p in u['paragraphs'])
    result['notes_text_chars'] = sum(len(n['text']) for n in result['notes'])
    result['media_count'] = len(media)
    (raw/'office-inventory.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return result


def binary_doc_inventory(source):
    import olefile
    if not olefile.isOleFile(source):
        raise ValueError('Legacy DOC requires a valid OLE compound document')
    with olefile.OleFileIO(source) as ole:
        streams=ole.listdir(streams=True,storages=False)
        if len(streams)>4096:
            raise ValueError('Legacy DOC exceeds4096streams')
        rows=[{'stream':'/'.join(n),'bytes':ole.get_size(n)} for n in streams]
        if not any(r['stream']=='WordDocument' for r in rows):
            raise ValueError('OLE document is not Word DOC')
        if any('vba' in r['stream'].lower() or 'macros' in r['stream'].lower() for r in rows):
            raise ValueError('Macro-bearing legacy DOC is unsupported')
        return {'streams':rows,'native_auxiliary_coverage':'derived_docx_only',
                'warnings':['Legacy binary DOC auxiliary/OLE objects are inventoried, not semantically decoded. Derived DOCX/PDF are not the original identity.']}
