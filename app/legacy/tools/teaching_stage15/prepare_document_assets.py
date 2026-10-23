"""Read-only inventory of the tested vision model/runtime for root installation.
Writes only this owned staging directory; no asset copy, chmod, service or GPU.
"""
from pathlib import Path
import hashlib,json,os,re,subprocess
ROOT=Path(__file__).resolve().parent
TARGET=Path('/opt/aicademiya-documents/shared/vision-stage15-r1')
def digest(p):
 with Path(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 assert os.geteuid()==1000
 cfg=Path('/etc/aicademiya-gpu-scheduler/workers-stage15-vision-r1.json');w=next(w for w in json.loads(cfg.read_text())['workers']if w['name']=='t10b');cmd=list(w['command']);exe=Path(cmd[0]);sources={}
 def add(source,relative):
  source=Path(source);assert source.is_file();sources[relative]={'source':str(source),'sha256':digest(source),'bytes':source.stat().st_size,'mode':0o755 if relative=='runtime/bin/llama-server'else 0o644}
 for p in sorted(exe.parent.iterdir()):
  if p.is_file()and(p.name=='llama-server'or p.name.startswith('lib')):add(p,'runtime/bin/'+p.name)
 env={**os.environ,'LD_LIBRARY_PATH':str(exe.parent)+':'+w['env']['LD_LIBRARY_PATH'],'CUDA_VISIBLE_DEVICES':''}
 ldd=subprocess.check_output(['ldd',str(exe)],env=env,text=True);assert 'not found'not in ldd
 for line in ldd.splitlines():
  match=re.search(r'=> (/[^ ]+)',line)
  if match:
   p=Path(match[1])
   if str(p).startswith('/home/adminz/llm/toolchains/'):
    add(p,'runtime/lib/'+p.name)
 for flag,name in [('-m','model.gguf'),('--mmproj','mmproj.gguf'),('--chat-template-file','template.jinja')]:
  add(cmd[cmd.index(flag)+1],name);cmd[cmd.index(flag)+1]=str(TARGET/name)
 cmd[0]=str(TARGET/'runtime/bin/llama-server')
 for flag,value in {'--alias':'aicademiya-materials','--port':'18893','--ctx-size':'8192','--kv-unified-per-slot':'8192'}.items():cmd[cmd.index(flag)+1]=value
 for flag in ('--slot-save-path','--spec-draft-n-max','--spec-draft-type-k','--spec-draft-type-v'):
  if flag in cmd:
   i=cmd.index(flag);del cmd[i:i+2]
 profile={'schema_version':1,'command':cmd,'environment':{'LD_LIBRARY_PATH':str(TARGET/'runtime/bin')+':'+str(TARGET/'runtime/lib')+':/opt/aicademiya-documents/shared/native-libs/usr/lib/x86_64-linux-gnu','CUDA_DEVICE_ORDER':'PCI_BUS_ID'},'model_alias':'aicademiya-materials','context_size':8192}
 for name,value in [('vision-profile.json',profile),('asset-manifest.json',{'target':str(TARGET),'source_fixed_config_sha256':digest(cfg),'files':sources,'source_ldd':ldd,'no_live_changes':True})]:
  p=ROOT/name;assert not p.exists();p.write_text(json.dumps(value,indent=2)+'\n');p.chmod(0o600)
 print(json.dumps({'status':'asset_inventory_only','asset_files':len(sources),'asset_bytes':sum(x['bytes']for x in sources.values()),'manifest_sha256':digest(ROOT/'asset-manifest.json'),'profile_sha256':digest(ROOT/'vision-profile.json')}))
if __name__=='__main__':main()
