"""One-time administrator installation of an isolated SSH document worker.

No new listener/service, no teaching-unit/driver changes. Copies the already
verified offline runtime/models into root-owned /opt and gives a dedicated
unprivileged account only its job directory and a forced-command public key.
"""
from pathlib import Path
import argparse,fcntl,grp,hashlib,json,os,pwd,re,shlex,shutil,subprocess,sys
SOURCE=Path('/home/adminz/llm/ocr-stage1-20261009')
DEST=Path('/opt/aicademiya-documents');RUNTIME=DEST/'runtime';SHARED=DEST/'shared'
USER='aicademiya-docs';HOME=Path('/var/lib/aicademiya-documents')

def prepare_model_locks(account):
 models=RUNTIME/'mineru-home/models';locks=models/'.locks'
 if not models.is_dir()or models.is_symlink()or locks.is_symlink():raise RuntimeError('Unexpected model/lock directory')
 locks.mkdir(mode=0o700,exist_ok=True)
 entries=list(locks.iterdir())
 if any(p.is_symlink()or not p.is_file()or p.suffix!='.lock'for p in entries):raise RuntimeError('Unexpected entries in model lock cache')
 os.chown(locks,account.pw_uid,account.pw_gid);os.chmod(locks,0o700)
 for path in entries:os.chown(path,account.pw_uid,account.pw_gid);os.chmod(path,0o600)
 test="from pathlib import Path;from filelock import FileLock;import os;p=Path("+repr(str(locks/'MinerU-4_models_onnx.lock'))+");f=FileLock(str(p));f.acquire(timeout=2);f.release();weights=Path("+repr(str(models/'MinerU2.5-Pro-2605-1.2B-GGUF'))+");assert not os.access(weights,os.W_OK);assert all(not os.access(x,os.W_OK)for x in weights.glob('*.gguf'));print('lock_write_verified_weights_read_only')"
 subprocess.run(['runuser','-u',USER,'--',str(RUNTIME/'.venv/bin/python'),'-c',test],check=True)

def main():
 p=argparse.ArgumentParser();p.add_argument('--public-key',required=True);p.add_argument('--gpu-uuid',default='');p.add_argument('--repair-model-locks',action='store_true');a=p.parse_args()
 if os.geteuid()!=0:raise SystemExit('Run this one-time installer with sudo; do not send a password to the assistant.')
 if a.gpu_uuid and not re.fullmatch(r'GPU-[0-9a-fA-F-]{36}',a.gpu_uuid):raise ValueError('Invalid GPU UUID')
 lock=None
 if (HOME/'serial.lock').exists():
  lock=(HOME/'serial.lock').open('r');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 public=Path(a.public_key).read_text().strip()
 if not re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/=]+(?: [^\r\n]+)?',public):raise ValueError('Expected one Ed25519 public key')
 try:
  account=pwd.getpwnam(USER)
  if account.pw_dir!=str(HOME)or account.pw_shell!='/bin/sh':raise RuntimeError('Existing account has a different purpose; no changes made')
 except KeyError:
  if a.repair_model_locks:raise RuntimeError('Worker must already be installed for lock repair')
  subprocess.run(['useradd','--system','--create-home','--home-dir',str(HOME),'--shell','/bin/sh',USER],check=True)
  account=pwd.getpwnam(USER)
 if a.repair_model_locks:
  prepare_model_locks(account)
  result=DEST/'install-result.json';report=json.loads(result.read_text());report['model_lock_permission_verified']=True
  result.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':'model_lock_permissions_repaired','weights_remain_read_only':True}));return
 DEST.mkdir(mode=0o755,exist_ok=True);SHARED.mkdir(mode=0o755,exist_ok=True)
 if not(RUNTIME/'runtime-ready.json').exists():
  if RUNTIME.exists():raise RuntimeError('Incomplete runtime directory exists; inspect it before retrying')
  RUNTIME.mkdir(mode=0o755)
  subprocess.run(['/usr/bin/python3','-m','venv','--without-pip',str(RUNTIME/'.venv')],check=True)
  old=SOURCE/'whole-document-pilot/.venv/lib/python3.12/site-packages'
  site=RUNTIME/'.venv/lib/python3.12/site-packages';shutil.copytree(old,site,dirs_exist_ok=True)
  shutil.copytree(SOURCE/'whole-document-pilot/mineru-home/models',RUNTIME/'mineru-home/models')
  shutil.copytree(SOURCE/'native-libs',SHARED/'native-libs')
  # New venv Python is system-bound, not linked to a cleanup-prone old venv.
  check=subprocess.run([str(RUNTIME/'.venv/bin/python'),'-c','import importlib.metadata as m; import pymupdf, PIL, onnxruntime; print(m.version("mineru"))'],capture_output=True,text=True,check=True)
  if check.stdout.strip()!='4.0.11':raise RuntimeError('Unexpected copied MinerU version')
  (RUNTIME/'runtime-ready.json').write_text(json.dumps({'mineru':'4.0.11','source_runtime':str(old),'copied_not_linked':True})+'\n')
 if a.gpu_uuid:
  cuda=SHARED/'cuda-runtime';cuda_libs=SHARED/'cuda-libs'
  # Copy the exact already-tested offline runtime; do not depend on adminz's home.
  shutil.copytree(SOURCE/'runtime/bin',cuda/'bin',dirs_exist_ok=True)
  cuda_libs.mkdir(parents=True,exist_ok=True)
  for library in ('libcudart.so.12','libcublas.so.12','libcublasLt.so.12'):
   src=Path('/home/adminz/llm/toolchains/cuda-12.8/lib')/library
   target=cuda_libs/library;shutil.copyfile(src,target)
   if hashlib.file_digest(src.open('rb'),'sha256').hexdigest()!=hashlib.file_digest(target.open('rb'),'sha256').hexdigest():raise RuntimeError('CUDA library copy verification failed')
  env=dict(os.environ,LD_LIBRARY_PATH=f'{cuda}/bin:{cuda_libs}',CUDA_VISIBLE_DEVICES=a.gpu_uuid)
  deps=subprocess.run(['ldd',str(cuda/'bin/llama-server')],env=env,capture_output=True,text=True,check=True).stdout
  if 'not found' in deps or '/home/adminz/' in deps:raise RuntimeError('CUDA runtime is not independently relocated')
 code=DEST/'code';code.mkdir(mode=0o755,exist_ok=True)
 names=['document_worker_service.py','parser_worker.py','parser_helpers.py']
 for name in names:
  src=Path(__file__).with_name(name);target=code/name;shutil.copyfile(src,target);os.chmod(target,0o644)
 # Runtime/model/code remain root-owned and readable, never writable by the worker.
 for tree in (RUNTIME,SHARED,code):
  for current,dirs,files in os.walk(tree):
   os.chmod(current,0o755)
   for name in files:
    f=Path(current)/name
    if not f.is_symlink():os.chmod(f,0o755 if os.access(f,os.X_OK)else 0o644)
 prepare_model_locks(account)
 os.chown(HOME,account.pw_uid,account.pw_gid);os.chmod(HOME,0o700)
 ssh=HOME/'.ssh';ssh.mkdir(mode=0o700,exist_ok=True);os.chown(ssh,account.pw_uid,account.pw_gid)
 variables=[f'AICADEMIYA_DOCUMENT_BASE={SHARED}',f'AICADEMIYA_DOCUMENT_RUNTIME={RUNTIME}',f'AICADEMIYA_DOCUMENT_HOME={HOME}']
 if a.gpu_uuid:variables.append(f'AICADEMIYA_DOCUMENT_GPU_UUID={a.gpu_uuid}')
 command=shlex.join(['/usr/bin/env',*variables,str(RUNTIME/'.venv/bin/python'),str(code/'document_worker_service.py'),'--stdio'])
 line='restrict,command="'+command+'" '+public
 authorized=ssh/'authorized_keys';old=authorized.read_text().splitlines()if authorized.exists()else[]
 # Replace this key's old CPU command, rather than appending an ignored duplicate.
 marker=' '.join(public.split()[:2]);kept=[row for row in old if marker not in row]
 authorized.write_text('\n'.join(kept+[line])+'\n')
 os.chmod(authorized,0o600);os.chown(authorized,account.pw_uid,account.pw_gid)
 report={'status':'installed','worker_user':USER,'uid':account.pw_uid,'runtime':str(RUNTIME),'home':str(HOME),'device':'cuda'if a.gpu_uuid else'cpu','gpu_uuid':a.gpu_uuid or None,'no_listener_created':True,'teaching_services_modified':False,'forced_command':command,'code_sha256':{n:hashlib.file_digest((code/n).open('rb'),'sha256').hexdigest()for n in names}}
 (DEST/'install-result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
