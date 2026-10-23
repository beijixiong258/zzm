"""Activate byte-identical immutable router code; drain and preserve model PIDs."""
from pathlib import Path
import asyncio,hashlib,json,subprocess,sys,time,urllib.request
NEW=Path('/opt/aicademiya-gpu-scheduler/releases/stage14-runtime-r2')
OLD=Path('/home/adminz/llm/operations/stage14-gpu-migration-r1/code-diag')
SOCKET='/home/adminz/llm/material-gpu-state/maintenance.sock'
DROP=Path.home()/'.config/systemd/user/aicademiya-router.service.d/90-material-scheduler.conf'
OUT=Path('/home/adminz/llm/operations/stage14-immutable-activation');OUT.mkdir(mode=0o700,exist_ok=False)
sys.path.insert(0,str(NEW));from maintenance_control import client

def control(op):return asyncio.run(client(SOCKET,op))
def inventory():return subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid','--format=csv,noheader,nounits'],text=True).splitlines()
def status():
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:18280/status',timeout=5)as r:return json.load(r)
def ready():
 end=time.monotonic()+60
 while time.monotonic()<end:
  try:
   s=status()
   if s['teaching_capacity']==3 and s['resources']['phase']=='teaching' and all(w['healthy']for w in s['workers']):return s
  except (OSError,KeyError,ValueError):pass
  time.sleep(.25)
 raise RuntimeError('Router did not recover healthy independent workers')
def main():
 m=json.loads((NEW/'manifest.json').read_text());assert len(m['files'])==10
 for n,v in m['files'].items():assert hashlib.sha256((NEW/n).read_bytes()).hexdigest()==v['sha256']==hashlib.sha256((OLD/n).read_bytes()).hexdigest()
 before=status();assert before['resources']['phase']=='teaching'and before['teaching_capacity']==3
 models=inventory();old=DROP.read_text();needle=str(OLD/'router.py');assert old.count(needle)==1
 config=Path('/home/adminz/llm/aicademiya-router/config-materials.json');config_hash=hashlib.sha256(config.read_bytes()).hexdigest()
 (OUT/'dropin-before.conf').write_text(old);report={'status':'running','model_pids_before':models,'source_bytes_identical':True,'config_sha256':config_hash,'steps':[]};changed=False
 try:
  report['close']=control('close');report['drain']=control('drain');assert not report['drain']['accepted_requests']and not report['drain']['busy']
  DROP.write_text(old.replace(needle,str(NEW/'router.py')));changed=True
  subprocess.run(['systemctl','--user','daemon-reload'],check=True);subprocess.run(['systemctl','--user','restart','aicademiya-router.service'],check=True,timeout=660)
  after=ready();report['open']=control('open');actual=inventory();assert sorted(actual)==sorted(models)
  assert hashlib.sha256(config.read_bytes()).hexdigest()==config_hash
  pid=int(subprocess.check_output(['systemctl','--user','show','aicademiya-router.service','--property=MainPID','--value'],text=True));argv=Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0');assert str(NEW/'router.py').encode()in argv
  report.update(status='passed',router_pid=pid,model_pids_after=actual,teaching_capacity=after['teaching_capacity'],source_path=str(NEW/'router.py'),config_unchanged=True)
 except BaseException as e:
  report.update(status='failed',error_type=type(e).__name__,error=str(e))
  if changed:
   DROP.write_text(old);subprocess.run(['systemctl','--user','daemon-reload'],check=True);subprocess.run(['systemctl','--user','restart','aicademiya-router.service'],check=True,timeout=660);ready();report['rolled_back_to_previous_path']=True
  control('open');raise
 finally:
  (OUT/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
