"""Run a real Ubuntu job while mirroring actual Codex quota and enforcing STOP."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import json
import queue
import shlex
import subprocess
import threading
import time
from budget import check, OUT

REMOTE='/home/adminz/llm/ocr-stage1-20261009'
SSH=['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8','ubuntu-gpu']


def control(code,timeout=45):
    # One observed transient SSH reset stopped a healthy benchmark. Retry the
    # same read/mirrored write once; persistent failure still pauses safely.
    for attempt in range(2):
        p=subprocess.run(SSH+['python3 -c '+shlex.quote(code)],capture_output=True,text=True,encoding='utf-8',timeout=timeout)
        if p.returncode==0:return p.stdout
        if attempt==0 and any(s in p.stderr for s in ('Connection reset','Connection closed','Connection timed out')):
            continue
        raise RuntimeError(p.stderr[-1000:])
    raise RuntimeError('SSH control failed')


def mirror():
    status=check(force=True)
    data=json.dumps(status)
    code='import os;from pathlib import Path;p=Path('+repr(REMOTE+'/budget-status.json')+');t=p.with_name(p.name+"."+str(os.getpid())+".tmp");t.write_text('+repr(data)+');t.replace(p)'
    control(code)
    return status


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--label',required=True);parser.add_argument('--restore',action='store_true');parser.add_argument('command',nargs=argparse.REMAINDER)
    a=parser.parse_args();command=a.command[1:]if a.command[:1]==['--']else a.command
    assert command
    logpath=OUT/(a.label+'.log');resultpath=OUT/(a.label+'-job.json')
    result={'label':a.label,'command':command,'started_at':datetime.now(timezone.utc).isoformat(),'status':'running','quota_checks':[]}
    p=None
    try:
        result['quota_checks'].append(mirror())
        p=subprocess.Popen(SSH+[shlex.join(command)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1)
        events=queue.Queue()
        def reader():
            for line in p.stdout:events.put(line)
            events.put(None)
        thread=threading.Thread(target=reader,daemon=True);thread.start()
        next_check=time.monotonic()+60
        with logpath.open('a',encoding='utf-8')as log:
            while True:
                try:line=events.get(timeout=1)
                except queue.Empty:line=''
                if line is None:break
                if line:
                    log.write(line);log.flush();print(line,end='',flush=True)
                if time.monotonic()>=next_check:
                    result['quota_checks'].append(mirror())
                    resultpath.write_text(json.dumps(result,indent=2)+'\n')
                    next_check=time.monotonic()+60
        result['returncode']=p.wait(timeout=30)
        result['status']='exited' if p.returncode==0 else 'failed'
    except BaseException as exc:
        result.update(status='paused',error_type=type(exc).__name__,error=str(exc)[:300])
        try:control('from pathlib import Path;Path('+repr(REMOTE+'/STOP')+').write_text("Parent quota/control pause; wait for user or verified recovery.\\n")')
        finally:
            if p is not None:
                try:p.wait(timeout=20)
                except subprocess.TimeoutExpired:p.terminate()
        raise
    finally:
        if a.restore:
            restoration=subprocess.run(SSH+['python3 '+REMOTE+'/tools/remote_control.py resume'],capture_output=True,text=True,encoding='utf-8',timeout=720)
            result['restoration']={'returncode':restoration.returncode,'stdout':restoration.stdout,'stderr':restoration.stderr}
            print(restoration.stdout,flush=True)
            if restoration.returncode:result['status']='restore_failed'
        result['ended_at']=datetime.now(timezone.utc).isoformat()
        resultpath.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'returncode':result.get('returncode'),'report':str(resultpath)}),flush=True)
    raise SystemExit(0 if result['status']=='exited'else 1)


if __name__=='__main__':main()
