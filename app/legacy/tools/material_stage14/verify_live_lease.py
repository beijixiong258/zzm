"""Actual exclusive GPU lease + concurrent teaching + return observations.

No process stop/start commands; document worker and resource owner own lifecycle.
Synthetic teaching prompts only, real model responses and GPU allocations.
"""
from pathlib import Path
import argparse
import concurrent.futures
import json
import subprocess
import time
import urllib.request
import uuid


def get(path,body=None):
    op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req=urllib.request.Request('http://127.0.0.1:18280'+path,data=json.dumps(body).encode()if body is not None else None,
                              headers={'Content-Type':'application/json'})
    with op.open(req,timeout=180)as r:return json.load(r)


def inventory():
    raw=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,used_gpu_memory','--format=csv,noheader,nounits'],text=True,timeout=8)
    return [{'uuid':p[0].strip(),'pid':int(p[1]),'mib':int(p[2])}for line in raw.splitlines()if len(p:=line.split(','))==3]


def teaching(index,tag):
    start=time.monotonic()
    response=get('/v1/chat/completions',{'model':'AIcademiya-64kx3-Qwen3.8-27B','messages':[
        {'role':'system','content':'This is an isolated infrastructure test, with no real student or course data.'},
        {'role':'user','content':'Explain the difference between formative and summative assessment in three concise sentences.'}],
        'user':tag+'-'+str(index),'temperature':0,'max_tokens':72,'stream':False})
    text=response['choices'][0]['message']['content'];assert isinstance(text,str)and text.strip()
    return {'index':index,'seconds':time.monotonic()-start,'text':text,'model':response.get('model'),'usage':response.get('usage')}


def main():
    cli=argparse.ArgumentParser();cli.add_argument('--output',required=True);cli.add_argument('--timeout',type=int,default=900);a=cli.parse_args()
    output=Path(a.output);assert not output.exists();output.parent.mkdir(parents=True,exist_ok=True)
    before=get('/status');base=inventory();expected={x['uuid']:x['pid']for x in base};elastic='GPU-105b82fb-41db-d6a1-13f0-ceddf5bed313'
    assert before['resources']['phase']=='teaching'and before['teaching_capacity']==3
    start=time.monotonic();samples=[];futures=[];result={'status':'running','real_gpu':True,'synthetic_teaching_prompts':True,'initial':before,'initial_allocations':base,'samples':samples};seen=False
    with concurrent.futures.ThreadPoolExecutor(max_workers=3)as pool:
        try:
            while time.monotonic()-start<a.timeout:
                status=get('/status');alloc=inventory();phase=status['resources']['phase']
                row={'seconds':time.monotonic()-start,'phase':phase,'capacity':status['teaching_capacity'],'queue':status['queue'],
                     'workers':[{k:w[k]for k in ['name','mode','busy','healthy']}for w in status['workers']],'allocations':alloc,
                     'last_transition_failure':status['resources'].get('last_transition_failure')}
                samples.append(row)
                for uid,pid in expected.items():
                    if uid!=elastic:assert any(x['uuid']==uid and x['pid']==pid for x in alloc),'Anchor teaching process changed during document lease'
                if phase=='leased':
                    assert status['teaching_capacity']==2
                    assert not any(x['uuid']==elastic and x['pid']==expected[elastic]for x in alloc),'Teaching allocation remained on leased GPU'
                    if not seen:
                        seen=True;tag='stage14-real-lease-'+uuid.uuid4().hex
                        futures=[pool.submit(teaching,index,tag)for index in range(3)]
                if phase=='teaching'and seen:
                    assert status['teaching_capacity']==3
                    after=[x for x in alloc if x['uuid']==elastic];assert len(after)==1 and after[0]['pid']!=expected[elastic]and after[0]['mib']>=10240
                    result['teaching_requests']=[f.result(timeout=180)for f in futures]
                    assert len(result['teaching_requests'])==3
                    result.update(status='passed',final=status,final_allocations=alloc,exclusive_lease_observed=True,anchor_pids_retained=True)
                    break
                if phase=='blocked'and seen:raise RuntimeError('Resource owner blocked during actual document cycle')
                if phase=='teaching'and not seen and status['resources']['epoch']>before['resources']['epoch']:
                    raise RuntimeError('A lease attempt ended without a grant; inspect the retained transition failure')
                output.write_text(json.dumps(result,indent=2)+'\n');time.sleep(.5)
            else:raise TimeoutError('Real lease/return observation deadline')
        except BaseException as e:
            result.update(status='failed',error_type=type(e).__name__,error=str(e));raise
        finally:
            result['wall_seconds']=time.monotonic()-start;result['maximum_queue_observed']=max((s['queue']for s in samples),default=0)
            output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if k not in ['samples','initial','final']}),flush=True)
    return 0
if __name__=='__main__':raise SystemExit(main())
