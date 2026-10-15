"""Both candidate benchmarks in one maintenance window, NUMA1 task isolation."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib,json,os,signal,subprocess,sys,time
import remote_control as control

ROOT=control.ROOT

def stop(signum,frame):raise KeyboardInterrupt('Owned suite interrupted')
signal.signal(signal.SIGTERM,stop)


def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    result={'status':'running','started_at':stamp,'numa_binding':'CPU1/memory1 task-only; no teaching configuration changes','quality_verified':False,'groups':[]};paused=False
    try:
        budget=json.loads((ROOT/'budget-status.json').read_text());assert not budget['paused']and budget['remaining_min_percent']>=1 and time.time()-budget['checked_epoch']<120
        manifest=json.loads((ROOT/'download-manifest.json').read_text())
        for x in manifest['items']:assert hashlib.file_digest(Path(x['path']).open('rb'),'sha256').hexdigest()==x['sha256']
        result['pause']=control.pause();paused=True;print(json.dumps(result['pause']),flush=True)
        env=os.environ.copy();env['LD_LIBRARY_PATH']=str(ROOT/'native-libs/usr/lib/x86_64-linux-gnu')
        expected={s['id']for s in json.loads((ROOT/'data/dataset/samples-server.json').read_text())['samples']};assert len(expected)==24
        for name in ['paddle','minicpm']:
            if (ROOT/'STOP').exists():raise SystemExit('Paused at model boundary')
            server=control.start(name);print(json.dumps(server),flush=True)
            py=ROOT/'.venv-paddle/bin/python'if name=='paddle'else Path(sys.executable)
            output=ROOT/'results'/name/'results.jsonl'
            cmd=['numactl','--cpunodebind=1','--membind=1',str(py),str(ROOT/'tools/remote_eval.py'),'--model',name,'--manifest',str(ROOT/'data/dataset/samples-server.json'),'--output',str(output)]
            p=subprocess.run(cmd,env=env)
            rows={}
            if output.exists():
                for line in output.read_text().splitlines():r=json.loads(line);rows[r['id']]=r
            group={'model':name,'returncode':p.returncode,'server':server,'expected_ids':sorted(expected),'recorded_ids':sorted(rows),'status_counts':{status:sum(r['status']==status for r in rows.values())for status in ['ok','no_text','error']},'all_ids_match':set(rows)==expected}
            group['execution_passed']=p.returncode==0 and group['all_ids_match']and all(r['status']=='ok'for r in rows.values())
            result['groups'].append(group);print(json.dumps(group),flush=True)
            control.stop_candidate()
            if (ROOT/'STOP').exists():raise SystemExit('Paused by quota/control marker')
        result['status']='passed'if all(g['execution_passed']for g in result['groups'])else'incomplete_or_failed'
    except BaseException as exc:result.update(status='failed',error_type=type(exc).__name__,error=str(exc)[:1500])
    finally:
        if paused:
            try:result['restoration']=control.resume()
            except BaseException as exc:result.update(status='restore_failed',restore_error=str(exc))
        result['ended_at']=datetime.now(timezone.utc).isoformat();target=ROOT/'evidence'/('suite-numa1-'+stamp+'.json');target.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({'status':result['status'],'report':str(target),'restoration':result.get('restoration'),'error':result.get('error')}),flush=True)
    raise SystemExit(0 if result['status']=='passed'else 1)


if __name__=='__main__':main()
