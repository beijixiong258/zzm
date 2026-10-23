"""Read the installed, root-pinned full-page vision runtime profile.
The document supervisor owns lifecycle/lease; this module only supplies its
fixed model argv. No source or request data may choose model files or commands.
"""
from pathlib import Path
import hashlib,json,os

def fixed_vision_profile(path,expected_sha):
 path=Path(path)
 if not path.is_absolute():raise ValueError('Absolute fixed vision profile required')
 for item in (path,*path.parents):
  stat=item.lstat()
  if item.is_symlink()or stat.st_uid!=0 or stat.st_mode&0o022:raise ValueError('Vision profile must be root-owned and not writable by model/document accounts')
 raw=path.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=expected_sha:raise ValueError('Fixed vision profile checksum mismatch')
 p=json.loads(raw)
 if set(p)!={'schema_version','command','environment','model_alias','context_size'}or p['schema_version']!=1:raise ValueError('Unsupported fixed vision profile')
 cmd=p['command'];env=p['environment']
 if not isinstance(cmd,list)or not cmd or not all(isinstance(x,str)and x for x in cmd)or not Path(cmd[0]).is_absolute():raise ValueError('Fixed vision argv required')
 def flag(name):
  if cmd.count(name)!=1 or cmd.index(name)+1==len(cmd):raise ValueError('Missing/duplicate fixed vision flag: '+name)
  return cmd[cmd.index(name)+1]
 if p['context_size']!=8192 or p['model_alias']!='aicademiya-materials':raise ValueError('Unsupported page-vision context/model profile')
 for k,v in {'--host':'127.0.0.1','--port':'18893','--parallel':'1','--ctx-size':'8192','--kv-unified-per-slot':'8192','--alias':p['model_alias'],'--spec-type':'none','--image-max-tokens':'3072','--cache-ram':'0'}.items():
  if flag(k)!=v:raise ValueError('Unexpected fixed page-vision setting: '+k)
 if '--slot-save-path'in cmd:raise ValueError('Document inference must not write teaching slot snapshots')
 for k in ('-m','--mmproj','--chat-template-file'):
  if not Path(flag(k)).is_absolute():raise ValueError('Absolute installed model/projector/template required')
 if not isinstance(env,dict)or set(env)!={'LD_LIBRARY_PATH','CUDA_DEVICE_ORDER'}or not all(isinstance(v,str)and v for v in env.values())or env['CUDA_DEVICE_ORDER']!='PCI_BUS_ID':raise ValueError('Fixed vision library environment required')
 return {'page_markdown':True,'exe':Path(cmd[0]),'command':cmd,'environment':env,'libraries':env['LD_LIBRARY_PATH'],'model_alias':p['model_alias'],'context_size':p['context_size']}
