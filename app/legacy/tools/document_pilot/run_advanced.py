"""Run MinerU Advanced on the complete scan and known regression images."""
from pathlib import Path
from datetime import datetime,timezone
import json,os,signal,subprocess,sys,time,urllib.request
BASE=Path('/home/adminz/llm/ocr-stage1-20261009');ROOT=BASE/'whole-document-pilot'
sys.path.insert(0,str(BASE/'tools'))
import remote_control as control


def stop(sig,frame):raise KeyboardInterrupt('Pilot interrupted')
signal.signal(signal.SIGTERM,stop)


def start_server():
    model=ROOT/'mineru-home/models/MinerU2.5-Pro-2605-1.2B-GGUF'
    exe=BASE/'runtime/bin/llama-server'
    args=['numactl','--cpunodebind=1','--membind=1',str(exe),'-m',str(model/'MinerU2.5-Pro-2605-1.2B-Q8_0.gguf'),'--mmproj',str(model/'mmproj-MinerU2.5-Pro-2605-1.2B-Q8_0.gguf'),'--alias','mineru-doc','--host','127.0.0.1','--port','18892','-ngl','99','--parallel','1','--ctx-size','8192','--no-kv-unified','--cache-ram','0','--special','--grammar','root ::= .*','--skip-chat-parsing','--no-warmup','--batch-size','512','--ubatch-size','256','--threads','4','--threads-batch','8','--flash-attn','auto']
    env={k:v for k,v in os.environ.items()if not k.startswith('LLAMA_')}
    env.update(CUDA_VISIBLE_DEVICES=control.GPU,CUDA_DEVICE_ORDER='PCI_BUS_ID',LD_LIBRARY_PATH='/home/adminz/llm/toolchains/cuda-12.8/lib')
    log=ROOT/'evidence'/('mineru-server-'+str(int(time.time()))+'.log')
    with log.open('w')as f:p=subprocess.Popen(args,env=env,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
    info={'pid':p.pid,'model':'MinerU2.5-Pro-2605-1.2B-Q8_0','executable':str(exe),'args':args,'gpu_uuid':control.GPU,'log':str(log)}
    control.PIDFILE.write_text(json.dumps(info,indent=2)+'\n')
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        if p.poll()is not None:raise RuntimeError('MinerU VLM startup failed: '+str(log))
        try:
            with urllib.request.urlopen('http://127.0.0.1:18892/health',timeout=2)as r:d=json.load(r)
            if d.get('status')=='ok':return info
        except Exception:pass
        time.sleep(.3)
    raise RuntimeError('MinerU VLM startup timeout')


def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    result={'status':'running','started_at':stamp,'quality_accepted':False,'cases':[]};paused=False;child=None
    receipt=ROOT/'evidence'/('advanced-run-'+stamp+'.json')
    try:
        budget=json.loads((BASE/'budget-status.json').read_text());assert budget['remaining_min_percent']>=1 and not budget['paused']and time.time()-budget['checked_epoch']<120
        result['pause']=control.pause();paused=True;print(json.dumps(result['pause']),flush=True)
        result['server']=start_server();print(json.dumps({'vlm':'ready','pid':result['server']['pid']}),flush=True)
        tasks=[('chapter10-advanced',BASE/'data/dataset/sources/src14.pdf',10)]
        tasks.extend(('regression-'+i,BASE/'data/dataset/images'/(i+'.png'),1)for i in ['sample18','sample16','sample21','sample23'])
        gaps=os.environ.get('PILOT_GUIDE_GAPS','')
        if gaps:tasks=[('guide317-image-pages',BASE/'data/dataset/sources/src02.pdf',len(gaps.split(',')))]
        env={**os.environ,'LD_LIBRARY_PATH':str(BASE/'native-libs/usr/lib/x86_64-linux-gnu'),'OMP_NUM_THREADS':'4','OPENBLAS_NUM_THREADS':'4'}
        for name,source,pages in tasks:
            if(BASE/'STOP').exists():raise SystemExit('Budget/control pause')
            cmd=['numactl','--cpunodebind=1','--membind=1',str(ROOT/'.venv/bin/python'),str(ROOT/'tools/parse_document.py'),'--input',str(source),'--name',name,'--tier','advanced','--ocr-mode','ocr','--expected-pages',str(pages)]
            if gaps:cmd+=['--page-range',gaps,'--expected-page-ids',gaps]
            log=ROOT/'evidence'/(name+'-'+stamp+'.log');start=time.monotonic()
            print(json.dumps({'case':name,'status':'started','all_pdf_pages':pages}),flush=True)
            with log.open('w')as f:
                child=subprocess.Popen(cmd,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
                while child.poll()is None:
                    if(BASE/'STOP').exists():os.killpg(child.pid,signal.SIGTERM);child.wait(timeout=20);raise SystemExit('Paused; current case retained incomplete')
                    time.sleep(.5)
                rc=child.returncode
            row={'case':name,'returncode':rc,'seconds':time.monotonic()-start,'log':str(log)}
            result['cases'].append(row);receipt.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(row),flush=True)
            if rc and name=='chapter10-advanced':raise RuntimeError('Primary full-document parse failed; diagnose before proceeding')
        result['status']='all_cases_parsed'if all(x['returncode']==0 for x in result['cases'])else'partial'
    except BaseException as e:
        result.update(status='failed',error_type=type(e).__name__,error=str(e)[:1500])
        if child is not None and child.poll()is None:
            os.killpg(child.pid,signal.SIGTERM)
            try:child.wait(timeout=15)
            except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL)
    finally:
        if paused:
            try:result['restoration']=control.resume()
            except BaseException as e:result.update(status='restore_failed',restore_error=str(e))
        result['ended_at']=datetime.now(timezone.utc).isoformat();receipt.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'report':str(receipt),'restoration':result.get('restoration'),'error':result.get('error')}),flush=True)
    raise SystemExit(0 if result['status']=='all_cases_parsed'else 1)


if __name__=='__main__':main()
