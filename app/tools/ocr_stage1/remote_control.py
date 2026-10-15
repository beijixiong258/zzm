"""Explicit, recoverable pause/restore of authorized teaching services for OCR QA."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import signal
import subprocess
import time
import urllib.request

ROOT=Path('/home/adminz/llm/ocr-stage1-20261009')
STATE=ROOT/'evidence/service-state.json'
PIDFILE=ROOT/'evidence/candidate-process.json'
CONFIG=Path('/home/adminz/llm/aicademiya-router/config.json')
UNITS=['aicademiya-lan.socket','aicademiya-lan.service','aicademiya-router.service']
GUARD='aicademiya-ocr-stage1-restore'
GPU='GPU-105b82fb-41db-d6a1-13f0-ceddf5bed313'


def run(args,check=True):
    p=subprocess.run(args,capture_output=True,text=True,timeout=180)
    if check and p.returncode:raise RuntimeError(p.stderr[-1500:] or p.stdout[-1500:])
    return p.stdout.strip()


def http(url):
    with urllib.request.urlopen(url,timeout=5)as r:return json.load(r)


def save(state):
    state['updated_epoch']=time.time()
    tmp=STATE.with_suffix('.tmp');tmp.write_text(json.dumps(state,indent=2)+'\n');tmp.replace(STATE)


def stop_candidate():
    if not PIDFILE.exists():return
    info=json.loads(PIDFILE.read_text());pid=info['pid']
    exe=Path('/proc')/str(pid)/'exe'
    if exe.exists():
        assert exe.resolve()==Path(info['executable']).resolve(), 'PID no longer belongs to candidate'
        os.kill(pid,signal.SIGTERM)
        deadline=time.monotonic()+20
        while exe.exists() and time.monotonic()<deadline:time.sleep(.2)
        if exe.exists():os.kill(pid,signal.SIGKILL)
    info['stopped']=True;PIDFILE.write_text(json.dumps(info,indent=2)+'\n')


def resume():
    stop_candidate()
    if not STATE.exists():return {'status':'no_pause_record'}
    state=json.loads(STATE.read_text())
    assert hashlib.file_digest(CONFIG.open('rb'),'sha256').hexdigest()==state['config_sha256'], 'Teaching config changed; do not overwrite it'
    if state['before']['aicademiya-router.service']=='active':run(['systemctl','--user','start','aicademiya-router.service'])
    for unit in ['aicademiya-lan.socket','aicademiya-lan.service']:
        if state['before'][unit]=='active':run(['systemctl','--user','start',unit])
    deadline=time.monotonic()+600
    last=None
    while time.monotonic()<deadline:
        try:
            status=http('http://127.0.0.1:18280/status')
            if status['model']==state['model'] and len(status['workers'])==3 and all(w['healthy']for w in status['workers']):
                last=status;break
        except Exception:pass
        time.sleep(1)
    if last is None:raise RuntimeError('Original model workers did not become healthy; retained state requires operator attention')
    state.update(phase='restored',restored_at=time.time(),workers=[{'name':w['name'],'healthy':w['healthy'],'busy':w['busy']}for w in last['workers']],unit_readback={u:run(['systemctl','--user','is-active',u],False)for u in UNITS})
    assert state['unit_readback']==state['before']
    save(state)
    run(['systemctl','--user','stop',GUARD+'.timer'],False)
    return {'status':'restored','workers':state['workers'],'units':state['unit_readback'],'config_unchanged':True}


def pause():
    assert not (ROOT/'STOP').exists(), 'Quota STOP marker present'
    status=http('http://127.0.0.1:18280/status')
    assert status['queue']==0 and not any(w['busy']for w in status['workers']), 'Teaching requests active; wait rather than interrupt accepted work'
    state={'phase':'preparing_pause','before':{u:run(['systemctl','--user','is-active',u],False)for u in UNITS},'model':status['model'],'config_sha256':hashlib.file_digest(CONFIG.open('rb'),'sha256').hexdigest(),'started_epoch':time.time()}
    assert all(v=='active'for v in state['before'].values()), 'Unexpected service baseline'
    save(state)
    try:
        run(['systemctl','--user','stop',GUARD+'.timer'],False)
        run(['systemctl','--user','reset-failed',GUARD+'.service'],False)
        run(['systemd-run','--user','--unit='+GUARD,'--on-active=3h','/usr/bin/python3',str(ROOT/'tools/remote_control.py'),'resume'])
        for unit in UNITS:run(['systemctl','--user','stop',unit])
        stopped={u:run(['systemctl','--user','is-active',u],False)for u in UNITS}
        assert all(v=='inactive'for v in stopped.values()), stopped
        state.update(phase='paused',paused_at=time.time(),pause_readback=stopped);save(state)
        return {'status':'paused','safety_restore_timer':'3h','units':stopped}
    except BaseException:
        resume();raise


def start(model):
    assert json.loads(STATE.read_text())['phase']=='paused'
    assert not (ROOT/'STOP').exists()
    stop_candidate()
    if model=='minicpm':
        weights=ROOT/'models/minicpm-v4.5/MiniCPM-V-4_5-Q4_K_M.gguf';projector=weights.parent/'mmproj-model-f16.gguf'
    else:
        weights=ROOT/'models/paddleocr-vl1.6/PaddleOCR-VL-1.6-GGUF.gguf';projector=weights.parent/'PaddleOCR-VL-1.6-GGUF-mmproj.gguf'
    assert weights.exists() and projector.exists()
    env={k:v for k,v in os.environ.items()if not k.startswith('LLAMA_')}
    env.update(CUDA_VISIBLE_DEVICES=GPU,CUDA_DEVICE_ORDER='PCI_BUS_ID',LD_LIBRARY_PATH='/home/adminz/llm/toolchains/cuda-12.8/lib')
    exe=ROOT/'runtime/bin/llama-server'
    args=[str(exe),'-m',str(weights),'--mmproj',str(projector),'--alias','ocr-eval','--host','127.0.0.1','--port','18891','-ngl','99','--split-mode','none','--parallel','1','--ctx-size','8192','--batch-size','512','--ubatch-size','256','--threads','4','--threads-batch','8','--flash-attn','auto','--jinja','--reasoning','off','--no-context-shift','--no-warmup','--log-verbosity','3']
    args=['numactl','--cpunodebind=1','--membind=1',*args]
    logpath=ROOT/'evidence'/('server-'+model+'-'+str(int(time.time()))+'.log')
    with logpath.open('w')as log:p=subprocess.Popen(args,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    info={'pid':p.pid,'model':model,'executable':str(exe),'args':args,'gpu_uuid':GPU,'log':str(logpath),'started_epoch':time.time()}
    PIDFILE.write_text(json.dumps(info,indent=2)+'\n')
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        if p.poll()is not None:raise RuntimeError('Candidate startup failed; '+str(logpath))
        try:
            if http('http://127.0.0.1:18891/health').get('status')=='ok':
                info['ready_at']=time.time();PIDFILE.write_text(json.dumps(info,indent=2)+'\n')
                return {'status':'ready','pid':p.pid,'model':model,'gpu_uuid':GPU,'log':str(logpath)}
        except Exception:pass
        time.sleep(.3)
    stop_candidate();raise RuntimeError('Candidate startup timed out')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['pause','resume','start','stop']);parser.add_argument('--model',choices=['minicpm','paddle'])
    a=parser.parse_args()
    if a.action=='pause':result=pause()
    elif a.action=='resume':result=resume()
    elif a.action=='start':assert a.model;result=start(a.model)
    else:stop_candidate();result={'status':'candidate_stopped'}
    print(json.dumps(result),flush=True)


if __name__=='__main__':main()
