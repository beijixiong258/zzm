"""Verify handed-back artifacts, consume fresh real Markdown and complete PDF data.
No new model calls. All output folders are fresh; prior evidence is immutable.
"""
from pathlib import Path
import json,hashlib,xml.etree.ElementTree as ET
import sys
APP=Path(__file__).resolve().parents[2];sys.path.insert(0,str(APP))
from tools.material_stage15 import write_image_bundle,verify_readback
from tools.material_stage15.prepared import augment_prepared_bundle
from backend.aicademiya.document_bundle import validate_bundle
ROOT=APP/'artifacts/stage15';OUT=ROOT/'integrated-inputs'
def sha(p):
 with p.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 OUT.mkdir(exist_ok=False);old=ROOT/'material-adapter/real10/bundles';rows=[]
 for bundle in sorted(p for p in old.iterdir()if p.is_dir()):
  m=json.loads((bundle/'manifest.json').read_text());validate_bundle(bundle,m['source_sha256'],m['page_count']);r=verify_readback(bundle);rows.append({'name':bundle.name,'blocks':sum(len(p['blocks'])for p in m['pages']),'source_image_assets':r['source_image_assets']})
 assert len(rows)==10
 x=ET.parse(ROOT/'material-adapter/tests/adapter-tests-pass.xml');assert len(x.findall('.//testcase'))==27 and not x.findall('.//failure')and not x.findall('.//error')
 result=json.loads((ROOT/'markdown-probe-r1/result.json').read_text());inputs=Path('C:/Users/17193/Desktop/AIcademiya-27B图文实测-20261012-113346/minimal-final/input');new=[]
 (OUT/'responses').mkdir()
 for c in result['cases']:
  image=inputs/c['name'];assert sha(image)==c['sha256'];response=OUT/'responses'/(image.stem+'.json');response.write_text(json.dumps(c,ensure_ascii=False,indent=2)+'\n')
  mapping=json.loads((old/image.stem/'raw/p0001-adapter.json').read_text())['source_mapping']
  dest=OUT/image.stem;receipt=write_image_bundle(image,c,dest,expected_raster_sha256=c['sha256'],source_mapping=mapping,response_file=response)
  m=json.loads((dest/'manifest.json').read_text());validate_bundle(dest,c['sha256'],1);body=next(b for b in m['pages'][0]['blocks']if b['type']=='text');assert body['text']==json.loads(c['content'])['body_text']and body['quality']=='extracted'
  new.append({'name':c['name'],'source_image':str(image),'bundle':str(dest),'sha256':c['sha256'],'body_characters':len(body['text']),'text_format':body['text_format'],'source_notes':[i for i in body['issues']if i.startswith('model_uncertainty:')]})
 complete=ROOT/'prepared-complete-input/mask-bundle';original=json.loads((complete/'manifest.json').read_text());validate_bundle(complete,original['source_sha256'],2)
 page_inputs=json.loads((ROOT/'material-adapter/prepared-page-inputs.json').read_text())
 page_inputs[0]['response_file']=str(OUT/'responses/01-native-page126.json')
 prepared=OUT/'combined-two-page-pdf';merge=augment_prepared_bundle(complete,prepared,page_inputs);actual=validate_bundle(prepared,original['source_sha256'],2)
 for p,base in zip(actual['pages'],original['pages']):
  assert p['number']==base['number']and p['blocks'][:len(base['blocks'])]==base['blocks']
 receipt={'status':'passed','prior_actual10':rows,'prior_total_blocks':sum(r['blocks']for r in rows),'prior_source_image_assets':sum(r['source_image_assets']for r in rows),'new_real_markdown':new,'prepared':{'bundle':str(prepared),'source_sha256':actual['source_sha256'],'pages':len(actual['pages']),'old_blocks_preserved':True,'strict_application_valid':True},'model_calls':0,'semantic_accuracy_approved':False}
 (OUT/'integration-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
