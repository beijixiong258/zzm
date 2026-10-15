"""Retained CPU pytest runner with machine-aggregated XML counts."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]


def main():
    cli=argparse.ArgumentParser();cli.add_argument('--label',required=True);cli.add_argument('--candidate-root',type=Path);cli.add_argument('tests',nargs='+');args=cli.parse_args()
    root=ROOT/'artifacts/stage16/formats';root.mkdir(parents=True,exist_ok=True)
    xml=root/(args.label+'.xml');log=root/(args.label+'.log');summary=root/(args.label+'.json')
    if any(p.exists()for p in (xml,log,summary)):raise ValueError('Use a fresh retained run label')
    scratch=Path('/mnt/c/Users/17193/AppData/Local/hermes/cache/scratch' if sys.platform=='linux'else'C:/Users/17193/AppData/Local/hermes/cache/scratch')
    work=Path(tempfile.mkdtemp(prefix='stage16-formats-',dir=scratch))
    env=dict(os.environ,TMPDIR=str(work),TEMP=str(work),TMP=str(work))
    cmd=[sys.executable,'-m','pytest',*args.tests,'-q','--capture=sys','--junitxml='+str(xml)]
    if args.candidate_root:
        env['PYTHONPATH']=str(ROOT)+os.pathsep+env.get('PYTHONPATH','')
    result=subprocess.run(cmd,cwd=args.candidate_root or ROOT,env=env,capture_output=True,text=True,timeout=600)
    log.write_text(result.stdout+'\nSTDERR\n'+result.stderr,encoding='utf-8')
    counts={'tests':0,'passed':0,'failures':0,'errors':0,'skipped':0}
    if xml.is_file():
        for case in ET.parse(xml).getroot().iter('testcase'):
            counts['tests']+=1
            status='failures'if case.find('failure')is not None else'errors'if case.find('error')is not None else'skipped'if case.find('skipped')is not None else'passed'
            counts[status]+=1
    receipt={'label':args.label,'returncode':result.returncode,'counts':counts,'xml':xml.name,'log':log.name,
        'scratch':str(work),'candidate_root':str(args.candidate_root)if args.candidate_root else None,
        'boundary':'CPU synthetic/protocol fixtures; no GPU, remote HTTP or deployment'}
    summary.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(receipt,ensure_ascii=False));return result.returncode


if __name__=='__main__':raise SystemExit(main())
