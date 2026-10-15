"""Stage a verified stage-3 release on CT255 without switching production."""
from pathlib import Path
import json,shlex,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
RELEASE='AIcademiya_V2-20261007-guided'
OUT=ROOT/'artifacts/stage3/release-guided'
MANIFEST=OUT/(RELEASE+'.manifest.json')
KEY='C:/Users/17193/.ssh/id_ed25519_aicademiya_pve'
HOST='root@192.168.10.16'
SSH=['ssh','-i',KEY,'-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8',HOST]
SCP=['scp','-i',KEY,'-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes']
INCOMING='/root/aicademiya-stage3-incoming/'+RELEASE
TARGET='/opt/aicademiya/releases/'+RELEASE

def remote(args,timeout=60):
 r=subprocess.run(SSH+[shlex.join(args)],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout)
 if r.returncode:raise RuntimeError(r.stderr or r.stdout)
 return r.stdout.strip()
def guest(args,timeout=60):return remote(['pct','exec','255','--']+args,timeout)
def main():
 m=json.loads(MANIFEST.read_text(encoding='utf-8'));assert m['release']==RELEASE
 report={'status':'staging','release':RELEASE,'target':TARGET,'production_switched':False}
 assert guest(['hostname'])=='aicademiya-v2'
 old=guest(['readlink','-f','/opt/aicademiya/current']);report['previous_release']=old
 assert old.startswith('/opt/aicademiya/releases/') and old!=TARGET
 assert guest(['systemctl','is-active','aicademiya.service'])=='active'
 remote(['python3','-c',f"from pathlib import Path;p=Path({INCOMING!r});p.mkdir(parents=True,mode=0o700,exist_ok=False)"])
 files=[OUT/x['name'] for x in m['archives'].values()]+[MANIFEST,OUT/(RELEASE+'.sha256'),ROOT/'tools/build_v2_release.py']
 for f in files:
  subprocess.run(SCP+[str(f),HOST+':'+INCOMING+'/'+f.name],check=True,capture_output=True,timeout=120)
 report['pve_archive_verification']=json.loads(remote(['python3',INCOMING+'/build_v2_release.py','verify','--manifest',INCOMING+'/'+MANIFEST.name]))
 guest(['python3','-c',f"from pathlib import Path;p=Path({INCOMING!r});p.mkdir(parents=True,mode=0o700,exist_ok=False)"])
 for f in files:remote(['pct','push','255',INCOMING+'/'+f.name,INCOMING+'/'+f.name,'--perms','0600'])
 staging='/opt/aicademiya/stage3-extract-'+RELEASE
 report['guest_archive_verification']=json.loads(guest(['python3',INCOMING+'/build_v2_release.py','verify','--manifest',INCOMING+'/'+MANIFEST.name,'--extract-to',staging]))
 guest(['python3','-c',f"from pathlib import Path;p=Path({TARGET!r});assert not p.exists();Path({(staging+'/'+RELEASE)!r}).rename(p)"])
 guest(['python3','-m','venv',TARGET+'/.venv'],timeout=120)
 pins=INCOMING+'/runtime-pins.txt'
 guest(['python3','-c',f"import subprocess;f=open({pins!r},'w');subprocess.run([{(old+'/.venv/bin/python')!r},'-m','pip','freeze'],stdout=f,check=True);f.close()"])
 install=guest([TARGET+'/.venv/bin/python','-m','pip','install','--disable-pip-version-check','-r',TARGET+'/backend/requirements.txt','-c',pins],timeout=480)
 (OUT/'linux-install.log').write_text(install,encoding='utf-8')
 report['pip_check']=guest([TARGET+'/.venv/bin/python','-m','pip','check'])
 guest(['chown','-R','root:aicademiya',TARGET]);guest(['chmod','-R','g+rX',TARGET])
 verifier="import json,hashlib;from pathlib import Path;m=json.loads(Path("+repr(INCOMING+'/'+MANIFEST.name)+").read_text());r=Path("+repr(TARGET)+");bad=[n for n,i in m['files'].items() if hashlib.sha256((r/n).read_bytes()).hexdigest()!=i['sha256']];assert not bad,bad;print(json.dumps({'files_verified':len(m['files'])}))"
 report['installed_files']=json.loads(guest(['python3','-c',verifier]))
 report['current_link_unchanged']=guest(['readlink','-f','/opt/aicademiya/current'])==old
 report['production_service_active']=guest(['systemctl','is-active','aicademiya.service'])=='active'
 assert report['current_link_unchanged'] and report['production_service_active']
 report['status']='staged'
 (OUT/'ct255-stage-result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
