"""Stage a verified stage4 release in CT255; never switch production."""
from pathlib import Path
import argparse,json,re,shlex,subprocess
ROOT=Path(__file__).resolve().parents[1]
KEY='C:/Users/17193/.ssh/id_ed25519_aicademiya_pve'
HOST='root@192.168.10.16'
SSH=['ssh','-i',KEY,'-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8',HOST]
SCP=['scp','-i',KEY,'-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes']
def remote(args,timeout=90,input=None):
 r=subprocess.run(SSH+[shlex.join(args)],input=input,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout)
 if r.returncode:raise RuntimeError(r.stderr or r.stdout)
 return r.stdout.strip()
def guest(args,**kwargs):return remote(['pct','exec','255','--']+args,**kwargs)
DEPENDENCIES=r'''
from pathlib import Path
import hashlib,importlib.metadata,json,os,shutil,socket,subprocess,sys
assert socket.gethostname()=='aicademiya-v2'
release,incoming=map(Path,sys.argv[1:]);old=Path('/opt/aicademiya/current').resolve()
assert old!=release and old.is_dir() and release.is_dir()
assert (old/'backend/requirements.txt').read_bytes()==(release/'backend/requirements.txt').read_bytes(),'Changed requirements; do not reuse dependencies'
def run(args):return subprocess.check_output([str(x) for x in args],text=True).strip()
subprocess.run(['python3','-m','venv',str(release/'.venv')],check=True)
source=Path(run([old/'.venv/bin/python','-c','import sysconfig;print(sysconfig.get_path("purelib"))'])).resolve()
target=Path(run([release/'.venv/bin/python','-c','import sysconfig;print(sysconfig.get_path("purelib"))'])).resolve()
assert source.is_relative_to(old/'.venv') and target.is_relative_to(release/'.venv')
assert run([old/'.venv/bin/python','-c','import sys;print(sys.version_info[:2])'])==run([release/'.venv/bin/python','-c','import sys;print(sys.version_info[:2])'])
assert not any(p.is_symlink() for p in source.rglob('*')) and not list(source.glob('*.pth'))
assert {p['name'] for p in json.loads(run([release/'.venv/bin/python','-m','pip','list','--format=json']))}=={'pip'}
bootstrap=target.with_name('site-packages-bootstrap');assert not bootstrap.exists();target.rename(bootstrap)
shutil.copytree(source,target,copy_function=shutil.copy2)
count=lambda root:sum(p.is_file() for p in root.rglob('*'))
assert count(source)==count(target)
check=run([release/'.venv/bin/python','-m','pip','check'])
probe="""import importlib.metadata as m,json
from pathlib import Path
from packaging.requirements import Requirement
import fastapi,uvicorn,httpx,pydantic,multipart,pymupdf,docx,pptx,openpyxl,rapidocr,onnxruntime,bs4
from backend.aicademiya.materials import extract_document
from backend.aicademiya.material_library import migrate_material_library
requirements=[Requirement(l) for l in Path('backend/requirements.txt').read_text().splitlines() if l.strip() and not l.startswith('#')]
for req in requirements:assert req.specifier.contains(m.version(req.name)),str(req)
weights=Path(rapidocr.__file__).parent/'models'
assert all((weights/n).is_file() for n in ('PP-OCRv6_det_small.onnx','ch_ppocr_mobile_v2.0_cls_mobile.onnx','PP-OCRv6_rec_small.onnx'))
print(json.dumps({'requirements':len(requirements),'imports':'ok','cpu_ocr_weights':'present'}))
"""
verified=json.loads(subprocess.check_output([str(release/'.venv/bin/python'),'-c',probe],cwd=release,text=True))
subprocess.run(['chown','-R','root:aicademiya',str(release)],check=True);subprocess.run(['chmod','-R','g+rX',str(release)],check=True)
m=json.loads((incoming/(release.name+'.manifest.json')).read_text())
bad=[n for n,i in m['files'].items() if hashlib.sha256((release/n).read_bytes()).hexdigest()!=i['sha256']];assert not bad,bad
assert Path('/opt/aicademiya/current').resolve()==old and run(['systemctl','is-active','aicademiya.service'])=='active'
result={'status':'staged','target':str(release),'previous_release':str(old),'dependency_method':'new Linux venv + physical copy of same-host identical-requirement packages; no old-prefix links','dependency_file_count':count(target),'pip_check':check,**verified,'installed_manifest_files':len(m['files']),'production_switched':False,'production_service_active':True}
(incoming/'stage-result.json').write_text(json.dumps(result,indent=2));os.chmod(incoming/'stage-result.json',0o600)
print(json.dumps(result))
'''
def main():
 p=argparse.ArgumentParser();p.add_argument('--manifest',required=True);a=p.parse_args()
 manifest=Path(a.manifest).resolve();m=json.loads(manifest.read_text());release=m['release']
 assert re.fullmatch(r'AIcademiya_V2-[A-Za-z0-9._-]+',release)
 incoming='/root/aicademiya-stage4-incoming/'+release;target='/opt/aicademiya/releases/'+release
 assert guest(['hostname'])=='aicademiya-v2'
 before=guest(['readlink','-f','/opt/aicademiya/current']);assert before!=target
 assert guest(['systemctl','is-active','aicademiya.service'])=='active'
 for run in (remote,guest):run(['python3','-c',f'from pathlib import Path;Path({incoming!r}).mkdir(parents=True,mode=0o700,exist_ok=False)'])
 files=[manifest.parent/x['name'] for x in m['archives'].values()]+[manifest,manifest.parent/(release+'.sha256'),ROOT/'tools/build_v2_release.py']
 for f in files:
  subprocess.run(SCP+[str(f),HOST+':'+incoming+'/'+f.name],check=True,capture_output=True,timeout=120)
  remote(['pct','push','255',incoming+'/'+f.name,incoming+'/'+f.name,'--perms','0600'])
 verify=['python3',incoming+'/build_v2_release.py','verify','--manifest',incoming+'/'+manifest.name]
 pve=json.loads(remote(verify));stage='/opt/aicademiya/stage4-extract-'+release
 installed=json.loads(guest(verify+['--extract-to',stage]))
 guest(['python3','-c',f'from pathlib import Path;p=Path({target!r});assert not p.exists();Path({(stage+"/"+release)!r}).rename(p)'])
 deps=json.loads(guest(['python3','-',target,incoming],input=DEPENDENCIES,timeout=240))
 assert guest(['readlink','-f','/opt/aicademiya/current'])==before
 report={**deps,'pve_archive':pve,'guest_archive':installed,'production_link_unchanged':True}
 output=manifest.parent/'ct255-stage-result.json';output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'status':report['status'],'report':str(output),'target':target,'installed_manifest_files':report['installed_manifest_files'],'production_switched':False},indent=2))
if __name__=='__main__':main()
