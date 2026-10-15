"""Read-only-original Linux Office native/prepared reuse probes; zero GPU calls."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time


def digest(path):
    with path.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    cli=argparse.ArgumentParser();cli.add_argument('--sources',required=True);cli.add_argument('--output',required=True);a=cli.parse_args()
    base=Path(a.sources);out=Path(a.output);out.mkdir(parents=True,exist_ok=False)
    entry=Path(__file__).resolve().parents[1]/'material_stage13/parse_material.py'
    env={**os.environ,'CUDA_VISIBLE_DEVICES':'','HF_HUB_OFFLINE':'1'}
    result={'status':'running','model_calls':0,'production_modified':False,'semantic_acceptance':False,'cases':[]}
    for sid,suffix in [('src15','pptx'),('src16','doc'),('src17','docx')]:
        source=base/(sid+'.'+suffix);sha=digest(source);case={'source':sid,'format':suffix,'original_sha256':sha}
        for phase in ['native','reuse']:
            target=out/(sid+'-'+phase)
            args=[sys.executable,str(entry),'--input',str(source),'--output',str(target),'--engine','native','--dpi','144','--deadline-seconds','600']
            if phase=='reuse':args+=['--prepared-dir',str(out/(sid+'-native'))]
            started=time.monotonic();p=subprocess.run(args,env=env,capture_output=True,text=True,timeout=630)
            (out/(sid+'-'+phase+'.log')).write_text(p.stdout+'\n'+p.stderr)
            receipt=json.loads((target/'receipt.json').read_text())if(target/'receipt.json').exists()else{}
            case[phase]={'returncode':p.returncode,'wall_seconds':time.monotonic()-started,'receipt':receipt}
            if p.returncode:
                result['status']='failed';break
            manifest=json.loads((target/'manifest.json').read_text());assert manifest['source_sha256']==sha and manifest['source_format']==suffix and manifest['complete']
            assert receipt['status']=='complete'and receipt['engine']=='native'
            assert not any(x.get('model_calls',0)or x.get('model_processed')for x in receipt['page_timings'])
            case[phase].update(page_count=manifest['page_count'],preview_sha256=digest(target/'preview.pdf'),native_blocks=sum(len(x['blocks'])for x in manifest['pages']))
        if result['status']=='running':
            assert case['native']['page_count']==case['reuse']['page_count']
            assert case['native']['preview_sha256']==case['reuse']['preview_sha256']
            assert case['reuse']['receipt']['conversion_reused_from_native_phase']
            assert (out/(sid+'-native')/'raw/office-inventory.json').read_bytes()==(out/(sid+'-reuse')/'raw/office-inventory.json').read_bytes()
            case['native_and_reused_manifest_pages_equal']=json.loads((out/(sid+'-native')/'manifest.json').read_text())['pages']==json.loads((out/(sid+'-reuse')/'manifest.json').read_text())['pages']
            assert case['native_and_reused_manifest_pages_equal']
        case['source_unchanged']=digest(source)==sha;assert case['source_unchanged'];result['cases'].append(case)
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({'source':sid,'status':result['status'],'page_count':case['native'].get('page_count'),'reuse_seconds':case.get('reuse',{}).get('wall_seconds')}),flush=True)
        if result['status']=='failed':return 1
    result['status']='passed';assert len(result['cases'])==3
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');return 0
if __name__=='__main__':raise SystemExit(main())
