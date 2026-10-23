"""Exercise the installed CT255 release with separate temporary QA services/data."""
from pathlib import Path
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
import uuid
import httpx

ROOT=Path(__file__).resolve().parents[1]
TOKEN=uuid.uuid4().hex[:10]
OUT=ROOT/'artifacts/stage2'/('ct255-acceptance-'+TOKEN)
GUEST='/var/lib/aicademiya-qa/'+TOKEN
BASE='http://192.168.32.55:18774'
SSH=['ssh','-i','C:/Users/17193/.ssh/id_ed25519_aicademiya_pve','-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8','root@192.168.10.16']


def guest(args, check=True):
    r=subprocess.run(SSH+[shlex.join(['pct','exec','255','--']+args)],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=40)
    if check and r.returncode:
        raise RuntimeError(r.stderr or r.stdout)
    return r


def main():
    OUT.mkdir(parents=True,exist_ok=False)
    summary={'status':'running','production_database_touched':False,'real_model_requests':0,'guest_root':GUEST,'groups':[]}
    (OUT/'result.json').write_text(json.dumps(summary,indent=2)+'\n')
    guest(['install','-d','-m','700','-o','aicademiya','-g','aicademiya',GUEST])
    node=shutil.which('node')
    groups=[('api',[sys.executable,'tools/stage2_api_acceptance.py','--base-url',BASE,'--confirm-test-database']),('browser',[node,'tools/stage2_browser_acceptance.mjs']),('baseline',[node,'tools/browser_acceptance.mjs']),('password',[node,'tools/password_browser_check.mjs'])]
    selected=set(os.getenv('AICADEMIYA_QA_GROUPS','api,browser,baseline,password').split(','))
    assert selected and selected <= {name for name,_ in groups}
    try:
        for name,command in groups:
            if name not in selected:continue
            unit='aicademiya-qa-'+TOKEN+'-'+name
            data=GUEST+'/'+name
            out=OUT/name;out.mkdir()
            guest(['install','-d','-m','700','-o','aicademiya','-g','aicademiya',data])
            args=['systemd-run','--unit='+unit,'--collect','--uid=aicademiya','--gid=aicademiya','--working-directory=/opt/aicademiya/current','--property=UMask=0077','--property=NoNewPrivileges=true']
            envs={'LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1','AICADEMIYA_DATA_DIR':data,'AICADEMIYA_DEMO_ENABLED':'true','AICADEMIYA_AI_MODE':'demo','AICADEMIYA_AI_PROVIDER':'','AICADEMIYA_AI_BASE_URL':'','AICADEMIYA_AI_MODEL':'','AICADEMIYA_AI_API_KEY':'','AICADEMIYA_WEB_SEARCH_ENABLED':'false','TAVILY_API_KEY':'','AICADEMIYA_ALLOWED_ORIGINS':BASE,'AICADEMIYA_COOKIE_SECURE':'false'}
            args += ['--setenv='+k+'='+v for k,v in envs.items()]
            args += ['/opt/aicademiya/current/.venv/bin/python','-m','uvicorn','backend.aicademiya.main:app','--host','192.168.32.55','--port','18774','--workers','1']
            record={'name':name,'unit':unit,'data_dir':data,'base_url':BASE,'status':'failed','artifacts':str(out)}
            try:
                guest(args)
                with httpx.Client(trust_env=False,timeout=2) as client:
                    deadline=time.monotonic()+30
                    while time.monotonic()<deadline:
                        try:
                            if client.get(BASE+'/api/health').status_code==200:break
                        except httpx.RequestError:pass
                        time.sleep(.2)
                    else:raise RuntimeError('Remote QA readiness failed')
                    assert client.get(BASE+'/api/bootstrap').json()['demo_enabled'] is True
                env=os.environ.copy();scratch=Path('C:/Users/17193/AppData/Local/hermes/cache/scratch')
                env.update(AICADEMIYA_TEST_URL=BASE,AICADEMIYA_TEST_ARTIFACT_DIR=str(out),TEMP=str(scratch),TMP=str(scratch),TMPDIR=str(scratch))
                completed=subprocess.run(command,cwd=ROOT,env=env,timeout=600)
                record['exit_code']=completed.returncode
                if completed.returncode:raise RuntimeError(name+' remote acceptance failed')
                record['status']='passed'
            finally:
                assert unit.startswith('aicademiya-qa-'+TOKEN)
                guest(['systemctl','stop',unit],check=False)
                status=guest(['systemctl','is-active',unit],check=False)
                record['owned_qa_service_stopped']=status.stdout.strip() not in ('active','activating','deactivating')
                logs=guest(['journalctl','-u',unit,'--no-pager','-n','350'],check=False)
                (out/'server.log').write_text(logs.stdout,encoding='utf-8')
                summary['groups'].append(record)
                (OUT/'result.json').write_text(json.dumps(summary,indent=2)+'\n')
        summary['status']='passed'
    except Exception as exc:
        summary['status']='failed'
        summary['error']=str(exc)
        raise
    finally:
        summary['production_service_active']=guest(['systemctl','is-active','aicademiya.service'],check=False).stdout.strip()=='active'
        (OUT/'result.json').write_text(json.dumps(summary,indent=2)+'\n')
        print(json.dumps({'status':summary['status'],'result':str(OUT/'result.json'),'guest_root':GUEST,'groups':summary['groups'],'production_service_active':summary['production_service_active']},indent=2))

if __name__=='__main__':main()
