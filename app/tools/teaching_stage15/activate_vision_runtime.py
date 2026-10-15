"""Controlled T10-B vision/router activation; no website or anchor restart.
Require installed root-pinned bytes. Drain first, load/verify T10-B before
starting the new public router. On failure restore only owned user drop-ins.
"""
from pathlib import Path
import asyncio,hashlib,json,os,sqlite3,subprocess,sys,time,urllib.request
STAGE=Path('/home/adminz/llm/operations/stage15-deploy-r1')
NEW=Path('/opt/aicademiya-gpu-scheduler/releases/stage15-runtime-r1')
OLD=Path('/opt/aicademiya-gpu-scheduler/releases/stage14-runtime-r2')
CONFIG=Path('/home/adminz/llm/aicademiya-router/config-materials-vision-stage15-r1.json')
FIXED=Path('/etc/aicademiya-gpu-scheduler/workers-stage15-vision-r1.json')
SOCKET='/home/adminz/llm/material-gpu-state/maintenance.sock'
ROUTER_DROP=Path.home()/'.config/systemd/user/aicademiya-router.service.d/90-material-scheduler.conf'
WORKER_DROP=Path.home()/'.config/systemd/user/aicademiya-teaching-t10b.service.d/90-stage15-vision.conf'
OUT=STAGE/'activation'
PY='/home/adminz/llm/envs/aicademiya-router/bin/python'
GPU='GPU-105b82fb-41db-d6a1-13f0-ceddf5bed313'
sys.path.insert(0,str(NEW))
from maintenance_control import client
from worker_lifecycle import SystemdLifecycle

def digest(b):return hashlib.sha256(b).hexdigest()
def control(op):return asyncio.run(client(SOCKET,op))
def systemctl(*args):return subprocess.run(['systemctl','--user',*args],check=True,timeout=660,capture_output=True,text=True)
def inventory():
 raw=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid','--format=csv,noheader,nounits'],text=True)
 return {a.strip():int(b.strip())for line in raw.splitlines()for a,b in [line.split(',')]}
def free_gpu():
 raw=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid','--format=csv,noheader,nounits'],text=True)
 return not any(line.startswith(GPU)for line in raw.splitlines())
def wait_clear():
 end=time.monotonic()+240
 while time.monotonic()<end:
  if free_gpu():return
  time.sleep(.2)
 raise RuntimeError('GPU allocation remains; no foreign process will be killed')
def api(port,path):
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(f'http://127.0.0.1:{port}'+path,timeout=5)as r:return json.load(r)
def cache_state(root):
 with sqlite3.connect('file:'+str(Path(root)/'catalog.sqlite3')+'?mode=ro',uri=True)as db:
  rows=db.execute('SELECT id,scope,worker,signature,file,tokens,size,created FROM entries ORDER BY id').fetchall()
 return {r[0]:(r,(Path(root)/r[4]).stat().st_size,(Path(root)/r[4]).stat().st_mtime_ns)for r in rows}
def wait_model(items):
 life=SystemdLifecycle(items);end=time.monotonic()+180
 while time.monotonic()<end:
  try:
   record=life.lookup('t10b')
   if record and api(18332,'/health').get('status')=='ok':
    props=api(18332,'/props');assert props['modalities']['vision']is True;return record,props
  except (OSError,ValueError):pass
  time.sleep(.3)
 raise RuntimeError('Fixed vision teaching worker did not become ready')
def wait_router(vision):
 end=time.monotonic()+90
 while time.monotonic()<end:
  try:
   s=api(18280,'/status')
   if s['teaching_capacity']==3 and s['resources']['phase']=='teaching'and(not vision or s['vision_teaching_capacity']==1):return s
  except (OSError,ValueError,KeyError):pass
  time.sleep(.3)
 raise RuntimeError('Router did not return healthy capacity')
def main():
 assert os.geteuid()==1000 and not OUT.exists()and not WORKER_DROP.exists()and not CONFIG.exists()
 receipt=json.loads((NEW/'install-result.json').read_text());assert receipt['status']=='installed_not_activated'
 m=json.loads((NEW/'manifest.json').read_text());assert digest((NEW/'manifest.json').read_bytes())==receipt['manifest_sha256']
 assert all(digest((NEW/n).read_bytes())==h for n,h in m['runtime_files'].items())
 assert digest(FIXED.read_bytes())==m['config_files']['workers-vision.json']
 candidate=(STAGE/'router-vision.json').read_bytes();assert digest(candidate)==m['config_files']['router-vision.json']
 assert digest(Path('/home/adminz/llm/aicademiya-router/config-materials.json').read_bytes())==m['baseline_router_sha256']
 cfg=json.loads(candidate);items={w['name']:w for w in cfg['workers']};before=inventory();assert set(before)=={w['identity']['uuid']for w in items.values()}
 status=api(18280,'/status');assert status['resources']['phase']=='teaching'and status['teaching_capacity']==3
 old_drop=ROUTER_DROP.read_bytes();assert str(OLD/'router.py').encode()in old_drop
 OUT.mkdir(mode=0o700);(OUT/'router-dropin-before.conf').write_bytes(old_drop)
 report={'status':'running','website_changed':False,'anchor_restarts_requested':False,'before_allocations':before,'steps':[]};changed=False;stopped=False
 try:
  report['closed']=control('close');report['drained']=control('drain');assert not report['drained']['accepted_requests']and not report['drained']['busy']
  assert report['drained']['resources']['phase']=='teaching','Another document lease is active; leave it running'
  for port in (18330,18331,18332):assert all(s['is_processing']is False for s in api(port,'/slots'))
  cache_before=cache_state(cfg['cache_dir']);report['cache_entries_before']=len(cache_before)
  systemctl('stop','aicademiya-router.service');stopped=True;systemctl('stop','aicademiya-teaching-t10b.service');wait_clear();report['steps'].append('router_drained_stopped_and_T10B_positively_free')
  CONFIG.write_bytes(candidate);CONFIG.chmod(0o600)
  WORKER_DROP.parent.mkdir(parents=True,exist_ok=True)
  worker_text=f'[Service]\nExecStart=\nExecStart={PY} {NEW}/worker_launcher.py --config {FIXED} --sha256 {m["config_files"]["workers-vision.json"]} --worker t10b\n'
  WORKER_DROP.write_text(worker_text);WORKER_DROP.chmod(0o600)
  new_drop=old_drop.decode().replace(str(OLD/'router.py'),str(NEW/'router.py')).replace('/home/adminz/llm/aicademiya-router/config-materials.json',str(CONFIG));assert new_drop!=old_drop.decode()
  pending=ROUTER_DROP.with_name(ROUTER_DROP.name+'.stage15-new');assert not pending.exists();pending.write_text(new_drop);pending.chmod(0o600);os.replace(pending,ROUTER_DROP);changed=True
  systemctl('daemon-reload');systemctl('start','aicademiya-teaching-t10b.service')
  record,props=wait_model(items);report.update(vision_worker=record,vision_modalities=props['modalities']);report['steps'].append('vision_model_verified_before_router_admission')
  systemctl('start','aicademiya-router.service');after=wait_router(True);report['opened']=control('open');actual=inventory()
  assert all(actual[u]==pid for u,pid in before.items()if u!=GPU)and actual[GPU]!=before[GPU]
  assert digest(CONFIG.read_bytes())==m['config_files']['router-vision.json']
  cache_after=cache_state(cfg['cache_dir']);assert all(cache_after.get(k)==v for k,v in cache_before.items());report.update(baseline_cache_entries_and_file_metadata_preserved=True,cache_entries_after=len(cache_after))
  pid=int(subprocess.check_output(['systemctl','--user','show','aicademiya-router.service','--property=MainPID','--value'],text=True));assert str(NEW/'router.py').encode()in Path(f'/proc/{pid}/cmdline').read_bytes().split(bytes([0]))
  report.update(status='passed',after_allocations=actual,router_pid=pid,router_state=after,anchor_pids_preserved=True,config=str(CONFIG));report['steps'].append('new_router_and_fixed_vision_worker_read_back')
 except BaseException as e:
  report.update(status='failed',error_type=type(e).__name__,error=str(e))
  if changed:
   systemctl('stop','aicademiya-router.service');systemctl('stop','aicademiya-teaching-t10b.service');wait_clear()
   assert ROUTER_DROP.read_text()==new_drop;ROUTER_DROP.write_bytes(old_drop)
  if WORKER_DROP.exists():WORKER_DROP.rename(OUT/'worker-dropin-failed.conf');systemctl('daemon-reload')
  if stopped:
   systemctl('start','aicademiya-teaching-t10b.service');systemctl('start','aicademiya-router.service');wait_router(False);report['old_service_definitions_restored']=True
  control('open');raise
 finally:
  (OUT/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items()if k not in ('closed','drained','opened','router_state')},indent=2))
if __name__=='__main__':main()
