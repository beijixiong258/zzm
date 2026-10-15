"""Install exact candidate code only; do not reload services or promote website."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,pwd,shutil,subprocess,re
STAGE=Path('/home/adminz/llm/operations/stage14-worker-r6')
EXPECTED={'worker/manifest.json': '94ea45b81979ad6902dc8269688af7e2e102fdf3abf6a617bb0d69bc800e43d7', 'scheduler-runtime/manifest.json': '440290e12ff9fc4237d4445cf4416697eb8e7187b9c311e5825c0c3f7fc137fb', 'install_worker_candidate.py': '0551adc8ea7c466471e487f37e0b546a80af86af0ba64fd4dd38f06c1cd4444c', 'cpu_install_check.py': '6ef56465c2b223bf4eb0c6f16e2d5ef46235f6c5f45c540080ff5522f962b1f2', 'worker/mask_install_check.py': '5ed006d849bff4421f4b261c1658e97ba07eb60a99eef4cfe209f411826784fd', 'worker/mask-base.bin': '2871e8682de9887630d75d73207df3237a25796a304512f20eeeba58f06393c3', 'worker/mask-alpha.bin': '5d37c73a3305f82f727c00f6f090fc9b9884edb2d58e674e32697ba9eb2b7c25'}
BASE=Path('/opt/aicademiya-documents');RELEASE=BASE/'releases/stage14-materials-r6'
QA=BASE/'qa/stage14-parser-install-r6';PY=BASE/'runtime/.venv/bin/python'
SCHED=Path('/opt/aicademiya-gpu-scheduler/releases/stage14-runtime-r2')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def inventory():return subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid','--format=csv,noheader,nounits'],text=True).splitlines()
def main():
 assert os.geteuid()==0,'Use the separate sudo terminal.'
 os.umask(0o022)
 for n,h in EXPECTED.items():assert sha(STAGE/n)==h,n
 assert not RELEASE.exists() and not QA.exists() and not SCHED.exists(),'Inspect existing/partial install, do not overwrite.'
 user=pwd.getpwnam('aicademiya-docs');assert user.pw_uid==999
 for d in Path('/proc').iterdir():
  if not d.name.isdigit():continue
  try:
   if d.stat().st_uid==999:assert b'document_worker_service.py'not in(d/'cmdline').read_bytes(),'An existing document task is active'
  except (FileNotFoundError,ProcessLookupError,PermissionError):pass
 before=inventory();QA.mkdir(parents=True,mode=0o755)
 result={'status':'running','services_reloaded':False,'website_promoted':False,'gpu_before':before,'steps':[]}
 try:
  subprocess.run(['/usr/bin/python3',str(STAGE/'install_worker_candidate.py'),'--source',str(STAGE/'worker'),'--manifest-sha256',EXPECTED['worker/manifest.json'],'--public-key',str(STAGE/'worker/ct255-worker.pub'),'--replace-bound-release','stage14-materials-r5'],check=True)
  result['steps'].append('immutable_worker_r6_installed_and_QA_key_bound')
  for src,dst in [('cpu_install_check.py','cpu_install_check.py'),('worker/mask_install_check.py','mask_install_check.py'),('worker/mask-base.bin','mask-base.bin'),('worker/mask-alpha.bin','mask-alpha.bin')]:
   shutil.copyfile(STAGE/src,QA/dst);(QA/dst).chmod(0o644);assert sha(QA/dst)==EXPECTED[src]
  env=['runuser','-u',user.pw_name,'--','env','CUDA_VISIBLE_DEVICES=','PYTHONDONTWRITEBYTECODE=1','LD_LIBRARY_PATH='+str(BASE/'shared/native-libs/usr/lib/x86_64-linux-gnu'),str(PY),'-B']
  commands=[('cpu-uid999',env+[str(QA/'cpu_install_check.py'),'--expected-uid','999','--models',str(BASE/'shared/rapidocr-models-stage14'),'--parser-dir',str(RELEASE/'material_stage13')]),('mask-uid999',env+[str(QA/'mask_install_check.py'),'--release',str(RELEASE),'--qa',str(QA)])]
  for label,command in commands:
   run=subprocess.run(command,capture_output=True,text=True);(QA/(label+'.log')).write_text(run.stdout+run.stderr);assert run.returncode==0,label
   receipt=json.loads(run.stdout);assert receipt['status']=='passed'and receipt['uid']==999
   (QA/(label+'.json')).write_text(json.dumps(receipt,indent=2)+'\n');result['steps'].append(label+'_passed')
  manifest=json.loads((STAGE/'scheduler-runtime/manifest.json').read_text());assert manifest['release']=='stage14-runtime-r2'
  assert len(manifest['files'])==10
  SCHED.mkdir(parents=True,mode=0o755)
  for name,record in manifest['files'].items():
   assert re.fullmatch('[a-z_]+[.]py',name);source=STAGE/'scheduler-runtime'/name;assert sha(source)==record['sha256'];shutil.copyfile(source,SCHED/name);(SCHED/name).chmod(0o644);assert sha(SCHED/name)==record['sha256']
  shutil.copyfile(STAGE/'scheduler-runtime/manifest.json',SCHED/'manifest.json');(SCHED/'manifest.json').chmod(0o644)
  result['steps'].append('same_live_scheduler_bytes_staged_immutable_NOT_activated')
  result['gpu_after']=inventory();assert sorted(before)==sorted(result['gpu_after']),'Concurrent GPU process change requires independent inspection'
  result.update(status='installed_uid999_cpu_verified',worker_release=str(RELEASE),scheduler_staged=str(SCHED),semantic_accepted=False)
 except BaseException as e:result.update(status='failed',error_type=type(e).__name__,error=str(e));raise
 finally:
  result['completed_at']=datetime.now(timezone.utc).isoformat();(QA/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
