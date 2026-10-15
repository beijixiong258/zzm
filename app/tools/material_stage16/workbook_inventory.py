"""Exact bounded OOXML workbook sources; never evaluate formulas or refresh links.

Enumerate stored cells, not dimension/print ranges. An absent grid cell is not a
stored source cell; explicit blank cells and merged ranges remain distinguishable.
"""
from __future__ import annotations
import json
import re
import zipfile
from pathlib import Path

S = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
MAX_SHEETS = 1000
MAX_CELLS = 200_000
MAX_LEDGER_CHARS = 24_000_000  # <=1000 preview pages; checked again after wrapping.


def coordinate(value):
    if not re.fullmatch(r'[A-Z]{1,3}[1-9][0-9]{0,6}', value or ''):
        raise ValueError('Invalid workbook cell coordinate')
    letters, digits = re.fullmatch(r'([A-Z]+)([0-9]+)', value).groups()
    column = 0
    for letter in letters:
        column = column * 26 + ord(letter) - 64
    row = int(digits)
    if column > 16384 or row > 1048576:
        raise ValueError('Workbook cell coordinate exceeds Excel grid bounds')
    return row, column


def literal_string(node):
    # Rich-text runs concatenate literally; phonetic guides are not cell text.
    if node is None:
        return ''
    pieces = []
    for child in node:
        if child.tag == S+'t': pieces.append(child.text or '')
        elif child.tag == S+'r': pieces.extend(text.text or '' for text in child if text.tag == S+'t')
    return ''.join(pieces)


def read_workbook(source):
    """Return every sheet and stored cell, preserving raw formula/cache identity."""
    from tools.material_stage13.office_inventory import preflight, xml_part, rels
    media = preflight(source, 'xlsx')
    result = {'source_format':'xlsx', 'sheets':[], 'notes':[], 'media':media,
              'native_units':[], 'image_references':[], 'auxiliary_parts':[],
              'warnings':[
                  'Workbook PDF is a paginated native cell ledger, not Excel print-layout rendering. Sheet names/cell coordinates are original-source locators, never original PDF page numbers.',
                  'All stored cells, including explicit blanks and hidden/non-print-area cells, are inventoried. Unstored grid cells are implicit blanks; merged ranges are retained without inventing cell values.',
                  'Formula text and stored cached values are separate. No formula evaluation, macro execution or external refresh is performed; cached values may be stale. Charts and unsupported visual media remain unverified source assets.'],
              'cell_count':0, 'formula_count':0, 'cached_formula_count':0,
              'explicit_blank_count':0, 'coverage_basis':'all_workbook_sheet_relationships_and_stored_cells'}
    with zipfile.ZipFile(source) as archive:
        names = set(archive.namelist())
        root = xml_part(archive, 'xl/workbook.xml')
        if root.tag != S+'workbook':
            raise ValueError('Workbook namespace is unsupported')
        mapping = rels(archive, 'xl/workbook.xml')
        shared = []
        if 'xl/sharedStrings.xml' in names:
            shared = [literal_string(node) for node in xml_part(archive, 'xl/sharedStrings.xml') if node.tag == S+'si']
        result['date_system'] = (root.find(S+'workbookPr').attrib if root.find(S+'workbookPr') is not None else {})
        result['defined_names'] = [dict(node.attrib, text=node.text or '') for node in root.findall(S+'definedNames/'+S+'definedName')]
        nodes = root.findall(S+'sheets/'+S+'sheet')
        if not 1 <= len(nodes) <= MAX_SHEETS:
            raise ValueError('Workbook must contain1..1000sheets')
        seen_parts, seen_names = set(), set()
        for ordinal, node in enumerate(nodes, 1):
            relation = mapping.get(node.get(R+'id'))
            if not relation or relation['external']:
                raise ValueError('Workbook sheet relationship is missing or external')
            part = relation['target']; name = node.get('name', '')
            kind = relation['type'].rsplit('/', 1)[-1]
            if kind not in ('worksheet','chartsheet','dialogsheet'):
                raise ValueError('Macro or unsupported workbook sheet type')
            if part in seen_parts or name in seen_names or not name:
                raise ValueError('Workbook sheet identity is ambiguous')
            seen_parts.add(part); seen_names.add(name)
            tree = xml_part(archive, part)
            if tree.tag != S+kind:
                raise ValueError('Workbook sheet part does not match its relationship')
            sheet = {'unit':ordinal, 'name':name, 'sheet_id':node.get('sheetId'),
                     'part':part, 'kind':kind, 'state':node.get('state','visible'),
                     'cells':[], 'merged_ranges':[], 'rows':[], 'columns':[],
                     'dimension':None, 'hidden':node.get('state','visible') != 'visible'}
            dimension = tree.find(S+'dimension')
            if dimension is not None: sheet['dimension'] = dimension.get('ref')
            sheet['columns'] = [dict(n.attrib) for n in tree.findall(S+'cols/'+S+'col')]
            seen_cells = set()
            for row_node in tree.findall(S+'sheetData/'+S+'row'):
                sheet['rows'].append(dict(row_node.attrib))
                for cell in row_node.findall(S+'c'):
                    ref = cell.get('r'); coordinate(ref)
                    if ref in seen_cells: raise ValueError('Duplicate workbook cell coordinate')
                    seen_cells.add(ref)
                    result['cell_count'] += 1
                    if result['cell_count'] > MAX_CELLS:
                        raise ValueError('Workbook exceeds200000stored cells; no partial cell coverage accepted')
                    formula, cached = cell.find(S+'f'), cell.find(S+'v')
                    typ = cell.get('t','n'); raw_value = cached.text if cached is not None else None
                    value = raw_value
                    if typ == 's' and raw_value is not None:
                        if not re.fullmatch(r'[0-9]+', raw_value) or int(raw_value) >= len(shared):
                            raise ValueError('Workbook shared string index is invalid')
                        value = shared[int(raw_value)]
                    elif typ == 'inlineStr':
                        value = literal_string(cell.find(S+'is'))
                    item = {'coordinate':ref, 'type':typ, 'style':cell.get('s'),
                            'attributes':dict(cell.attrib), 'value':value, 'raw_value':raw_value,
                            'formula':None if formula is None else {'text':formula.text or '', 'attributes':dict(formula.attrib)},
                            'cache_present':formula is not None and cached is not None,
                            'cached_value':value if formula is not None and cached is not None else None,
                            'explicit_blank':formula is None and cached is None and cell.find(S+'is') is None}
                    result['formula_count'] += formula is not None
                    result['cached_formula_count'] += item['cache_present']
                    result['explicit_blank_count'] += item['explicit_blank']
                    sheet['cells'].append(item)
            sheet['merged_ranges'] = [n.get('ref') for n in tree.findall(S+'mergeCells/'+S+'mergeCell')]
            for merged in sheet['merged_ranges']:
                first, separator, last = (merged or '').partition(':')
                coordinate(first); coordinate(last if separator else first)
            sheet['cell_count'] = len(sheet['cells'])
            result['sheets'].append(sheet)
            result['native_units'].append({'unit':ordinal,'part':part,'hidden':sheet['hidden'],
                'sheet_name':name,'paragraphs':[]})
            for relationship in rels(archive, part).values():
                if relationship['type'].endswith('/comments'):
                    note_part = relationship['target']; note_tree = xml_part(archive, note_part)
                    authors = [a.text or '' for a in note_tree.findall(S+'authors/'+S+'author')]
                    for comment in note_tree.findall(S+'commentList/'+S+'comment'):
                        result['notes'].append({'sheet':ordinal,'sheet_name':name,'part':note_part,
                            'coordinate':comment.get('ref'), 'author_id':comment.get('authorId'),
                            'authors':authors,'text':literal_string(comment.find(S+'text'))})
            # Drawing anchors and their media relationships remain in exact XML.
            for drawing in tree.findall(S+'drawing'):
                result['image_references'].append({'part':part,'unit':ordinal,'relationship_id':drawing.get(R+'id'),
                    'drawing_part':mapping_part(rels(archive,part), drawing.get(R+'id'))})
    result.update(sheet_count=len(result['sheets']), sheets_complete=True, cells_complete=True,
                  media_count=len(media), notes_text_chars=sum(len(n['text']) for n in result['notes']),
                  native_text_chars=sum(len(c.get('value') or '') + len((c.get('formula') or {}).get('text',''))
                                        for s in result['sheets'] for c in s['cells']))
    return result


def mapping_part(mapping, ident):
    row = mapping.get(ident)
    return row['target'] if row else None


def inventory(source, raw):
    """Persist all package parts/media plus the complete structured cell index."""
    result = read_workbook(source)
    raw = Path(raw); raw.mkdir(parents=True, exist_ok=True)
    (raw/'office-parts').mkdir(exist_ok=True)
    (raw/'office-media').mkdir(exist_ok=True)
    with zipfile.ZipFile(source) as archive:
        # Retain non-XML embedding/chart resources too, not just the cell index.
        for ordinal, name in enumerate(archive.namelist()):
            if name.endswith('/'): continue
            ref = f'office-parts/part{ordinal:04}.bin'
            (raw/ref).write_bytes(archive.read(name))
            result['auxiliary_parts'].append({'part':name,'raw_asset':'raw/'+ref})
        for ordinal, row in enumerate(result['media']):
            suffix = Path(row['part']).suffix.lower()
            if not re.fullmatch(r'\.[a-z0-9]{1,8}', suffix): suffix = '.bin'
            ref = f'office-media/m{ordinal:04}{suffix}'
            (raw/ref).write_bytes(archive.read(row['part']))
            row['raw_asset'] = 'raw/'+ref
    (raw/'office-inventory.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return result


def ledger_rows(result):
    """Readable, explicitly labelled literal source records (not computed values)."""
    yield 'WORKBOOK NATIVE CELL LEDGER — derived preview pages, not print-layout pages.'
    yield 'Stored formula text and cached values below are separate; no calculation or refresh.'
    for sheet in result['sheets']:
        label = f"Sheet {sheet['unit']} {json.dumps(sheet['name'], ensure_ascii=False)} ({sheet['state']}; {sheet['kind']})"
        yield '\n'+label
        if not sheet['cells']: yield '[No stored cells; implicit blank grid not enumerated.]'
        for cell in sheet['cells']:
            value = json.dumps(cell['value'], ensure_ascii=False)
            if cell['formula'] is not None:
                formula = json.dumps(cell['formula']['text'], ensure_ascii=False)
                attributes = json.dumps(cell['formula']['attributes'], ensure_ascii=False, sort_keys=True)
                cache = json.dumps(cell['cached_value'], ensure_ascii=False) if cell['cache_present'] else '[absent]'
                yield f"{label} ! {cell['coordinate']} type={cell['type']}: formula_text={formula}; formula_attributes={attributes}; stored_cache={cache}"
            else:
                yield f"{label} ! {cell['coordinate']} type={cell['type']}: " + ('[explicit blank]' if cell['explicit_blank'] else 'stored_value='+value)
        for merged in sheet['merged_ranges']: yield f'{label}: merged_range={merged}'
    # Comments/notes stay separate and staff-only, not in ordinary reading text.
    if result['notes']: yield f"[Workbook comments retained separately: {len(result['notes'])}; not inserted into cell reading.]"
