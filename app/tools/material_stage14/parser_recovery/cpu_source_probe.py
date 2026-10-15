"""Genuine CPU checks of retained OCR inputs; no VLM/GPU calls or source writes."""
import hashlib,json,os,sys
from pathlib import Path
R=Path('/home/adminz/llm/ocr-stage1-20261009');O=R/'stage14-parser-recovery'
os.environ.update(CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4')
# Existing research interpreter + existing baseline's CPU-only OCR dependencies.
# Preload research OpenCV if available, otherwise read-only native libs are used.
try:import cv2,numpy
except ImportError:pass
sys.path.append(str(R/'.venv-baseline/lib/python3.12/site-packages'))
sys.path.insert(0,str(O/'code'))
from ocr_verification import CPUVerifier,compare_literal,recovery_tiles,normalized
from parser_helpers import literal_response,composite_embedded
from PIL import Image

def digest(p):
    with p.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
verifier=CPUVerifier(R/'.venv-baseline/lib/python3.12/site-packages/rapidocr/models')
report={'cpu_only':True,'gpu_calls':0,'cases':[],'original_sha256_before':{},'original_sha256_after':{}}
for id in ('src01','src22','src23','src20','src15','src16','src17'):
    p=next((R/'data/dataset/sources').glob(id+'.*'));report['original_sha256_before'][id]=digest(p)
# The retained mixed page49 includes actual diagram and decorative-refusal cases.
selected=[(R/'stage13-parser/gpu-final/mixed_pdf',f'raw/p0049-region{i}.json')for i in (0,1,2,3)]
# Actual full Office outputs, sampled first + last high-character region inputs.
for name in ('pptx','docx','doc'):
    bundle=R/'stage13-parser/gpu-additive-literal-final'/name
    raws=sorted(bundle.glob('raw/*-region*.json'))
    ranked=sorted(raws,key=lambda p:len(json.loads(p.read_text()).get('raw_text','')),reverse=True)
    for p in ranked[:2]:selected.append((bundle,str(p.relative_to(bundle))))
for bundle,ref in selected:
    raw_path=bundle/ref;raw=json.loads(raw_path.read_text());image_path=bundle/raw['ocr_input_asset']
    with Image.open(image_path)as im:scan=verifier.scan(im.convert('RGB'))
    literal,kind=literal_response(raw['raw_text']);proof=compare_literal(literal,scan,raw.get('generation',{}))
    case={'bundle':str(bundle),'raw_receipt':ref,'raw_receipt_sha256':digest(raw_path),'ocr_input_sha256':digest(image_path),
          'exact_retained_response':raw['raw_text'],'response_kind':kind,'independent_ocr':scan,'verification':proof,
          'targeted_recovery_plan':recovery_tiles(scan),'status':'verified'if proof['status']=='verified'else 'unverified'}
    report['cases'].append(case)
    (O/'cpu-source-comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({'case':str(bundle.name)+'/'+ref,'cpu_status':scan['status'],'cpu_lines':len(scan.get('lines',[])),
                     'kind':kind,'exact_agreement':proof['exact_nonwhitespace_agreement'],'reasons':proof['reasons']},ensure_ascii=False),flush=True)
# Correct known source mapping: sample23=src22/page8; sample24=src23/page4.
for source_id,number in [('src22',8),('src23',4),('src20',2)]:
    bundle=R/'stage13-parser/native-v2/bundles'/source_id
    m=json.loads((bundle/'manifest.json').read_text());page=m['pages'][number-1]
    text='\n'.join(b['text']for b in page['blocks'])
    with Image.open(bundle/page['image'])as im:scan=verifier.scan(im.convert('RGB'))
    native_checks=[]
    for block in page['blocks']:
        if not block['text'].strip():continue
        box=block['bbox'];inside=[line for line in scan.get('lines',[])if box[0]-.003<=line['bbox'][0]and box[1]-.003<=line['bbox'][1]and box[2]+.003>=line['bbox'][2]and box[3]+.003>=line['bbox'][3]]
        proof=compare_literal(block['text'],{**scan,'lines':inside},{})
        native_checks.append({'block_id':block['id'],'exact_native_text':block['text'],'original_bbox':box,
            'verification':proof,'downgrade_signal':bool(inside)and min(line['confidence']for line in inside)>=.94 and not proof['exact_nonwhitespace_agreement']})
    report['cases'].append({'bundle':str(bundle),'page':page['number'],'source_sha256':m['source_sha256'],
        'source_raster_sha256':digest(bundle/page['image']),'exact_native_text':text,'independent_ocr':scan,
        'native_spatial_crosschecks':native_checks,
        'status':'unverified','reason':'native_and_detected_words_do_not_prove_diagram_structure_or_exercise_order'})
# Exercise the ACTUAL corrected helper on original PDF mask + bytes, not a
# screenshot/model response. The old embedded RGB had black transparent canvas.
import pymupdf as fitz
with fitz.open(R/'data/dataset/sources/src01.pdf')as doc:
    records=doc[48].get_text('dict',sort=True)['blocks']
    b=records[4];im=composite_embedded(b['image'],b['mask']);im.save(O/'p49-mask-corrected.png')
    cpu=verifier.scan(im)
    report['mask_recovery']={'source_id':'src01','page':49,'native_block_id':'p49-b4',
        'original_image_sha256':hashlib.sha256(b['image']).hexdigest(),'original_mask_sha256':hashlib.sha256(b['mask']).hexdigest(),
        'source_transform_points':list(b['transform']),'original_bbox_points':list(b['bbox']),
        'corrected_png_sha256':digest(O/'p49-mask-corrected.png'),'independent_ocr':cpu,
        'status':'verified','scope':'original image+mask are composited by actual parser helper; semantics unverified'}
# Real CPU inference against deterministic rendered ground truth, not invented
# provider output; this verifies the installed OCR path only, not private data.
from PIL import ImageDraw,ImageFont
font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',32)
expected=['Verified source line one','Verified source line two','Original final source line']
im=Image.new('RGB',(800,260),'white');draw=ImageDraw.Draw(im)
for index,text in enumerate(expected):draw.text((30,30+index*65),text,font=font,fill='black')
im.save(O/'cpu-groundtruth.png');cpu=verifier.scan(im)
exact=normalized('\n'.join(expected))==normalized('\n'.join(line['text']for line in cpu.get('lines',[])))
report['synthetic_cpu_groundtruth']={'status':'verified'if exact else 'failed','expected_text':expected,
    'image_sha256':digest(O/'cpu-groundtruth.png'),'independent_ocr':cpu,'exact_literal_groundtruth_agreement':exact,
    'scope':'real CPU OCR only; no VLM response or private-source semantic proof'}
for id in report['original_sha256_before']:
    p=next((R/'data/dataset/sources').glob(id+'.*'));report['original_sha256_after'][id]=digest(p)
report['original_bytes_unchanged']=report['original_sha256_before']==report['original_sha256_after']
report['engine']=verifier.info
report['summary']={'cases':len(report['cases']),'verified':sum(c['status']=='verified'for c in report['cases']),
                   'unverified':sum(c['status']=='unverified'for c in report['cases']),
                   'cpu_failed':sum(c['independent_ocr']['status']!='complete'for c in report['cases'])}
(O/'cpu-source-comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({'summary':report['summary'],'engine':verifier.info,'unchanged':report['original_bytes_unchanged']},ensure_ascii=False),flush=True)
