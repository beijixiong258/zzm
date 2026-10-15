"""Aggregate real receipts, close all 15 audit locators, and hash handoff files."""
import ast,difflib,hashlib,json,re
from pathlib import Path
from xml.etree import ElementTree as ET
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'artifacts/stage14/mask-recovery'
def sha(path):
    with path.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def main():
    proof=json.loads((OUT/'linux-source/source-proof.json').read_text());windows=json.loads((OUT/'windows-source/source-proof.json').read_text())
    audit=[json.loads(line)for line in (ROOT/'artifacts/stage14/corpus-audit/unresolved-mask-units.jsonl').read_text(encoding='utf-8').splitlines() if line]
    expected={r['occurrence_id']:r for r in audit};actual={r['occurrence_id']:r for r in proof['occurrences']}
    assert len(expected)==len(actual)==15 and set(expected)==set(actual)
    for key,a in expected.items():
        b=actual[key]
        assert a['bbox_points']==b['bbox_points'] and a['transform']==b['transform']
        assert a['original_image_sha256']==b['original_image_sha256'] and a['original_softmask_sha256']==b['original_mask_sha256']
        assert a['original_image_bytes']==b['original_image_bytes'] and a['original_softmask_bytes']==b['original_mask_bytes']
        assert b['image_only_render_matches_composite'] and b['compositing']['mask_extrema']==[0,0] and not b['compositing']['includes_page_overlays']
    assert windows['source_unchanged'] and proof['source_unchanged'] and proof['worker']['returncode']==0
    assert proof['worker']['pages']==220 and proof['worker']['application_validation']['passed']
    assert proof['same_grid_p49_regression']['pixel_identical_to_sha_verified_baseline'] and windows['same_grid_p49_regression']['pixel_identical_to_sha_verified_baseline']
    assert len(proof['worker']['occurrences'])==15
    negative=json.loads((OUT/'linux-negative-worker-receipts.json').read_text());assert negative['tests']==4 and negative['failures']==negative['errors']==0
    suites=ET.parse(OUT/'windows-tests.xml').getroot().findall('testsuite');cases=[case for suite in suites for case in suite.findall('testcase')]
    assert len(cases)==12 and all(int(s.get('failures','0'))==int(s.get('errors','0'))==0 for s in suites)
    linux_counts={}
    for name,count in [('linux-unit.log',12),('linux-negative-worker.log',4),('linux-existing-regressions.log',22)]:
        log=(OUT/name).read_text(encoding='utf-8');match=re.search(r'Ran (\d+) tests? in',log)
        assert match and int(match[1])==count and re.search(r'\nOK\s*$',log)
        linux_counts[name]=int(match[1])
    protected=ROOT/'tools/material_stage13/ocr_verification.py';assert sha(protected)=='1649770889ca88e017fd426de8c96f97531d0d71e354489458cace1324066748'
    helpers=ROOT/'tools/document_stage12/parser_helpers.py';worker=ROOT/'tools/document_stage12/parser_worker.py'
    original_helper=OUT/'linux-source/baseline-parser_helpers.py';assert sha(original_helper)=='4f34bb016681043966e2655a9003b84872058ebefe56b8d1499f70cc96a1d841'
    def other_nodes(path):return [ast.dump(n,include_attributes=False)for n in ast.parse(path.read_text()).body if not isinstance(n,ast.FunctionDef) or n.name!='composite_embedded']
    assert other_nodes(helpers)==other_nodes(original_helper)
    text=worker.read_text(encoding='utf-8');candidate=text
    preflight='''                if embedded[1]:
                    # A small base may reference a much larger mask. Bound its
                    # PDF header before get_pixmap/get_text decode either one.
                    mask_header=[doc.xref_get_key(embedded[1],key) for key in ('Width','Height')]
                    if any(kind!='int' or int(value)<=0 for kind,value in mask_header):
                        raise ValueError('Embedded softmask has invalid source dimensions')
                    mask_size=tuple(int(value) for _,value in mask_header)
                    if mask_size[0]*mask_size[1]>16000000:
                        raise ValueError('Embedded softmask exceeds16million source pixels')
                    if mask_size!=(embedded[2],embedded[3]) and doc.xref_get_key(embedded[1],'Matte')[0]!='null':
                        raise ValueError('Embedded image mask dimensions disagree; unequal Matte softmask unsupported')
'''
    newcall='''                        compositing={'source_image_sha256':digest_image,
                            'source_mask_sha256':mask_digest if original_record['mask'] else None,
                            'source_image_bytes':len(original_image),
                            'source_mask_bytes':len(original_record['mask']) if original_record['mask'] is not None else None,
                            'source_bbox_points':original_record['bbox_points'],'parent_id':parent['id']}
                        region_image=composite_embedded(original_image,original_record['mask'],pdf_softmask=True,evidence=compositing)
'''
    changes=[(preflight,''),("'transform_points':list(b.get('transform',[])), 'bbox_points':list(b['bbox'])}","'transform_points':list(b.get('transform',[]))}"),
        ('                    compositing=None\n',''),(newcall,"                        region_image=composite_embedded(original_image,original_record['mask'])\n"),
        ("                        if compositing['source_image_size']!=compositing['output_size']:\n                            input_kind += '; opaque_constant_colour_expanded_to_original_mask_resolution; no_page_overlays'\n",''),
        ("'source_transform_points':source_transform,'source_compositing':compositing,'ocr_input_asset':ocr_ref,","'source_transform_points':source_transform,'ocr_input_asset':ocr_ref,")]
    for new,old in changes:
        assert text.count(new)==1,new;text=text.replace(new,old,1)
    data=text.encode('utf-8');assert hashlib.sha256(data).hexdigest()=='1eecb7e96454471f494c9686ddd6e49bf3d596a9adb53c2363ee9cc7167667de'
    (OUT/'baseline-parser_worker.py').write_bytes(data)
    (OUT/'owned-source-diff.patch').write_text(''.join(difflib.unified_diff(original_helper.read_text().splitlines(True),helpers.read_text().splitlines(True),fromfile='baseline/parser_helpers.py',tofile='candidate/parser_helpers.py'))+''.join(difflib.unified_diff(text.splitlines(True),candidate.splitlines(True),fromfile='baseline/parser_worker.py',tofile='candidate/parser_worker.py')),encoding='utf-8')
    version=next(ast.literal_eval(n.value)for n in ast.parse(candidate).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='VERSION'for t in n.targets));assert version=='1.2.1'
    paths=[helpers,worker,protected,*sorted((ROOT/'tools/material_stage14/mask_recovery').glob('*.py'))]
    hashes={p.relative_to(ROOT).as_posix():sha(p)for p in paths}
    transported=json.loads((OUT/'transport-readback.json').read_text())['source_files']
    assert all(transported.get(n)==v for n,v in hashes.items() if 'finalize_receipts.py' not in n)
    summary={'status':'passed','scope':'CPU source-fidelity recovery only, not OCR/semantic approval or deployed worker acceptance',
        'source_instances':len(actual),'audit_locator_set_closed':True,'same_image_and_mask_bytes_and_transforms_preserved':True,
        'baseline_failures_reproduced':proof['baseline_failures_reproduced'],'recovered_image_resolution':[287,112],
        'real_mask_extrema':[0,0],'effective_alpha_extrema':[0,0],'transparent_image_not_native_text':True,
        'windows_pytest_testcases':len(cases),'windows_pytest_declared_tests':sum(int(s.get('tests','0'))for s in suites),
        'windows_subtests':11,'linux_tests_by_log':linux_counts,'linux_tests_total':sum(linux_counts.values()),
        'real_source_worker':{'version':version,'pages':220,'returncode':0,'image_occurrences_checked':len(proof['worker']['occurrences']),
            'validation':proof['worker']['validation'],'application_validation':proof['worker']['application_validation'],'model_service_calls':0,'ocr_proof':False},
        'p49_pixels_unchanged':True,'sources_before_after':{'windows':{'before':windows['source_before'],'after':windows['source_after']},'linux':{'before':proof['source_before'],'after':proof['source_after']}},
        'protected_ocr_verification_unchanged':True,'geometry_budget_cli_model_logic_unchanged':True,
        'helpers_other_ast_nodes_unchanged':True,'restored_worker_baseline_sha256':hashlib.sha256(data).hexdigest(),
        'code_sha256':hashes,'gpu_calls':0,'model_service_calls':0,'deployment_operations':0,'service_operations':0,'semantic_approved':False,
        'preserved_initial_failure':'linux-existing-regressions-initial-unavailable.log: 7 import errors (QA snapshot lacked backend); supplied read-only document_bundle module in own QA snapshot, final 22 passed; no environment/package change',
        'unknown':['Nonuniform base with unequal mask grids remains unsupported and raises explicitly','Generic Matte/unblending, PDF blend modes and arbitrary renderer context are not newly supported','No GPU/OCR semantics/human approval/installed UID999/release promotion evidence from this lane']}
    write(OUT/'verification-summary.json',summary)
    source_assets={n:sha(OUT/n)for n in ['verification-summary.json','owned-source-diff.patch','windows-tests.xml','windows-source/source-proof.json','linux-source/source-proof.json','linux-source/worker-bundle/receipt.json','linux-source/worker-bundle/manifest.json','linux-negative-worker-receipts.json']}
    write(OUT/'handoff-hashes.json',{'source_files':hashes,'key_evidence_files':source_assets})
    print(json.dumps(summary,ensure_ascii=False,indent=2));print('handoff-hashes.json SHA256',sha(OUT/'handoff-hashes.json'))
if __name__=='__main__':main()
