"""Copy only this CPU QA snapshot to its owned remote directory; verify readback.
No deployed release, package, service, model or source PDF is changed.
"""
import argparse,hashlib,json,shlex,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'artifacts/stage14/mask-recovery'
REMOTE='/home/adminz/llm/ocr-stage1-20261009/stage14-mask-recovery'
PY='/opt/aicademiya-documents/runtime/.venv/bin/python'
NATIVE='/opt/aicademiya-documents/shared/native-libs/usr/lib/x86_64-linux-gnu'
def sha(path):
    with path.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def remote(command,timeout=180):
    return subprocess.run(['ssh','-o','BatchMode=yes','ubuntu-gpu',command],check=True,capture_output=True,text=True,encoding='utf-8',timeout=timeout)
def main():
    cli=argparse.ArgumentParser();cli.add_argument('--resume',action='store_true');args=cli.parse_args()
    files=[ROOT/'tools/document_stage12/parser_helpers.py',ROOT/'tools/document_stage12/parser_worker.py',ROOT/'tools/material_stage13/ocr_verification.py',
        ROOT/'backend/aicademiya/document_bundle.py',ROOT/'tools/material_stage14/parser_recovery/test_ocr_verification.py',*sorted((ROOT/'tools/material_stage14/mask_recovery').glob('*.py'))]
    expected={p.relative_to(ROOT).as_posix():sha(p)for p in files}
    assert expected['tools/material_stage13/ocr_verification.py']=='1649770889ca88e017fd426de8c96f97531d0d71e354489458cace1324066748'
    dirs=sorted({REMOTE+'/app/'+p.relative_to(ROOT).parent.as_posix()for p in files}|{REMOTE+'/tmp',REMOTE+'/app/artifacts/stage14/mask-recovery/linux-source'})
    remote('mkdir -p '+' '.join(shlex.quote(d)for d in dirs),60)
    for p in files:subprocess.run(['scp',str(p),'ubuntu-gpu:'+REMOTE+'/app/'+p.relative_to(ROOT).as_posix()],check=True,timeout=90)
    code='import pathlib,json,hashlib; r=pathlib.Path('+repr(REMOTE+'/app')+');names='+repr(list(expected))+';print(json.dumps({n:hashlib.sha256((r/n).read_bytes()).hexdigest()for n in names}))'
    actual=json.loads(remote(PY+' -B -c '+shlex.quote(code),60).stdout);assert actual==expected
    dump={'remote_directory':REMOTE,'python':PY,'source_files':actual,'all_remote_readback_hashes_match':True,'gpu_calls':0,'model_service_calls':0}
    OUT.mkdir(parents=True,exist_ok=True);(OUT/'transport-readback.json').write_text(json.dumps(dump,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    env='CUDA_VISIBLE_DEVICES="" PYTHONDONTWRITEBYTECODE=1 TMPDIR='+shlex.quote(REMOTE+'/tmp')+' LD_LIBRARY_PATH='+shlex.quote(NATIVE)+' MASK_RECOVERY_OUT='+shlex.quote(REMOTE+'/app/artifacts/stage14/mask-recovery')+' '
    tests=[('linux-unit.log',env+PY+' -B '+REMOTE+'/app/tools/material_stage14/mask_recovery/test_mask_recovery.py'),
        ('linux-negative-worker.log',env+PY+' -B '+REMOTE+'/app/tools/material_stage14/mask_recovery/test_mask_worker.py'),
        ('linux-existing-regressions.log',env+PY+' -B -m unittest discover -s '+REMOTE+'/app/tools/material_stage14/parser_recovery -p test_ocr_verification.py -v'),
        ('linux-source.log',env+PY+' -B '+REMOTE+'/app/tools/material_stage14/mask_recovery/run_source_proof.py --src03 /home/adminz/llm/ocr-stage1-20261009/data/dataset/sources/src03.pdf --src01 /home/adminz/llm/ocr-stage1-20261009/data/dataset/sources/src01.pdf --out '+REMOTE+'/app/artifacts/stage14/mask-recovery/linux-source --worker')]
    run=json.loads((OUT/'linux-test-execution.json').read_text()) if args.resume else []
    if args.resume:
        (OUT/'linux-existing-regressions.log').rename(OUT/'linux-existing-regressions-initial-unavailable.log')
    for name,cmd in (tests[2:] if args.resume else tests):
        p=subprocess.run(['ssh','-o','BatchMode=yes','ubuntu-gpu',cmd],capture_output=True,text=True,encoding='utf-8',timeout=1200)
        (OUT/name).write_text(p.stdout+'\nSTDERR\n'+p.stderr,encoding='utf-8')
        run.append({'log':name,'returncode':p.returncode,'command':cmd});print(name,p.returncode,p.stdout[-1000:],p.stderr[-1400:],flush=True)
        (OUT/'linux-test-execution.json').write_text(json.dumps(run,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        if p.returncode:raise SystemExit(p.returncode)
    # Pull only owned receipts/outputs; validate file hash readback from remote.
    subprocess.run(['scp','-r','ubuntu-gpu:'+REMOTE+'/app/artifacts/stage14/mask-recovery/linux-source',str(OUT)],check=True,timeout=300)
    subprocess.run(['scp','ubuntu-gpu:'+REMOTE+'/app/artifacts/stage14/mask-recovery/linux-negative-worker-receipts.json',str(OUT)],check=True,timeout=90)
    code='import pathlib,json,hashlib; r=pathlib.Path('+repr(REMOTE+'/app/artifacts/stage14/mask-recovery')+'); files=list((r/"linux-source").rglob("*"))+[r/"linux-negative-worker-receipts.json"];print(json.dumps({p.relative_to(r).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in files if p.is_file()}))'
    hashes=json.loads(remote(PY+' -B -c '+shlex.quote(code),120).stdout);assert all(sha(OUT/n)==v for n,v in hashes.items())
    (OUT/'artifact-readback.json').write_text(json.dumps({'all_hashes_match':True,'files':hashes},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'copied_source_files':len(actual),'readback_files':len(hashes),'all_hashes_match':True,'gpu_calls':0}))
if __name__=='__main__':main()
