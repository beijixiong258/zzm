"""Bounded live model/search smoke against an isolated CT255 database."""
from pathlib import Path
import json,os,shlex,subprocess,sys,time,uuid
import httpx

ROOT=Path(__file__).resolve().parents[1]
TAG=uuid.uuid4().hex[:10]
OUT=ROOT/'artifacts/stage2'/('ct255-live-'+TAG)
DATA='/var/lib/aicademiya-qa/live-'+TAG
BASE='http://192.168.32.55:18774'
UNIT='aicademiya-qa-live-'+TAG
SSH=['ssh','-i','C:/Users/17193/.ssh/id_ed25519_aicademiya_pve','-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes','root@192.168.10.16']

def guest(args,check=True):
    r=subprocess.run(SSH+[shlex.join(['pct','exec','255','--']+args)],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=35)
    if check and r.returncode:raise RuntimeError(r.stderr or r.stdout)
    return r


def main():
    OUT.mkdir(parents=True)
    report={'status':'running','synthetic_only':True,'production_database_touched':False,'data_dir':DATA,'application_chat_calls':[]}
    with httpx.Client(trust_env=False,timeout=15) as probe:
        health=probe.get('http://192.168.32.5:18280/health').json()
    assert health['queue']==0 and all(not w['busy'] and w['healthy'] for w in health['workers']), 'Shared model is not idle/healthy; no probe started'
    report['router_requests_before']=health['requests']
    guest(['install','-d','-m','700','-o','aicademiya','-g','aicademiya',DATA])
    # Source credentials only inside the guest process, then override every QA scope.
    command='set -a; . /etc/aicademiya/aicademiya.conf; export AICADEMIYA_DATA_DIR='+shlex.quote(DATA)+'; export AICADEMIYA_DEMO_ENABLED=true AICADEMIYA_ALLOWED_ORIGINS='+shlex.quote(BASE)+'; export PYTHONDONTWRITEBYTECODE=1; exec /opt/aicademiya/current/.venv/bin/python -m uvicorn backend.aicademiya.main:app --host 192.168.32.55 --port 18774 --workers 1'
    guest(['systemd-run','--unit='+UNIT,'--collect','--uid=aicademiya','--gid=aicademiya','--working-directory=/opt/aicademiya/current','--property=UMask=0077','--property=NoNewPrivileges=true','/bin/bash','-c',command])
    try:
        with httpx.Client(base_url=BASE,trust_env=False,timeout=620) as client:
            deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                try:
                    if client.get('/api/health',timeout=2).status_code==200:break
                except httpx.RequestError:pass
                time.sleep(.2)
            else:raise RuntimeError('Live QA startup failed')
            boot=client.get('/api/bootstrap').json()
            assert boot['demo_enabled'] and boot['ai']['mode']=='openai' and boot['ai']['configured']
            assert client.post('/api/auth/demo',json={'role':'student','student_index':1}).status_code==200
            workspace=client.get('/api/sessions/session-4/workspace').json()
            version=workspace['version']['id']
            for search,message in [(False,'Synthetic deployment check: I think limited time and available resources relate to practicality. Give one short formative hint in English, without revealing the reference answer.'),(True,'Synthetic deployment check: find a public Cambridge English source about assessment reliability. Give one brief English explanation with the retrieved source.')]:
                start=time.monotonic()
                payload={'message':message,'question_id':'S4-T1-Q01','intent':'ask','web_search':search,'request_id':'ct255-live-'+uuid.uuid4().hex}
                response=client.post('/api/sessions/session-4/chat',params={'version_id':version},json=payload)
                if response.status_code!=200:
                    report['application_chat_calls'].append({'web_search':search,'status':response.status_code,'error':response.text[:600]})
                    raise RuntimeError('Live application chat failed')
                w=client.get('/api/sessions/session-4/workspace',params={'version_id':version}).json()
                message=w['messages'][-1]
                assert message['role']=='assistant' and message['mode']=='openai' and message['content'].strip() and 'Demo feedback preview' not in message['content']
                citations=message.get('citations',[])
                if search:assert citations and all(c['url'].startswith('https://') for c in citations)
                else:assert not citations
                report['application_chat_calls'].append({'web_search':search,'status':200,'seconds':round(time.monotonic()-start,3),'mode':message['mode'],'content':message['content'],'citations':citations})
                (OUT/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
                print(json.dumps({'completed_chat':len(report['application_chat_calls']),'search':search,'seconds':report['application_chat_calls'][-1]['seconds'],'citations':len(citations)}))
        report['status']='passed'
    except Exception as exc:
        report['status']='failed';report['error']=str(exc);raise
    finally:
        guest(['systemctl','stop',UNIT],check=False)
        report['qa_service_stopped']=guest(['systemctl','is-active',UNIT],check=False).stdout.strip()!='active'
        with httpx.Client(trust_env=False,timeout=15) as probe:
            after=probe.get('http://192.168.32.5:18280/health').json()
        report['router_requests_after']=after['requests']
        report['router_queue_after']=after['queue']
        (OUT/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'status':report['status'],'result':str(OUT/'result.json'),'error':report.get('error'),'qa_service_stopped':report['qa_service_stopped']}))

if __name__=='__main__':main()
