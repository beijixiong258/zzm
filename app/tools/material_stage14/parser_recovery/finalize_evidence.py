"""Aggregate exact test/source/runtime evidence; no new verification/inference."""
import hashlib,json,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'artifacts/stage14/parser-recovery'
def digest(p):
    with p.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def tests(path):
    tree=ET.parse(path);cases=tree.findall('.//testcase')
    return {'records':len(cases),'failures':sum(c.find('failure')is not None for c in cases),
            'errors':sum(c.find('error')is not None for c in cases),'skipped':sum(c.find('skipped')is not None for c in cases),
            'sha256':digest(path)}
source=json.loads((OUT/'cpu-source-comparison.json').read_text(encoding='utf-8'))
qa=json.loads((OUT/'qa-cpu-comparison.json').read_text(encoding='utf-8'))
qa_identity=json.loads((OUT/'qa-fresh-scan/read-only-diagnosis.json').read_text(encoding='utf-8'))
runtime=json.loads((OUT/'runtime-vision-support.json').read_text(encoding='utf-8'))
metadata=json.loads((OUT/'source-diagnosis.json').read_text(encoding='utf-8'))
upstream=json.loads((OUT/'vision-upstream.json').read_text(encoding='utf-8'))
model=next(m for m in metadata['models']if m['metadata']['general.architecture']=='qwen35')
projector=next(m for m in metadata['models']if m['metadata']['general.architecture']=='clip')
files=['tools/document_stage12/parser_worker.py','tools/document_stage12/parser_helpers.py',
       'tools/material_stage13/ocr_verification.py','tools/material_stage13/simple_material.py',
       'tools/material_stage13/parse_material.py','tools/material_stage13/COVERAGE_KEYS.md',
       'tools/material_stage14/test_simple_material.py']
code={rel:{'sha256':digest(ROOT/rel),'bytes':(ROOT/rel).stat().st_size}for rel in files}
code['tools/material_stage13/source_text.py']={'sha256':digest(ROOT/'tools/material_stage13/source_text.py'),'modified_by_lane':False}
report={'scope':'implemented CPU verification/recovery + all-frame adapters; no deployment/GPU model execution',
    'semantic_quality_accepted':False,'gpu_calls_by_lane':0,'immutable_r2_snapshot_modified':False,
    'code':code,'tests':tests(OUT/'final-all-tests.xml'),
    'verified':[
        {'check':'final WSL runtime/worker/schema/adapter regression','evidence':'final-all-tests.xml','tests_passed':102,'subtests_passed':8},
        {'check':'real independent CPU inference','evidence':'cpu-source-comparison.json','result':source['summary'],'providers':source['engine']['actual_providers']},
        {'check':'real deterministic CPU rendered-text ground truth','evidence':'cpu-source-comparison.json#synthetic_cpu_groundtruth','status':source['synthetic_cpu_groundtruth']['status']},
        {'check':'actual source PDF softmask restoration','evidence':'cpu-source-comparison.json#mask_recovery','original_image_sha256':source['mask_recovery']['original_image_sha256'],'original_mask_sha256':source['mask_recovery']['original_mask_sha256']},
        {'check':'selected originals unchanged','source_ids':list(source['original_sha256_before']),'unchanged':source['original_bytes_unchanged'],'evidence':'cpu-source-comparison.json'},
        {'check':'parent fresh installed QA exact source identity read-only','source_sha256':qa_identity['source']['source_sha256'],'pages':qa_identity['page_count'],'blocks':qa_identity['blocks'],'evidence':'qa-fresh-scan/read-only-diagnosis.json'},
        {'check':'fresh QA real CPU/source postcheck','result':qa['summary'],'evidence':'qa-cpu-comparison.json'},
        {'check':'existing vision projector metadata/static runtime support','model_architecture':model['metadata']['general.architecture'],
         'text_embedding':model['metadata']['qwen35.embedding_length'],'vision_projection':projector['metadata']['clip.vision.projection_dim'],
         'projector_bytes':projector['bytes'],'projector_sha256':projector['sha256'],'publisher_revision':upstream['revision'],
         'built_projector_types':runtime['built_mtmd_projector_strings'],'evidence':['source-diagnosis.json','runtime-vision-support.json','vision-upstream.json']}],
    'unverified':[
        {'check':'new verifier/targeted recovery actual GPU execution','owner':'parent','reason':'lane has no GPU/model permission; protocol fixtures are not recognition accuracy evidence'},
        {'check':'all retained source OCR accepted','result':source['summary'],'reason':'disagreement/low confidence/nonlinear geometry/old unknown finish stay unverified'},
        {'check':'fresh QA semantic acceptance','result':qa['summary'],'reason':'old finish unavailable; prose omission/table hierarchy unresolved; no QA writes'},
        {'check':'strong27B actual image load/generation/VRAM','owner':'parent','reason':'projector/model metadata match and installed mtmd support are static proof only'},
        {'check':'installed-user independent RapidOCR/package/permissions','owner':'parent','reason':'research CPU used existing baseline package/models read-only; no installed dependency mutation'},
        {'check':'application all-frame admission','owner':'parent','reason':'source_identity must validate all frames and return full n_frames; worker-only frame tests bypass old admission explicitly'},
        {'check':'all5232 original image occurrences semantically recognized','reason':'not executed; inventory is not accuracy'}],
    'failed_observed':[
        {'check':'retained Stage13 PPTX page10 primary OCR','reason':'8654 characters repetitive Prosservs/EVIDENCE vs actual source labels; exact raw evidence retained','evidence':'cpu-source-comparison.json'},
        {'check':'retained Stage13 PPTX page1 primary OCR','reason':'4096 characters repetitive 1. on blurry answer-sheet photograph; independent CPU detects no text','evidence':'cpu-source-comparison.json'},
        {'check':'old page49 embedded RGB input','reason':'discarded original soft mask rendered black strokes/headings invisible; corrected helper restores original source image+mask','evidence':'p49-source-ocr.png vs p49-mask-corrected.png'},
        {'check':'fresh QA page9 whole-region source completeness','reason':'1736 normalized primary chars vs4664 detected CPU chars; substantial source prose omitted','evidence':'qa-cpu-comparison.json'},
        {'check':'initial CPU dependency/preflight probe','reason':'baseline libGL needs existing native library path; incorrect classifier filename and Enum config fixed; initial unavailable result retained','evidence':'cpu-source-comparison-initial-unavailable.json'},
        {'check':'initial focused test harness','result':tests(OUT/'focused-first.xml'),'reason':'fixture lacked NumPy; isolated mock corrected without changing parent venv'},
        {'check':'QA column test harness initial ordering assumption','result':tests(OUT/'final-qa-regression.xml'),'reason':'source-order selected crops interleave columns; replaced false sequential-y assumption with actual pairwise spatial non-overlap check'}],
    'integration':'tools/material_stage14/parser_recovery/INTEGRATION.md',
    'vision_recipe':'tools/material_stage14/parser_recovery/VISION_PATH.md'}
assert report['tests']['failures']==report['tests']['errors']==report['tests']['skipped']==0
assert source['original_bytes_unchanged'] and source['summary']['cpu_failed']==0 and qa['summary']['cpu_failed_pages']==0
(OUT/'verification-summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'tests':report['tests'],'source_cpu':source['summary'],'qa_cpu':qa['summary'],'source_originals_unchanged':source['original_bytes_unchanged'],
    'projector':{'bytes':projector['bytes'],'sha256':projector['sha256']},'summary':str(OUT/'verification-summary.json')},ensure_ascii=False,indent=2))
