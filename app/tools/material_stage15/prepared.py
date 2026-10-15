"""Append imported page evidence to a new copy of an existing prepared bundle."""
from __future__ import annotations
import json
from pathlib import Path
import re
import shutil

from tools.document_stage12.parser_helpers import dump, sha256, validate_bundle
from .adapter import CropPolicy, VERSION, adapt_page, verify_readback


def augment_prepared_bundle(prepared_root: Path | str, output: Path | str,
                            page_inputs: list[dict], *, body_format: str = 'markdown',
                            policy: CropPolicy = CropPolicy()) -> dict:
    """page_inputs=[{page_number, raster_sha256, response_file, source_mapping?}].

    Use the prepared bundle's exact page rasters and source identity. Native blocks,
    unrelated pages, preview and supplements are preserved. Appending VLM prose may
    duplicate native prose; the parent's reader chooses suitable evidence by type.
    No source hash/page renumbering; no in-place mutation or application import.
    """
    prepared, out = Path(prepared_root), Path(output)
    original = json.loads((prepared / 'manifest.json').read_text(encoding='utf-8'))
    validate_bundle(prepared, original)
    if out.exists() or out.resolve().is_relative_to(prepared.resolve()):
        raise ValueError('A distinct, new output bundle is required')
    pages = {p['number']: p for p in original['pages']}
    numbers = [row['page_number'] for row in page_inputs]
    if not numbers or len(set(numbers)) != len(numbers):
        raise ValueError('Unique actual prepared page numbers required')
    for row in page_inputs:
        if row['page_number'] not in pages or sha256(prepared / pages[row['page_number']]['image']) != row['raster_sha256']:
            raise ValueError('Prepared source page identity mismatch')
    shutil.copytree(prepared, out)
    dump(out / 'raw/stage15-prepared-manifest.json', original)
    for row in page_inputs:
        page = pages[row['page_number']]
        if page['rotation'] != 0:
            raise ValueError('Pass an already upright prepared page; do not guess rotated mappings')
        indices = [int(re.match(r'p\d+-b(\d+)', b['id']).group(1)) for b in page['blocks']]
        source_mapping = row.get('source_mapping', {
            'kind': 'prepared_source_page', 'source_sha256': original['source_sha256'],
            'source_format': original.get('source_format', 'pdf'), 'page_number': page['number'],
            'page_number_kind': 'original_pdf_physical' if original.get('source_format', 'pdf') == 'pdf' else 'derived_rendered_page',
            'raster_page_bbox': [0.0, 0.0, 1.0, 1.0]})
        if source_mapping.get('source_sha256') != original['source_sha256'] or source_mapping.get('page_number') != page['number']:
            raise ValueError('Source mapping must bind the exact prepared original/page')
        response_file = Path(row['response_file'])
        adapted = adapt_page(out / page['image'], json.loads(response_file.read_text(encoding='utf-8')), out,
            expected_raster_sha256=row['raster_sha256'], source_mapping=source_mapping,
            page_number=page['number'], printed_label=page['printed_label'], body_format=body_format,
            policy=policy, start_index=max(indices, default=-1) + 1, response_file=response_file)
        page['blocks'].extend(adapted['blocks'])
        page['issues'].extend(adapted['issues'])
        if adapted['status'] == 'needs_review':
            page['status'] = 'needs_review'
    original['parser'] = {'name': 'stage15-material-adapter', 'version': VERSION,
                          'recipe': 'prepared-source-preserved+imported-completed-vlm-append'}
    original['warnings'].append('Appended model transcription/descriptions are not independently verified.')
    # Existing processing counters belong to the preserved prior parser snapshot.
    # Keep source frame metadata, but do not advertise stale block counters.
    previous_coverage = original.get('coverage') or {}
    original['coverage'] = {key: previous_coverage[key] for key in (
        'version', 'representation', 'expected_pages', 'rendered_pages', 'page_set_complete',
        'semantic_accuracy_approved', 'all_visuals_transcribed', 'original_image',
        'rendered_pdf_sha256', 'rendered_pdf_pages', 'original_source_format') if key in previous_coverage}
    original['coverage'].update(version=1, expected_pages=original['page_count'],
        rendered_pages=len(original['pages']), page_set_complete=original['complete'], semantic_accuracy_approved=False)
    dump(out / 'manifest.json', original)
    receipt = {'status': 'complete', 'device': 'cpu', 'model_calls': 0,
               'quality_accepted': False, 'independent_verification': False,
               'validation': validate_bundle(out), 'readback': verify_readback(out)}
    dump(out / 'stage15-receipt.json', receipt)
    return receipt
