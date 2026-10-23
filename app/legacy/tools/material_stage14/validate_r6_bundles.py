"""Validate installed r6 real bundles and reject a damaged final APNG frame."""
from pathlib import Path
import collections,hashlib,json,os,struct,subprocess,sys,time,urllib.request,zlib
from PIL import Image
APP=Path('/opt/aicademiya/releases/AIcademiya_V2-20261012-materials-r6');sys.path.insert(0,str(APP))
from backend.aicademiya.document_bundle import BundleError,validate_bundle,source_identity
ROOT=Path('/var/lib/aicademiya-qa/stage14-r6-final')
def status():
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://192.168.32.5:18280/status',timeout=5)as r:return json.load(r)
def main():
 assert os.geteuid()==999;manifest=json.loads((ROOT/'manifest.json').read_text());report={'status':'running','semantic_accepted':False,'actual_uid':os.geteuid()}
 for name,file,pages in [('mask-bundle','src03-pages126-127.pdf',2),('frames-bundle','three-frames.png',3)]:
  result=validate_bundle(ROOT/name,manifest['files'][file]['sha256'],pages);report[name]={'strict_application_validator':'passed','pages':pages}
 m=json.loads((ROOT/'frames-bundle/manifest.json').read_text());expected=manifest['apng_expected_text_by_frame']
 assert len(m['pages'])==len(expected)==3
 for p,text in zip(m['pages'],expected):assert[b['text']for b in p['blocks']if b['quality']=='extracted']==[text]
 assert source_identity(ROOT/'three-frames.png')==(manifest['files']['three-frames.png']['sha256'],3)
 report['all_three_frames_exact_extracted']=True
 regions=[]
 for p in(ROOT/'mask-bundle/raw').glob('*-region*.json'):
  v=json.loads(p.read_text());c=v.get('source_compositing',{})
  if c.get('source_image_size')==[2,2]and c.get('source_mask_size')==[287,112]:
   assert c['mask_extrema']==[0,0]and c['effective_alpha_extrema']==[0,0]and c['includes_page_overlays']is False
   assert not v['raw_text']and v['uniform_decorative']and not v['generation']['events']
   with Image.open(ROOT/'mask-bundle'/v['ocr_input_asset'])as im:assert im.convert('RGB').getextrema()==((255,255),)*3
   regions.append({'page':v['original_pdf_page'],'parent':c['parent_id']})
 assert len(regions)==len({(r['page'],r['parent'])for r in regions})==15;report['mask_occurrences_verified']=regions
 raw=(ROOT/'three-frames.png').read_bytes();off=8;chunks=[]
 while off<len(raw):
  size=struct.unpack('>I',raw[off:off+4])[0];chunks.append((off,size,raw[off+4:off+8]));off+=size+12
 off,size,kind=next(x for x in reversed(chunks)if x[2]==b'fdAT');data=bytearray(raw[off+8:off+8+size]);data[4]=0
 damaged=raw[:off+8]+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)+raw[off+12+size:];bad=ROOT/'corrupt-final-frame.png';assert not bad.exists();bad.write_bytes(damaged)
 with Image.open(bad)as image:
  assert image.n_frames==3;image.seek(0);image.load();image.seek(1);image.load()
  try:image.seek(2);image.load()
  except OSError:pass
  else:raise AssertionError('Fixture final frame was not corrupt')
 try:source_identity(bad)
 except BundleError as e:report['application_final_frame_rejected']={'type':type(e).__name__,'message':str(e)}
 else:raise AssertionError('Application accepted corrupt late frame')
 before=status();assert before['resources']['phase']=='teaching'
 args=['/usr/bin/python3','/var/lib/aicademiya-qa/stage14-native-0986d5dd/bridge.py','--ssh-host','aicademiya-docs@192.168.32.5','--ssh-key','/var/lib/aicademiya/worker-ssh-stage14/id_ed25519','--known-hosts','/var/lib/aicademiya/worker-ssh-stage14/known_hosts','--input',str(bad),'--output',str(ROOT/'bad-frame-bundle'),'--timeout','60']
 r=subprocess.run(args,capture_output=True,text=True,timeout=80);(ROOT/'bad-frame-attempt.stderr').write_text(r.stderr);assert r.returncode!=0
 s=json.loads((ROOT/'bad-frame-bundle/raw/supervisor.json').read_text());assert s['status']=='failed'and s['gpu_lease_used']is False and 'model_pid'not in s
 after=status();assert after['resources']['epoch']==before['resources']['epoch']and after['teaching_capacity']==3
 report.update(status='passed',invalid_late_frame_worker=s,negative_test_returncode=r.returncode,negative_test_leased_gpu=False,negative_test_model_started=False)
 (ROOT/'final-validation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
