"""Index native Office notes/alt text as explicit, separately located sources.

No model calls or source edits. Supplements are staff-only by default; the
original part/node remains explicit and is never guessed to be a Word PDF page.
"""
import json
import posixpath
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from .document_bundle import BundleError
from .extraction_limits import office_guard

W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
A='{http://schemas.openxmlformats.org/drawingml/2006/main}'
P='{http://schemas.openxmlformats.org/presentationml/2006/main}'
R='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'


def parse_xml(archive,name):
    info=archive.getinfo(name)
    if info.file_size>16*1024*1024:raise BundleError('Supplementary XML exceeds the source limit')
    raw=archive.read(name)
    if b'<!DOCTYPE' in raw.upper()or b'<!ENTITY' in raw.upper():raise BundleError('Supplementary XML entities are unsupported')
    return ET.fromstring(raw)


def paragraphs(node,namespace):
    values=[]
    for paragraph in node.iter(namespace+'p'):
        parts=[]
        for item in paragraph.iter():
            if item.tag==namespace+'t':parts.append(item.text or '')
            elif item.tag==namespace+'tab':parts.append('\t')
            elif item.tag in (namespace+'br',namespace+'cr'):parts.append('\n')
        values.append(''.join(parts))
    return '\n'.join(values)


def relationships(archive,part):
    name=posixpath.join(posixpath.dirname(part),'_rels',posixpath.basename(part)+'.rels')
    if name not in archive.namelist():return {}
    result={}
    for node in parse_xml(archive,name):
        if node.get('TargetMode')=='External':continue
        value=node.get('Target','')
        target=value.lstrip('/')if value.startswith('/')else posixpath.normpath(posixpath.join(posixpath.dirname(part),value))
        if target.startswith('../')or ':'in target or '\\'in target:raise BundleError('Unsafe supplementary source relationship')
        result[node.get('Id')]={'target':target,'type':node.get('Type','')}
    return result


def generated_note_shape(shape):
    """LibreOffice can drop p:ph but retain a field-only slide number.

    Classify the XML field, never its displayed text. Authored <number> and
    mixed authored/field shapes remain exact source evidence.
    """
    fields = list(shape.iter(A + 'fld'))
    if not fields or any(field.get('type') != 'slidenum' for field in fields):
        return False
    generated = {id(node) for field in fields for node in field.iter(A + 't')}
    return not any((node.text or '').strip() for node in shape.iter(A + 't') if id(node) not in generated)


def index_supplements(source,bundle,manifest):
    source,bundle=Path(source),Path(bundle);fmt=source.suffix.lower().lstrip('.')
    if fmt in ('xls','xlsx'):
        from tools.material_stage16.workbook_supplements import index_workbook_comments
        return index_workbook_comments(source,bundle,manifest)
    if fmt not in ('pptx','ppt','docx','doc'):return []
    archive_path=bundle/('raw/derived.'+('docx'if fmt=='doc'else'pptx'))if fmt in ('doc','ppt')else source
    if not archive_path.is_file():
        # Older/explicit fixture workers may not retain native auxiliary parts.
        if (manifest.get('coverage')or{}).get('notes_retained'):raise BundleError('Declared native auxiliary evidence is missing')
        return []
    office_guard(archive_path,max_expanded=100*1024*1024)
    collected=[]
    def add(kind,part,node,text,page=None):
        if not text.strip():return
        # No truncation: each retained chunk carries exact character boundaries.
        for first in range(0,len(text),12000):
            last=min(len(text),first+12000)
            collected.append({'id':'s'+str(len(collected)+1),'kind':kind,'source_part':part,'source_node':node,
                              'page_hint':page,'char_start':first,'char_end':last,'text':text[first:last],
                              'quality':'extracted','visibility':'teacher','derivation':{'doc':'libreoffice_docx','ppt':'libreoffice_pptx'}.get(fmt,'original_office_xml')})
            if len(collected)>10000:raise BundleError('Supplementary source count exceeds the document limit')
    with zipfile.ZipFile(archive_path)as archive:
        names=set(archive.namelist());note_pages={};slide_pages={}
        if fmt in ('ppt','pptx'):
            presentation=parse_xml(archive,'ppt/presentation.xml');mapping=relationships(archive,'ppt/presentation.xml')
            for ordinal,node in enumerate(presentation.findall('.//'+P+'sldId'),1):
                part=mapping[node.get(R+'id')]['target'];slide_pages[part]=ordinal
                for relation in relationships(archive,part).values():
                    if relation['type'].endswith('/notesSlide'):note_pages[relation['target']]=ordinal
        for name in sorted(names):
            if re.fullmatch(r'ppt/notesSlides/notesSlide\d+\.xml',name):
                tree=parse_xml(archive,name)
                for number,shape in enumerate(tree.iter(P+'sp')):
                    placeholder=shape.find('.//'+P+'ph')
                    if placeholder is not None and placeholder.get('type')in ('sldNum','hdr','ftr','dt','sldImg'):continue
                    if generated_note_shape(shape):continue
                    add('speaker_notes',name,str(number),paragraphs(shape,A),note_pages.get(name))
            elif re.fullmatch(r'word/(comments|footnotes|endnotes)\.xml',name):
                kind={'comments':'comment','footnotes':'footnote','endnotes':'endnote'}[Path(name).stem]
                tree=parse_xml(archive,name)
                for number,node in enumerate(tree):
                    add(kind,name,node.get(W+'id',str(number)),paragraphs(node,W))
            elif re.fullmatch(r'word/(header|footer)\d+\.xml',name):
                add('header'if '/header'in name else'footer',name,'story',paragraphs(parse_xml(archive,name),W))
            elif re.fullmatch(r'ppt/diagrams/data\d+\.xml',name):
                add('diagram_text',name,'diagram',paragraphs(parse_xml(archive,name),A))
            # Drawing alt text is authored source data, not inferred from pixels.
            if name=='word/document.xml'or re.fullmatch(r'ppt/slides/slide\d+\.xml',name):
                tree=parse_xml(archive,name)
                for number,node in enumerate(tree.iter()):
                    if node.tag.rsplit('}',1)[-1]not in ('docPr','cNvPr'):continue
                    values=[node.get(k,'')for k in ('title','descr')if node.get(k)]
                    if values:add('alt_text',name,node.get('id',str(number)),'\n'.join(values),slide_pages.get(name))
    count=manifest['page_count']
    if any(s['page_hint'] is not None and(type(s['page_hint'])is not int or not 1<=s['page_hint']<=count)for s in collected):
        raise BundleError('Supplementary slide locator does not match rendered source')
    return collected


def eligible_supplements(document,include_staff=False):
    return [s for s in document['manifest'].get('supplements')or[]if include_staff or s.get('visibility')=='student']


def supplement_block(supplement):
    page={'number':supplement['page_hint'],'printed_label':None,'supplement_id':supplement['id'],
          'source_part':supplement['source_part'],'source_kind':supplement['kind']}
    block={'id':supplement['id'],'type':'text','text':supplement['text'],'quality':supplement['quality'],
           'supplement_visibility':supplement['visibility']}
    return page,block
