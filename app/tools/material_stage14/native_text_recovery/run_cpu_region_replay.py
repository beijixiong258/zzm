"""Actual Linux worker path, real retained CPU scan, rejecting model sentinel.

The CPU scans were freshly executed on Windows and are bound to exact pixels.
No OCR response is synthesized here, and any model call fails this replay.
"""
import contextlib, hashlib, io, json, sys, types
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'artifacts/stage14/native-text-recovery'
sys.path[:0]=[str(ROOT),str(ROOT/'tools/document_stage12'),str(ROOT/'tools/material_stage13')]
import parser_worker
from parser_helpers import dump,sha256,validate_bundle
from backend.aicademiya.document_bundle import validate_bundle as app_validate
SUBSET=ROOT/'artifacts/stage14/r6-final-inputs/src03-pages126-127.pdf'

def main():
 scans={}
 for physical in (126,127):
  scan=json.loads((OUT/f'fresh-cpu-p{physical}.json').read_text())
  assert scan['status']=='complete'and scan['actual_providers']==['CPUExecutionProvider']
  scans[scan['input_pixel_sha256']]=scan
 class RealCPUReadback:
  info={'available':True,'mode':'real_fresh_CPU_readback_exact_pixel_replay','new_onnx_inference_in_this_process':False}
  def __init__(self,*args):self.inputs=[]
  def scan(self,image):
   digest=hashlib.sha256(image.convert('RGB').tobytes()+str(image.size).encode()).hexdigest()
   assert digest in scans,'Only exact source scan pixels may be replayed'
   self.inputs.append(digest)
   return scans[digest]
 model_calls=[]
 class RejectModel:
  prompts={'[default]':'Text Recognition:'}
  def __init__(self,**kwargs):pass
  def content_extract(self,*args,**kwargs):model_calls.append('forbidden');raise AssertionError('No VLM call permitted')
  async def aclose(self):pass
 utils=types.ModuleType('mineru_vl_utils');utils.MinerUClient=RejectModel
 client=types.ModuleType('mineru_vl_utils.vlm_client');client.SamplingParams=lambda **kwargs:kwargs
 output=OUT/'cpu-region-replay-bundle';capture=io.StringIO()
 with patch.dict(sys.modules,{'mineru_vl_utils':utils,'mineru_vl_utils.vlm_client':client}),patch.object(parser_worker,'CPUVerifier',RealCPUReadback),contextlib.redirect_stdout(capture):
  rc=parser_worker.main(['--input',str(SUBSET),'--output',str(output),'--dpi','144','--engine','region-text',
                        '--models',str(OUT/'source-fonts'),'--vlm-url','http://127.0.0.1:18894','--ocr-recovery-call-limit','0'])
 (OUT/'cpu-region-worker.log').write_text(capture.getvalue())
 assert rc==0 and not model_calls
 m=json.loads((output/'manifest.json').read_text());r=json.loads((output/'receipt.json').read_text())
 assert all(p['model_calls']==0 for p in r['page_timings'])
 validation={'parser':validate_bundle(output,m),'application':app_validate(output,sha256(SUBSET),2)}
 uniform=[];native=[]
 for page in m['pages']:
  for b in page['blocks']:
   if 'source_transcription_native'in b['issues']:native.append(b)
   if 'image_class_decorative_uniform'in b['issues']:
    assert 'image_ocr_not_needed_uniform'in b['issues'];uniform.append(b['id'])
 assert len(uniform)==15
 assert any(b['text']=='Ss clap their hands when they 'and 'fragment'in b['id']for b in native)
 verified=[b['id']for b in native if any(i.startswith('native_machine_verified_literal:')for i in b['issues'])]
 assert len(verified)==19
 dump(OUT/'cpu-region-worker-result.json',{'worker_exit_code':rc,'GPU_calls':0,'VLM_calls':len(model_calls),
  'new_CPU_inference_in_this_process':False,'real_CPU_source':'fresh-cpu-p126.json/fresh-cpu-p127.json (exact pixel hash checked)',
  'model_client':'rejecting sentinel, no fabricated model response','mask_uniform_occurrences':uniform,
  'native_verified_literal_block_ids':verified,'validation':validation,'semantic_accuracy_approved':False})
 print(json.dumps({'worker_exit_code':rc,'uniform_occurrences':len(uniform),'native_verified_blocks':len(verified),
                   'total_blocks':sum(len(p['blocks'])for p in m['pages']),'VLM_calls':0,'GPU_calls':0}))
 return rc
if __name__=='__main__':raise SystemExit(main())
