"""Fresh strong-client GPU capture using the already tested owner lease probe.
No production config/worker writes. Adapter receives real HTTP replies; no fake
transport. Independent CPU verification runs on exactly the captured image bytes.
"""
from pathlib import Path
import base64,hashlib,json,sys,os
ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'app/tools/material_stage14')]
from tools.material_stage14.strong_recovery import LoopbackLineClient,align_evidence
from tools.material_stage14.strong_recovery.offline import verify_spatial
from tools.material_stage13.ocr_verification import CPUVerifier
import vision_probe
INPUT=ROOT/'input';OUT=ROOT/'live-r1';CAPTURES=ROOT/'captures-r1'
NAMES=['p1-left-page-2x.png','p9-left-page-2x.png']
def write(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
def main():
 assert os.getuid()==1000
 CAPTURES.mkdir(exist_ok=False)
 by_hash={hashlib.sha256((INPUT/n).read_bytes()).hexdigest():n for n in NAMES}
 original_api=vision_probe.api
 def routed_api(port,path,body=None,timeout=5):
  if path!='/v1/chat/completions':return original_api(port,path,body,timeout)
  items=body['messages'][-1]['content'];uri=next(x['image_url']['url']for x in items if x['type']=='image_url')
  image=base64.b64decode(uri.split(',',1)[1]);digest=hashlib.sha256(image).hexdigest();name=by_hash[digest]
  client=LoopbackLineClient(f'http://127.0.0.1:{port}/v1','material-vision-qa',timeout=600,max_tokens=3072)
  capture=client.transcribe(image,evidence_kind='actual_GPU_owner_UID1000_source_capture_not_worker_acceptance')
  write(CAPTURES/(name+'.capture.json'),capture)
  if capture['generation']['protocol_errors']:raise RuntimeError('Actual strong-client protocol failed; raw capture retained')
  return capture['response']['parsed']  # Exact parsed HTTP response, not synthesized output.
 vision_probe.api=routed_api
 sys.argv=['vision_probe.py','--lease-module',str(ROOT/'app/tools/document_stage12/gpu_lease.py'),'--input-dir',str(INPUT),'--output',str(OUT),'--images',*NAMES,'--image-tokens','4096','--output-tokens','3072','--timeout','900']
 vision_probe.main()
 runtime=json.loads((OUT/'result.json').read_text());assert runtime['owned_model_closed']and runtime['lease_return'].get('teaching_ready')
 assert all(any(a['gpu']==b['gpu']and a['pid']==b['pid']for a in runtime['final_allocations'])for b in runtime['initial_allocations']if b['gpu']!=runtime['gpu_uuid'])
 cpu=CPUVerifier('/opt/aicademiya-documents/shared/rapidocr-models-stage14');transforms=json.loads((INPUT/'transforms.json').read_text());cases=[]
 import pymupdf as fitz
 source=Path('/home/adminz/llm/ocr-stage1-20261009/data/dataset/sources/src14.pdf')
 source_sha='5ffdc6a8dce6d5136397afb13bcaf627a5396f8c004ab1007d6493981ca8e723'
 with source.open('rb')as f:assert hashlib.file_digest(f,'sha256').hexdigest()==source_sha
 from PIL import Image
 for name in NAMES:
  capture=json.loads((CAPTURES/(name+'.capture.json')).read_text());raw=base64.b64decode(capture['response']['body_base64']);assert hashlib.sha256(raw).hexdigest()==capture['response']['body_sha256'];assert not capture['transport_injected']
  with Image.open(INPUT/name)as image:scan=cpu.scan(image.convert('RGB'))
  write(CAPTURES/(name+'.cpu.json'),scan)
  transform=next(t for t in transforms if t['output']==name)
  spatial=verify_spatial(INPUT,transform,scan,{'sha256':capture['image_sha256']});assert spatial['input_binding_verified']and spatial['crop_to_raster_verified']
  page_number=1 if name=='p1-left-page-2x.png'else 9
  with fitz.open(source)as doc:
   page=doc[page_number-1];assert page.rotation==0
   rendered=page.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
   with Image.open(INPUT/transform['source'])as raster:
    rgb=raster.convert('RGB');assert rgb.size==(rendered.width,rendered.height)and rgb.tobytes()==rendered.samples
  placement={'source_sha256':source_sha,'physical_pdf_page':page_number,'source_raster_sha256':transform['source_sha256'],'render_scale':2,'pdf_rotation':0,'full_page_render_pixels_identical':True,'scope':'Source raster placement proved; no generated/approved citations'}
  proposal=align_evidence(scan,capture['generation'],spatial,evidence_kind='fresh_GPU_and_independent_CPU_capture',region_kind='prose_crop_with_headers_and_bullets')
  proposal['parent_verified_document_placement']=placement
  write(CAPTURES/(name+'.proposal.json'),proposal)
  cases.append({'image':name,'source_sha256':capture['image_sha256'],'finish':capture['generation']['finish_reason'],'usage':capture['generation']['usage'],'counts':proposal['counts'],'global_withheld_reasons':proposal['global_withheld_reasons'],'raw_HTTP_response_captured':True,'fresh_CPU_inference':True,'page_location_status':'spatial-parent-only','whole_source_accepted':False})
 report={'status':'fresh_GPU_client_and_CPU_alignment_exercised','operator_uid':os.getuid(),'installed_UID999_acceptance':False,'production_changed':False,'cases':cases,'runtime_result':str(OUT/'result.json'),'owned_model_closed':True,'teaching_returned':True,'semantic_accepted':False}
 write(ROOT/'acceptance-r1.json',report);print(json.dumps(report,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
