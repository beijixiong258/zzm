"""Protocol fixtures test adapter behavior, NOT real model extraction accuracy."""
from __future__ import annotations
import json
from pathlib import Path

from PIL import Image
import pytest

from tools.document_stage12.parser_helpers import dump, sha256
from tools.material_stage15.adapter import CropPolicy, adapt_page, map_region, plan_page, verify_readback, write_image_bundle
from tools.material_stage15.prepared import augment_prepared_bundle


def response(body='', images=None, uncertainty='', finish='stop'):
    return {'choices': [{'finish_reason': finish, 'message': {'role': 'assistant',
            'content': json.dumps({'body_text': body, 'images': images or [], 'uncertainty': uncertainty}, ensure_ascii=False)}}],
            'usage': {'completion_tokens': 123}, 'model': 'synthetic_protocol_fixture'}


def image_candidate(box, description='Derived unverified description'):
    return {'description': description, 'bbox': box}


@pytest.fixture
def raster(tmp_path):
    path = tmp_path / 'source.png'
    image = Image.new('RGB', (100, 80))
    image.putdata([(x * 2, y * 3, (x + y) % 256) for y in range(80) for x in range(100)])
    image.save(path)
    image.close()
    return path


def make_bundle(tmp_path, raster, actual_response, **kwargs):
    return write_image_bundle(raster, actual_response, tmp_path / 'bundle', expected_raster_sha256=sha256(raster), **kwargs)


def test_markdown_table_literal_preservation(tmp_path, raster):
    fixture = json.loads((Path(__file__).parent / 'fixtures/markdown-table-protocol.json').read_text(encoding='utf-8'))
    assert fixture['fixture_kind'] == 'synthetic_protocol_fixture_not_real_model_output'
    protocol = fixture['protocol']
    receipt = make_bundle(tmp_path, raster, response(**{'body': protocol['body_text'], 'images': protocol['images']}))
    manifest = json.loads((tmp_path / 'bundle/manifest.json').read_text(encoding='utf-8'))
    body = manifest['pages'][0]['blocks'][0]
    assert body['text'] == protocol['body_text']
    assert body['text_format'] == 'markdown'
    assert body['quality'] == 'extracted'
    assert 'not_independently_verified' in body['issues']
    assert receipt['model_calls'] == 0 and receipt['readback']['body_literal_preserved']
    assert '| --- | --- | --- | --- |' in body['text']
    assert 'T → C; T ↔ Ss' in body['text'] and '2-' in body['text']
    assert 'a. ____; b. ____' in body['text']


def test_plain_tabular_body_is_not_reconstructed():
    body = 'Timing\tSteps\n5 mins\tMotivation'
    plan = plan_page(response(body), width=100, height=80)
    assert plan['page']['blocks'][0]['text'] == body
    assert '| --- |' not in plan['page']['blocks'][0]['text']
    plain = plan_page(response(body), width=100, height=80, body_format='plain')
    assert plain['page']['blocks'][0]['text_format'] == 'plain'


def test_no_candidates_retains_complete_image(tmp_path, raster):
    receipt = make_bundle(tmp_path, raster, response('Visible source text'))
    page = json.loads((tmp_path / 'bundle/manifest.json').read_text())['pages'][0]
    images = [b for b in page['blocks'] if b['type'] == 'image']
    assert len(images) == 1 and images[0]['bbox'] == [0, 0, 1, 1]
    assert sha256(tmp_path / 'bundle' / images[0]['assets'][0]) == sha256(raster)
    assert receipt['readback']['whole_sources'] == 1
    assert receipt['readback']['input_candidates'] == 0


def test_duplicate_and_overlap_policy():
    images = [image_candidate([100, 100, 700, 700], 'one'), image_candidate([100, 100, 700, 700], 'two'),
              image_candidate([200, 200, 800, 800], 'overlapping unequal'), image_candidate([0, 0, 1000, 1000], 'whole')]
    plan = plan_page(response(images=images), width=100, height=80, policy=CropPolicy(0, 0))
    assert len(plan['regions']) == 3
    assert plan['regions'][1]['candidate_indices'] == [0, 1]
    assert plan['regions'][1]['descriptions'] == ['one', 'two']
    assert plan['regions'][1]['overlaps'] == [plan['regions'][2]['block_id']]
    assert plan['regions'][0]['candidate_indices'] == [3]
    image_blocks = [b for b in plan['page']['blocks'] if b['type'] == 'image']
    assert all(b['text'] == '' and b['quality'] == 'extracted' for b in image_blocks)


def test_padding_and_edge_snap_are_recorded():
    plan = plan_page(response(images=[image_candidate([50, 100, 900, 900])]), width=100, height=100,
                     policy=CropPolicy(2, 8))
    region = plan['regions'][1]
    assert region['candidate_boxes_1000'] == [[50, 100, 900, 900]]
    assert region['candidate_pixel_boxes'] == [[5, 10, 90, 90]]
    assert region['pixel_bbox'] == [0, 0, 100, 100]
    assert region['adjustments'] == ['outward_padding_clamped_to_source', 'snap_near_source_edge_outward']


def test_source_pixels_are_cropped_and_read_back(tmp_path, raster):
    receipt = make_bundle(tmp_path, raster, response(images=[image_candidate([123, 167, 731, 789])]),
                          policy=CropPolicy(3, 0))
    crop = receipt['readback']['evidence'][1]
    assert crop['pixel_bbox'] == [9, 10, 77, 67]
    assert crop['source_pixels_equal']
    assert crop['size'] == [68, 57]


def test_uncertainty_does_not_make_source_pixels_unusable():
    plan = plan_page(response('Body with unclear label', [image_candidate([0, 0, 500, 500])], 'The label might be 2-.'),
                     width=100, height=80)
    assert plan['page']['blocks'][0]['quality'] == 'extracted'
    assert 'model_uncertainty:The label might be 2-.' in plan['page']['blocks'][0]['issues']
    assert 'not_independently_verified' in plan['page']['blocks'][0]['issues']
    assert plan['page']['status'] == 'needs_review'
    assert all(b['quality'] == 'extracted' for b in plan['page']['blocks'] if b['type'] == 'image')
    assert plan['protocol']['uncertainty'] == 'The label might be 2-.'


def test_observed_explicit_none_keeps_raw_annotation_without_quarantining_body():
    plan = plan_page(response('MELAB grading text', uncertainty='无'), width=100, height=80)
    assert plan['page']['status'] == 'text'
    assert plan['page']['blocks'][0]['quality'] == 'extracted'
    assert plan['protocol']['uncertainty'] == '无'


@pytest.mark.parametrize('box', [[-1, 0, 20, 20], [0, 0, 1001, 10], [20, 0, 10, 20], [0, 0, 0, 20],
                               [0, float('nan'), 20, 20], [True, 0, 20, 20], [0, 1, 2]],
                         ids=['negative', 'outside', 'inverted', 'zero-area', 'nan', 'bool', 'missing'])
def test_bad_boxes_rejected(box):
    with pytest.raises(ValueError):
        plan_page(response(images=[image_candidate(box)]), width=100, height=80)


@pytest.mark.parametrize('finish', ['length', None, 'content_filter'], ids=['truncated', 'missing', 'filtered'])
def test_incomplete_finish_rejected(finish):
    with pytest.raises(ValueError, match='stop finish'):
        plan_page(response(finish=finish), width=100, height=80)


def test_page_dimensions_and_page_number_match_schema_limits():
    for width, height, page in ((20001, 1, 1), (4001, 4001, 1), (0, 80, 1), (100, 80, 1001)):
        with pytest.raises(ValueError, match='bounded'):
            plan_page(response(), width=width, height=height, page_number=page)


def test_bad_hash_rejected_before_output(tmp_path, raster):
    with pytest.raises(ValueError, match='SHA mismatch'):
        write_image_bundle(raster, response(), tmp_path / 'bundle', expected_raster_sha256='0' * 64)
    assert not (tmp_path / 'bundle').exists()


def test_raw_response_is_byte_exact(tmp_path, raster):
    raw = tmp_path / 'actual-response.json'
    actual = response('Keep spacing, punctuation O/0 and I/l exactly.\n')
    raw.write_bytes(json.dumps(actual, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
    make_bundle(tmp_path, raster, actual, response_file=raw)
    assert (tmp_path / 'bundle/raw/p0001-response.json').read_bytes() == raw.read_bytes()


def test_original_page_mapping():
    assert map_region([0, 0, 1, 1], {'raster_page_bbox': [0, 0, 0.5, 1]}) == [0, 0, 0.5, 1]
    assert map_region([0.2, 0.1, 0.8, 0.9], {'raster_page_bbox': [0, 0, 0.5, 1]}) == [0.1, 0.1, 0.4, 0.9]
    assert map_region([0, 0, 1, 1], {'kind': 'standalone_image_source'}) is None


def test_readback_detects_corrupt_crop(tmp_path, raster):
    receipt = make_bundle(tmp_path, raster, response(images=[image_candidate([100, 100, 700, 700])]), policy=CropPolicy(0, 0))
    asset = tmp_path / 'bundle' / receipt['readback']['evidence'][1]['asset']
    asset.write_bytes(raster.read_bytes())
    with pytest.raises(ValueError, match='Crop identity'):
        verify_readback(tmp_path / 'bundle')


def test_readback_detects_body_change(tmp_path, raster):
    make_bundle(tmp_path, raster, response('Actual body'))
    path = tmp_path / 'bundle/manifest.json'
    manifest = json.loads(path.read_text())
    manifest['pages'][0]['blocks'][0]['text'] = 'Invented replacement'
    dump(path, manifest)
    with pytest.raises(ValueError, match='literal'):
        verify_readback(tmp_path / 'bundle')


def test_no_evidence_overwrite(tmp_path, raster):
    root = tmp_path / 'bundle'
    adapt_page(raster, response(), root, expected_raster_sha256=sha256(raster))
    before = (root / 'raw/p0001-adapter.json').read_bytes()
    with pytest.raises(ValueError, match='overwrite'):
        adapt_page(raster, response('replacement'), root, expected_raster_sha256=sha256(raster))
    assert (root / 'raw/p0001-adapter.json').read_bytes() == before


def test_prepared_bundle_composition_preserves_original_and_other_page(tmp_path, raster):
    import pymupdf
    prepared = tmp_path / 'prepared'
    (prepared / 'pages').mkdir(parents=True)
    for index in (1, 2):
        (prepared / f'pages/p{index:04d}.png').write_bytes(raster.read_bytes())
    original_pdf = tmp_path / 'original.pdf'
    with pymupdf.open() as pdf:
        pdf.new_page(width=100, height=80)
        pdf.new_page(width=100, height=80)
        pdf.save(original_pdf)
    pages = [{'number': n, 'printed_label': None, 'rotation': 0, 'image': f'pages/p{n:04d}.png',
        'width': 100, 'height': 80, 'status': 'text', 'issues': [], 'blocks': [
        {'id': f'p{n}-b0', 'type': 'text', 'bbox': [0.0, 0.0, 1.0, 1.0], 'text': f'Native page {n}',
         'quality': 'extracted', 'issues': ['source_transcription_native'], 'assets': [], 'parent_id': None}]} for n in (1, 2)]
    manifest = {'schema_version': 1, 'source_sha256': sha256(original_pdf), 'source_format': 'pdf',
                'parser': {'name': 'synthetic-prepared', 'version': '1', 'recipe': 'fixture'},
                'page_count': 2, 'complete': True, 'warnings': [], 'pages': pages}
    dump(prepared / 'manifest.json', manifest)
    response_path = tmp_path / 'page2-response.json'
    dump(response_path, response('Fixture Markdown\n', [image_candidate([100, 100, 700, 700])]))
    receipt = augment_prepared_bundle(prepared, tmp_path / 'composed', [
        {'page_number': 2, 'raster_sha256': sha256(raster), 'response_file': str(response_path)}])
    result = json.loads((tmp_path / 'composed/manifest.json').read_text())
    assert result['source_sha256'] == sha256(original_pdf) and result['source_format'] == 'pdf'
    assert result['pages'][0] == pages[0]
    assert result['pages'][1]['blocks'][0] == pages[1]['blocks'][0]
    assert [b['id'] for b in result['pages'][1]['blocks']] == ['p2-b0', 'p2-b1', 'p2-b2', 'p2-b3']
    assert json.loads((prepared / 'manifest.json').read_text()) == manifest
    assert receipt['readback']['adapted_pages'] == 1


def test_app_plain_normalization_and_description_limits(tmp_path, raster):
    from backend.aicademiya.document_bundle import validate_bundle
    make_bundle(tmp_path, raster, response('Legacy-compatible plain body'), body_format='plain')
    normalized = validate_bundle(tmp_path / 'bundle', sha256(raster), 1)
    assert all('text_format' not in b and 'visual_description' not in b for b in normalized['pages'][0]['blocks'])
    for images in ([image_candidate([0, 0, 1000, 1000], 'x' * 2001)],
                   [image_candidate([100, 100, 700, 700], 'a' * 1000), image_candidate([100, 100, 700, 700], 'b' * 1000)]):
        with pytest.raises(ValueError, match='2000'):
            plan_page(response(images=images), width=100, height=80)


def test_current_application_optional_fields(tmp_path, raster):
    from tools.material_stage15.__main__ import application_validation
    from backend.aicademiya.document_bundle import Block
    make_bundle(tmp_path, raster, response('Fixture', [image_candidate([0, 0, 1000, 1000])]))
    actual = application_validation(tmp_path / 'bundle')
    if {'text_format', 'visual_description'} <= set(Block.model_fields):
        assert actual['valid']
    else:
        assert actual['unknown_fields'] == ['text_format', 'visual_description']
        assert all(e['type'] == 'extra_forbidden' for e in actual['errors'])
