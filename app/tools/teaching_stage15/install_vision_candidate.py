"""Root-only immutable code/config staging, with no service reload or cutover."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,copy,hashlib,json,os,subprocess
STAGE=Path('/home/adminz/llm/operations/stage15-deploy-r1')
TARGET=Path('/opt/aicademiya-gpu-scheduler/releases/stage15-runtime-r1')
CONFIG=Path('/etc/aicademiya-gpu-scheduler/workers-stage15-vision-r1.json')
BASE_CONFIG=Path('/etc/aicademiya-gpu-scheduler/workers.json')
ROUTER_CONFIG=Path('/home/adminz/llm/aicademiya-router/config-materials.json')
FILES={'migration_steps.py','worker_launcher.py','worker_lifecycle.py','router_resources.py','router.py','maintenance_control.py','render_install.py','lease_scheduler.py','local_control.py','migration_gate.py'}
def digest(b):return hashlib.sha256(b).hexdigest()
def inventory():return subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid','--format=csv,noheader,nounits'],text=True).splitlines()
def main():
 p=argparse.ArgumentParser();p.add_argument('--manifest-sha256',required=True);a=p.parse_args();assert os.geteuid()==0,'Use the masked sudo terminal';os.umask(0o022)
 data=(STAGE/'manifest.json').read_bytes();assert digest(data)==a.manifest_sha256;m=json.loads(data);assert m['release']=='stage15-runtime-r1'and set(m['runtime_files'])==FILES
 assert not TARGET.exists()and not CONFIG.exists(),'Inspect existing/partial destination rather than overwriting'
 assert digest(BASE_CONFIG.read_bytes())==m['baseline_workers_sha256'];assert digest(ROUTER_CONFIG.read_bytes())==m['baseline_router_sha256']
 blobs={}
 for n,h in m['runtime_files'].items():
  f=STAGE/'code'/n;assert not f.is_symlink();b=f.read_bytes();assert digest(b)==h;compile(b,str(f),'exec');blobs[n]=b
 configs={}
 for n,h in m['config_files'].items():
  assert n in ('workers-vision.json','router-vision.json');b=(STAGE/n).read_bytes();assert digest(b)==h;configs[n]=b
 baseline=json.loads(BASE_CONFIG.read_text());candidate=json.loads(configs['workers-vision.json']);router=json.loads(configs['router-vision.json'])
 assert candidate['workers']==router['workers'];old={w['name']:w for w in baseline['workers']};new={w['name']:w for w in candidate['workers']};assert set(new)==set(old)=={'v100','t10a','t10b'}
 assert new['v100']==old['v100']and new['t10a']==old['t10a'];assert new['t10b']['env']==old['t10b']['env']
 expected=copy.deepcopy(old['t10b']);projector=Path(expected['identity']['model']).parent/'mmproj-Qwen3.8-27B-BF16.gguf'
 with projector.open('rb')as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
 assert actual==m['projector_sha256']=='13cb7bebccbd04afc8f4090cb949ecf8937cdf7377c5799b1a0c594e7c0d3e16'
 changes={'--mmproj':str(projector),'--batch-size':'256','--ubatch-size':'128','--spec-type':'none','--image-max-tokens':'3072'}
 for flag,value in changes.items():
  if flag in expected['command']:expected['command'][expected['command'].index(flag)+1]=value
  else:expected['command'].extend([flag,value])
 expected['identity'].update(mtp=0,ubatch=128,batch=256,projector_sha256=actual,projector=str(projector),image_max_tokens=3072)
 assert new['t10b']==expected
 before=inventory();TARGET.mkdir(mode=0o755)
 for n,b in blobs.items():(TARGET/n).write_bytes(b);(TARGET/n).chmod(0o644)
 (TARGET/'manifest.json').write_bytes(data);(TARGET/'manifest.json').chmod(0o644)
 CONFIG.write_bytes(configs['workers-vision.json']);CONFIG.chmod(0o644)
 assert all(digest((TARGET/n).read_bytes())==h for n,h in m['runtime_files'].items())and digest(CONFIG.read_bytes())==m['config_files']['workers-vision.json']
 assert digest(BASE_CONFIG.read_bytes())==m['baseline_workers_sha256']and digest(ROUTER_CONFIG.read_bytes())==m['baseline_router_sha256']
 after=inventory();assert sorted(before)==sorted(after),'Concurrent model PID change requires inspection'
 receipt={'status':'installed_not_activated','runtime':str(TARGET),'worker_config':str(CONFIG),'manifest_sha256':a.manifest_sha256,'worker_config_sha256':digest(CONFIG.read_bytes()),'runtime_files_verified':len(blobs),'model_pids_before':before,'model_pids_after':after,'services_reloaded':False,'website_promoted':False,'completed_at':datetime.now(timezone.utc).isoformat()}
 (TARGET/'install-result.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
