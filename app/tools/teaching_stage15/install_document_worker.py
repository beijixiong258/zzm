"""Install immutable Stage15 document worker + isolated root-owned vision assets.
No teaching/router/site restart and no GPU allocation. Rebind only the existing
QA leased-worker public key after CPU closure checks; preserve all originals.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,os,pwd,re,shlex,shutil,subprocess
STAGE=Path('/home/adminz/llm/operations/stage15-worker-r1')
BASE=Path('/opt/aicademiya-documents');RELEASE=BASE/'releases/stage15-materials-r1'
ASSETS=BASE/'shared/vision-stage15-r1';PROFILE=Path('/etc/aicademiya-documents/vision-stage15-r1.json')
QA=BASE/'qa/stage15-install-r1';PY=BASE/'runtime/.venv/bin/python';HOME=Path('/var/lib/aicademiya-documents')
FILES={
 'tools/document_stage12/'+n for n in ['document_worker_service.py','parser_worker.py','parser_helpers.py','gpu_lease.py','page_vision_runtime.py']}
FILES|={'tools/material_stage13/'+n for n in ['parse_material.py','prepared_material.py','simple_material.py','source_text.py','office_inventory.py','archive_guard.py','ocr_verification.py']}
FILES|={'tools/material_stage15/'+n for n in ['__init__.py','adapter.py','prepared.py','provenance.py','page_worker.py']}
def sha(p):
 with Path(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def inventory():return subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid','--format=csv,noheader,nounits'],text=True).splitlines()
def main():
 p=argparse.ArgumentParser()
 for n in ['package','assets','profile','public-key']:p.add_argument('--'+n+'-sha256',required=True)
 a=p.parse_args();assert os.geteuid()==0,'Use the separate masked sudo terminal';os.umask(0o022)
 for name,h in [('worker-manifest.json',a.package_sha256),('asset-manifest.json',a.assets_sha256),('vision-profile.json',a.profile_sha256),('ct255-worker.pub',a.public_key_sha256)]:assert sha(STAGE/name)==h,name
 assert all(not x.exists()for x in [RELEASE,ASSETS,PROFILE,QA]),'Inspect existing/partial install; never overwrite'
 m=json.loads((STAGE/'worker-manifest.json').read_text());assets=json.loads((STAGE/'asset-manifest.json').read_text());profile=json.loads((STAGE/'vision-profile.json').read_text())
 assert m['release']=='stage15-materials-r1'and set(m['files'])==FILES and assets['target']==str(ASSETS)
 assert sha('/etc/aicademiya-gpu-scheduler/workers-stage15-vision-r1.json')==assets['source_fixed_config_sha256']
 user=pwd.getpwnam('aicademiya-docs');assert user.pw_uid==999 and user.pw_dir==str(HOME)
 assert PY.is_file()and (BASE/'runtime/runtime-ready.json').is_file()
 for proc in Path('/proc').iterdir():
  if not proc.name.isdigit():continue
  try:
   if proc.stat().st_uid==user.pw_uid:assert b'document_worker_service.py'not in(proc/'cmdline').read_bytes(),'An existing document job is active'
  except(FileNotFoundError,ProcessLookupError,PermissionError):pass
 public=(STAGE/'ct255-worker.pub').read_text().strip();assert re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/=]+(?: [^\r\n]+)?',public)
 auth=HOME/'.ssh/authorized_keys';old=auth.read_text();marker=' '.join(public.split()[:2]);lines=old.splitlines(keepends=True);matches=[i for i,line in enumerate(lines)if marker in line];assert len(matches)==1
 old_entry='/opt/aicademiya-documents/releases/stage14-materials-r6/document_stage12/document_worker_service.py --stdio'
 assert old_entry in lines[matches[0]]and 'AICADEMIYA_DOCUMENT_GPU_LEASE_SOCKET=/run/aicademiya-gpu/lease.sock'in lines[matches[0]]
 blobs={}
 for name,row in m['files'].items():
  src=STAGE/'worker'/name;assert not src.is_symlink()and sha(src)==row['sha256'];blob=src.read_bytes();compile(blob,str(src),'exec');blobs[name]=blob
 for name,row in assets['files'].items():
  assert re.fullmatch(r'(?:runtime/(?:bin|lib)/)?[A-Za-z0-9_.-]+',name)and Path(row['source']).is_file()
 before=inventory();QA.mkdir(parents=True,mode=0o755)
 result={'status':'running','website_changed':False,'teaching_restarts_requested':False,'before_allocations':before,'steps':[]}
 try:
  ASSETS.mkdir(mode=0o755)
  for name,row in assets['files'].items():
   dst=ASSETS/name;dst.parent.mkdir(parents=True,exist_ok=True,mode=0o755)
   print('Copying verified existing asset: '+name,flush=True);shutil.copyfile(row['source'],dst);dst.chmod(row['mode']);assert dst.stat().st_size==row['bytes']and sha(dst)==row['sha256'],name
  result['steps'].append('existing_asset_bytes_copied_without_modifying_teaching_originals')
  (ASSETS/'asset-manifest.json').write_bytes((STAGE/'asset-manifest.json').read_bytes())
  RELEASE.mkdir(mode=0o755)
  for name,blob in blobs.items():
   dst=RELEASE/name;dst.parent.mkdir(parents=True,exist_ok=True,mode=0o755);dst.write_bytes(blob);dst.chmod(0o644)
  (RELEASE/'manifest.json').write_bytes((STAGE/'worker-manifest.json').read_bytes())
  PROFILE.parent.mkdir(parents=True,exist_ok=True,mode=0o755);PROFILE.write_bytes((STAGE/'vision-profile.json').read_bytes());PROFILE.chmod(0o644)
  env=['runuser','-u',user.pw_name,'--','env','CUDA_VISIBLE_DEVICES=','PYTHONDONTWRITEBYTECODE=1','PYTHONPATH='+str(RELEASE),'LD_LIBRARY_PATH='+profile['environment']['LD_LIBRARY_PATH'],'AICADEMIYA_RAPIDOCR_MODELS='+str(BASE/'shared/rapidocr-models-stage14')]
  check="from pathlib import Path;import os,sys;sys.path[:0]="+repr([str(RELEASE),str(RELEASE/'tools/document_stage12'),str(RELEASE/'tools/material_stage13')])+";from tools.material_stage15 import page_worker;from page_vision_runtime import fixed_vision_profile;p=fixed_vision_profile("+repr(str(PROFILE))+','+repr(a.profile_sha256)+");assert p['context_size']==8192;root=Path("+repr(str(ASSETS))+");assert all(not os.access(f,os.W_OK)for f in root.rglob('*')if f.is_file());assert not os.access(root,os.W_OK);print('uid999_tools_imports_profile_and_readonly_assets_passed')"
  commands=[('imports',env+[str(PY),'-B','-c',check]),('ldd',env+['/usr/bin/ldd',str(ASSETS/'runtime/bin/llama-server')]),('version',env+[str(ASSETS/'runtime/bin/llama-server'),'--version']),('cpu-ocr',env+[str(PY),'-B',str(BASE/'qa/stage14-parser-install-r6/cpu_install_check.py'),'--expected-uid','999','--models',str(BASE/'shared/rapidocr-models-stage14'),'--parser-dir',str(RELEASE/'tools/material_stage13')])]
  for label,command in commands:
   r=subprocess.run(command,capture_output=True,text=True,timeout=180);(QA/(label+'.log')).write_text(r.stdout+r.stderr);assert r.returncode==0,label+' CPU closure failed; retained log'
   if label=='ldd':assert 'not found'not in r.stdout and '/home/adminz/'not in r.stdout,'Runtime still resolves to operator build paths'
   result['steps'].append(label+'_passed_as_uid999_no_GPU')
  assert all(sha(RELEASE/name)==row['sha256']for name,row in m['files'].items())
  (RELEASE/'authorized_keys.before').write_text(old);(RELEASE/'authorized_keys.before').chmod(0o600)
  command=shlex.join(['/usr/bin/env',f'AICADEMIYA_DOCUMENT_BASE={BASE}/shared',f'AICADEMIYA_DOCUMENT_RUNTIME={BASE}/runtime',f'AICADEMIYA_DOCUMENT_HOME={HOME}',f'AICADEMIYA_RAPIDOCR_MODELS={BASE}/shared/rapidocr-models-stage14','AICADEMIYA_DOCUMENT_GPU_UUID=GPU-105b82fb-41db-d6a1-13f0-ceddf5bed313','AICADEMIYA_DOCUMENT_GPU_LEASE_SOCKET=/run/aicademiya-gpu/lease.sock','AICADEMIYA_DOCUMENT_GPU_OWNER_UID=1000',f'AICADEMIYA_DOCUMENT_VISION_PROFILE={PROFILE}',f'AICADEMIYA_DOCUMENT_VISION_PROFILE_SHA256={a.profile_sha256}',str(PY),str(RELEASE/'tools/document_stage12/document_worker_service.py'),'--stdio'])
  assert auth.read_text()==old,'Authorized key file changed during staging'
  lines[matches[0]]='restrict,command="'+command+'" '+public+'\n';updated=''.join(lines);tmp=auth.with_name('authorized_keys.stage15');assert not tmp.exists();tmp.write_text(updated);tmp.chmod(0o600);os.chown(tmp,user.pw_uid,user.pw_gid);os.replace(tmp,auth);assert auth.read_text()==updated
  result['steps'].append('only_existing_QA_lease_key_rebound_from_r6')
  after=inventory();assert sorted(before)==sorted(after),'Concurrent GPU PID change requires inspection'
  result.update(status='installed_cpu_verified_not_live_accepted',release=str(RELEASE),assets=str(ASSETS),profile=str(PROFILE),worker_files_verified=len(blobs),asset_files_verified=len(assets['files']),after_allocations=after,source_manifest_sha256=a.package_sha256,asset_manifest_sha256=a.assets_sha256,profile_sha256=a.profile_sha256,site_gate_unchanged=True)
 except BaseException as e:result.update(status='failed',error_type=type(e).__name__,error=str(e));raise
 finally:
  result['completed_at']=datetime.now(timezone.utc).isoformat();(QA/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
if __name__=='__main__':main()
