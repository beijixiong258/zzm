"""Reuse this job's CPU Office preparation without invoking LibreOffice twice."""
from __future__ import annotations
import json
import shutil
from pathlib import Path
from parser_helpers import dump, sha256, validate_bundle

OFFICE_RAW = ('office-inventory.json', 'office-media', 'office-parts',
              'legacy-doc-inventory.json', 'derived.docx',
              'legacy-ppt-inventory.json', 'derived.pptx')


def reuse_office(prepared, source, fmt, out):
    prepared, source, out = Path(prepared), Path(source), Path(out)
    if not prepared.is_dir() or prepared.is_symlink() or any(p.is_symlink() for p in prepared.parents):
        raise ValueError('A safe prepared Office bundle is required')
    manifest = json.loads((prepared/'manifest.json').read_text(encoding='utf-8'))
    receipt = json.loads((prepared/'receipt.json').read_text(encoding='utf-8'))
    validate_bundle(prepared, manifest)
    if (manifest.get('source_sha256') != sha256(source) or manifest.get('source_format') != fmt
            or manifest.get('preview_pdf') != 'preview.pdf' or not manifest.get('complete')
            or receipt.get('status') != 'complete' or receipt.get('engine') != 'native'
            or any(row.get('model_processed') or row.get('model_calls', 0) for row in receipt.get('page_timings', []))):
        raise ValueError('Prepared Office bundle does not match this original/native phase')
    preview = prepared/'preview.pdf'
    if preview.is_symlink() or sha256(preview) != manifest.get('coverage', {}).get('rendered_pdf_sha256'):
        raise ValueError('Prepared Office PDF identity changed')
    for name in OFFICE_RAW:
        path = prepared/'raw'/name
        if path.is_symlink() or (path.is_dir() and any(p.is_symlink() for p in path.rglob('*'))):
            raise ValueError('Unsafe prepared Office evidence')
    (out/'raw').mkdir(parents=True, exist_ok=True)
    shutil.copyfile(preview, out/'preview.pdf')
    for name in OFFICE_RAW:
        path = prepared/'raw'/name
        if path.is_dir():
            shutil.copytree(path, out/'raw'/name)
        elif path.is_file():
            shutil.copyfile(path, out/'raw'/name)
    dump(out/'raw/native-preparation-receipt.json', receipt)
    native = json.loads((out/'raw/office-inventory.json').read_text(encoding='utf-8'))
    binary_path = out/('raw/legacy-'+fmt+'-inventory.json')
    binary = json.loads(binary_path.read_text(encoding='utf-8')) if binary_path.is_file() else None
    return native, binary, manifest['page_count'], receipt.get('conversion', [])


def visual_plan(manifest, receipt):
    """Conservative structural triage, not an OCR/semantic accuracy decision."""
    if manifest.get('source_format') in ('txt','md'):
        return {'needs_gpu':False,'visual_pages':[],'fullpage_pages':[],
                'classification':'exact_native_text_no_ocr_needed'}
    if (manifest.get('coverage') or {}).get('representation') == 'workbook_native_cell_ledger':
        pages = manifest['coverage'].get('media_gallery_pages', [])
        return {'needs_gpu':bool(pages),'visual_pages':pages,'fullpage_pages':pages,
                'classification':'exact_native_cells; only_original_media_requires_visual_review'}
    timings = {row['page']:row for row in receipt['page_timings']}
    pages, full_pages = [], []
    for page in manifest['pages']:
        if page['status'] == 'blank':
            continue
        blocks = page['blocks']
        text = '\n'.join(b['text'] for b in blocks)
        issues = [i for b in blocks for i in b['issues']] + page.get('issues', [])
        full = (len(text.strip()) < 40 or timings.get(page['number'], {}).get('vector_paths', 0) > 0
                or any('font_mapping' in i or 'symbol_density_suspect' in i or 'bbox_invalid' in i
                       or i == 'broken_text_layer' for i in issues))
        if full:
            full_pages.append(page['number'])
        if full or any(b['type'] in ('image','table','equation','other') for b in blocks):
            pages.append(page['number'])
    return {'needs_gpu':bool(pages), 'visual_pages':pages, 'fullpage_pages':full_pages,
            'classification':'native_structure_only_not_semantic_approval'}
