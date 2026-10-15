"""Install exact independent-worker candidates; never start/stop a service."""
from pathlib import Path
from datetime import datetime,timezone
import argparse
import ast
import hashlib
import json
import os
import pwd
import re
import subprocess

RUNTIME=('router.py','lease_scheduler.py','local_control.py','router_resources.py',
         'worker_lifecycle.py','worker_launcher.py','maintenance_control.py')


def install_file(path,blob,mode=0o644,gid=0):
    assert not path.is_symlink()
    if path.exists():
        assert path.is_file()and path.stat().st_uid==0 and path.read_bytes()==blob,'Different existing target; no overwrite: '+str(path)
    else:
        path.parent.mkdir(parents=True,exist_ok=True,mode=0o755)
        with path.open('xb')as f:f.write(blob)
        os.chown(path,0,gid);path.chmod(mode)
    assert path.read_bytes()==blob


def main():
    cli=argparse.ArgumentParser();cli.add_argument('--source',required=True);cli.add_argument('--manifest-sha256',required=True);a=cli.parse_args()
    if os.geteuid()!=0:raise SystemExit('Authenticate only in the local masked sudo terminal.')
    source=Path(a.source).resolve();manifest_bytes=(source/'install-manifest.json').read_bytes()
    assert re.fullmatch('[a-f0-9]{64}',a.manifest_sha256)and hashlib.sha256(manifest_bytes).hexdigest()==a.manifest_sha256
    manifest=json.loads(manifest_bytes);blobs={}
    for name,digest in manifest['files'].items():
        assert re.fullmatch(r'(code|install)/[A-Za-z0-9_.-]+',name)
        p=source/name;assert not p.is_symlink()and p.stat().st_size<1024*1024
        blob=p.read_bytes();assert hashlib.sha256(blob).hexdigest()==digest;blobs[name]=blob
        if name.endswith('.py'):ast.parse(blob)
    model=pwd.getpwnam('adminz');assert model.pw_uid==1000
    targets={}
    for name in RUNTIME:targets[Path('/opt/aicademiya-gpu-scheduler')/name]=('code/'+name,0o644,0)
    targets[Path('/etc/aicademiya-gpu-scheduler/workers.json')]=('install/workers.json',0o640,model.pw_gid)
    for name in ('v100','t10a','t10b'):
        unit='aicademiya-teaching-'+name+'.service'
        targets[Path('/etc/systemd/user')/unit]=('install/'+unit,0o644,0)
    targets[Path('/etc/tmpfiles.d/aicademiya-material-gpu.conf')]=('install/aicademiya-gpu.conf',0o644,0)
    # Validate every existing destination before any file installation.
    for path,(name,mode,gid)in targets.items():
        assert name in blobs and not path.is_symlink()
        if path.exists():assert path.stat().st_uid==0 and path.read_bytes()==blobs[name],'Unexpected existing target: '+str(path)
    for path,(name,mode,gid)in targets.items():install_file(path,blobs[name],mode,gid)
    env={**os.environ,'XDG_RUNTIME_DIR':'/run/user/1000','DBUS_SESSION_BUS_ADDRESS':'unix:path=/run/user/1000/bus'}
    units=[str(Path('/etc/systemd/user')/('aicademiya-teaching-'+n+'.service'))for n in ('v100','t10a','t10b')]
    subprocess.run(['runuser','-u','adminz','--','systemd-analyze','--user','verify',*units],env=env,check=True,timeout=30)
    workers_sha=hashlib.sha256(blobs['install/workers.json']).hexdigest()
    check="import sys;sys.path.insert(0,'/opt/aicademiya-gpu-scheduler');from worker_launcher import trusted_config;assert set(trusted_config('/etc/aicademiya-gpu-scheduler/workers.json',"+repr(workers_sha)+"))=={'v100','t10a','t10b'};print('fixed_config_readable_and_verified')"
    subprocess.run(['runuser','-u','adminz','--','/home/adminz/llm/envs/aicademiya-router/bin/python','-c',check],env=env,check=True,timeout=20)
    result={'status':'installed_not_started','files':{str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in targets},
            'worker_config_sha256':workers_sha,'manifest_sha256':a.manifest_sha256,
            'models_started':False,'services_restarted':False,'production_router_replaced':False,'completed_at':datetime.now(timezone.utc).isoformat()}
    report=Path('/opt/aicademiya-gpu-scheduler/install-result.json');report.write_text(json.dumps(result,indent=2)+'\n');report.chmod(0o644)
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
