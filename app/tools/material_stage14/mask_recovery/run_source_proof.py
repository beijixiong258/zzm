"""Real-source CPU proof: original objects, isolated rendering and worker lane.

Worker OCR/HTTP clients are rejecting in-process test doubles. No OCR text is
fabricated and no model endpoint is contacted. Pixel proof uses real MuPDF.
"""
import argparse, ast, contextlib, hashlib, importlib.util, io, json, os, sys, types
from pathlib import Path
from unittest.mock import patch
import pymupdf as fitz
from PIL import Image, ImageChops

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'tools/document_stage12')]
from parser_helpers import composite_embedded,sha256,validate_bundle
SRC03='c9406dc6f68ddbefeb9e8680691e09557baf62b428e43f6bd40c5c06da8430c1'
SRC01='c3fd10771feefa9b014b2ace902e8b8807d12b094bd5fff4781e3e58b1c1e993'
BASELINE='4f34bb016681043966e2655a9003b84872058ebefe56b8d1499f70cc96a1d841'
BASELINE_FUNCTION='''def composite_embedded(image_bytes,mask_bytes=None):
    """Use the original PDF soft mask; RGB conversion must not erase strokes."""
    import io
    from PIL import Image,ImageChops
    with Image.open(io.BytesIO(image_bytes))as embedded:
        if embedded.width*embedded.height>16_000_000:raise ValueError('Embedded raster exceeds16million source pixels')
        rgba=embedded.convert('RGBA')
        if mask_bytes:
            with Image.open(io.BytesIO(mask_bytes))as mask:
                if mask.size!=rgba.size:raise ValueError('Embedded image mask dimensions disagree')
                rgba.putalpha(ImageChops.multiply(rgba.getchannel('A'),mask.convert('L')))
        result=Image.new('RGB',rgba.size,'white');result.paste(rgba,mask=rgba.getchannel('A'))
        return result


'''
def h(data):return hashlib.sha256(data).hexdigest()
def png(image):
    data=io.BytesIO();image.save(data,format='PNG');return data.getvalue()
def dump(path,data):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def baseline(out):
    current=(ROOT/'tools/document_stage12/parser_helpers.py').read_bytes()
    restored=current[:current.index(b'def composite_embedded(')]+BASELINE_FUNCTION.encode()+current[current.index(b'def text_of('):]
    assert h(restored)==BASELINE,(h(restored),'baseline bytes not exact')
    path=out/'baseline-parser_helpers.py';path.write_bytes(restored)
    spec=importlib.util.spec_from_file_location('mask_original_helper',path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod

def worker_probe(source,out,expected):
    import parser_worker
    model_calls=[];counter={'calls':0,'events':[]}
    class NoOCR:
        info={'available':False,'test_double':True,'reason':'CPU OCR excluded from pixel-only acceptance'}
        def __init__(self,*args):pass
        def scan(self,image):return {'status':'unavailable','lines':[],'reason':self.info['reason']}
    class NoModel:
        prompts={'[default]':'Text Recognition:'}
        def __init__(self,**kwargs):pass
        def content_extract(self,*args,**kwargs):
            model_calls.append('forbidden');raise AssertionError('transparent isolated input must not request a model')
        async def aclose(self):pass
    utils=types.ModuleType('mineru_vl_utils');utils.MinerUClient=NoModel
    client=types.ModuleType('mineru_vl_utils.vlm_client');client.SamplingParams=lambda **kw:kw
    bundle=out/'worker-bundle';models=out/'empty-fixture-model-directory';models.mkdir()
    with patch.dict(sys.modules,{'mineru_vl_utils':utils,'mineru_vl_utils.vlm_client':client}),patch.object(parser_worker,'CPUVerifier',NoOCR),patch.object(parser_worker,'observe_vlm_http',return_value=(counter,lambda:None)),contextlib.redirect_stdout((out/'worker-console.jsonl').open('w',encoding='utf-8')):
        rc=parser_worker.main(['--input',str(source),'--output',str(bundle),'--engine','region-text','--vision-pages','126,127',
            '--models',str(models),'--vlm-url','http://127.0.0.1:18894','--deadline-seconds','900'])
    receipt=json.loads((bundle/'receipt.json').read_text());assert rc==0,(rc,receipt)
    manifest=json.loads((bundle/'manifest.json').read_text());assert manifest['parser']['version']=='1.2.1';assert len(manifest['pages'])==220
    assert not model_calls and counter['calls']==0;assert not receipt['targeted_recovery_calls']
    checks=[]
    for row in expected:
        number=row['page'];parent=row['parent_id'];page=manifest['pages'][number-1]
        native=next(b for b in page['blocks'] if b['id']==parent)
        raw_files=list((bundle/'raw').glob(f'p{number:04}-region*.json'))
        candidates=[(p,json.loads(p.read_text()))for p in raw_files]
        raw_path,raw=next((p,r)for p,r in candidates if r.get('source_compositing',{}).get('parent_id')==parent)
        comp=raw['source_compositing'];assert comp['decode_status']=='complete' and comp['output_size']==[287,112]
        assert comp['source_bbox_points']==row['bbox_points'] and raw['source_transform_points']==row['transform']
        assert comp['source_image_sha256']==row['original_image_sha256'] and comp['source_mask_sha256']==row['original_mask_sha256']
        assert sha256(bundle/raw['source_image_asset'])==row['original_image_sha256']
        assert sha256(bundle/raw['source_mask_asset'])==row['original_mask_sha256']
        assert raw['uniform_decorative'] and raw['raw_text']=='' and not raw['generation']['events']
        assert not comp['includes_page_overlays'] and 'original_mask_resolution' in raw['input_kind']
        assert 'image_ocr_not_needed_uniform' in native['issues'] and 'image_ocr_attempted' not in native['issues']
        children=[b for b in page['blocks']if b['parent_id']==parent];assert len(children)==1 and children[0]['text']=='' and children[0]['quality']=='needs_review'
        checks.append({'parent_id':parent,'raw_ref':raw_path.relative_to(bundle).as_posix(),'child_id':children[0]['id'],
            'source_compositing':comp,'input_kind':raw['input_kind'],'uniform_decorative':raw['uniform_decorative'],'raw_text':raw['raw_text'],'model_calls':0})
    assert len(checks)==15 and not manifest['coverage']['semantic_accuracy_approved']
    from backend.aicademiya.document_bundle import validate_bundle as app_validate
    app_validation=app_validate(bundle,SRC03,220)
    return {'returncode':rc,'pages':len(manifest['pages']),'actual_worker_version':manifest['parser']['version'],
        'validation':validate_bundle(bundle,manifest),'application_validation':{'passed':True,'source_sha256':app_validation['source_sha256'],'pages':len(app_validation['pages'])},'fixture_boundary':'Real 220-page parser/render execution; rejecting in-process OCR/model clients, no network or recognition proof',
        'model_calls':0,'targeted_recovery_calls':0,'occurrences':checks,'receipt':receipt}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--src03',type=Path,required=True);ap.add_argument('--src01',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True);ap.add_argument('--worker',action='store_true');a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    before={str(a.src03):sha256(a.src03),str(a.src01):sha256(a.src01)};assert before[str(a.src03)]==SRC03 and before[str(a.src01)]==SRC01
    old=baseline(a.out);rows=[];failed_baseline=0
    assets=a.out/'assets';assets.mkdir(exist_ok=True)
    with fitz.open(a.src03)as doc,fitz.open(stream=a.src03.read_bytes(),filetype='pdf')as isolated:
        for number in (126,127):
            page=doc[number-1];images=page.get_images(full=True);assert len(images)==1
            xref,maskxref,*_=images[0];name=images[0][7]
            assert doc.xref_get_key(maskxref,'Matte')[0]=='null'
            for i,b in enumerate(page.get_text('dict',sort=True)['blocks']):
                if b['type']!=1:continue
                parent=f'p{number}-b{i}';info={};got=composite_embedded(b['image'],b['mask'],pdf_softmask=True,evidence=info)
                try:old.composite_embedded(b['image'],b['mask'])
                except ValueError as error:
                    assert str(error)=='Embedded image mask dimensions disagree';failed_baseline+=1
                else:raise AssertionError('baseline unexpectedly succeeded')
                assert got.size==(287,112) and got.getextrema()==((255,255),)*3 and info['mask_extrema']==[0,0]
                image=Image.open(io.BytesIO(b['image']));mask=Image.open(io.BytesIO(b['mask']));assert image.size==(2,2) and mask.size==(287,112)
                assert image.getextrema()==((0,0),)*3 and mask.getextrema()==(0,0)
                rect=fitz.Rect(b['bbox']);matrix=fitz.Matrix(8,8)
                original_pix=page.get_pixmap(matrix=matrix,clip=rect,alpha=False)
                original=Image.frombytes('RGB',(original_pix.width,original_pix.height),original_pix.samples)
                ip=isolated[number-1];content=ip.get_contents()[0];width,height=b['transform'][:1]+b['transform'][3:4]
                stream=f'q {width} 0 0 {height} {rect.x0} {page.rect.height-rect.y1} cm /{name} Do Q\n'.encode('ascii')
                isolated.update_stream(content,stream)
                pix=ip.get_pixmap(matrix=matrix,clip=rect,alpha=False);rendered=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
                assert rendered.getextrema()==((255,255),)*3 and original.getextrema()!=rendered.getextrema()
                expected=got.resize(rendered.size,Image.Resampling.NEAREST);assert ImageChops.difference(expected,rendered).getbbox() is None
                # Original page/XObject dictionary copied in memory only. Remove
                # all content except this exact image operator; never write source.
                native_trace=[{'bbox':list(t['bbox']),'render_mode':t['type'],'text':''.join(chr(c[0])for c in t['chars'])}
                    for t in page.get_texttrace() if fitz.Rect(t['bbox']).intersects(rect)]
                assert native_trace
                original_bytes=png(original);isolated_bytes=png(rendered);composite_bytes=png(got)
                for suffix,data in [('page-clip',original_bytes),('image-only-render',isolated_bytes),('composite',composite_bytes)]:
                    (assets/f'{parent}-{suffix}.png').write_bytes(data)
                (assets/'original-image.png').write_bytes(b['image']);(assets/'original-mask.png').write_bytes(b['mask'])
                rows.append({'occurrence_id':'src03/'+parent,'page':number,'parent_id':parent,'native_number':b['number'],
                    'bbox_points':list(b['bbox']),'transform':list(b['transform']),'source_page_xref':page.xref,'image_xref':xref,'mask_xref':maskxref,
                    'original_image_sha256':h(b['image']),'original_mask_sha256':h(b['mask']),
                    'original_image_bytes':len(b['image']),'original_mask_bytes':len(b['mask']),
                    'image_dictionary':doc.xref_object(xref),'mask_dictionary':doc.xref_object(maskxref),'compositing':info,
                    'baseline_error':'Embedded image mask dimensions disagree','image_only_render_matches_composite':True,
                    'original_clip_includes_other_page_content':True,'original_clip_sha256':h(original_bytes),
                    'isolated_render_sha256':h(isolated_bytes),'composite_sha256':h(composite_bytes),'native_text_trace_overlapping':native_trace,
                    'semantic_approved':False})
    assert len(rows)==15 and failed_baseline==15
    with fitz.open(a.src01)as doc:
        items=[(i,b)for i,b in enumerate(doc[48].get_text('dict',sort=True)['blocks']) if b['type']==1]
        i,b=next((i,b)for i,b in items if h(b['image'])=='f8e190e6319f15939caec05366f023b9a5f2c5870af2683a4dae2547a8d9640e')
        info={};got=composite_embedded(b['image'],b['mask'],pdf_softmask=True,evidence=info);expected=old.composite_embedded(b['image'],b['mask'])
        assert got.size==Image.open(io.BytesIO(b['mask'])).size and ImageChops.difference(got,expected).getbbox() is None
        assert got.getextrema()==((0,255),)*3
        (assets/'src01-p49-composite.png').write_bytes(png(got))
        p49={'source_sha256':SRC01,'page':49,'parent_id':f'p49-b{i}','image_sha256':h(b['image']),'mask_sha256':h(b['mask']),
            'compositing':info,'pixel_identical_to_sha_verified_baseline':True,'pixel_sha256':h(got.tobytes()),'semantic_approved':False}
    worker=worker_probe(a.src03,a.out,rows) if a.worker else {'not_run':'Windows helper/pixel run only; formal worker is Linux-only'}
    after={str(a.src03):sha256(a.src03),str(a.src01):sha256(a.src01)};assert after==before
    summary={'status':'passed','pymupdf':fitz.__doc__,'source_before':before,'source_after':after,'source_unchanged':True,
        'baseline_helpers_sha256':BASELINE,'baseline_failures_reproduced':failed_baseline,'real_instances_checked':len(rows),
        'occurrences':rows,'same_grid_p49_regression':p49,'worker':worker,'gpu_calls':0,'model_service_calls':0,'semantic_approved':False}
    dump(a.out/'source-proof.json',summary)
    print(json.dumps({'status':'passed','instances':len(rows),'baseline_failures':failed_baseline,'source_unchanged':after==before,'p49_identical':True,'worker':worker.get('returncode'),'gpu_calls':0},ensure_ascii=False))
if __name__=='__main__':main()
