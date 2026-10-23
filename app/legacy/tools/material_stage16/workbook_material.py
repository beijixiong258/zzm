"""CPU-native XLSX cell-ledger preview with all stored cells and original media.

XLS is first converted to XLSX by the existing controlled converter. The preview
is intentionally not a print-area export: rendering cannot prove full cell
coverage and importing XLSX must not recalculate a workbook just to read it.
"""
from __future__ import annotations
import io
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

from tools.material_stage16.workbook_inventory import inventory, ledger_rows, MAX_LEDGER_CHARS


def helper_modules():
    root = Path(__file__).resolve().parents[1]
    for path in (root/'document_stage12', root/'material_stage13'):
        if str(path) not in sys.path: sys.path.insert(0, str(path))
    from parser_helpers import dump, sha256, coverage_of, validate_bundle
    return dump, sha256, coverage_of, validate_bundle


def append_media(out, manifest, receipt, native, deadline):
    import pymupdf as fitz
    from PIL import Image, ImageOps
    out = Path(out); map_rows = []
    pdf = fitz.open(out/'preview.pdf')
    try:
        for media in native['media']:
            if media['raster_pixels'] is None: continue
            with Image.open(out/media['raw_asset']) as source:
                frames = getattr(source, 'n_frames', 1)
                if len(manifest['pages']) + frames > 1000:
                    raise ValueError('Workbook cell/media preview exceeds1000pages')
                for index in range(frames):
                    if time.monotonic() >= deadline: raise TimeoutError('Workbook rendering deadline reached')
                    source.seek(index)
                    if source.width*source.height > 16_000_000:
                        raise ValueError('Workbook embedded frame exceeds16million pixels')
                    source.load()
                    rgba = ImageOps.exif_transpose(source).convert('RGBA')
                    buffer = io.BytesIO(); rgba.save(buffer, format='PNG'); data = buffer.getvalue()
                    number = len(manifest['pages'])+1
                    asset = f'assets/workbook-media-p{number}-frame{index}.png'; (out/'assets').mkdir(exist_ok=True)
                    (out/asset).write_bytes(data)
                    rgb = Image.new('RGB', rgba.size, 'white'); rgb.paste(rgba, mask=rgba.getchannel('A'))
                    display = io.BytesIO(); rgb.save(display, format='PNG')
                    page = pdf.new_page(width=595, height=842)
                    page.insert_text((36,30), f'Workbook original media gallery; frame {index}; derived page {number}', fontsize=9)
                    rect = fitz.Rect(36,50,559,806)
                    page.insert_image(rect, stream=display.getvalue(), keep_proportion=True)
                    pix = page.get_pixmap(matrix=fitz.Matrix(1.5,1.5), alpha=False)
                    image = f'pages/p{number:04}.png'; pix.save(out/image)
                    manifest['pages'].append({'number':number,'printed_label':None,'rotation':0,
                        'image':image,'width':pix.width,'height':pix.height,'status':'needs_review',
                        'issues':['workbook_original_media_gallery; not_excel_sheet_layout'],
                        'blocks':[{'id':f'p{number}-b0','type':'image','bbox':[36/595,50/842,559/595,806/842],
                            'text':'','quality':'needs_review','issues':['original_workbook_media:'+media['part'],
                                f'original_media_frame:{index}; source_layout_not_applied'],
                            'assets':[asset],'parent_id':None}]})
                    receipt['page_timings'].append({'page':number,'seconds':0,'mode':'native',
                        'model_processed':False,'model_calls':0,'imported_evidence':False,'vector_paths':0})
                    map_rows.append({'page':number,'source_part':media['part'],'frame_index':index,
                        'source_asset':media['raw_asset'],'display_asset':asset,'source_layout_applied':False})
        if map_rows:
            pdf.save(out/'preview-media.pdf')
    finally: pdf.close()
    if map_rows: (out/'preview-media.pdf').replace(out/'preview.pdf')
    return map_rows


def render_ledger(ledger, out, seconds):
    """Wrap and draw with the SAME embedded font and exact source spans.

    The older text adapter measures a proportional CJK Font but draws with the
    built-in fixed-width CJK encoding; that can clip Latin rows at the right
    margin. Keep this workbook-specific renderer independent of that adapter.
    """
    import math
    import pymupdf as fitz
    from simple_material import text_lines
    dump, sha256, coverage_of, _ = helper_modules()
    text = Path(ledger).read_text(encoding='utf-8'); font = fitz.Font('china-s')
    lines = list(text_lines(text,font,523,11)); count = max(1,math.ceil(len(lines)/48))
    if count > 1000: raise ValueError('Rendered workbook ledger exceeds1000pages; no partial cells accepted')
    out = Path(out); (out/'pages').mkdir(parents=True,exist_ok=True)
    manifest = {'schema_version':1,'source_sha256':sha256(ledger),'source_format':'txt','preview_pdf':'preview.pdf',
        'parser':{'name':'stage16-workbook','version':'1.0.0','recipe':'exact-cell-ledger-font-bound-pdf'},
        'page_count':count,'complete':True,'warnings':[],'pages':[]}
    receipt = {'status':'complete','source_sha256':manifest['source_sha256'],'source_format':'txt',
        'device':'cpu','vlm_device':'cpu','engine':'native','quality_accepted':False,'page_timings':[]}
    started = time.monotonic(); offset = 0; pdf = fitz.open()
    try:
        for number in range(1,count+1):
            if time.monotonic()-started > seconds: raise TimeoutError('Workbook ledger rendering deadline reached')
            page = pdf.new_page(width=595,height=842)
            page.insert_font(fontname='source-ledger',fontbuffer=font.buffer)
            chunk = lines[(number-1)*48:number*48]
            for ordinal,(first,last,literal) in enumerate(chunk):
                assert first==offset; offset=last
                page.insert_text((36,42+ordinal*16),literal.rstrip('\r\n').replace('\t','    '),
                    fontname='source-ledger',fontsize=11)
            first,last = (chunk[0][0],chunk[-1][1]) if chunk else (0,0)
            blocks = [] if not chunk else [{'id':f'p{number}-b0','type':'text',
                'bbox':[36/595,30/842,559/595,(46+(len(chunk)-1)*16)/842],
                'text':text[first:last],'quality':'extracted','issues':['source_transcription_native',f'workbook_ledger_chars:{first}:{last}'],
                'assets':[],'parent_id':None}]
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False)
            image = f'pages/p{number:04}.png';pix.save(out/image)
            manifest['pages'].append({'number':number,'printed_label':None,'rotation':0,'image':image,
                'width':pix.width,'height':pix.height,'status':'text'if blocks else'blank','issues':[],'blocks':blocks})
            receipt['page_timings'].append({'page':number,'seconds':0,'mode':'native','model_processed':False,
                'model_calls':0,'imported_evidence':False,'vector_paths':0})
        assert offset==len(text) and ''.join(b['text']for p in manifest['pages']for b in p['blocks'])==text
        pdf.save(out/'preview.pdf')
    finally: pdf.close()
    manifest['coverage'] = coverage_of(manifest)
    dump(out/'manifest.json',manifest);dump(out/'receipt.json',receipt)


def build_native(source, out, fmt, seconds, *, convert):
    dump, sha256, coverage_of, validate_bundle = helper_modules()
    from tools.material_stage16.legacy_office import binary_inventory
    source, out = Path(source), Path(out)
    started = time.monotonic(); deadline = started+seconds; digest = sha256(source)
    out.mkdir(parents=True, exist_ok=False)
    try:
        conversion = []; binary = None
        if fmt == 'xls':
            binary = binary_inventory(source, fmt)
            dump(out/'raw/legacy-xls-inventory.json', binary)
            with tempfile.TemporaryDirectory(prefix='workbook-', dir=out) as directory:
                temp = Path(directory); copy = temp/'source.xls'
                shutil.copyfile(source, copy); copy.chmod(0o400)
                derived, row = convert(copy, temp, 'xlsx', max(.1,deadline-time.monotonic()),
                    {**os.environ,'CUDA_VISIBLE_DEVICES':'','HF_HUB_OFFLINE':'1','SAL_USE_VCLPLUGIN':'svp','SAL_MAX_CONCURRENCY':'4'})
                conversion.append(row)
                native = inventory(derived, out/'raw')
                shutil.copyfile(derived, out/'raw/derived.xlsx')
                native.update(original_source_format='xls',inventory_derivation='libreoffice_xlsx',
                    original_source_sha256=digest,derived_source_sha256=sha256(derived))
        else:
            native = inventory(source, out/'raw')
            native.update(original_source_format='xlsx',inventory_derivation='original_ooxml',original_source_sha256=digest)
        dump(out/'raw/office-inventory.json', native)
        pieces = []; size = 0
        for row in ledger_rows(native):
            size += len(row)+1
            if size > MAX_LEDGER_CHARS: raise ValueError('Workbook cell ledger exceeds bounded characters; no partial coverage accepted')
            pieces.append(row)
        text = '\n'.join(pieces)+'\n'
        ledger = out/'raw/workbook-ledger.txt'; ledger.write_text(text, encoding='utf-8')
        render_ledger(ledger, out, max(.01,deadline-time.monotonic()))
        manifest = json.loads((out/'manifest.json').read_text(encoding='utf-8'))
        receipt = json.loads((out/'receipt.json').read_text(encoding='utf-8'))
        ledger_pages = manifest['page_count']
        for page in manifest['pages']:
            page['issues'].append('derived_workbook_cell_ledger_page; not_original_sheet_or_print_page')
            for block in page['blocks']:
                block['issues'] = [issue.replace('original_text_chars:', 'workbook_ledger_chars:')
                                   if issue.startswith('original_text_chars:') else issue for issue in block['issues']]
                block['issues'] += ['original_locator_in_text:sheet_name_and_cell_coordinate',
                    'ledger_literal_source:raw/workbook-ledger.txt',
                    'workbook_formula_and_cache_distinct; no_evaluation',
                    'workbook_inventory_derivation:'+native['inventory_derivation']]
        media_map = append_media(out, manifest, receipt, native, deadline)
        manifest.update(source_sha256=digest,source_format=fmt,page_count=len(manifest['pages']),complete=True,
            parser={'name':'stage16-workbook','version':'1.0.0','recipe':fmt+'-native-cell-ledger+original-media+derived-pdf'},
            warnings=native['warnings']+(binary['warnings'] if binary else []))
        if (out/'preview.pdf').stat().st_size > 64*1024*1024: raise ValueError('Derived workbook PDF exceeds64MiB')
        manifest['coverage'] = coverage_of(manifest)
        manifest['coverage'].update(representation='workbook_native_cell_ledger', original_source_format=fmt,
            original_source_bytes=source.stat().st_size, rendered_pdf_sha256=sha256(out/'preview.pdf'),
            rendered_pdf_pages=manifest['page_count'], original_sheet_count=native['sheet_count'],
            stored_cells=native['cell_count'],stored_cells_complete=True,sheets_complete=True,
            formula_cells=native['formula_count'], formula_cache_cells=native['cached_formula_count'],
            formula_evaluation_performed=False if fmt=='xlsx' else None,
            native_formula_evaluation_performed=False, external_refresh_performed=False,
            cell_coverage_basis=native['coverage_basis'], office_raw_inventory='raw/office-inventory.json',
            inventory_derivation=native['inventory_derivation'], ledger_pages=ledger_pages,
            media_gallery_pages=[row['page'] for row in media_map], media_page_map=media_map,
            notes_count=len(native['notes']),notes_text_chars=native['notes_text_chars'],
            notes_retained=True,notes_integrated_in_reading=False,
            missing_components=['original_excel_print_layout_not_rendered','chart_relationships_not_semantically_verified'])
        if binary:
            manifest['coverage'].update(legacy_source_conversion=True,
                original_binary_cells_decoded=False,
                conversion_may_recalculate=True,
                conversion_formula_cache_policy='values_retained_from_libreoffice_conversion; original_binary_caches_not_claimed')
        receipt.update(source_sha256=digest,source_format=fmt,conversion=conversion,engine='native',
            status='complete',wall_seconds=time.monotonic()-started,original_source_bytes=source.stat().st_size)
        if sha256(source) != digest: raise ValueError('Original workbook changed during preparation')
        dump(out/'manifest.json',manifest)
        receipt['validation'] = validate_bundle(out,manifest)
        dump(out/'receipt.json',receipt)
        return 0
    except BaseException as exc:
        row = {'status':'failed','source_sha256':digest,'source_format':fmt,'engine':'native',
            'quality_accepted':False,'error_type':type(exc).__name__,
            'error':str(exc) if isinstance(exc,(ValueError,RuntimeError,TimeoutError,InterruptedError)) else 'Workbook preparation failed; raw evidence retained',
            'conversion':locals().get('conversion',[]),'page_timings':[], 'wall_seconds':time.monotonic()-started}
        if hasattr(exc,'row'): row['conversion'].append(exc.row)
        if (out/'manifest.json').is_file():
            manifest = json.loads((out/'manifest.json').read_text(encoding='utf-8'))
            manifest['complete'] = False
            if 'coverage' in manifest: manifest['coverage']['page_set_complete'] = False
            dump(out/'manifest.json',manifest)
        for private in (str(source),str(out)): row['error'] = row['error'].replace(private,'[job-path]')
        dump(out/'receipt.json',row)
        return 2


def reuse_native(source, prepared, out, fmt):
    dump, sha256, _, validate_bundle = helper_modules()
    source, prepared, out = Path(source), Path(prepared), Path(out)
    from parse_material import reject_symlinks
    if prepared.is_symlink() or any(p.is_symlink() for p in prepared.parents): raise ValueError('Unsafe prepared workbook')
    reject_symlinks(prepared)
    manifest = json.loads((prepared/'manifest.json').read_text(encoding='utf-8'))
    receipt = json.loads((prepared/'receipt.json').read_text(encoding='utf-8'))
    validate_bundle(prepared,manifest)
    if (manifest['source_sha256'] != sha256(source) or manifest.get('source_format') != fmt
            or receipt.get('status') != 'complete' or receipt.get('engine') != 'native'
            or not manifest.get('complete') or manifest.get('coverage',{}).get('representation') != 'workbook_native_cell_ledger'
            or sha256(prepared/'preview.pdf') != manifest['coverage']['rendered_pdf_sha256']
            or any(row.get('model_calls',0) or row.get('model_processed') for row in receipt.get('page_timings',[]))):
        raise ValueError('Prepared workbook does not match this original/native phase')
    shutil.copytree(prepared,out)
    return manifest,receipt


def process(source, out, fmt, seconds, forward, prepared=None):
    dump, sha256, coverage_of, validate_bundle = helper_modules()
    from parse_material import convert, run_owned
    source, out = Path(source), Path(out)
    if '--evidence-dir' in forward or '--evidence-source-sha256' in forward:
        raise ValueError('Imported PDF evidence is unsupported for workbook sources')
    if prepared:
        manifest,receipt = reuse_native(source,prepared,out,fmt)
    else:
        rc = build_native(source,out,fmt,seconds,convert=convert)
        if rc: return rc
        manifest = json.loads((out/'manifest.json').read_text(encoding='utf-8'))
        receipt = json.loads((out/'receipt.json').read_text(encoding='utf-8'))
    engine = forward[forward.index('--engine')+1] if '--engine' in forward else 'native'
    if engine == 'native' or not manifest['coverage']['media_gallery_pages']: return 0
    # Older hybrid worker: only gallery-page extraction may replace gallery
    # blocks. Exact cell-ledger pages are never replaced by PDF/OCR glyph text.
    rc, stdout, stderr = run_owned([sys.executable,str(Path(__file__).resolve().parents[1]/'document_stage12/parser_worker.py'),
        '--input',str(out/'preview.pdf'),'--output',str(out/'pdf-work'),'--deadline-seconds',str(seconds)]+list(forward),
        seconds=seconds+5,env={**os.environ,'CUDA_VISIBLE_DEVICES':''})
    work = out/'pdf-work'
    child_manifest = json.loads((work/'manifest.json').read_text(encoding='utf-8'))
    child_receipt = json.loads((work/'receipt.json').read_text(encoding='utf-8'))
    dump(out/'raw/workbook-pdf-parser-receipt.json',child_receipt)
    if rc:
        manifest['complete'] = False; receipt.update(status='failed',error='Derived workbook media parser failed',child_receipt='raw/workbook-pdf-parser-receipt.json')
        dump(out/'manifest.json',manifest);dump(out/'receipt.json',receipt);return rc
    for number in manifest['coverage']['media_gallery_pages']:
        page = child_manifest['pages'][number-1]
        # Keep the original RGBA media block/asset. Child page crops may contain
        # labels/background; they are derived, not the original embedded pixels.
        original_page = manifest['pages'][number-1]
        original_block = original_page['blocks'][0]
        original_block['id'] = f'p{number}-b0-original'
        original_page['blocks'] = [original_block]+page['blocks']
        receipt['page_timings'][number-1] = child_receipt['page_timings'][number-1]
        # PDF-parser DPI may differ; retain the native page raster/dimensions.
        for block in page['blocks']:
            for asset in block['assets']:
                (out/asset).parent.mkdir(exist_ok=True,parents=True);shutil.copyfile(work/asset,out/asset)
    original_coverage = manifest['coverage'];manifest['coverage'] = coverage_of(manifest)
    for key,value in original_coverage.items():
        if key not in manifest['coverage']:manifest['coverage'][key] = value
    receipt.update(engine=child_receipt['engine'],device=child_receipt['device'],vlm_device=child_receipt['vlm_device'])
    shutil.rmtree(work)
    if manifest['source_sha256'] != sha256(source): raise ValueError('Original workbook changed during parsing')
    dump(out/'manifest.json',manifest);receipt['validation'] = validate_bundle(out,manifest);dump(out/'receipt.json',receipt)
    return 0
