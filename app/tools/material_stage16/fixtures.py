"""Synthetic OOXML fixture, not a LibreOffice or real-user workbook export."""
import io
import zipfile
from pathlib import Path

S = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


def workbook(path, *, media=False, extra=None, cells=None):
    sheet_cells = cells or '''<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1"><v>2</v></c><c r="C1"><f>SUM(B1:B2)</f><v>999</v></c><c r="D1"><f t="shared" si="0" ref="D1:D2">B1*2</f><v>4</v></c><c r="E1"/></row>
    <row r="2" hidden="1"><c r="B2"><v>3</v></c><c r="D2"><f t="shared" si="0"/><v>6</v></c><c r="F2"><f>NOW()</f></c><c r="G2" t="inlineStr"><is><r><t>Exact </t></r><r><t>rich text</t></r><rPh sb="0" eb="1"><t>PHONETIC_NOT_VALUE</t></rPh></is></c></row>
    <row r="1000"><c r="Q1000" t="inlineStr"><is><t>OUTSIDE_PRINT_AREA</t></is></c></row>'''
    parts = {
        '[Content_Types].xml':f'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' + ''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in (1,2,3))+'</Types>',
        '_rels/.rels':f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{R}/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        'xl/workbook.xml':f'<workbook xmlns="{S}" xmlns:r="{R}"><workbookPr date1904="1"/><sheets><sheet name="Main 课程" sheetId="1" r:id="rId1"/><sheet name="Hidden" sheetId="2" state="veryHidden" r:id="rId2"/><sheet name="Blank" sheetId="3" r:id="rId3"/></sheets><definedNames><definedName name="_xlnm.Print_Area" localSheetId="0">Main!$A$1:$C$1</definedName></definedNames></workbook>',
        'xl/_rels/workbook.xml.rels':f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(f'<Relationship Id="rId{i}" Type="{R}/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in (1,2,3))+'</Relationships>',
        'xl/sharedStrings.xml':f'<sst xmlns="{S}" count="1" uniqueCount="1"><si><r><t>Literal </t></r><r><t>title</t></r></si></sst>',
        'xl/worksheets/sheet1.xml':f'<worksheet xmlns="{S}" xmlns:r="{R}"><dimension ref="A1:C1"/><cols><col min="7" max="7" hidden="1"/></cols><sheetData>{sheet_cells}</sheetData><mergeCells><mergeCell ref="A4:C4"/></mergeCells>'+('<drawing r:id="drawing"/>' if media else '')+'</worksheet>',
        'xl/worksheets/sheet2.xml':f'<worksheet xmlns="{S}"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>HIDDEN_SHEET_VALUE</t></is></c></row></sheetData></worksheet>',
        'xl/worksheets/sheet3.xml':f'<worksheet xmlns="{S}"><sheetData/></worksheet>',
        'xl/worksheets/_rels/sheet1.xml.rels':f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="comments" Type="{R}/comments" Target="../comments1.xml"/>'+ (f'<Relationship Id="drawing" Type="{R}/drawing" Target="../drawings/drawing1.xml"/>' if media else '')+'</Relationships>',
        'xl/comments1.xml':f'<comments xmlns="{S}"><authors><author>Synthetic Teacher</author></authors><commentList><comment ref="B1" authorId="0"><text><t>PRIVATE_WORKBOOK_COMMENT</t></text></comment></commentList></comments>',
        'xl/styles.xml':f'<styleSheet xmlns="{S}"><numFmts count="1"><numFmt numFmtId="164" formatCode="yyyy-mm-dd"/></numFmts></styleSheet>'}
    if media:
        from PIL import Image
        buffer = io.BytesIO();Image.new('RGBA',(32,24),(20,80,140,128)).save(buffer,format='PNG')
        parts['xl/media/image1.png'] = buffer.getvalue()
        parts['xl/drawings/drawing1.xml'] = '<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"/>'
    parts.update(extra or {})
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in parts.items(): archive.writestr(name,data)
    return Path(path)


def presentation(path):
    p='http://schemas.openxmlformats.org/presentationml/2006/main';a='http://schemas.openxmlformats.org/drawingml/2006/main'
    parts={'[Content_Types].xml':'<Types/>',
        'ppt/presentation.xml':f'<p:presentation xmlns:p="{p}" xmlns:r="{R}"><p:sldIdLst><p:sldId id="1" r:id="one"/><p:sldId id="2" r:id="two"/></p:sldIdLst></p:presentation>',
        'ppt/_rels/presentation.xml.rels':f'<Relationships><Relationship Id="one" Type="{R}/slide" Target="slides/slide1.xml"/><Relationship Id="two" Type="{R}/slide" Target="slides/slide2.xml"/></Relationships>'}
    for i in (1,2):
        parts[f'ppt/slides/slide{i}.xml']=f'<p:sld xmlns:p="{p}" xmlns:a="{a}" show="{1 if i==1 else 0}"><a:p><a:r><a:t>Synthetic slide {i} native literal content over forty characters.</a:t></a:r></a:p></p:sld>'
        parts[f'ppt/slides/_rels/slide{i}.xml.rels']=f'<Relationships><Relationship Id="notes" Type="{R}/notesSlide" Target="../notesSlides/notesSlide{i}.xml"/></Relationships>'
        parts[f'ppt/notesSlides/notesSlide{i}.xml']=f'<p:notes xmlns:p="{p}" xmlns:a="{a}"><p:sp><a:p><a:r><a:t>PRIVATE_SYNTHETIC_NOTE_{i}</a:t></a:r></a:p></p:sp></p:notes>'
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in parts.items():archive.writestr(name,data)
    return Path(path)
