"""Adversarial parser boundary checks, small SYNTHETIC images with short IDs."""
import copy
import json
from pathlib import Path
import pytest
from backend.aicademiya import document_bundle as bundle
from .test_stage12_document_api import synthetic_bundle, pdf_bytes, docenv, complete, upload, wait_job, endpoint
from .conftest import expect


@pytest.fixture
def output(tmp_path):
    source = tmp_path/'synthetic.pdf'
    source.write_bytes(pdf_bytes())
    root = tmp_path/'bundle'
    value = synthetic_bundle(source, root)
    return source, root, value


def update(path, value):
    (path/'manifest.json').write_text(json.dumps(value), encoding='utf-8')


def damage(value, case):
    page = value['pages'][0]
    block = page['blocks'][0]
    if case == 'hash': value['source_sha256'] = '0'*64
    elif case == 'count': value['page_count'] = 3
    elif case == 'missing': value['pages'].pop()
    elif case == 'order': value['pages'].reverse()
    elif case == 'repeat-page': value['pages'][1]['number'] = 1
    elif case == 'partial': value['complete'] = False
    elif case == 'schema': value['schema_version'] = 2
    elif case == 'extra': value['provider_config'] = {'secret':'SYNTHETIC private'}
    elif case == 'absolute': page['image'] = 'C:/private.png'
    elif case == 'traversal': page['image'] = 'pages/../private.png'
    elif case == 'backslash': page['image'] = 'pages\\p1.png'
    elif case == 'rawasset': block['assets'] = ['raw/private.png']
    elif case == 'missingasset': block['assets'] = ['assets/absent.png']
    elif case == 'nan': block['bbox'][0] = float('nan')
    elif case == 'infinite': block['bbox'][1] = float('inf')
    elif case == 'negative': block['bbox'][0] = -.1
    elif case == 'inverted': block['bbox'] = [1.,1.,0.,0.]
    elif case == 'wrong-id': block['id'] = 'p2-b0'
    elif case == 'duplicate-id': page['blocks'].append(copy.deepcopy(block))
    elif case == 'parent': block['parent_id'] = 'p1-b90'
    elif case == 'self-parent': block['parent_id'] = block['id']
    elif case == 'cross-parent': block['parent_id'] = 'p2-b0'
    elif case == 'approval': block['quality'] = 'approved'
    elif case == 'review': block['review'] = {'by':'spoof','at':'now','reason':'No'}
    elif case == 'rawtext': block['raw_text'] = 'Invented original'
    elif case == 'dimensions': page['width'] = 33
    elif case == 'hugepixels': page.update(width=20000,height=20000)
    elif case == 'wrongtype': value['page_count'] = '2'
    elif case == 'bool-schema': value['schema_version'] = True
    elif case == 'bool-rotation': page['rotation'] = False
    else: raise AssertionError(case)


CASES = ['hash','count','missing','order','repeat-page','partial','schema','extra','absolute','traversal',
         'backslash','rawasset','missingasset','nan','infinite','negative','inverted','wrong-id','duplicate-id',
         'parent','self-parent','cross-parent','approval','review','rawtext','dimensions','hugepixels','wrongtype',
         'bool-schema','bool-rotation']


@pytest.mark.parametrize('case', CASES, ids=CASES)
def test_invalid_bundle_rejected_before_revision_commit(output, case):
    source, root, value = output
    damage(value, case)
    update(root, value)
    with pytest.raises(bundle.BundleError):
        bundle.validate_bundle(root, bundle.sha256_file(source), 2)


@pytest.mark.parametrize('case', ['manifest','file','total','blocks','image'], ids=['manifest-bytes','file-bytes','bundle-bytes','block-count','image-content'])
def test_actual_resource_limits_not_only_declared_fields(output, monkeypatch, case):
    source, root, value = output
    if case == 'manifest': monkeypatch.setattr(bundle, 'MAX_MANIFEST_BYTES', 100)
    elif case == 'file': (root/'raw'/'big.bin').write_bytes(b'x'*1000); monkeypatch.setattr(bundle, 'MAX_FILE_BYTES', 100)
    elif case == 'total': monkeypatch.setattr(bundle, 'MAX_BUNDLE_BYTES', 100)
    elif case == 'blocks': monkeypatch.setattr(bundle, 'MAX_BLOCKS', 1)
    elif case == 'image': (root/'pages'/'p1.png').write_bytes(b'Not an image')
    with pytest.raises(bundle.BundleError):
        bundle.validate_bundle(root, bundle.sha256_file(source), 2)


@pytest.mark.parametrize('name', ['../x.png','pages//x.png','pages/./x.png','/x.png','C:/x.png','pages/x:stream.png','pages/NUL.png','pages/x.png.','pages/x.png '], ids=['parent','double','dot','absolute','drive','ads','device','dot-end','space-end'])
def test_relative_filenames_portable_safe(name):
    with pytest.raises(bundle.BundleError):
        bundle.relative_name(name)


def test_symlinks_unreferenced_raw_and_registered_asset_rejected(output):
    source, root, value = output
    # Windows developer mode may disable symlink creation. A deterministic mock
    # checks the same regular-file gate; real links are also exercised when available.
    target = root/'raw'/'outside.txt'
    try:
        target.symlink_to(source)
    except OSError:
        from unittest.mock import patch
        original = Path.is_symlink
        with patch.object(Path, 'is_symlink', lambda self: self == root/'raw'/'synthetic-receipt.txt' or original(self)):
            with pytest.raises(bundle.BundleError):
                bundle.validate_bundle(root, bundle.sha256_file(source), 2)
        return
    with pytest.raises(bundle.BundleError):
        bundle.validate_bundle(root, bundle.sha256_file(source), 2)


def test_blank_image_page_complete_and_cycle_rejected(output):
    source, root, value = output
    value['pages'][1].update(status='blank', blocks=[])
    update(root, value)
    assert bundle.validate_bundle(root, bundle.sha256_file(source), 2)['page_count'] == 2
    first = value['pages'][0]['blocks'][0]
    second = copy.deepcopy(first)
    second.update(id='p1-b1', parent_id=first['id'])
    first['parent_id'] = second['id']
    value['pages'][0]['blocks'].append(second)
    update(root, value)
    with pytest.raises(bundle.BundleError):
        bundle.validate_bundle(root, bundle.sha256_file(source), 2)


def test_duplicate_manifest_keys_rejected(output):
    source, root, value = output
    encoded = json.dumps(value)
    (root/'manifest.json').write_text('{"schema_version":1,'+encoded[1:], encoding='utf-8')
    with pytest.raises(bundle.BundleError):
        bundle.validate_bundle(root, bundle.sha256_file(source), 2)


@pytest.mark.parametrize('case', ['hash','partial','missingasset','approval'], ids=['sha-mismatch','partial','asset-missing','worker-approval'])
def test_parser_invalid_output_job_failed_raw_retained_no_fake_pages(docenv, case):
    app, teacher, student, processor = docenv
    processor.mutate = lambda value: damage(value, case)
    material = expect(upload(teacher))
    mid = material['id']
    job = wait_job(teacher, mid)
    assert job['status'] == 'failed' and job['processed_pages'] == 0 and job['revision_id'] is None
    info = expect(teacher.get(endpoint(mid)))
    assert info['document'] is None and info['pages'] == []
    assert (app.state.document_queue.uploads/'documents'/job['id']/'raw'/'synthetic-receipt.txt').is_file()
    with app.state.database.connect() as conn:
        assert conn.execute('SELECT count(*) FROM document_revisions').fetchone()[0] == 0
