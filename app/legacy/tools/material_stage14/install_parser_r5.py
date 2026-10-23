"""Parent-controlled narrow r5 installation. No services, GPU allocation or app cutover."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib,json,os,pwd,shutil,subprocess
STAGE=Path('/home/adminz/llm/operations/stage14-worker-r5')
PAYLOAD=Path('/home/adminz/llm/ocr-stage1-20261009/stage14-parser-integration')
BASE=Path('/opt/aicademiya-documents')
VENV=BASE/'runtime/.venv';MODELS=BASE/'shared/rapidocr-models-stage14'
RELEASE=BASE/'releases/stage14-materials-r5';QA=BASE/'qa/stage14-parser-install-r5'
EXPECTED={'/home/adminz/llm/operations/stage14-worker-r5/worker/manifest.json': 'af0638ababb0af5b0512b941c4d0edc315742db54fc755fdd38b8e8ef32623ea', '/home/adminz/llm/operations/stage14-worker-r5/install_worker_candidate.py': '0551adc8ea7c466471e487f37e0b546a80af86af0ba64fd4dd38f06c1cd4444c', '/home/adminz/llm/ocr-stage1-20261009/stage14-parser-integration/dependency-manifest.json': 'efec41811708dd11bcd9c4ae6fd12aac11295efc4bc8876ae29440abda2148a8', '/home/adminz/llm/ocr-stage1-20261009/stage14-parser-integration/requirements-offline.txt': '26f817f984f360c6422dd3860de303d69485eb20678f1800e129d18378024ef8', '/home/adminz/llm/ocr-stage1-20261009/stage14-parser-integration/code/dependency_install.py': 'c88518d7ff5c9b19764ad63bc6903c2ac8196e46e118402adc0d08f76285bfdd', '/home/adminz/llm/ocr-stage1-20261009/stage14-parser-integration/code/cpu_install_check.py': '6ef56465c2b223bf4eb0c6f16e2d5ef46235f6c5f45c540080ff5522f962b1f2', '/home/adminz/llm/ocr-stage1-20261009/stage14-parser-integration/code/ocr_verification.py': '6702a8d2b639be9ef997146fd17c4a5c91882acd6cffb42c89d22b13dd664665'}

def verify():
 for path,wanted in EXPECTED.items():
  p=Path(path);assert p.is_file() and not p.is_symlink() and hashlib.sha256(p.read_bytes()).hexdigest()==wanted,str(p)
 assert not MODELS.exists() and not RELEASE.exists() and not QA.exists(),'Inspect partial/existing install instead of repeating it'
 assert pwd.getpwnam('aicademiya-docs').pw_uid==999
 # No concurrent document task may observe a partially installed CPU environment.
 running=[]
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:
   if p.stat().st_uid==999 and b'document_worker_service.py' in (p/'cmdline').read_bytes():running.append(int(p.name))
  except (FileNotFoundError,ProcessLookupError,PermissionError):pass
 assert not running,('Document worker is active',running)

def allocations():
 return subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid','--format=csv,noheader,nounits'],text=True).splitlines()

def main():
 if os.geteuid()!=0:raise SystemExit('Use sudo in the separate masked terminal.')
 verify();before=allocations();QA.mkdir(parents=True,mode=0o755)
 report={'status':'running','services_changed':False,'website_promoted':False,'gpu_before':before,'steps':[]}
 try:
  install=[str(VENV/'bin/python'),'-B',str(PAYLOAD/'code/dependency_install.py'),'--payload',str(PAYLOAD),'--venv',str(VENV),'--models-target',str(MODELS)]
  subprocess.run(install,check=True)
  with (QA/'dependencies.log').open('w') as log:subprocess.run(install+['--install'],check=True,stdout=log,stderr=subprocess.STDOUT)
  report['steps'].append('offline_cpu_dependencies_installed')
  subprocess.run(['/usr/bin/python3',str(STAGE/'install_worker_candidate.py'),'--source',str(STAGE/'worker'),'--manifest-sha256','af0638ababb0af5b0512b941c4d0edc315742db54fc755fdd38b8e8ef32623ea','--public-key',str(STAGE/'worker/ct255-worker.pub'),'--replace-bound-release','stage14-materials-r4'],check=True)
  report['steps'].append('new_candidate_installed_and_qa_key_bound')
  check=QA/'cpu_install_check.py';shutil.copyfile(PAYLOAD/'code/cpu_install_check.py',check);check.chmod(0o644)
  command=['runuser','-u','aicademiya-docs','--','env','CUDA_VISIBLE_DEVICES=','PYTHONDONTWRITEBYTECODE=1','LD_LIBRARY_PATH='+str(BASE/'shared/native-libs/usr/lib/x86_64-linux-gnu'),str(VENV/'bin/python'),'-B',str(check),'--expected-uid','999','--models',str(MODELS),'--parser-dir',str(RELEASE/'material_stage13')]
  result=subprocess.run(command,text=True,capture_output=True);(QA/'cpu-uid999.log').write_text(result.stdout+result.stderr)
  if result.returncode:raise RuntimeError('UID999 CPU acceptance failed; see retained private QA log')
  cpu=json.loads(result.stdout);assert cpu['status']=='passed' and cpu['uid']==999 and cpu['exact_groundtruth_agreement']
  (QA/'cpu-uid999.json').write_text(json.dumps(cpu,indent=2)+'\n')
  report['steps'].append('installed_uid999_cpu_provider_and_exact_groundtruth_passed')
  report['gpu_after']=allocations();assert sorted(before)==sorted(report['gpu_after']),'Concurrent allocation changed; inspect independently'
  report['status']='installed_cpu_verified_not_semantic_acceptance'
 except BaseException as e:
  report.update(status='failed',error_type=type(e).__name__,error=str(e));raise
 finally:
  report['completed_at']=datetime.now(timezone.utc).isoformat();(QA/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
