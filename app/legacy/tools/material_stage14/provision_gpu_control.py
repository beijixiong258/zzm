"""Provision only the private GPU control directory and its boot-time rule.

No model process/service/configuration changes, package installs, or credentials.
"""
from pathlib import Path
from datetime import datetime,timezone
import grp
import json
import os
import pwd
import stat
import subprocess


def main():
    if os.geteuid()!=0:raise SystemExit('Use sudo in the masked local terminal; no credentials in chat.')
    router=pwd.getpwnam('adminz');docs=pwd.getpwnam('aicademiya-docs')
    assert router.pw_uid==1000 and docs.pw_uid==999 and docs.pw_gid==988
    directory=Path('/run/aicademiya-gpu')
    rule=Path('/etc/tmpfiles.d/aicademiya-material-gpu.conf')
    content='d /run/aicademiya-gpu 2750 adminz aicademiya-docs -\n'
    assert not directory.is_symlink()and not rule.is_symlink()
    if rule.exists():
        assert rule.stat().st_uid==0 and rule.read_text()==content,'Unexpected existing rule; no overwrite'
    else:
        with rule.open('x')as f:f.write(content)
        rule.chmod(0o644)
    if directory.exists():
        s=directory.stat();assert stat.S_ISDIR(s.st_mode)and s.st_uid==router.pw_uid and s.st_gid==docs.pw_gid and stat.S_IMODE(s.st_mode)==0o2750
    else:
        directory.mkdir(mode=0o2750)
        os.chown(directory,router.pw_uid,docs.pw_gid);directory.chmod(0o2750)
    subprocess.run(['systemd-tmpfiles','--create',str(rule)],check=True,timeout=10)
    code="import os,json; p='/run/aicademiya-gpu'; assert os.geteuid()==999; print(json.dumps({'traverse':os.access(p,os.X_OK),'read':os.access(p,os.R_OK),'write':os.access(p,os.W_OK)}))"
    checked=json.loads(subprocess.check_output(['runuser','-u','aicademiya-docs','--','/usr/bin/python3','-c',code],text=True,timeout=10))
    assert checked=={'traverse':True,'read':True,'write':False}
    metadata=directory.stat()
    result={'status':'provisioned','directory':str(directory),'uid':metadata.st_uid,'gid':metadata.st_gid,
            'mode':oct(stat.S_IMODE(metadata.st_mode)),'document_access':checked,'rule':str(rule),
            'model_processes_modified':False,'services_restarted':False,'checked_at':datetime.now(timezone.utc).isoformat()}
    target=Path('/opt/aicademiya-documents/gpu-control-provision.json')
    target.write_text(json.dumps(result,indent=2)+'\n');target.chmod(0o644)
    print(json.dumps(result,indent=2),flush=True)
if __name__=='__main__':main()
