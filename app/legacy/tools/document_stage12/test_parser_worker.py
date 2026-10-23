"""Real Ubuntu worker acceptance checks against read-only source PDF."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from parser_helpers import dump, sha256, validate_bundle

ROOT=Path(__file__).parent
BASE=Path('/home/adminz/llm/ocr-stage1-20261009')
SRC=BASE/'data/dataset/sources/src02.pdf'
PYTHON=BASE/'whole-document-pilot/.venv/bin/python'


def main():
    env=dict(os.environ,CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4')
    checks=[]
    for name in ('chapter10-imported-v2','guide317-native-v2'):
        dest=ROOT/'bundles'/name
        checks.append({'case':name,**validate_bundle(dest)})
    dest=ROOT/'bundles'/('deadline-partial-'+str(time.time_ns()))
    cmd=[str(PYTHON),str(ROOT/'parser_worker.py'),'--input',str(SRC),'--output',str(dest),'--dpi','96','--deadline-seconds','1']
    p=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=30)
    receipt=json.loads((dest/'receipt.json').read_text())
    manifest=json.loads((dest/'manifest.json').read_text())
    assert p.returncode!=0 and not manifest['complete'] and receipt['status']=='failed'
    checks.append({'case':'deadline-partial','returncode':p.returncode,'status':receipt['status'],'represented_pages':len(manifest['pages']),'page_count':manifest['page_count'],'error':receipt['error'],'wall_seconds':receipt['wall_seconds']})
    dest=ROOT/'bundles/guide317-native-v2';before=sha256(dest/'manifest.json')
    p=subprocess.run([str(PYTHON),str(ROOT/'parser_worker.py'),'--input',str(SRC),'--output',str(dest)],env=env,capture_output=True,text=True,timeout=30)
    assert p.returncode!=0 and before==sha256(dest/'manifest.json')
    checks.append({'case':'immutable-existing-output','returncode':p.returncode,'manifest_unchanged':True})
    doc=json.loads((dest/'manifest.json').read_text())
    import pymupdf as fitz
    source_doc=fitz.open(SRC)
    native97=source_doc[96].get_text('dict',sort=True)['blocks']
    raw97=json.loads((dest/'raw/p0097-native.json').read_text())['blocks']
    manifest97=doc['pages'][96]['blocks']
    assert len(native97)==len(raw97)==len(manifest97)
    assert {b['id'] for b in manifest97}=={f'p97-b{i}' for i in range(len(native97))}
    by_id={b['id']:b for b in manifest97}
    anomalies=[]
    for i,b in enumerate(native97):
        original=list(b['bbox'])
        if original[0]>original[2] or original[1]>original[3]:
            block=by_id[f'p97-b{i}']
            assert raw97[i]['original_bbox_points']==original
            assert block['bbox']==[0,0,1,1] and block['quality']=='needs_review'
            assert block['assets'] and any('native_bbox_invalid' in s for s in block['issues'])
            anomalies.append({'native_index':i,'native_type':b['type'],'original_bbox_points':original,
                              'source_image_transform':list(b['transform']) if 'transform' in b else None,
                              'retained_block_id':block['id'],'normalized_review_fallback':block['bbox'],
                              'quality':block['quality'],'text_unchanged':block['text']==raw97[i]['content']})
    assert anomalies
    source_native_count=0;raw_native_count=0;blank_fallback_pages=[]
    import struct
    for number,source_page in enumerate(source_doc,1):
        source_blocks=source_page.get_text('dict',sort=True)['blocks']
        raw_blocks=json.loads((dest/f'raw/p{number:04}-native.json').read_text())['blocks']
        manifest_page=doc['pages'][number-1]
        assert len(source_blocks)==len(raw_blocks)
        source_native_count+=len(source_blocks);raw_native_count+=len(raw_blocks)
        assert {f'p{number}-b{i}' for i in range(len(source_blocks))}.issubset({b['id'] for b in manifest_page['blocks']})
        if not source_blocks:blank_fallback_pages.append(number)
        with (dest/manifest_page['image']).open('rb') as image:
            header=image.read(24)
        assert header[:8]==b'\x89PNG\r\n\x1a\n'
        assert struct.unpack('>II',header[16:24])==(manifest_page['width'],manifest_page['height'])
    source_doc.close()
    checks.append({'case':'all-original-native-blocks-and-raster-dimensions-retained','source_native_blocks':source_native_count,
                   'retained_raw_native_blocks':raw_native_count,'original_page_count':317,'all_native_ids_retained':True,
                   'raster_dimensions_match_png_headers':True,'blank_or_no-native-block_fallback_pages':blank_fallback_pages})
    checks.append({'case':'inverted-bbox-minimal-source-regression','original_pdf_page':97,
                   'source_native_blocks':len(native97),'retained_raw_blocks':len(raw97),'retained_manifest_blocks':len(manifest97),
                   'exact_native_id_set':True,'anomalies':anomalies,'precision_note':'conservative full-page review fallback, NOT recovered precise image geometry'})
    assert doc['pages'][268]['number']==269 and doc['pages'][-1]['number']==317
    checks.append({'case':'native-anomaly-and-late-locators','page97_anomaly_retained':True,'late_pages':[269,317]})
    dump(ROOT/'worker-acceptance.json',checks)
    print(json.dumps(checks,indent=2))


if __name__=='__main__':main()
