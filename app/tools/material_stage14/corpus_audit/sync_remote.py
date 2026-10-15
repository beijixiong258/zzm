"""同步自身审计产物至自身CPU目录并读回精确hash；不写任何源/服务路径。"""
import json,subprocess,shlex,hashlib
from pathlib import Path
APP=Path('D:/HermesProjects/EDUC7703/app');O=APP/'artifacts/stage14/corpus-audit';T=APP/'tools/material_stage14/corpus_audit'
REMOTE='/home/adminz/llm/ocr-stage1-20261009/stage14-corpus-audit';PY='/home/adminz/llm/ocr-stage1-20261009/whole-document-pilot/.venv/bin/python'
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
files=[*T.glob('*.py'),*[p for p in O.glob('*.json') if p.name!='transport-readback.json'],*O.glob('*.jsonl'),O/'HANDOFF.md',O/'priority-bundle.tar.gz']
for i in range(0,len(files),12):subprocess.run(['scp',*[str(x) for x in files[i:i+12]],'ubuntu-gpu:'+REMOTE+'/'],check=True,timeout=180)
code="import pathlib,json,hashlib,tarfile; r=pathlib.Path("+repr(REMOTE)+"); names="+repr([p.name for p in files])+"; t=tarfile.open(r/'priority-bundle.tar.gz'); t.extractall(r,filter='data'); print(json.dumps({n:hashlib.file_digest((r/n).open('rb'),'sha256').hexdigest() for n in names}))"
proc=subprocess.run(['ssh','-o','BatchMode=yes','ubuntu-gpu',PY+' -B -c '+shlex.quote(code)],check=True,capture_output=True,text=True,timeout=90)
actual=json.loads(proc.stdout);expected={p.name:sha(p) for p in files};assert actual==expected
checks=[]
for args in ['--validate-all','--page src08:1']:
    p=subprocess.run(['ssh','-o','BatchMode=yes','ubuntu-gpu','CUDA_VISIBLE_DEVICES="" PYTHONDONTWRITEBYTECODE=1 '+PY+' -B '+REMOTE+'/materialize_inputs.py '+args],capture_output=True,text=True,check=True,timeout=120)
    checks.append({'args':args,'returncode':p.returncode,'result':json.loads(p.stdout)})
report={'说明':'精确同步目标读回及Linux真实CPU物化检查，不含GPU/模型/服务操作。','remote_directory':REMOTE,'files':actual,'all_transported_hashes_match':True,'checks':checks,'gpu_calls':0}
(O/'transport-readback.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'transported_files':len(actual),'all_hashes_match':True,'remote_cpu_checks':[x['args'] for x in checks],'gpu_calls':0},ensure_ascii=False,indent=2))
