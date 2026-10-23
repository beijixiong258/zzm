"""CPU source/preview tests. Legacy conversions below are labelled protocols."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import types
import zipfile
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[2]
for path in (ROOT,ROOT/'tools/material_stage13',ROOT/'tools/document_stage12'):
    if str(path) not in sys.path:sys.path.insert(0,str(path))
from tools.material_stage16.fixtures import workbook,presentation,S,R
from tools.material_stage16.workbook_inventory import read_workbook
from tools.material_stage16.workbook_material import process
from parser_helpers import sha256,validate_bundle
from prepared_material import visual_plan,reuse_office


def test_all_stored_cells_not_dimensions_or_print_ranges(tmp_path):
    source=workbook(tmp_path/'original.xlsx');before=sha256(source)
    native=read_workbook(source)
    assert native['sheet_count']==3 and native['cell_count']==11
    assert native['formula_count']==4 and native['cached_formula_count']==3
    assert native['sheets'][0]['dimension']=='A1:C1'
    assert native['sheets'][0]['merged_ranges']==['A4:C4']
    cells={c['coordinate']:c for c in native['sheets'][0]['cells']}
    assert cells['Q1000']['value']=='OUTSIDE_PRINT_AREA'
    assert cells['C1']['formula']['text']=='SUM(B1:B2)' and cells['C1']['cached_value']=='999'
    assert not cells['F2']['cache_present'] and cells['F2']['cached_value']is None
    assert cells['D2']['formula']=={'text':'','attributes':{'t':'shared','si':'0'}}
    assert cells['E1']['explicit_blank']
    assert cells['G2']['value']=='Exact rich text'
    assert native['sheets'][1]['state']=='veryHidden' and native['sheets'][2]['cells']==[]
    assert native['notes'][0]['text']=='PRIVATE_WORKBOOK_COMMENT'
    assert sha256(source)==before


def test_real_cpu_bundle_cells_raw_media_and_distinct_pdf_pages(tmp_path):
    source=workbook(tmp_path/'actual.xlsx',media=True);before=source.read_bytes()
    assert process(source,tmp_path/'bundle','xlsx',60,['--engine','native'])==0
    root=tmp_path/'bundle';m=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    r=json.loads((root/'receipt.json').read_text(encoding='utf-8'))
    from backend.aicademiya.document_bundle import validate_bundle as backend_validate
    assert backend_validate(root,sha256(source),None)['source_format']=='xlsx'
    assert validate_bundle(root,m)['valid']
    assert m['source_sha256']==sha256(source) and source.read_bytes()==before
    assert m['coverage']['original_sheet_count']==3 and m['coverage']['stored_cells']==11
    assert m['coverage']['stored_cells_complete'] and m['coverage']['sheets_complete']
    assert m['coverage']['representation']=='workbook_native_cell_ledger'
    text=''.join(b['text'] for p in m['pages'] for b in p['blocks'])
    assert 'Q1000' in text and 'OUTSIDE_PRINT_AREA' in text and 'HIDDEN_SHEET_VALUE'in text
    assert 'stored_cache="999"' in text and 'formula_text="SUM(B1:B2)"' in text
    assert '[explicit blank]'in text and 'Blank'in text
    assert 'PRIVATE_WORKBOOK_COMMENT'not in text
    assert m['coverage']['media_gallery_pages'] and not any(row['model_calls'] for row in r['page_timings'])
    import pymupdf as fitz
    with fitz.open(root/'preview.pdf')as pdf:
        for page in list(pdf)[:m['coverage']['ledger_pages']]:
            spans=[span for block in page.get_text('dict')['blocks']if 'lines'in block for line in block['lines']for span in line['spans']]
            assert spans and all(span['bbox'][2]<=559.1 for span in spans), 'Ledger font metrics must match actual drawn glyphs; no right-edge clipping'
    with zipfile.ZipFile(source)as archive:
        assert (root/'raw/office-media/m0000.png').read_bytes()==archive.read('xl/media/image1.png')
    from PIL import Image
    with Image.open(root/'assets'/f"workbook-media-p{m['page_count']}-frame0.png")as image:
        assert image.size==(32,24) and image.getpixel((0,0))==(20,80,140,128)
    plan=visual_plan(m,r)
    assert plan['visual_pages']==m['coverage']['media_gallery_pages']
    assert plan['needs_gpu']  # Decision only; no lease/model process is started.


def test_ledger_native_only_requires_no_gpu(tmp_path):
    source=workbook(tmp_path/'native.xlsx')
    assert process(source,tmp_path/'bundle','xlsx',60,['--engine','native'])==0
    m=json.loads((tmp_path/'bundle/manifest.json').read_text(encoding='utf-8'))
    r=json.loads((tmp_path/'bundle/receipt.json').read_text(encoding='utf-8'))
    assert visual_plan(m,r)['needs_gpu']is False
    assert process(source,tmp_path/'reuse','xlsx',60,['--engine','native'],tmp_path/'bundle')==0
    assert (tmp_path/'bundle/preview.pdf').read_bytes()==(tmp_path/'reuse/preview.pdf').read_bytes()
    source.write_bytes(source.read_bytes()+b'changed')
    with pytest.raises(ValueError,match='does not match'):
        process(source,tmp_path/'bad-reuse','xlsx',60,['--engine','native'],tmp_path/'bundle')


@pytest.mark.parametrize('extra,reason',[
    ({'xl/vbaProject.bin':b'fake macro'},'Macro'),
    ({'xl/_rels/external.xml.rels':f'<Relationships><Relationship Type="{R}/externalLink" TargetMode="External" Target="https://never.invalid/value"/></Relationships>'},'linked'),
    ({'xl/comments1.xml':'<!DOCTYPE a [<!ENTITY x "external">]><a/>'},'entities'),
    ({'xl/worksheets/sheet1.xml':f'<worksheet xmlns="{S}"><sheetData><row><c r="XFE1"><v>1</v></c></row></sheetData></worksheet>'},'grid'),
    ({'xl/worksheets/sheet1.xml':f'<worksheet xmlns="{S}"><sheetData><row><c r="A1"/><c r="A1"/></row></sheetData></worksheet>'},'Duplicate'),
    ({'xl/worksheets/sheet1.xml':f'<worksheet xmlns="{S}"><sheetData><row><c r="A1" t="s"><v>999</v></c></row></sheetData></worksheet>'},'shared string'),
],ids=['macro','external-refresh','xml-entity','grid-bounds','duplicate-cell','bad-string-index'])
def test_fail_closed_before_conversion_or_lease(tmp_path,extra,reason):
    with pytest.raises(ValueError,match=reason):read_workbook(workbook(tmp_path/'bad.xlsx',extra=extra))


def test_cell_budget_no_partial_acceptance(tmp_path,monkeypatch):
    import tools.material_stage16.workbook_inventory as module
    monkeypatch.setattr(module,'MAX_CELLS',4)
    with pytest.raises(ValueError,match='stored cells'):read_workbook(workbook(tmp_path/'too-many.xlsx'))


def test_pdf_page_budget_is_not_sheet_count(tmp_path,monkeypatch):
    import simple_material
    monkeypatch.setattr(simple_material.math,'ceil',lambda n:1001)
    source=workbook(tmp_path/'too-many-pages.xlsx')
    assert process(source,tmp_path/'failed','xlsx',60,['--engine','native'])==2
    receipt=json.loads((tmp_path/'failed/receipt.json').read_text(encoding='utf-8'))
    assert '1000pages' in receipt['error'] and receipt['status']=='failed'


def test_long_workbook_pagination_retains_all_later_cells(tmp_path):
    cells=''.join(f'<row r="{i}"><c r="A{i}" t="inlineStr"><is><t>LITERAL_VALUE_{i}</t></is></c></row>' for i in range(1,301))
    source=workbook(tmp_path/'many.xlsx',cells=cells)
    assert process(source,tmp_path/'bundle','xlsx',60,['--engine','native'])==0
    m=json.loads((tmp_path/'bundle/manifest.json').read_text(encoding='utf-8'))
    assert m['page_count']>3 and m['coverage']['original_sheet_count']==3
    assert m['coverage']['stored_cells']==301
    assert 'LITERAL_VALUE_300'in ''.join(b['text']for p in m['pages']for b in p['blocks'])


def fake_ole(monkeypatch,streams):
    class Ole:
        def __init__(self,path):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def listdir(self,**kwargs):return [[s]for s in streams]
        def get_size(self,path):return 64
    monkeypatch.setitem(sys.modules,'olefile',types.SimpleNamespace(isOleFile=lambda p:True,OleFileIO=Ole))


@pytest.mark.parametrize('fmt,streams,accepted',[('ppt',['PowerPoint Document'],True),('xls',['Workbook'],True),
    ('xls',['PowerPoint Document'],False),('ppt',['PowerPoint Document','VBA'],False)],ids=['ppt','xls','mismatch','macro'])
def test_legacy_container_protocol(tmp_path,monkeypatch,fmt,streams,accepted):
    from tools.material_stage16.legacy_office import binary_inventory
    source=tmp_path/('source.'+fmt);source.write_bytes(b'synthetic OLE protocol')
    fake_ole(monkeypatch,streams)
    if accepted:
        result=binary_inventory(source,fmt)
        assert result['source_format']==fmt and 'derived_'in result['native_auxiliary_coverage']
    else:
        with pytest.raises(ValueError):binary_inventory(source,fmt)


@pytest.mark.skipif(sys.platform!='linux',reason='existing Linux process limits')
def test_legacy_xls_conversion_protocol_preserves_original_and_marks_derivation(tmp_path,monkeypatch):
    import parse_material
    source=tmp_path/'original.xls';source.write_bytes(b'SYNTHETIC LEGACY XLS PROTOCOL NOT REAL BIFF');before=sha256(source)
    fake_ole(monkeypatch,['Workbook'])
    calls=[]
    def convert(copy,temp,target,seconds,env):
        assert copy!=source and copy.read_bytes()==source.read_bytes() and target=='xlsx'
        calls.append(target)
        return workbook(Path(temp)/'source.xlsx'),{'target_format':'xlsx','fixture_label':'protocol, no LibreOffice executed','returncode':0}
    monkeypatch.setattr(parse_material,'convert',convert)
    assert process(source,tmp_path/'bundle','xls',60,['--engine','native'])==0
    m=json.loads((tmp_path/'bundle/manifest.json').read_text(encoding='utf-8'))
    assert calls==['xlsx'] and m['source_sha256']==before and sha256(source)==before
    assert m['source_format']=='xls' and m['coverage']['inventory_derivation']=='libreoffice_xlsx'
    assert m['coverage']['original_binary_cells_decoded']is False
    assert (tmp_path/'bundle/raw/derived.xlsx').is_file()


@pytest.mark.skipif(sys.platform!='linux',reason='existing Linux process limits/signals')
@pytest.mark.parametrize('fmt',['ppt','doc'])
def test_legacy_existing_doc_and_ppt_conversion_protocol(tmp_path,monkeypatch,fmt):
    import parse_material
    source=tmp_path/('original.'+fmt);source.write_bytes(('SYNTHETIC '+fmt+' PROTOCOL').encode());before=sha256(source)
    fake_ole(monkeypatch,['WordDocument'if fmt=='doc'else'PowerPoint Document'])
    calls=[]
    def convert(copy,temp,target,seconds,env):
        assert copy!=source and copy.read_bytes()==source.read_bytes()
        calls.append(target);dest=Path(temp)/('source.'+target)
        if target=='pdf':
            import pymupdf as fitz
            doc=fitz.open()
            for number in range(1,2 if fmt=='doc'else 3):
                p=doc.new_page();p.insert_text((30,30),f'Protocol PDF native literal text page {number}, over forty characters long.')
            doc.save(dest);doc.close()
        elif target=='pptx':presentation(dest)
        else:
            with zipfile.ZipFile(dest,'w')as archive:
                archive.writestr('[Content_Types].xml','<Types/>')
                archive.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:t>Existing DOC derived text</w:t></w:p></w:document>')
        return dest,{'target_format':target,'fixture_label':'protocol, no LibreOffice executed','returncode':0}
    monkeypatch.setattr(parse_material,'convert',convert)
    out=tmp_path/'bundle'
    assert parse_material.main(['--input',str(source),'--output',str(out),'--engine','native','--deadline-seconds','60'])==0
    m=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
    assert m['source_sha256']==before and sha256(source)==before and m['source_format']==fmt
    assert calls==['docx'if fmt=='doc'else'pptx','pdf']
    assert m['coverage']['inventory_derivation']=='libreoffice_'+('docx'if fmt=='doc'else'pptx')
    if fmt=='ppt':assert m['coverage']['hidden_slides']==1 and m['coverage']['notes_count']==2
    reused=tmp_path/'reuse';reused.mkdir()
    native,binary,count,rows=reuse_office(out,source,fmt,reused)
    assert binary and count==m['page_count'] and len(rows)==2
    assert (reused/'raw'/('derived.'+('docx'if fmt=='doc'else'pptx'))).read_bytes()==(out/'raw'/('derived.'+('docx'if fmt=='doc'else'pptx'))).read_bytes()


@pytest.mark.skipif(sys.platform!='linux',reason='actual Ubuntu CLI')
def test_actual_cli_cpu_xlsx(tmp_path):
    source=workbook(tmp_path/'actual.xlsx');before=sha256(source)
    result=subprocess.run([sys.executable,str(ROOT/'tools/material_stage13/parse_material.py'),
        '--input',str(source),'--output',str(tmp_path/'bundle'),'--engine','native','--deadline-seconds','60'],
        capture_output=True,text=True,timeout=70)
    assert result.returncode==0,(result.stdout,result.stderr)
    assert sha256(source)==before
    assert json.loads((tmp_path/'bundle/manifest.json').read_text())['source_format']=='xlsx'


@pytest.mark.skipif(sys.platform!='linux',reason='actual Ubuntu CPU supervisor')
def test_actual_supervisor_xlsx_native_never_leases(tmp_path,monkeypatch):
    import document_worker_service as service
    source=workbook(tmp_path/'native.xlsx');before=sha256(source)
    service.STOP.clear()
    monkeypatch.setattr(service,'HOME',tmp_path/'job-home')
    monkeypatch.setattr(service,'cpu_prefix',lambda:(0,[]))
    monkeypatch.setattr(service,'runtime_python',lambda:Path(sys.executable))
    monkeypatch.setattr(service,'available_mib',lambda:12000)
    def forbidden(*args,**kwargs):raise AssertionError('Native cells must not query, lease or start a GPU model')
    monkeypatch.setattr(service,'runtime_spec',forbidden)
    monkeypatch.setattr(service,'DocumentLease',forbidden)
    monkeypatch.setattr(service,'gpu_free_mib',forbidden)
    report=service.run_job(source,tmp_path/'complete',timeout=60)
    assert report['status']=='complete' and report['execution_kind']=='native_only'
    assert not report['gpu_lease_used'] and not report['fresh_inference']
    assert sha256(source)==before
    manifest=json.loads((tmp_path/'complete/manifest.json').read_text(encoding='utf-8'))
    assert manifest['source_format']=='xlsx' and manifest['coverage']['stored_cells']==11


@pytest.mark.skipif(sys.platform!='linux',reason='actual CPU PDF child simulates old hybrid merge, no model')
def test_old_hybrid_protocol_keeps_exact_cells_rgba_and_native_page_dpi(tmp_path,monkeypatch):
    import parse_material
    from backend.aicademiya.document_bundle import validate_bundle as backend_validate
    source=workbook(tmp_path/'media.xlsx',media=True)
    assert process(source,tmp_path/'native','xlsx',60,['--engine','native'])==0
    original=json.loads((tmp_path/'native/manifest.json').read_text(encoding='utf-8'))
    ledger=''.join(b['text']for p in original['pages']for b in p['blocks'])
    media_page=original['coverage']['media_gallery_pages'][0]
    asset=original['pages'][media_page-1]['blocks'][0]['assets'][0]
    original_bytes=(tmp_path/'native'/asset).read_bytes()
    real_run_owned=parse_material.run_owned
    def cpu_protocol_child(command,**kwargs):
        assert command[command.index('--engine')+1]=='hybrid'
        command=list(command);command[command.index('--engine')+1]='native'
        return real_run_owned(command,**kwargs)  # Actual CPU child, not a model response.
    monkeypatch.setattr(parse_material,'run_owned',cpu_protocol_child)
    assert process(source,tmp_path/'merged','xlsx',60,['--engine','hybrid','--dpi','96'],tmp_path/'native')==0
    merged=backend_validate(tmp_path/'merged',sha256(source),None)
    assert ''.join(b['text']for p in merged['pages'][:original['coverage']['ledger_pages']]for b in p['blocks'])==ledger
    assert (tmp_path/'merged'/asset).read_bytes()==original_bytes
    assert merged['pages'][media_page-1]['width']==original['pages'][media_page-1]['width']
    assert merged['pages'][media_page-1]['blocks'][0]['assets']==[asset]
    assert len(merged['pages'][media_page-1]['blocks'])>1


@pytest.mark.skipif(sys.platform!='linux',reason='controlled LibreOffice argv/profile protocol')
@pytest.mark.parametrize('suffix,target,filter_text',[
    ('.ppt','pdf','impress_pdf_Export'),('.ppt','pptx','Impress MS PowerPoint'),('.xls','xlsx','Calc MS Excel')])
def test_controlled_converter_protocol_filters_profile_and_immutable_copy(tmp_path,monkeypatch,suffix,target,filter_text):
    import parse_material
    source=tmp_path/('source'+suffix);source.write_bytes(b'SYNTHETIC CONVERTER PROTOCOL')
    monkeypatch.setattr(parse_material.shutil,'which',lambda name:'/synthetic/libreoffice')
    original_read=Path.read_text
    def read_text(path,*args,**kwargs):
        if str(path)=='/proc/meminfo':return 'MemAvailable: 12000000 kB\n'
        return original_read(path,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',read_text)
    def run_owned(command,**kwargs):
        assert command[0]=='/synthetic/libreoffice' and filter_text in command[command.index('--convert-to')+1]
        assert '--headless'in command and kwargs['limits'] and kwargs['seconds']<=120
        profile=original_read(tmp_path/('profile-'+target)/'user/registrymodifications.xcu')
        assert 'MacroSecurityLevel'in profile and '<value>3</value>'in profile
        assert '/org.openoffice.Office.Calc/Content/Update'in profile and 'Link'in profile
        if target=='pdf':assert 'ExportHiddenSlides'in command[command.index('--convert-to')+1]
        destination=Path(command[command.index('--outdir')+1])/(source.stem+'.'+target)
        destination.write_bytes(b'SYNTHETIC CONVERTER OUTPUT')
        return 0,'protocol converter output',''
    monkeypatch.setattr(parse_material,'run_owned',run_owned)
    derived,row=parse_material.convert(source,tmp_path,target,900,{})
    assert row['returncode']==0 and derived.is_file() and source.read_bytes()==b'SYNTHETIC CONVERTER PROTOCOL'
