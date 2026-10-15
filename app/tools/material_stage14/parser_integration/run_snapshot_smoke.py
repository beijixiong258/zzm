"""Exercise extracted allowlist parser CLI and strict app bundle on WSL CPU."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

APP=Path(__file__).resolve().parents[3]
OUT=APP/'artifacts/stage14/parser-integration'


def linux_path(value):
    p=Path(value)
    drive=p.drive.rstrip(':').lower()
    return '/mnt/'+drive+'/'+p.as_posix()[3:]


def main():
    snapshot=json.loads((OUT/'runtime-module-snapshot.json').read_text())
    root=linux_path(snapshot['extracted_root'])
    scratch=Path(tempfile.mkdtemp(prefix='s14-packaged-native-',dir=os.environ['TMPDIR']))
    data=linux_path(scratch);python='/mnt/d/HermesProjects/EDUC7703/app/.venv-stage14-linux/bin/python'
    native='Packaged source exact text\nSecond source line 中文\nFINAL_SENTINEL\n'
    (scratch/'source.txt').write_text(native,encoding='utf-8')
    commands=[[python,'-B',root+'/tools/document_stage12/parser_worker.py','--help'],
              [python,'-B',root+'/tools/material_stage13/parse_material.py','--help'],
              [python,'-B',root+'/tools/material_stage13/parse_material.py','--input',data+'/source.txt','--output',data+'/bundle','--engine','native','--deadline-seconds','60']]
    results=[]
    for command in commands:
        r=subprocess.run(['wsl','--exec',*command],capture_output=True,text=True,timeout=80)
        results.append({'command':command,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
        if r.returncode:break
    code="import pathlib,sys;sys.path.insert(0,sys.argv[1]);from backend.aicademiya.document_bundle import source_identity,validate_bundle;import backend.aicademiya.document_bundle as m;root=pathlib.Path(sys.argv[1]);assert pathlib.Path(m.__file__).is_relative_to(root);source=pathlib.Path(sys.argv[2]);digest,count=source_identity(source);v=validate_bundle(sys.argv[3],digest,count);literal=''.join(b['text'] for p in v['pages'] for b in p['blocks']);assert literal==source.read_bytes().decode('utf-8');print('extracted native CLI + exact-text application bundle passed')"
    r=subprocess.run(['wsl','--exec',python,'-B','-c',code,root,data+'/source.txt',data+'/bundle'],capture_output=True,text=True,timeout=30)
    results.append({'check':'extracted exact-text app bundle','returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
    report={'scope':'isolated extracted runtime-module snapshot; actual WSL CPU CLI/native only; no deployment/GPU/OCR proof',
            'archive_sha256':snapshot['archive_sha256'],'results':results,'all_passed':all(x['returncode']==0 for x in results)}
    (OUT/'runtime-snapshot-linux-smoke.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'all_passed':report['all_passed'],'checks':len(results),'final_check':results[-1]}))
    return 0 if report['all_passed'] else 1


if __name__=='__main__':raise SystemExit(main())
