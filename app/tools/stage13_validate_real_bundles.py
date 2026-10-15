"""Read-only current application boundary validation of actual parser outputs; no GPU calls."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,sys,time

def main():
 p=argparse.ArgumentParser();p.add_argument('--module',required=True);p.add_argument('--inventory',required=True);p.add_argument('--output',required=True);a=p.parse_args()
 spec=importlib.util.spec_from_file_location('stage13_app_bundle',a.module);module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
 inventory=json.loads(Path(a.inventory).read_text());sources=inventory['sources'];assert len(sources)==len({s['id']for s in sources})==23
 base=Path('/home/adminz/llm/ocr-stage1-20261009');root=base/'stage13-parser';target=Path(a.output);assert not target.exists();target.parent.mkdir(parents=True,exist_ok=True)
 rows=[];start=time.monotonic();deadline=start+300
 jobs=[(s,root/'native-v2/bundles'/s['id'],'native')for s in sources]
 for name,sid in [('pptx','src15'),('docx','src17'),('doc','src16')]:jobs.append((next(s for s in sources if s['id']==sid),root/'gpu-additive-literal-final'/name,'hybrid'))
 for source,bundle,mode in jobs:
  if time.monotonic()>deadline:break
  row={'source_id':source['id'],'mode':mode,'bundle':str(bundle)}
  try:
   original=base/'data/dataset/sources'/(source['id']+'.'+source['type'])
   with original.open('rb')as f:assert hashlib.file_digest(f,'sha256').hexdigest()==source['sha256']
   count=json.loads((bundle/'manifest.json').read_text())['page_count']
   validated=module.validate_bundle(bundle,source['sha256'],count)
   row.update(status='passed',pages=validated['page_count'],blocks=sum(len(x['blocks'])for x in validated['pages']),source_format=validated.get('source_format','pdf'))
  except Exception as e:row.update(status='failed',error_type=type(e).__name__,error=str(e))
  rows.append(row)
  result={'status':'running','expected_native_sources':23,'expected_hybrid_cases':3,'model_calls':0,'semantic_acceptance':False,'rows':rows}
  target.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(row),flush=True)
 result.update(status='passed'if len(rows)==len(jobs)and all(x['status']=='passed'for x in rows)else'failed',seconds=time.monotonic()-start)
 target.write_text(json.dumps(result,indent=2)+'\n');return 0 if result['status']=='passed'else 1
if __name__=='__main__':raise SystemExit(main())
