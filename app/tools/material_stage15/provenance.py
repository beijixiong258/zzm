"""Resolve experiment provenance from recorded manifests, never filename guesses."""
from __future__ import annotations
import json
from pathlib import Path

from tools.document_stage12.parser_helpers import sha256


def _load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _checked_original(source):
    path = Path(source['strict_original_path'])
    if not path.is_file() or sha256(path) != source['sha256']:
        raise ValueError('Recorded corpus original is unavailable or changed: ' + source['id'])
    return {'source_id': source['id'], 'original_source_path': str(path),
            'source_sha256': source['sha256'], 'source_format': source['type'],
            'original_hash_checked': True}


def resolve_experiment_trace(app_root: Path | str, experiment: Path | str,
                             name: str, expected_sha256: str) -> dict:
    """Known source/page traces are supplemental to the standalone PNG identity.

    Missing geometric chains stay standalone: a manifest's descriptive label is
    retained as a hint, not promoted to an original-PDF page/region assertion.
    """
    app, experiment = Path(app_root), Path(experiment)
    entries = _load(experiment / 'source-manifest.json')['cases']
    matches = [entry for entry in entries if entry['folder'] + '.png' == name]
    if len(matches) != 1:
        raise ValueError('Input has no unique source-manifest entry')
    entry = matches[0]
    original_image = Path(entry['image_source'])
    if not original_image.is_file() or sha256(original_image) != expected_sha256:
        raise ValueError('Experiment image differs from recorded source image')
    base = {'kind': 'standalone_image_source', 'input_name': name,
            'recorded_image_source': str(original_image), 'image_source_hash_checked': True,
            'declared_source_hint': entry['source'], 'evidence': ['source-manifest.json'],
            'trace_status': 'standalone_image_source; original_page_geometry_unresolved'}
    dataset = app / 'artifacts/ocr-stage1/dataset'
    samples = _load(dataset / 'samples.json')['samples']
    sources = {row['id']: row for row in _load(app / 'artifacts/stage14/corpus-audit/sources-final.json')}
    sample_matches = [row for row in samples if Path(row['image_path']) == original_image]
    if sample_matches:
        if len(sample_matches) != 1:
            raise ValueError('Ambiguous dataset raster mapping')
        sample = sample_matches[0]
        if sample['image_sha256'] != expected_sha256:
            raise ValueError('Dataset image SHA disagrees with actual experiment input')
        source = sources[sample['source_id']]
        original = _checked_original(source)
        render_path = dataset / sample['render_source_relpath']
        if not render_path.is_file():
            raise ValueError('Recorded dataset rendering source is missing')
        render = sample['render']
        outer, page = render['crop_points'], render['original_page_points']
        width, height = page[2] - page[0], page[3] - page[1]
        box = [(outer[0] - page[0]) / width, (outer[1] - page[1]) / height,
               (outer[2] - page[0]) / width, (outer[3] - page[1]) / height]
        return {**base, **original, 'kind': 'recorded_source_page',
            'trace_status': 'recorded_geometry_and_source_hashes_checked; not_independent_content_review',
            'sample_id': sample['id'], 'page_number': sample['page_1based'],
            'page_number_kind': 'original_pdf_physical' if source['type'] == 'pdf' else 'derived_office_rendered_page',
            'render_source_sha256': sha256(render_path), 'render_source_path': str(render_path),
            'raster_page_bbox': box, 'recorded_render': render,
            'evidence': base['evidence'] + ['artifacts/ocr-stage1/dataset/samples.json',
                                          'artifacts/stage14/corpus-audit/sources-final.json']}
    r6 = app / 'artifacts/stage14/r6-final-inputs'
    mask_root = r6 / 'readback/mask-bundle'
    mask_manifest = _load(mask_root / 'manifest.json')
    for page in mask_manifest['pages']:
        if mask_root / page['image'] == original_image:
            record = _load(r6 / 'manifest.json')
            original_sha = record['source_pdf_original_sha256']
            originals = [s for s in sources.values() if s['sha256'] == original_sha]
            if len(originals) != 1:
                raise ValueError('Subset has no unique recorded original source')
            original = _checked_original(originals[0])
            return {**base, **original, 'kind': 'recorded_source_page',
                'page_number': record['subset_pages_mapping'][str(page['number'])],
                'page_number_kind': 'original_pdf_physical', 'subset_page_number': page['number'],
                'subset_source_sha256': mask_manifest['source_sha256'],
                'raster_page_bbox': [0.0, 0.0, 1.0, 1.0],
                'trace_status': 'recorded_subset_page_mapping_and_source_hash_checked',
                'evidence': base['evidence'] + ['artifacts/stage14/r6-final-inputs/manifest.json']}
    scan_root = app / 'artifacts/stage14/parser-recovery/qa-fresh-scan'
    if original_image.parent == scan_root / 'raw':
        scan = _load(scan_root / 'manifest.json')
        matches = [s for s in sources.values() if s['sha256'] == scan['source_sha256']]
        region = _load(original_image.with_name(original_image.name.replace('-ocr.png', '.json')))
        if len(matches) != 1:
            raise ValueError('Scan bundle has no unique recorded original')
        return {**base, **_checked_original(matches[0]), 'kind': 'recorded_source_page',
            'page_number': region['original_pdf_page'], 'page_number_kind': 'original_pdf_physical',
            'raster_page_bbox': region['final_raster_bbox'],
            'trace_status': 'recorded_region_geometry_and_source_hash_checked',
            'evidence': base['evidence'] + [str(original_image.with_name(original_image.name.replace('-ocr.png', '.json'))),
                                          'artifacts/stage14/parser-recovery/qa-fresh-scan/manifest.json']}
    transforms = _load(app / 'artifacts/stage14/vision-focused-input/source-transforms.json')
    matches = [row for row in transforms if row['output'] == original_image.name and row['sha256'] == expected_sha256]
    if len(matches) == 1:
        transform = matches[0]
        if sha256(transform['source']) != transform['source_sha256']:
            raise ValueError('Pre-experiment transform source changed')
        base['recorded_transform'] = transform
        base['evidence'].append('artifacts/stage14/vision-focused-input/source-transforms.json')
        # This chain ends at a corrected PNG, not a verified original PDF bbox.
    return base
