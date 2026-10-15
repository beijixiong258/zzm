"""Install Stage16 document-worker code, CPU-check as UID999, then rebind only
its existing restricted CT key. No model/router/site restart or weight copy.
Owner runs this through a masked sudo terminal after the real CPU format gate.
"""
from pathlib import Path
import argparse,hashlib,json,os,pwd,re,shlex,subprocess,sys

STAGE=Path('/home/adminz/llm/operations/stage16-worker-r1')
BASE=Path('/opt/aicademiya-documents');RELEASE=BASE/'releases/stage16-materials-r1'
OLD=BASE/'releases/stage15-materials-r1/tools/document_stage12/document_worker_service.py'
NEW=RELEASE/'tools/document_stage12/document_worker_service.py'
PY=BASE/'runtime/.venv/bin/python';QA=BASE/'qa/stage16-install-r1'
FILES={'tools/document_stage12/'+n for n in ['document_worker_service.py','parser_worker.py','parser_helpers.py','gpu_lease.py','page_vision_runtime.py']}
FILES|={'tools/material_stage13/'+n for n in ['parse_material.py','prepared_material.py','simple_material.py','source_text.py','office_inventory.py','archive_guard.py','ocr_verification.py']}
FILES|={'tools/material_stage15/'+n for n in ['__init__.py','adapter.py','prepared.py','provenance.py','page_worker.py']}
FILES|={'tools/material_stage16/'+n for n in ['workbook_inventory.py','workbook_material.py','legacy_office.py','workbook_supplements.py']}
def sha(p):
 with Path(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def gpu():return subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid','--format=csv,noheader,nounits'],text=True).splitlines()
def main():
 p=argparse.ArgumentParser();p.add_argument('--manifest-sha256',required=True);a=p.parse_args()
 assert os.geteuid()==0 and re.fullmatch('[0-9a-f]{64}',a.manifest_sha256)
 assert sha(STAGE/'manifest.json')==a.manifest_sha256
 m=json.loads((STAGE/'manifest.json').read_text());assert set(m['files'])==FILES and len(FILES)==21
 assert not RELEASE.exists() and not QA.exists(),'Inspect a partial/existing install before retrying'
 user=pwd.getpwnam('aicademiya-docs');assert user.pw_uid==999
 assert PY.is_file()and Path('/usr/lib/libreoffice/program/libscfiltlo.so').is_file(),'Calc filter required'
 for proc in Path('/proc').iterdir():
  if not proc.name.isdigit():continue
  try:
   if proc.stat().st_uid==user.pw_uid and b'document_worker_service.py'in(proc/'cmdline').read_bytes():raise RuntimeError('Existing document job active; leave it untouched')
  except(FileNotFoundError,ProcessLookupError,PermissionError):pass
 public=(STAGE/'ct-worker.pub').read_text().strip();assert sha(STAGE/'ct-worker.pub')==m['public_key_sha256']
 assert re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/=]+(?: [^\r\n]+)?',public)
 auth=Path(user.pw_dir)/'.ssh/authorized_keys';old=auth.read_text();lines=old.splitlines(keepends=True);marker=' '.join(public.split()[:2]);matching=[i for i,line in enumerate(lines)if marker in line];assert len(matching)==1
 index=matching[0];line=lines[index];assert str(OLD)+' --stdio'in line and line.count(str(OLD))==1
 command=re.search(r'command="([^"]+)"',line);assert command
 argv=shlex.split(command[1]);env_values={x.split('=',1)[0]:x.split('=',1)[1]for x in argv if x.startswith('AICADEMIYA_')and'='in x}
 profile=env_values['AICADEMIYA_DOCUMENT_VISION_PROFILE'];profile_hash=env_values['AICADEMIYA_DOCUMENT_VISION_PROFILE_SHA256'];assert sha(profile)==profile_hash
 for name,row in m['files'].items():
  src=STAGE/'worker'/name;assert src.is_file()and not src.is_symlink()and sha(src)==row['sha256'];compile(src.read_bytes(),name,'exec')
 before=gpu();result={'status':'running','before_allocations':before,'release':str(RELEASE),'worker_files':len(FILES),'models_restarted':False,'website_changed':False,'active_binding_changed':False}
 changed=None
 try:
  RELEASE.mkdir(mode=0o755)
  for name,row in m['files'].items():
   dest=RELEASE/name;dest.parent.mkdir(parents=True,exist_ok=True,mode=0o755);dest.write_bytes((STAGE/'worker'/name).read_bytes());dest.chmod(0o644);assert sha(dest)==row['sha256']
  (RELEASE/'manifest.json').write_bytes((STAGE/'manifest.json').read_bytes())
  (RELEASE/'authorized_keys.before').write_text(old);(RELEASE/'authorized_keys.before').chmod(0o600)
  QA.mkdir(mode=0o700);os.chown(QA,user.pw_uid,user.pw_gid);(QA/'tmp').mkdir(mode=0o700);os.chown(QA/'tmp',user.pw_uid,user.pw_gid)
  text='SYNTHETIC Stage16 native check. Literal symbols: x² ≥ 16; blank _____.\n'
  (QA/'native.txt').write_text(text,encoding='utf-8');os.chown(QA/'native.txt',user.pw_uid,user.pw_gid)
  (QA/'native.xlsx').write_bytes((STAGE/'native.xlsx').read_bytes());assert sha(QA/'native.xlsx')==m['xlsx_sha256'];os.chown(QA/'native.xlsx',user.pw_uid,user.pw_gid)
  env=['runuser','-u',user.pw_name,'--','env','CUDA_VISIBLE_DEVICES=','HF_HUB_OFFLINE=1','PYTHONDONTWRITEBYTECODE=1','PYTHONPATH='+str(RELEASE),'TMPDIR='+str(QA/'tmp')]
  code="import sys;sys.path[:0]="+repr([str(RELEASE),str(RELEASE/'tools/document_stage12'),str(RELEASE/'tools/material_stage13')])+";from page_vision_runtime import fixed_vision_profile;from tools.material_stage16 import workbook_material;fixed_vision_profile("+repr(profile)+','+repr(profile_hash)+");print('UID999 candidate imports and unchanged pinned profile verified')"
  r=subprocess.run(env+[str(PY),'-B','-c',code],capture_output=True,text=True,timeout=40);(QA/'imports.log').write_text(r.stdout+r.stderr);assert r.returncode==0,'UID999 imports/profile check failed'
  checks=[]
  for fmt in ('txt','xlsx'):
   out=QA/('bundle-'+fmt);args=[str(PY),'-B',str(RELEASE/'tools/material_stage13/parse_material.py'),'--input',str(QA/('native.'+fmt)),'--output',str(out),'--engine','native','--deadline-seconds','180']
   r=subprocess.run(env+args,capture_output=True,text=True,timeout=200);(QA/(fmt+'.log')).write_text(r.stdout+r.stderr);assert r.returncode==0,fmt+' CPU parser failed'
   manifest=json.loads((out/'manifest.json').read_text());assert manifest['complete']and manifest['source_sha256']==sha(QA/('native.'+fmt))
   if fmt=='txt':assert ''.join(b['text']for p in manifest['pages']for b in p['blocks'])==text
   checks.append({'format':fmt,'uid':user.pw_uid,'page_count':manifest['page_count'],'source_sha256':manifest['source_sha256'],'engine':'native'})
  result['cpu_checks']=checks
  assert auth.read_text()==old,'Restricted key bindings changed concurrently'
  lines[index]=line.replace(str(OLD),str(NEW));changed=''.join(lines)
  temp=auth.with_name('authorized_keys.stage16');assert not temp.exists();temp.write_text(changed);temp.chmod(0o600);os.chown(temp,user.pw_uid,user.pw_gid);os.replace(temp,auth);assert auth.read_text()==changed
  result['active_binding_changed']=True
  after=gpu();assert sorted(before)==sorted(after),'GPU allocations changed during CPU install; inspect before proceeding'
  assert sha(profile)==profile_hash and all(sha(RELEASE/name)==v['sha256']for name,v in m['files'].items())
  result.update(status='installed_cpu_verified_pending_app_worker_acceptance',after_allocations=after,pinned_profile_unchanged=True,source_manifest_sha256=a.manifest_sha256)
 except BaseException as exc:
  result.update(status='failed',error_type=type(exc).__name__,error=str(exc))
  if changed is not None and auth.read_text()==changed:
   temp=auth.with_name('authorized_keys.stage16-rollback');assert not temp.exists();temp.write_text(old);temp.chmod(0o600);os.chown(temp,user.pw_uid,user.pw_gid);os.replace(temp,auth);result['binding_rolled_back']=auth.read_text()==old
  raise
 finally:
  if QA.exists():(QA/'result.json').write_text(json.dumps(result,indent=2)+'\n');(QA/'result.json').chmod(0o644)
  (STAGE/'install-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
if __name__=='__main__':main()
