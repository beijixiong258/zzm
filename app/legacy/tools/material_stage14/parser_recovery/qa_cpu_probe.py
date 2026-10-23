"""Actual CPU comparison of fresh installed QA outputs; zero model/GPU calls."""
import hashlib,json,os,sys
from pathlib import Path
R=Path('/home/adminz/llm/ocr-stage1-20261009');O=R/'stage14-parser-recovery';Q=O/'qa-fresh-scan'
os.environ.update(CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4')
try:import cv2,numpy
except ImportError:pass
sys.path.append(str(R/'.venv-baseline/lib/python3.12/site-packages'));sys.path.insert(0,str(O/'code'))
from ocr_verification import CPUVerifier,compare_literal,recovery_tiles,normalized
from PIL import Image
verifier=CPUVerifier(R/'.venv-baseline/lib/python3.12/site-packages/rapidocr/models')
m=json.loads((Q/'manifest.json').read_text());report={'scope':'read-only postcheck of parent installed R3 QA; not runtime GPU acceptance',
    'source_sha256':m['source_sha256'],'cases':[],'gpu_calls':0,'qa_modified':False}
def digest(p):
    with p.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
for page in (3,8,9):
    p=m['pages'][page-1]
    with Image.open(Q/p['image'])as im:scan=verifier.scan(im.convert('RGB'))
    checks=[]
    for block in p['blocks']:
        if not any('fullpage_model_candidate'in issue for issue in block['issues']):continue
        box=block['bbox'];inside=[line for line in scan.get('lines',[])if box[0]-.003<=line['bbox'][0]and box[1]-.003<=line['bbox'][1]and box[2]+.003>=line['bbox'][2]and box[3]+.003>=line['bbox'][3]]
        proof=compare_literal(block['text'],{**scan,'lines':inside},{})
        checks.append({'block_id':block['id'],'old_quality':block['quality'],'verification':proof})
    region=json.loads((Q/f'raw/p{page:04}-region0.json').read_text())
    text=normalized(region['raw_text'])
    covered=[block['id']for block in p['blocks']if any('fullpage_model_candidate'in issue for issue in block['issues'])and len(normalized(block['text']))>30 and normalized(block['text'])in text]
    case={'page':page,'page_raster_sha256':digest(Q/p['image']),'independent_ocr':scan,'fullpage_spatial_checks':checks,
          'fullpage_region_exact_contained_block_ids':covered,'status':'unverified','scope':'literal source postcheck; old finish metadata absent'}
    if page in (8,9):
        with Image.open(Q/region['ocr_input_asset'])as im:region_scan=verifier.scan(im.convert('RGB'))
        tiles=recovery_tiles(region_scan,candidate_text=region['raw_text'])
        planned={i for tile in tiles for i in tile['cpu_line_indices']}
        case['whole_region']={'exact_retained_text':region['raw_text'],'independent_ocr':region_scan,
            'verification':compare_literal(region['raw_text'],region_scan,region.get('generation',{})),
            'targeted_plan':tiles,'detected_lines':len(region_scan.get('lines',[])),
            'planned_lines':len(planned),'unattempted_lines':sorted(set(range(len(region_scan.get('lines',[]))))-planned)}
    report['cases'].append(case)
    (O/'qa-cpu-comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({'page':page,'cpu_lines':len(scan.get('lines',[])),'checked_blocks':len(checks),
        'literal_exact_agreement_blocks':sum(c['verification']['exact_nonwhitespace_agreement']for c in checks),
        'unverified_blocks':sum(c['verification']['status']!='verified'for c in checks),'duplicated_text_blocks':len(covered),
        'region_detected_lines':case.get('whole_region',{}).get('detected_lines'),
        'region_planned_lines':case.get('whole_region',{}).get('planned_lines')},ensure_ascii=False),flush=True)
report['engine']=verifier.info
report['summary']={'pages_checked':len(report['cases']),'fullpage_blocks_checked':sum(len(c['fullpage_spatial_checks'])for c in report['cases']),
    'machine_verified_blocks':sum(ch['verification']['status']=='verified'for c in report['cases']for ch in c['fullpage_spatial_checks']),
    'raw_duplicate_text_blocks':sum(len(c['fullpage_region_exact_contained_block_ids'])for c in report['cases']),
    'cpu_failed_pages':sum(c['independent_ocr']['status']!='complete'for c in report['cases'])}
(O/'qa-cpu-comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report['summary']),flush=True)
