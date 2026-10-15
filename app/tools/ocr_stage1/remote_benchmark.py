"""Execute real course-image candidate evaluation and restore teaching in finally."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import signal
import subprocess
import sys
import time
import remote_control as control

ROOT=control.ROOT

def interrupted(signum,frame):raise KeyboardInterrupt('Owned benchmark interrupted')
signal.signal(signal.SIGTERM,interrupted)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--model',choices=['minicpm','paddle'],required=True);parser.add_argument('--ids',default='')
    a=parser.parse_args();stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    result={'status':'running','model':a.model,'started_at':stamp,'synthetic':False};paused=False
    try:
        status=json.loads((ROOT/'budget-status.json').read_text());assert not status['paused'] and status['remaining_min_percent']>=1 and time.time()-status['checked_epoch']<120
        manifest=json.loads((ROOT/'download-manifest.json').read_text())
        for item in manifest['items']:
            if (a.model=='minicpm' and item.get('model','').startswith('minicpm'))or(a.model=='paddle' and item.get('model','').startswith('paddle')):
                assert hashlib.file_digest(Path(item['path']).open('rb'),'sha256').hexdigest()==item['sha256']
        result['pause']=control.pause();paused=True
        print(json.dumps(result['pause']),flush=True)
        result['server']=control.start(a.model);print(json.dumps(result['server']),flush=True)
        py=ROOT/'.venv-paddle/bin/python' if a.model=='paddle' else Path(sys.executable)
        output=ROOT/'results'/a.model/'results.jsonl'
        args=[str(py),str(ROOT/'tools/remote_eval.py'),'--model',a.model,'--manifest',str(ROOT/'data/dataset/samples-server.json'),'--output',str(output)]
        if a.ids:args+=['--ids',a.ids]
        import os
        env=os.environ.copy()
        env['LD_LIBRARY_PATH']=str(ROOT/'native-libs/usr/lib/x86_64-linux-gnu')+(':'+env['LD_LIBRARY_PATH'] if env.get('LD_LIBRARY_PATH') else '')
        p=subprocess.run(args,env=env)
        result['evaluation_returncode']=p.returncode
        latest={}
        if output.exists():
            for line in output.read_text().splitlines():
                r=json.loads(line);latest[r['id']]=r
        expected=set(a.ids.split(',')) if a.ids else {r['id']for r in json.loads((ROOT/'data/dataset/samples-server.json').read_text())['samples']}
        result.update(expected_ids=sorted(expected),observed_ids=sorted(latest),status_by_id={i:r['status']for i,r in latest.items()})
        result['status']='passed' if p.returncode==0 and expected.issubset(latest) and all(latest[i]['status']=='ok' for i in expected)else'incomplete_or_failed'
    except BaseException as exc:result.update(status='failed',error_type=type(exc).__name__,error=str(exc)[:1500])
    finally:
        if paused:
            try:result['restoration']=control.resume()
            except BaseException as exc:result.update(status='restore_failed',restore_error=str(exc))
        result['ended_at']=datetime.now(timezone.utc).isoformat()
        target=ROOT/'evidence'/(a.model+'-benchmark-'+stamp+'.json');target.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({'status':result['status'],'report':str(target),'restoration':result.get('restoration'),'error':result.get('error')}),flush=True)
    raise SystemExit(0 if result['status']=='passed'else 1)


if __name__=='__main__':main()
