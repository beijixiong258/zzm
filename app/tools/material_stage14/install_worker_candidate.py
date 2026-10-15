"""Install an immutable leased-GPU worker candidate and a separate restricted key.
Does not replace Stage12 code/key, restart services or allocate GPUs.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,os,pwd,re,shlex,subprocess
BASE=Path('/opt/aicademiya-documents');USER='aicademiya-docs';HOME=Path('/var/lib/aicademiya-documents')
def main():
 p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--manifest-sha256',required=True);p.add_argument('--public-key',required=True);p.add_argument('--replace-bound-release');a=p.parse_args()
 if os.geteuid()!=0:raise SystemExit('Use the separate sudo terminal; no credentials in commands or chat.')
 source=Path(a.source).resolve();data=(source/'manifest.json').read_bytes();assert hashlib.sha256(data).hexdigest()==a.manifest_sha256
 m=json.loads(data);tag=m['release'];assert re.fullmatch(r'[A-Za-z0-9_-]{1,80}',tag)
 user=pwd.getpwnam(USER);assert user.pw_dir==str(HOME)
 assert (BASE/'runtime/runtime-ready.json').is_file()and(BASE/'shared/cuda-runtime/bin/llama-server').is_file()
 assert Path('/usr/bin/libreoffice').is_file()
 public=Path(a.public_key).read_text().strip();assert re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/=]+(?: [^\r\n]+)?',public)
 files=m['files'];assert 3<=len(files)<=30
 required={'document_stage12/document_worker_service.py','document_stage12/parser_worker.py','document_stage12/parser_helpers.py','document_stage12/gpu_lease.py','material_stage13/parse_material.py','material_stage13/prepared_material.py','material_stage13/simple_material.py','material_stage13/source_text.py','material_stage13/office_inventory.py','material_stage13/archive_guard.py','material_stage13/ocr_verification.py'};assert required==set(files)
 ocr_models=BASE/'shared/rapidocr-models-stage14'
 assert all((ocr_models/n).is_file() and not (ocr_models/n).is_symlink() for n in ('PP-OCRv6_det_small.onnx','PP-OCRv6_rec_small.onnx','ch_ppocr_mobile_v2.0_cls_mobile.onnx')),'Install and verify offline CPU weights before binding the new candidate'
 blobs={}
 for name,info in files.items():
  assert re.fullmatch(r'(?:document_stage12|material_stage13)/[A-Za-z0-9_-]+\.py',name)
  path=source/name;assert not path.is_symlink()and path.resolve().is_relative_to(source)
  blob=path.read_bytes();assert len(blob)<=1024*1024 and hashlib.sha256(blob).hexdigest()==info['sha256'];blobs[name]=blob
 target=BASE/'releases'/tag;target.mkdir(parents=True,exist_ok=False,mode=0o755)
 for name,blob in blobs.items():
  path=target/name;path.parent.mkdir(parents=True,exist_ok=True,mode=0o755);path.write_bytes(blob);os.chmod(path,0o644)
 (target/'manifest.json').write_bytes(data)
 check='from pathlib import Path;import ast;root=Path('+repr(str(target))+');[ast.parse(p.read_text())for p in root.rglob("*.py")];print("candidate_syntax_ok")'
 subprocess.run(['runuser','-u',USER,'--',str(BASE/'runtime/.venv/bin/python'),'-c',check],check=True)
 command=shlex.join(['/usr/bin/env',f'AICADEMIYA_DOCUMENT_BASE={BASE}/shared',f'AICADEMIYA_DOCUMENT_RUNTIME={BASE}/runtime',f'AICADEMIYA_DOCUMENT_HOME={HOME}',f'AICADEMIYA_RAPIDOCR_MODELS={ocr_models}','AICADEMIYA_DOCUMENT_GPU_UUID=GPU-105b82fb-41db-d6a1-13f0-ceddf5bed313','AICADEMIYA_DOCUMENT_GPU_LEASE_SOCKET=/run/aicademiya-gpu/lease.sock','AICADEMIYA_DOCUMENT_GPU_OWNER_UID=1000',str(BASE/'runtime/.venv/bin/python'),str(target/'document_stage12/document_worker_service.py'),'--stdio'])
 auth=HOME/'.ssh/authorized_keys';old=auth.read_text();marker=' '.join(public.split()[:2]);lines=old.splitlines(keepends=True);matches=[i for i,line in enumerate(lines)if marker in line]
 line='restrict,command="'+command+'" '+public+'\n'
 if matches:
  assert a.replace_bound_release and re.fullmatch(r'stage14-materials-r[0-9]+',a.replace_bound_release)and len(matches)==1,'Explicit exact candidate rebind required'
  expected=str(BASE/'releases'/a.replace_bound_release/'document_stage12/document_worker_service.py')+' --stdio'
  assert expected in lines[matches[0]]and 'AICADEMIYA_DOCUMENT_GPU_LEASE_SOCKET=/run/aicademiya-gpu/lease.sock'in lines[matches[0]],'Existing key is not the named leased candidate'
  lines[matches[0]]=line;updated=''.join(lines)
 else:
  assert not a.replace_bound_release;updated=old+(''if old.endswith('\n')else'\n')+line
 backup=target/'authorized_keys.before';backup.write_text(old);backup.chmod(0o600)
 tmp=auth.with_name('authorized_keys.stage14');tmp.write_text(updated);os.chmod(tmp,0o600);os.chown(tmp,user.pw_uid,user.pw_gid);os.replace(tmp,auth)
 report={'status':'candidate_installed','release':tag,'target':str(target),'source_manifest_sha256':a.manifest_sha256,'code_sha256':{n:hashlib.sha256(b).hexdigest()for n,b in blobs.items()},'production_key_or_code_replaced':False,'candidate_key_rebound_from':a.replace_bound_release,'services_restarted':False,'completed_at':datetime.now(timezone.utc).isoformat()}
 (target/'install-result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
