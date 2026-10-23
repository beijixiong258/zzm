"""A small CPU adapter for the real {body_text, images, uncertainty} protocol.

plan_page is pure. adapt_page writes only source-derived pixels and raw evidence.
An image's quality describes retained pixels, not the accuracy of its description.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import shutil

from PIL import Image
from tools.document_stage12.parser_helpers import dump, sha256, validate_bundle

VERSION = '0.1.1'
MAX_PIXELS = 16_000_000


@dataclass(frozen=True)
class CropPolicy:
    padding_px: int = 12
    edge_snap_px: int = 24

    def __post_init__(self):
        if type(self.padding_px) is not int or type(self.edge_snap_px) is not int or min(self.padding_px, self.edge_snap_px) < 0:
            raise ValueError('Crop policy requires nonnegative integer pixels')


def decode_response(response: dict) -> tuple[dict, dict]:
    """Accept the saved OpenAI response, or an experiment result case, unchanged."""
    if 'choices' in response:
        choices = response['choices']
        if len(choices) != 1:
            raise ValueError('Exactly one completed choice is required')
        content = choices[0]['message']['content']
        finish = choices[0].get('finish_reason')
    else:
        content, finish = response.get('content'), response.get('finish_reason')
    if finish != 'stop':
        raise ValueError('Complete stop finish required; truncated/unknown output is not accepted')
    if not isinstance(content, str):
        raise ValueError('Actual JSON response content is required')
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError('Duplicate protocol JSON key')
            obj[key] = value
        return obj
    parsed = json.loads(content, object_pairs_hook=unique)
    if not isinstance(parsed, dict) or set(parsed) != {'body_text', 'images', 'uncertainty'}:
        raise ValueError('Expected minimal body_text/images/uncertainty protocol')
    if not isinstance(parsed['body_text'], str) or not isinstance(parsed['uncertainty'], str) or not isinstance(parsed['images'], list):
        raise ValueError('Invalid minimal protocol field type')
    if len(parsed['body_text']) > 1_000_000 or len(parsed['images']) > 100:
        raise ValueError('Response exceeds page limits')
    for candidate in parsed['images']:
        if not isinstance(candidate, dict) or set(candidate) != {'description', 'bbox'} or not isinstance(candidate['description'], str) or len(candidate['description']) > 2000:
            raise ValueError('Invalid image candidate or visual_description exceeds 2000 characters')
        box = candidate['bbox']
        if not isinstance(box, list) or len(box) != 4 or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1000 for v in box):
            raise ValueError('Candidate bbox must use finite 0..1000 coordinates')
        if box[0] >= box[2] or box[1] >= box[3]:
            raise ValueError('Candidate bbox must have positive area')
    return parsed, {'finish_reason': finish, 'usage': response.get('usage'),
                    'technical_completion_only': True, 'independent_verification': False}


def _pixels(box, width, height, policy):
    candidate = [math.floor(box[0] * width / 1000), math.floor(box[1] * height / 1000),
                 math.ceil(box[2] * width / 1000), math.ceil(box[3] * height / 1000)]
    padded = [max(0, candidate[0] - policy.padding_px), max(0, candidate[1] - policy.padding_px),
              min(width, candidate[2] + policy.padding_px), min(height, candidate[3] + policy.padding_px)]
    final = list(padded)
    for axis, edge in ((0, 0), (1, 0), (2, width), (3, height)):
        if abs(final[axis] - edge) <= policy.edge_snap_px:
            final[axis] = edge
    adjustments = []
    if padded != candidate:
        adjustments.append('outward_padding_clamped_to_source')
    if final != padded:
        adjustments.append('snap_near_source_edge_outward')
    return candidate, final, adjustments


def plan_page(response: dict, *, width: int, height: int, page_number: int = 1,
              printed_label: str | None = None, body_format: str = 'markdown',
              policy: CropPolicy = CropPolicy(), start_index: int = 0) -> dict:
    """Pure conversion. No solution generation, textual reordering or table repair.

    Markdown is stored literally; tabular plain text is NOT converted to a table.
    Full-source image is always independently available, including with images=[].
    Exact repeated boxes share one region; unequal overlapping boxes are retained.
    """
    if any(type(v) is not int or v < 1 for v in (width, height, page_number)) or page_number > 1000 or max(width, height) > 20000 or width * height > MAX_PIXELS:
        raise ValueError('Positive bounded source dimensions/page number required')
    if type(start_index) is not int or start_index < 0 or body_format not in ('plain', 'markdown'):
        raise ValueError('Invalid block start index or text format')
    parsed, finish = decode_response(response)
    uncertainty = parsed['uncertainty'].strip()
    # Observed real replies use '无' as an explicit empty value. Other unlocated
    # comments remain model annotations, not proof that every body word is bad.
    if uncertainty.casefold() in ('无', 'none', 'no uncertainty'):uncertainty = ''
    raw_ref = f'raw/p{page_number:04d}-adapter.json'
    blocks, regions, seen = [], [], {}
    def block(kind, box, text='', issues=None, assets=None, quality='extracted', description=None):
        ident = f'p{page_number}-b{start_index + len(blocks)}'
        row = {'id': ident, 'type': kind, 'bbox': box, 'text': text, 'quality': quality,
               'issues': issues or [], 'assets': assets or [], 'parent_id': None}
        if kind == 'text':
            row['text_format'] = body_format
        if description:
            row['visual_description'] = description
        blocks.append(row)
        return row
    if parsed['body_text']:
        issues = ['source_transcription_ocr; machine_extracted_vlm',
                  'not_independently_verified', 'body_geometry_unlocalized; whole_source_locator',
                  'raw_provenance:' + raw_ref]
        if uncertainty:
            issues.append('model_uncertainty_unscoped; see_raw_uncertainty')
            issues.append('model_uncertainty:' + uncertainty[:1900])
        block('text', [0.0, 0.0, 1.0, 1.0], parsed['body_text'], issues=issues)
    full = block('image', [0.0, 0.0, 1.0, 1.0], issues=[
        'source_image_occurrence; full_source_retained',
        'source_pixels_extracted; no_semantic_approval',
        'complete_source_context; retain_instructions_blanks_options_and_connections',
        'raw_provenance:' + raw_ref])
    full['assets'] = [f'assets/{full["id"]}.png']
    whole = [0, 0, width, height]
    regions.append({'block_id': full['id'], 'asset': full['assets'][0], 'role': 'whole_source',
                    'candidate_indices': [], 'candidate_boxes_1000': [], 'descriptions': [],
                    'candidate_pixel_boxes': [], 'pixel_bbox': whole, 'adjustments': [], 'overlaps': []})
    for index, candidate in enumerate(parsed['images']):
        key = tuple(candidate['bbox'])
        original, final, adjustments = _pixels(candidate['bbox'], width, height, policy)
        # A literal whole-source box reuses the mandatory whole-source image.
        if key == (0, 0, 1000, 1000):
            region = regions[0]
        elif key in seen:
            region = seen[key]
        else:
            box = [final[0] / width, final[1] / height, final[2] / width, final[3] / height]
            row = block('image', box, issues=['source_image_occurrence; candidate_region',
                        'source_pixels_extracted; no_semantic_approval',
                        'visual_description_derived_unverified; not_source_quote',
                        'whole_source_context:' + full['id'], 'raw_provenance:' + raw_ref])
            row['assets'] = [f'assets/{row["id"]}.png']
            region = {'block_id': row['id'], 'asset': row['assets'][0], 'role': 'candidate_region',
                      'candidate_indices': [], 'candidate_boxes_1000': [], 'descriptions': [],
                      'candidate_pixel_boxes': [], 'pixel_bbox': final, 'adjustments': adjustments, 'overlaps': []}
            regions.append(region)
            seen[key] = region
        region['candidate_indices'].append(index)
        region['candidate_boxes_1000'].append(candidate['bbox'])
        region['candidate_pixel_boxes'].append(original)
        region['descriptions'].append(candidate['description'])
        row = next(b for b in blocks if b['id'] == region['block_id'])
        descriptions = list(dict.fromkeys(d for d in region['descriptions'] if d))
        if descriptions:
            combined = '\n'.join(descriptions)
            if len(combined) > 2000:
                raise ValueError('Deduplicated visual_description exceeds 2000 characters; raw descriptions are not truncated')
            row['visual_description'] = combined
            if 'visual_description_derived_unverified; not_source_quote' not in row['issues']:
                row['issues'].append('visual_description_derived_unverified; not_source_quote')
        if len(region['candidate_indices']) > 1:
            row['issues'] = list(dict.fromkeys(row['issues'] + ['exact_candidate_bbox_deduplicated; raw_candidates_retained']))
    candidates = regions[1:]
    for i, a in enumerate(candidates):
        for b in candidates[i + 1:]:
            x, y = a['pixel_bbox'], b['pixel_bbox']
            if max(x[0], y[0]) < min(x[2], y[2]) and max(x[1], y[1]) < min(x[3], y[3]):
                a['overlaps'].append(b['block_id'])
                b['overlaps'].append(a['block_id'])
    issues = ['source_grounded_multimodal_adapter', 'raw_provenance:' + raw_ref]
    if uncertainty:
        issues.append('model_uncertainty_unscoped; see_raw_uncertainty')
    return {'page': {'number': page_number, 'printed_label': printed_label, 'rotation': 0,
                     'image': f'pages/p{page_number:04d}.png', 'width': width, 'height': height,
                     'status': 'needs_review' if uncertainty else 'text',
                     'issues': issues, 'blocks': blocks},
            'regions': regions, 'protocol': parsed, 'finish': finish, 'crop_policy': asdict(policy),
            'raw_ref': raw_ref, 'body_text_format': body_format}


def _source_image(path):
    with Image.open(path) as image:
        if image.format != 'PNG' or getattr(image, 'n_frames', 1) != 1:
            raise ValueError('This page adapter requires an already prepared single PNG raster')
        if max(image.width, image.height) > 20000 or image.width * image.height > MAX_PIXELS:
            raise ValueError('Source raster exceeds schema dimension/pixel limit')
        image.load()
        # No EXIF transform, resizing, overlays or RGB conversion in the adapter.
        return image.copy()


def map_region(box: list[float], mapping: dict) -> list[float] | None:
    """Map into original/rendered page only when a recorded outer crop is supplied."""
    outer = mapping.get('raster_page_bbox')
    if outer is None:
        return None
    if len(outer) != 4 or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in outer) or outer[0] >= outer[2] or outer[1] >= outer[3]:
        raise ValueError('Invalid recorded raster-to-source page bbox')
    x0, y0, x1, y1 = outer
    return [x0 + box[0] * (x1 - x0), y0 + box[1] * (y1 - y0),
            x0 + box[2] * (x1 - x0), y0 + box[3] * (y1 - y0)]


def adapt_page(raster: Path | str, response: dict, bundle_root: Path | str, *,
               expected_raster_sha256: str, source_mapping: dict | None = None,
               page_number: int = 1, printed_label: str | None = None,
               body_format: str = 'markdown', policy: CropPolicy = CropPolicy(),
               start_index: int = 0, response_file: Path | str | None = None) -> dict:
    """Write a page into a caller-owned new/prepared bundle and return page dict.

    source_mapping is recorded evidence, never a model-generated ID/page mapping.
    For prepared PDF callers pass real page_number and original source mapping.
    start_index lets the caller append to existing block identities safely.
    """
    raster, root = Path(raster), Path(bundle_root)
    if not re.fullmatch(r'[0-9a-f]{64}', expected_raster_sha256) or sha256(raster) != expected_raster_sha256:
        raise ValueError('Source raster SHA mismatch')
    if response_file is not None and json.loads(Path(response_file).read_text(encoding='utf-8')) != response:
        raise ValueError('Raw response file does not match supplied response')
    source = _source_image(raster)
    try:
        plan = plan_page(response, width=source.width, height=source.height,
                         page_number=page_number, printed_label=printed_label,
                         body_format=body_format, policy=policy, start_index=start_index)
        mapping = dict(source_mapping or {'kind': 'standalone_image_source'})
        mapping['input_raster_sha256'] = expected_raster_sha256
        for region in plan['regions']:
            box = region['pixel_bbox']
            normalized = [box[0] / source.width, box[1] / source.height, box[2] / source.width, box[3] / source.height]
            region['source_page_bbox'] = map_region(normalized, mapping)
        paths = [plan['page']['image'], f'raw/p{page_number:04d}-source.png',
                 f'raw/p{page_number:04d}-response.json', plan['raw_ref']] + [r['asset'] for r in plan['regions']]
        page_path = root / plan['page']['image']
        if page_path.exists() and sha256(page_path) != expected_raster_sha256:
            raise ValueError('Prepared page raster identity differs from adapter input')
        if any((root / p).exists() for p in paths[1:]):
            raise ValueError('Adapter refuses to overwrite existing page evidence/assets')
        for ref in paths:
            (root / ref).parent.mkdir(parents=True, exist_ok=True)
        if not page_path.exists():
            shutil.copyfile(raster, page_path)
        shutil.copyfile(raster, root / f'raw/p{page_number:04d}-source.png')
        raw_response = root / f'raw/p{page_number:04d}-response.json'
        if response_file is None:
            dump(raw_response, response)
        else:
            shutil.copyfile(response_file, raw_response)
        for region in plan['regions']:
            target = root / region['asset']
            if region['role'] == 'whole_source':
                shutil.copyfile(raster, target)
            else:
                with source.crop(tuple(region['pixel_bbox'])) as crop:
                    crop.save(target, format='PNG')
            region['asset_sha256'] = sha256(target)
        dump(root / plan['raw_ref'], {**plan, 'source_mapping': mapping,
             'source_raster': f'raw/p{page_number:04d}-source.png',
             'source_raster_sha256': expected_raster_sha256,
             'response_asset': f'raw/p{page_number:04d}-response.json',
             'response_sha256': sha256(raw_response),
             'representation_note': 'Literal body string preserved; Markdown tag does not imply tabular reconstruction.'})
        return plan['page']
    finally:
        source.close()


def write_image_bundle(raster: Path | str, response: dict, output: Path | str, *,
                       expected_raster_sha256: str, source_mapping: dict | None = None,
                       response_file: Path | str | None = None, body_format: str = 'markdown',
                       policy: CropPolicy = CropPolicy()) -> dict:
    """One standalone PNG document; preview.pdf is explicitly derived, not original."""
    from tools.material_stage13.simple_material import image_pdf
    raster, out = Path(raster), Path(output)
    # Resolve the prerequisites before creating a possibly partial output.
    decode_response(response)
    if sha256(raster) != expected_raster_sha256:
        raise ValueError('Source raster SHA mismatch')
    with _source_image(raster):
        pass
    out.mkdir(parents=True, exist_ok=False)
    page = adapt_page(raster, response, out, expected_raster_sha256=expected_raster_sha256,
                      source_mapping=source_mapping, response_file=response_file,
                      body_format=body_format, policy=policy)
    info = image_pdf(raster, out / 'preview.pdf', 'png')
    manifest = {'schema_version': 1, 'source_sha256': expected_raster_sha256, 'source_format': 'png',
                'preview_pdf': 'preview.pdf', 'parser': {'name': 'stage15-material-adapter',
                'version': VERSION, 'recipe': 'imported-completed-vlm+literal-body+retained-source-pixels'},
                'page_count': 1, 'complete': True,
                'warnings': ['Imported model transcription is not independently verified.',
                             'Visual descriptions are derived retrieval metadata, not source quotations.',
                             'Whole source is retained; use it when an exercise needs complete context.'],
                'pages': [page], 'coverage': {'version': 1, 'representation': 'original_image',
                'expected_pages': 1, 'rendered_pages': 1, 'page_set_complete': True,
                'semantic_accuracy_approved': False, 'all_visuals_transcribed': False,
                'original_image': info, 'rendered_pdf_sha256': sha256(out / 'preview.pdf')}}
    dump(out / 'manifest.json', manifest)
    receipt = {'status': 'complete', 'device': 'cpu', 'engine': 'imported_evidence',
               'model_calls': 0, 'quality_accepted': False, 'independent_verification': False,
               'source_sha256': expected_raster_sha256, 'validation': validate_bundle(out),
               'readback': verify_readback(out)}
    dump(out / 'receipt.json', receipt)
    return receipt


def _pixel_hash(image):
    return hashlib.sha256(image.tobytes()).hexdigest()


def verify_readback(bundle_root: Path | str) -> dict:
    """Read exact persisted targets; compare every crop against recorded source pixels.

    This verifies adapter geometry/bytes/literal preservation, not model accuracy.
    """
    root = Path(bundle_root)
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    validation = validate_bundle(root, manifest)
    evidence, candidate_count = [], 0
    for page in manifest['pages']:
        record_path = root / f'raw/p{page["number"]:04d}-adapter.json'
        if not record_path.exists():
            continue  # Other, unchanged pages in a prepared bundle are parser-validated.
        record = json.loads(record_path.read_text(encoding='utf-8'))
        source_path = root / record['source_raster']
        if sha256(source_path) != record['source_raster_sha256'] or sha256(root / page['image']) != record['source_raster_sha256']:
            raise ValueError('Retained source image changed')
        response_path = root / record['response_asset']
        if sha256(response_path) != record['response_sha256']:
            raise ValueError('Raw response bytes changed')
        parsed, _ = decode_response(json.loads(response_path.read_text(encoding='utf-8')))
        blocks = {b['id']: b for b in page['blocks']}
        body = [b for b in record['page']['blocks'] if b['type'] == 'text']
        if len(body) != bool(parsed['body_text']) or (body and blocks[body[0]['id']]['text'] != parsed['body_text']):
            raise ValueError('Body text is not the literal saved model string')
        candidate_count += len(parsed['images'])
        with _source_image(source_path) as source:
            for region in record['regions']:
                block = blocks[region['block_id']]
                if block['type'] != 'image' or block['text'] != '' or block['quality'] != 'extracted' or block['assets'] != [region['asset']]:
                    raise ValueError('Source image block contract changed')
                expected_box = [region['pixel_bbox'][0] / source.width, region['pixel_bbox'][1] / source.height,
                                region['pixel_bbox'][2] / source.width, region['pixel_bbox'][3] / source.height]
                if block['bbox'] != expected_box or sha256(root / region['asset']) != region['asset_sha256']:
                    raise ValueError('Crop identity or normalized geometry changed')
                with source.crop(tuple(region['pixel_bbox'])) as expected, Image.open(root / region['asset']) as actual:
                    actual.load()
                    if actual.mode != expected.mode or actual.size != expected.size or actual.tobytes() != expected.tobytes():
                        raise ValueError('Crop differs from original source pixels')
                    evidence.append({'page': page['number'], 'block_id': block['id'], 'asset': region['asset'],
                        'role': region['role'], 'pixel_bbox': region['pixel_bbox'], 'size': list(actual.size),
                        'sha256': region['asset_sha256'], 'pixel_sha256': _pixel_hash(actual),
                        'source_pixels_equal': True, 'source_page_bbox': region['source_page_bbox'],
                        'candidate_indices': region['candidate_indices'], 'adjustments': region['adjustments'],
                        'overlaps': region['overlaps']})
    return {'valid': True, 'parser_validation': validation, 'adapted_pages': len({r['page'] for r in evidence}),
            'input_candidates': candidate_count, 'source_image_assets': len(evidence),
            'whole_sources': sum(r['role'] == 'whole_source' for r in evidence),
            'body_literal_preserved': True, 'evidence': evidence,
            'semantic_accuracy_approved': False, 'model_calls': 0}
