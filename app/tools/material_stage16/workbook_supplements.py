"""Native workbook comments for the parent's existing staff-only supplement inlet."""
import json
from pathlib import Path


def index_workbook_comments(source, bundle, manifest):
    """No PDF page hint: a sheet/cell is not a rendered page coordinate."""
    source,bundle=Path(source),Path(bundle)
    fmt=source.suffix.lower().lstrip('.')
    if fmt not in ('xls','xlsx'):return []
    path=bundle/'raw/office-inventory.json'
    if not path.is_file():raise ValueError('Workbook comments require the retained native inventory')
    native=json.loads(path.read_text(encoding='utf-8'))
    if native.get('original_source_sha256')!=manifest['source_sha256']:
        raise ValueError('Workbook comment inventory does not match original source')
    result=[]
    for note in native.get('notes',[]):
        text=note['text']
        if not text.strip():continue
        node=f"sheet:{note['sheet']}; cell:{note.get('coordinate') or '[unspecified]'}"
        for first in range(0,len(text),12000):
            last=min(len(text),first+12000)
            result.append({'id':'s'+str(len(result)+1),'kind':'comment','source_part':note['part'],
                'source_node':node,'page_hint':None,'char_start':first,'char_end':last,
                'text':text[first:last],'quality':'extracted','visibility':'teacher',
                'derivation':'original_office_xml'if fmt=='xlsx'else'libreoffice_xlsx'})
            if len(result)>10000:raise ValueError('Workbook comments exceed10000supplements')
    return result
