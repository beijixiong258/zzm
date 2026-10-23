"""Read-only security/deployment observations, no config secrets or application writes."""
import json, subprocess, urllib.request, urllib.error
from pathlib import Path
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[1]
REMOTE=r'''
import json,subprocess,os,stat,urllib.request,urllib.error
from pathlib import Path
props=['User','Group','NoNewPrivileges','ProtectSystem','ProtectHome','PrivateTmp','ReadWritePaths','UMask','RestrictSUIDSGID','MemoryMax','TasksMax']
p=subprocess.check_output(['systemctl','show','aicademiya.service',*[f'--property={p}'for p in props]],text=True)
c={}
for line in Path('/etc/aicademiya/aicademiya.conf').read_text().splitlines():
 if '=' in line:
  k,v=line.split('=',1)
  if k in ['AICADEMIYA_ALLOWED_ORIGINS','AICADEMIYA_COOKIE_SECURE','AICADEMIYA_DEMO_ENABLED']:c[k]=v.strip().strip('"\'')
paths={}
for s in ['/etc/aicademiya/aicademiya.conf','/var/lib/aicademiya','/var/lib/aicademiya/aicademiya.sqlite3']:
 t=os.stat(s);paths[s]={'mode':oct(stat.S_IMODE(t.st_mode)),'uid':t.st_uid,'gid':t.st_gid}
r={'current':str(Path('/opt/aicademiya/current').resolve()),'service_security':p,'public_configuration_only':c,'permissions':paths,'listeners':subprocess.check_output(['ss','-lnt'],text=True)}
print(json.dumps(r))
'''
cmd=['ssh','-i','C:/Users/17193/.ssh/id_ed25519_aicademiya_pve','-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8','root@192.168.10.16','pct exec 255 -- python3 -']
p=subprocess.run(cmd,input=REMOTE,text=True,capture_output=True,timeout=30,check=True)
r=json.loads(p.stdout);r['at']=datetime.now(timezone.utc).isoformat();r['http']=[]
for path in ['/','/api/bootstrap','/api/auth/me','/api/settings','/api/admin/access-settings','/openapi.json','/docs','/.env','/backend/aicademiya/config.py','/data-v2/aicademiya.sqlite3','/sample_data/catalog.json']:
 try: response=urllib.request.urlopen('http://192.168.32.55:18773'+path,timeout=10)
 except urllib.error.HTTPError as e:response=e
 body=response.read(1000000)
 item={'path':path,'status':response.status,'content_type':response.headers.get('content-type'),'bytes_read':len(body),'headers':{k:response.headers.get(k)for k in ['content-security-policy','x-frame-options','x-content-type-options','referrer-policy','cache-control','strict-transport-security']}}
 if path=='/api/bootstrap':
  b=json.loads(body);item['top_level_keys']=list(b);item['ai_keys']=list(b.get('ai',{}));item['anonymous_ai_base_url_exposed']=bool(b.get('ai',{}).get('base_url'));item['demo_enabled']=b.get('demo_enabled')
 if path.startswith('/.') or path in ['/backend/aicademiya/config.py','/data-v2/aicademiya.sqlite3','/sample_data/catalog.json']:item['spa_fallback']=b'<div id="root"'in body;item['sqlite_magic']=body.startswith(b'SQLite format 3')
 r['http'].append(item)
out=ROOT/'artifacts/stage10/infra-before.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
