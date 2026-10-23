"""Assemble this lane's handoff from retained results; no new experiment."""
import collections, difflib, hashlib, json, xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'artifacts/stage14/native-text-recovery'
def read(name):return json.loads((OUT/name).read_text(encoding='utf-8'))
def save(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def xml_counts(name):
 root=ET.parse(OUT/name).getroot();cases=root.findall('.//testcase')
 return {'xml':name,'sha256':digest(OUT/name),'xml_testcases':len(cases),
         'failures':len(root.findall('.//failure')),'errors':len(root.findall('.//error')),
         'skips':len(root.findall('.//skipped'))}
def main():
 result=read('cpu-replay-result.json');summary=read('fresh-cpu-replay-bundle-summary.json');units=summary['units']
 native_nonempty=[u for u in units if u['text'].strip()]
 remaining=[u for u in units if u['quality']=='needs_review']
 fragments=[u for u in units if 'native-fragment'in u['id']]
 chars=[]
 for n in (1,2):
  native=read(f'after-native-bundle-dpi144/raw/p{n:04}-native.json')
  for block in native['blocks']:
   for span in block.get('source_text_spans',[]):
    for c in span['characters']:
     if '\uf000'<=c['text']<='\uf8ff':chars.append({'source_subset_page':n,'original_physical_page':125+n,
      'native_index':block['index'],'font':span['font'],'character':c['text'],'codepoint':f'U+{ord(c["text"]):04X}',
      'text_offset':c['text_offset'],'original_bbox_points':c['original_bbox_points'],'bbox':c['bbox']})
 save('remaining-unusable.json',{'PUA_glyph_count':len(chars),'PUA_glyphs':chars,'remaining_native_parent_blocks':remaining,
      'exact_readable_fragments':fragments,'source_position_counts':{k:v for k,v in summary.items()if k.endswith('source_characters')},
      'table_graph_relationships_verified':False,'semantic_accuracy_approved':False})
 runtime=['tools/document_stage12/parser_worker.py','tools/document_stage12/parser_helpers.py','tools/material_stage13/ocr_verification.py']
 changed={};diff=[]
 for name in runtime:
  old=OUT/'before-code'/Path(name).name;new=ROOT/name
  changed[name]={'before_sha256':digest(old),'after_sha256':digest(new),'bytes':new.stat().st_size}
  diff.extend(difflib.unified_diff(old.read_text(encoding='utf-8').splitlines(True),new.read_text(encoding='utf-8').splitlines(True),
                                 fromfile='before/'+name,tofile='after/'+name))
 (OUT/'code-changes.diff').write_text(''.join(diff),encoding='utf-8')
 helper_files=sorted((ROOT/'tools/material_stage14/native_text_recovery').glob('*.py'))
 save('modified-file-hashes.json',{'runtime_files':changed,'new_lane_files':{p.relative_to(ROOT).as_posix():digest(p)for p in helper_files}})
 tests={
  'before_root_cause_regression':dict(xml_counts('before-regression.xml'),tool_exit_code=1,pytest_reported='1 failed'),
  'final_parser_regression':dict(xml_counts('final-parser-regression-r2.xml'),tool_exit_code=0,pytest_reported='77 passed; 15 subtests passed; no failures/skips'),
  'windows_literal_regression':dict(xml_counts('windows-literal-regression.xml'),tool_exit_code=0,pytest_reported='14 passed; 4 subtests passed; 8 Linux-worker tests deselected here and included in final WSL suite'),
  'initial_collection_error':dict(xml_counts('final-parser-regression.xml'),tool_exit_code=2,
    cause='test_parser_limits.py is a command-line script, not a pytest module; retained failure then executed its real CLI'),
  'parser_limits_cli':{'evidence':'parser-limits-cli/result.json','sha256':digest(OUT/'parser-limits-cli/result.json'),
     'tool_exit_code':0,'cases':read('parser-limits-cli/result.json')['cases']}}
 masks=read('cpu-region-worker-result.json')
 report={'status':'completed_minimal_local_cpu_fix_not_deployed','parser_version':'1.2.2',
  'scope':'Only three authorized runtime files plus this new tools/artifacts lane; no server/GPU/site changes',
  'root_causes':[
   {'status':'located_and_fixed','finding':'Any page-level PUA/replacement glyph warning was applied to every native text block: nine Wingdings glyphs in five parents produced mapping warnings on all 81 native blocks.'},
   {'status':'located_and_fixed','finding':'Native text was compared with an incomplete set of CPU detector lines inside its block. Missing headings/body lines became false whole-block disagreement. Complete one-to-one source/CPU spatial lines are now required for actionable disagreement.'},
   {'status':'located_and_fixed','finding':'Native comparisons inherited unrelated VLM finish metadata and had no distinct verified-native literal marker. Native now uses exact PDF text plus actual independent CPU OCR, never fabricated generation finish.'},
   {'status':'true_corruption_still_withheld','finding':'src20 page2 G1 Type0 Identity-H font has no ToUnicode; visible glyphs extract as controls/punctuation/digits. Ten affected original native blocks remain needs_review, including short blocks missed by the old density heuristic.'}],
  'real_source_identity':result['source_hashes_after'],'all_sources_unchanged':result['source_hashes_before']==result['source_hashes_after'],
  'retained_gpu_before':result['retained_gpu_bundle'],
  'cpu_replay':{'source_original_native_blocks':summary['original_native_text_blocks'],
   'nonempty_original_parents':sum(u['text'].strip()!=''and 'native-fragment'not in u['id']for u in units),
   'output_native_blocks_including_whitespace':summary['output_native_text_blocks'],
   'nonempty_output_native_units':len(native_nonempty),
   'nonempty_literal_states':dict(collections.Counter(u['literal_state']for u in native_nonempty)),
   'restored_nonempty_original_parents':sum(u['text'].strip()!=''and 'native-fragment'not in u['id']and u['quality']=='extracted'for u in units),
   'exact_source_fragments':len(fragments),'PUA_glyphs':len(chars),'remaining_native_parent_blocks':len(remaining),
   'original_native_text_and_boxes_unchanged':True,'original_subset_retained_fresh_raster_pixels_equal':True,
   'unique_source_character_counts':{k:v for k,v in summary.items()if k.endswith('source_characters')},
   'fresh_and_retained_CPU_replay_status_counts_equal':result['fresh_cpu_replay']==result['retained_cpu_replay'],
   'strict_bundle_validators':'native before/after, src20 before/after, both CPU replay bundles, actual Linux region-worker replay: parser validator and unchanged application strict validator passed',
   'raw_scans':['fresh-cpu-p126.json','fresh-cpu-p127.json'],'literal_only':True},
  'actual_region_worker_cpu_readback':{k:v for k,v in masks.items()if k!='validation'},
  'tests':tests,'counts_are_overlapping_not_summed':True,'modified_runtime_files':changed,
  'remaining_limits':[
   'Nine original PUA characters were not guessed, translated or normalized. Five mixed parents remain needs_review; eleven exact good-font fragments are separately retained, without inferred arrow relationships.',
   'Three other parents (p2-b14, p2-b18, p2-b39) retain strict punctuation disagreement between native and high-confidence CPU. Both literal forms remain; no automatic correction.',
   'The 45 ordinary nonempty native units are not independent-OCR verified; missing/low-confidence OCR does not prove a damaged font or successful two-engine verification.',
   'Table cell structure, split labels and arrow relations are unverified. No entire-document semantic complete/approved claim.',
   'The real src20 mapping corruption remains unresolved. This localization fix detects/isolates it but does not reconstruct its letters.',
   'No new installed UID999/GPU/end-to-end/deployment acceptance occurred. Parent must independently integrate if later authorized.'],
  'encountered_issues':[
   'First WSL pytest FD capture over Windows scratch failed truncate(); sys capture solved it without changing product behavior.',
   'Initial replay used worker default120dpi but retained r6 raster was144dpi; exact-pixel assertion correctly failed. Those bundles remain. New dpi144 bundles passed actual pixel equality; no resize or relaxed comparison.',
   'Initial pytest collection included the CLI-only parser-limits script; collection failure XML remains. Its actual CLI subsequently passed, with oversized inputs returning expected nonzero failures.',
   'WSL runtime lacks RapidOCR; native preparation did not claim verification. Actual fresh OCR executed locally in Windows with three CPUExecutionProvider sessions. Linux region replay reuses those exact real pixel-bound scans and a rejecting model sentinel, not generated OCR data.'],
  'semantic_accuracy_approved':False,'deployment_performed':False,'GPU_calls':0,'new_VLM_calls':0,
  'ownership_returned':['parser_worker.py','parser_helpers.py','ocr_verification.py','tools/material_stage14/native_text_recovery/','artifacts/stage14/native-text-recovery/']}
 save('verification-summary.json',report)
 print(json.dumps({'runtime_hashes':changed,'cpu_counts':report['cpu_replay'],'test_results':{k:v.get('pytest_reported',v.get('tool_exit_code'))for k,v in tests.items()}},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
