"""Generate exact candidate configs from current fixed configs; NO activation."""
from pathlib import Path
import copy,hashlib,json,os
ROOT=Path(__file__).resolve().parent
OLD_ROUTER=Path('/home/adminz/llm/aicademiya-router/config-materials.json')
OLD_WORKERS=Path('/etc/aicademiya-gpu-scheduler/workers.json')
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
 assert os.geteuid()==1000
 old_router=OLD_ROUTER.read_bytes();old_workers=OLD_WORKERS.read_bytes();router=json.loads(old_router);workers=json.loads(old_workers)
 by_name={w['name']:w for w in workers['workers']};live={w['name']:w for w in router['workers']};assert by_name==live,'Fixed launcher and router definitions differ'
 candidate=copy.deepcopy(workers);vision=next(w for w in candidate['workers']if w['name']=='t10b');before=copy.deepcopy(vision)
 projector=Path(vision['identity']['model']).parent/'mmproj-Qwen3.8-27B-BF16.gguf'
 with projector.open('rb')as f:projector_hash=hashlib.file_digest(f,'sha256').hexdigest()
 assert projector_hash=='13cb7bebccbd04afc8f4090cb949ecf8937cdf7377c5799b1a0c594e7c0d3e16'
 flags={'--mmproj':str(projector),'--batch-size':'256','--ubatch-size':'128','--spec-type':'none','--image-max-tokens':'3072'}
 for name,value in flags.items():
  if name in vision['command']:vision['command'][vision['command'].index(name)+1]=value
  else:vision['command'].extend([name,value])
 vision['identity'].update(mtp=0,ubatch=128,batch=256,projector_sha256=projector_hash,projector=str(projector),image_max_tokens=3072)
 assert vision['identity']['ctx']==65536 and vision['env']==before['env']
 for name in ('v100','t10a'):assert next(w for w in candidate['workers']if w['name']==name)==by_name[name]
 router['workers']=copy.deepcopy(candidate['workers'])
 blobs={'workers-vision.json':(json.dumps(candidate,indent=2)+'\n').encode(),'router-vision.json':(json.dumps(router,indent=2)+'\n').encode()}
 for name,data in [('baseline-router.json',old_router),('baseline-workers.json',old_workers),*blobs.items()]:
  p=ROOT/name;assert not p.exists();p.write_bytes(data);p.chmod(0o600)
 files={p.name:sha(p.read_bytes())for p in(ROOT/'code').glob('*.py')};assert len(files)==10
 report={'release':'stage15-runtime-r1','runtime_files':files,'config_files':{n:sha(b)for n,b in blobs.items()},'baseline_router_sha256':sha(old_router),'baseline_workers_sha256':sha(old_workers),'projector_sha256':projector_hash,'only_worker_changed':'t10b','anchor_definitions_unchanged':True,'config_changes':flags,'activated':False}
 (ROOT/'manifest.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':'staged_not_activated','manifest_sha256':sha((ROOT/'manifest.json').read_bytes()),'changed_worker':'t10b','context_retained':65536,'runtime_files':len(files)}))
if __name__=='__main__':main()
