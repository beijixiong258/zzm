"""CPU-only real-source replay and source-position union accounting.

Windows orchestrates already installed WSL native CLI and local RapidOCR CPU.
No GPU, VLM client, service control, publication, or imported model output.
"""
import collections, copy, hashlib, json, os, shutil, subprocess, sys, unicodedata
from pathlib import Path
import pymupdf as fitz
from PIL import Image
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'artifacts/stage14/native-text-recovery'
sys.path[:0]=[str(ROOT),str(ROOT/'tools/document_stage12'),str(ROOT/'tools/material_stage13')]
from parser_helpers import dump,sha256,coverage_of,validate_bundle,rotate_bbox
from ocr_verification import CPUVerifier,apply_native_verification
from backend.aicademiya.document_bundle import validate_bundle as app_validate
SUBSET=ROOT/'artifacts/stage14/r6-final-inputs/src03-pages126-127.pdf'
RETAINED=ROOT/'artifacts/stage14/r6-final-inputs/readback/mask-bundle'
PY='/mnt/d/HermesProjects/EDUC7703/app/.venv-stage14-linux/bin/python'
def wsl_path(path):
 p=Path(path).resolve().as_posix();return '/mnt/'+p[0].lower()+p[2:]
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def execute(label,args,timeout=180):
 result=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',timeout=timeout)
 (OUT/(label+'.log')).write_text(result.stdout,encoding='utf-8')
 record={'label':label,'command':args,'exit_code':result.returncode,'log':label+'.log'}
 dump(OUT/(label+'-command.json'),record)
 if result.returncode:raise RuntimeError(f'{label} failed with {result.returncode}; retained log')
 return record

def cli(label,source,code,dpi=144,reuse=False):
 output=OUT/label
 if reuse and output.exists():
  assert read(output/'manifest.json')['source_sha256']==sha256(source)
  return output,read(OUT/(label+'-command.json'))
 args=['wsl.exe','-d','Ubuntu-24.04','--','/usr/bin/env','TMPDIR=/mnt/c/Users/17193/AppData/Local/hermes/cache/scratch',
       'PYTHONPATH='+wsl_path(code.parent),PY,wsl_path(code),'--input',wsl_path(source),'--output',wsl_path(output),'--engine','native','--dpi',str(dpi),'--deadline-seconds','180']
 record=execute(label,args)
 m=read(output/'manifest.json');r=read(output/'receipt.json')
 assert r['status']=='complete'and r['targeted_recovery_calls']==0
 assert all(p['model_calls']==0 for p in r['page_timings'])
 checks={'parser':validate_bundle(output,m),'application':app_validate(output,sha256(source),len(m['pages']))}
 dump(OUT/(label+'-validators.json'),checks)
 return output,record

def source_records(bundle):
 records={}
 for page in read(bundle/'manifest.json')['pages']:
  raw=read(bundle/f'raw/p{page["number"]:04}-native.json')
  for parent in raw['blocks']:
   for item in [parent]+parent.get('children',[]):records[f'p{page["number"]}-b{item["index"]}']=(page,item)
 return records

def union_counts(manifest, records):
 universe={};sets={'verified':set(),'ordinary':set()};units=[]
 for ident,(page,item)in records.items():
  if 'source_parent_index'in item or item['type']!='text':continue
  for i,c in enumerate(item['content']):universe[(page['number'],item['index'],i)]=c
 for page in manifest['pages']:
  for block in page['blocks']:
   if block['id']not in records or block['type']!='text':continue
   source_page,item=records[block['id']]
   if 'source_parent_index'in item:
    parent=item['source_parent_index'];start,end=item['source_text_range']
   else:parent=item['index'];start,end=0,len(item['content'])
   keys={(page['number'],parent,i)for i in range(start,end)}
   assert all(key in universe for key in keys)
   verified=any(i.startswith('native_machine_verified_literal:')for i in block['issues'])
   state='verified'if verified else 'ordinary'if block['quality']=='extracted'else 'withheld'
   if state in sets:sets[state]|=keys
   units.append({'id':block['id'],'source_parent_index':parent,'source_text_range':[start,end],
                 'quality':block['quality'],'literal_state':state,'text':block['text'],'bbox':block['bbox'],'issues':block['issues']})
 eligible=sets['verified']|sets['ordinary'];sets['ordinary']-=sets['verified'];withheld=set(universe)-eligible
 def count(keys):return {'characters_including_layout':len(keys),'nonwhitespace_characters':sum(not universe[k].isspace()for k in keys)}
 result={'source_position_policy':'unique (source page, original native index, exact raw text offset); fragments never added to parent length',
   'original_native_text_blocks':sum(item['type']=='text'and 'source_parent_index'not in item for page,item in records.values()),
   'output_native_text_blocks':len(units),'quality_counts':dict(collections.Counter(u['quality']for u in units)),
   'literal_state_counts':dict(collections.Counter(u['literal_state']for u in units)),
   'source_characters':count(universe),'eligible_unique_source_characters':count(eligible),
   'verified_unique_source_characters':count(sets['verified']),'ordinary_unverified_unique_source_characters':count(sets['ordinary']),
   'withheld_unique_source_characters':count(withheld),'units':units,'semantic_accuracy_approved':False}
 assert len(eligible)+len(withheld)==len(universe)
 return result

def replay(label,native_bundle,scans,source_info):
 output=OUT/label;shutil.copytree(native_bundle,output)
 m=read(output/'manifest.json');records=source_records(output);checks=[]
 for page in m['pages']:
  scan=scans[page['number']];page_checks=[]
  for block in page['blocks']:
   if block['type']!='text'or not block['text'].strip():continue
   box=block['bbox'];subset={**scan,'lines':[line for line in scan.get('lines',[])if
      box[0]-.003<=line['bbox'][0]and box[1]-.003<=line['bbox'][1]and box[2]+.003>=line['bbox'][2]and box[3]+.003>=line['bbox'][3]]}
   lines=[{**line,'bbox':rotate_bbox(line['bbox'],page['rotation'])}for line in records[block['id']][1]['source_text_lines']]
   proof=apply_native_verification(block,subset,lines,f'raw/p{page["number"]:04}-text-verification.json#{block["id"]}')
   page_checks.append({'block_id':block['id'],'native_text_preserved':True,'verification':proof})
  dump(output/f'raw/p{page["number"]:04}-text-verification.json',{'original_pdf_page':page['number'],
    'source_info':source_info,'independent_ocr':scan,'checks':page_checks})
  checks+=page_checks
  page['status']='needs_review'if any(b['quality']=='needs_review'for b in page['blocks'])else 'text'
 m['coverage']=coverage_of(m);m['parser']['recipe']+='; cpu-only-literal-replay-not-vlm'
 dump(output/'manifest.json',m)
 validation={'parser':validate_bundle(output,m),'application':app_validate(output,m['source_sha256'],m['page_count'])}
 counts=union_counts(m,records);counts['validation']=validation;counts['comparison_counts']=dict(collections.Counter(
    c['verification']['status']for c in checks))
 dump(OUT/(label+'-summary.json'),counts)
 dump(output/'receipt.json',{'status':'complete','mode':'cpu_literal_replay_from_actual_native_cli','source_info':source_info,
   'source_sha256':m['source_sha256'],'model_calls':0,'gpu_calls':0,'semantic_accuracy_approved':False,'validation':validation})
 return counts

def font_evidence(doc,page,label):
 records=[];(OUT/'source-fonts').mkdir(exist_ok=True)
 for font in page.get_fonts(full=True):
  xref=font[0];data=doc.extract_font(xref)[3];asset=None
  if data:
   asset=f'source-fonts/{hashlib.sha256(data).hexdigest()}.{font[1]}';(OUT/asset).write_bytes(data)
  kind,value=doc.xref_get_key(xref,'ToUnicode');cmap=None
  if kind=='xref':
   cx=int(value.split()[0]);data=doc.xref_stream(cx);ref=f'source-fonts/{hashlib.sha256(data).hexdigest()}.cmap';(OUT/ref).write_bytes(data)
   cmap={'xref':cx,'asset':ref,'sha256':sha256(OUT/ref)}
  records.append({'resource':list(font),'dictionary':doc.xref_object(xref),'embedded_asset':asset,'to_unicode':cmap})
 streams=[]
 for xref in page.get_contents():
  data=doc.xref_stream(xref);ref=f'source-fonts/{label}-content-{xref}.bin';(OUT/ref).write_bytes(data)
  streams.append({'xref':xref,'asset':ref,'sha256':sha256(OUT/ref)})
 trace=[]
 for entry in page.get_texttrace():
  trace.append({k:v for k,v in entry.items()})
 dump(OUT/(label+'-font-glyph-evidence.json'),{'fonts':records,'contents':streams,'texttrace':trace})


def main():
 OUT.mkdir(parents=True,exist_ok=True)
 sources=read(ROOT/'artifacts/stage14/corpus-audit/sources-final.json')
 original=Path(next(s['path']for s in sources if s['id']=='src03'))
 corrupt=Path(next(s['path']for s in sources if s['id']=='src20'))
 before_hashes={str(p):sha256(p)for p in [original,corrupt,SUBSET,RETAINED/'manifest.json']}
 commands=[]
 before,command=cli('before-native-bundle-dpi144',SUBSET,OUT/'before-code/parser_worker.py');commands.append(command)
 native,command=cli('after-native-bundle-dpi144',SUBSET,ROOT/'tools/document_stage12/parser_worker.py');commands.append(command)
 bad_before,command=cli('before-src20-native-bundle',corrupt,OUT/'before-code/parser_worker.py',reuse=True);commands.append(command)
 bad_after,command=cli('after-src20-native-bundle',corrupt,ROOT/'tools/document_stage12/parser_worker.py',reuse=True);commands.append(command)
 retained=read(RETAINED/'manifest.json');fresh=read(native/'manifest.json');fresh_records=source_records(native)
 retained_native=[(p['number'],b)for p in retained['pages']for b in p['blocks']if 'source_transcription_native'in b['issues']]
 for page,b in retained_native:
  source=fresh_records[b['id']][1]
  assert b['text']==source['content']and b['bbox']==source['bbox'],b['id']
  assert 'source_parent_index'not in source
 assert len(retained_native)==81
 same_pixel_scans={}
 for page in retained['pages']:
  old_image=Image.open(RETAINED/page['image']).convert('RGB');new_image=Image.open(native/page['image']).convert('RGB')
  assert old_image.size==new_image.size and old_image.tobytes()==new_image.tobytes()
  scan=read(RETAINED/f'raw/p{page["number"]:04}-text-verification.json')['independent_ocr']
  digest=hashlib.sha256(old_image.tobytes()+str(old_image.size).encode()).hexdigest()
  assert digest==scan['input_pixel_sha256']
  same_pixel_scans[page['number']]=scan
 old_counts=replay('retained-cpu-replay-bundle',native,same_pixel_scans,{
  'kind':'real_installed_r6_independent_cpu_output_reused_exact_pixels','retained_manifest_sha256':sha256(RETAINED/'manifest.json'),
  'source_original_sha256':sha256(original),'physical_pages':[126,127],'subset_sha256':sha256(SUBSET)})
 # CPUVerifier's only model initialization is explicitly local ONNX. Block
 # accidental networking as an executable guard, not an alternative OCR engine.
 import socket
 def blocked(*args,**kwargs):raise RuntimeError('Network prohibited in CPU replay')
 socket.create_connection=blocked
 verifier=CPUVerifier();scans={};doc=fitz.open(original);subset=fitz.open(SUBSET)
 for n,physical in enumerate((126,127),1):
  p=doc[physical-1];pix=p.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
  sp=subset[n-1].get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
  assert (pix.width,pix.height,pix.samples)==(sp.width,sp.height,sp.samples)
  image=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
  image.save(OUT/f'fresh-cpu-p{physical}.png')
  scan=verifier.scan(image);assert scan['status']=='complete'and scan['actual_providers']==['CPUExecutionProvider']
  scans[n]=scan;dump(OUT/f'fresh-cpu-p{physical}.json',scan)
  font_evidence(doc,p,f'src03-p{physical}')
 counts=replay('fresh-cpu-replay-bundle',native,scans,{
  'kind':'fresh_real_local_RapidOCR_CPU_from_original_pdf_matrix2','source_original_sha256':sha256(original),
  'physical_pages':[126,127],'subset_sha256':sha256(SUBSET),'original_subset_matrix2_pixels_equal':True})
 bad_doc=fitz.open(corrupt);font_evidence(bad_doc,bad_doc[1],'src20-p2')
 bad_records=source_records(bad_after);bad_m=read(bad_after/'manifest.json')
 bad_result=union_counts(bad_m,bad_records)
 corrupt_blocks=[]
 for ident,(page,item)in bad_records.items():
  if page['number']!=2 or 'source_parent_index'in item or item['type']!='text':continue
  controls=[c for s in item['source_text_spans']for c in s['characters']if unicodedata.category(c['text'])=='Cc']
  if controls:
   assert item['quality']=='needs_review'
   assert 'native_font_mapping_unusable'in item['issues']
   corrupt_blocks.append({'id':ident,'glyph_controls':controls,'text':item['content']})
 assert corrupt_blocks
 bad_result['known_control_corrupt_page2_blocks']=corrupt_blocks
 dump(OUT/'src20-corruption-summary.json',bad_result)
 after_hashes={p:sha256(Path(p))for p in before_hashes};assert before_hashes==after_hashes
 result={'gpu_calls':0,'new_vlm_model_calls':0,'commands':commands,'source_hashes_before':before_hashes,'source_hashes_after':after_hashes,
  'retained_gpu_bundle':{'total_blocks':sum(len(p['blocks'])for p in retained['pages']),
     'quality_counts':dict(collections.Counter(b['quality']for p in retained['pages']for b in p['blocks'])),
     'native_original_blocks':len(retained_native),'all_native_text_and_boxes_exactly_preserved':True,
     'all_retained_and_native_worker_page_pixels_exactly_equal':True},
  'retained_cpu_replay':{k:v for k,v in old_counts.items()if k not in ('units','validation')},
  'fresh_cpu_replay':{k:v for k,v in counts.items()if k not in ('units','validation')},
  'src20_true_corruption':{'physical_page':2,'control_corrupt_blocks':len(corrupt_blocks),'remain_needs_review':True,
     'font_mapping':'G1 Type0 Identity-H resource xref388 has no ToUnicode; original glyph trace/content retained; not decoded or repaired'},
  'literal_scope_only':True,'semantic_accuracy_approved':False}
 dump(OUT/'cpu-replay-result.json',result)
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
