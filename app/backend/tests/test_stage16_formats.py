"""Stage16 format admission and bounded preview; synthetic source fixtures only."""
import hashlib
import json
from pathlib import Path

import pytest

from backend.aicademiya.document_bundle import source_identity,validate_manifest,BundleError,FULL_FORMATS
from backend.aicademiya.material_extraction import extract_document
from tools.material_stage16.fixtures import workbook
from tools.material_stage16.workbook_inventory import inventory
from tools.material_stage16.workbook_supplements import index_workbook_comments


def test_xlsx_identity_has_no_pdf_page_count(tmp_path):
    source=workbook(tmp_path/'multi.xlsx');before=source.read_bytes()
    digest,count=source_identity(source)
    assert digest==hashlib.sha256(before).hexdigest() and count is None
    assert source.read_bytes()==before
    assert all(fmt in FULL_FORMATS for fmt in ('doc','ppt','xls','xlsx'))


@pytest.mark.parametrize('fmt',['ppt','xls','doc'])
def test_legacy_admission_is_container_only_worker_must_validate_streams(tmp_path,fmt):
    source=tmp_path/('protocol.'+fmt);source.write_bytes(bytes.fromhex('d0cf11e0a1b11ae1')+b'\0'*504)
    digest,count=source_identity(source)
    assert count is None and len(digest)==64
    source.write_bytes(b'not OLE')
    with pytest.raises(BundleError):source_identity(source)


def test_xlsx_preview_all_sheets_nonprint_cells_and_formula_cache(tmp_path):
    source=workbook(tmp_path/'multi.xlsx');before=source.read_bytes()
    result=extract_document(source);report=result['extraction_report']
    assert result['status']=='needs_review' and report['method']=='native'
    assert report['units_total']==report['units_processed']==3
    assert report['ocr_units']==0 and report['visual_review_required']
    assert 'OUTSIDE_PRINT_AREA'in result['excerpt'] and 'HIDDEN_SHEET_VALUE'in result['excerpt']
    assert 'formula_text="SUM(B1:B2)"'in result['excerpt'] and 'stored_cache="999"'in result['excerpt']
    assert '[explicit blank]'in result['excerpt'] and 'Blank'in result['excerpt']
    assert 'PRIVATE_WORKBOOK_COMMENT'not in result['excerpt']
    assert source.read_bytes()==before


def test_xlsx_preview_truncation_is_not_cell_coverage_failure(tmp_path):
    cells=''.join(f'<row r="{i}"><c r="A{i}" t="inlineStr"><is><t>{"LITERAL_LONG_CELL"*8}_{i}</t></is></c></row>'for i in range(1,501))
    result=extract_document(workbook(tmp_path/'large.xlsx',cells=cells));report=result['extraction_report']
    assert report['truncated'] and report['excerpt_chars']==50000 and report['chars_extracted']>50000
    assert report['units_processed']==3
    assert any('later units were still processed'in note for note in report['notes'])


def test_wrong_xlsx_and_macro_never_admitted(tmp_path):
    wrong=tmp_path/'wrong.xlsx';wrong.write_bytes(b'not a workbook')
    with pytest.raises(BundleError):source_identity(wrong)
    macro=workbook(tmp_path/'macro.xlsx',extra={'xl/vbaProject.bin':b'no execution'})
    with pytest.raises(BundleError):source_identity(macro)
    assert extract_document(macro)['status']=='error'


def test_64_mib_boundary_precedes_office_reader(tmp_path):
    large=tmp_path/'large.xlsx'
    with large.open('wb')as file:file.truncate(64*1024*1024+1)
    with pytest.raises(BundleError,match='64 MiB'):source_identity(large)


def test_comments_staff_only_sheet_cell_no_page_guess(tmp_path):
    source=workbook(tmp_path/'source.xlsx');digest=source_identity(source)[0]
    native=inventory(source,tmp_path/'bundle/raw');native['original_source_sha256']=digest
    (tmp_path/'bundle/raw/office-inventory.json').write_text(json.dumps(native),encoding='utf-8')
    rows=index_workbook_comments(source,tmp_path/'bundle',{'source_sha256':digest})
    assert rows[0]['text']=='PRIVATE_WORKBOOK_COMMENT' and rows[0]['visibility']=='teacher'
    assert rows[0]['source_node']=='sheet:1; cell:B1' and rows[0]['page_hint']is None
    assert rows[0]['derivation']=='original_office_xml'


@pytest.mark.parametrize('fmt',['ppt','xls','xlsx'])
def test_schema1_new_formats_require_derived_pdf(fmt):
    # Protocol-only manifest boundary. Actual rendered workbook bundles are
    # exercised in the Linux format suite against both strict validators.
    manifest={'schema_version':1,'source_sha256':'a'*64,'source_format':fmt,'preview_pdf':'preview.pdf',
        'parser':{'name':'synthetic-protocol','version':'1','recipe':'explicit-fixture'},'page_count':1,'complete':True,'warnings':[],
        'pages':[{'number':1,'printed_label':None,'rotation':0,'image':'pages/p0001.png','width':100,'height':100,
                  'status':'blank','issues':[],'blocks':[]}]}
    assert validate_manifest(manifest)['source_format']==fmt
    manifest.pop('preview_pdf')
    with pytest.raises(BundleError,match='retained rendered PDF'):validate_manifest(manifest)
