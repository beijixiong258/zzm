"""Bounded CPU-only Stage12 probe; owns only this tree and port18893.

Run with existing pilot Python on Ubuntu. No pause/resume/service operations.
Quota is periodically mirrored by the parent run_remote_job.py wrapper.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from parser_helpers import dump, sha256, validate_bundle

BASE = Path('/home/adminz/llm/ocr-stage1-20261009')
PILOT = BASE/'whole-document-pilot'
ROOT = BASE/'stage12-parser'
PYTHON = PILOT/'.venv/bin/python'


def command(args):
    p = subprocess.run(args, capture_output=True, text=True, timeout=20)
    return {'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}


def snapshot():
    status = json.load(urllib.request.urlopen('http://127.0.0.1:18280/status',timeout=5))
    lines = command(['ps','-eo','pid,ppid,rss,args'])['stdout'].splitlines()
    processes = [s for s in lines if ('llama-server' in s or '18280' in s or 'router' in s) and 'parser_probe' not in s]
    config = []
    for line in lines:
        if '--config' in line:
            words = line.split()
            try:
                path = Path(words[words.index('--config')+1])
                if path.is_file():
                    config.append({'name':path.name,'sha256':sha256(path)})
            except (IndexError,ValueError):
                pass
    return {'router':status,'protected_processes':processes,'configs':config,
            'units':command(['systemctl','show','llama-router.service','--property=ActiveState,SubState,MainPID']),
            'teaching_user_units':command(['systemctl','--user','show','aicademiya-router.service','aicademiya-lan.service','--property=ActiveState,SubState,MainPID']),
            'teaching_lan_socket':command(['systemctl','show','aicademiya-lan.socket','--property=ActiveState,SubState']),
            'listeners':command(['ss','-ltnp']),
            'gpu':command(['nvidia-smi','--query-gpu=index,name,memory.used','--format=csv']),
            'gpu_processes':command(['nvidia-smi','--query-compute-apps=pid,process_name,used_memory','--format=csv']),
            'numa':command(['numactl','--hardware'])}


def sample(pids):
    available = int(next(s for s in Path('/proc/meminfo').read_text().splitlines() if s.startswith('MemAvailable:')).split()[1])//1024
    rss = {}
    for pid in pids:
        try:
            rows = Path(f'/proc/{pid}/status').read_text().splitlines()
            rss[str(pid)] = int(next(s for s in rows if s.startswith('VmRSS:')).split()[1])//1024
        except (FileNotFoundError,StopIteration):
            pass
    return {'elapsed_epoch':time.time(),'available_mib':available,'rss_mib':rss}


def quota():
    p = BASE/'budget-status.json'
    value = json.loads(p.read_text())
    if value['remaining_min_percent'] < 1 or value['paused'] or time.time()-value['checked_epoch'] > 150:
        raise RuntimeError('quota mirror expired/paused/below1%; stop owned work')


def stop_owned(process):
    if process is None or process.poll() is not None:
        return
    os.killpg(process.pid,signal.SIGTERM)
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid,signal.SIGKILL)
        process.wait(timeout=10)


def prepare():
    import pymupdf as fitz
    from PIL import Image
    d = ROOT/'inputs';d.mkdir(exist_ok=True)
    mappings = []
    for name,src,number,rotation in [('chapter1',BASE/'data/dataset/sources/src14.pdf',1,0),
                                     ('guide16-upright',BASE/'data/dataset/sources/src02.pdf',16,90)]:
        original = fitz.open(src)
        pix = original[number-1].get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
        im = Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
        if rotation: im=im.rotate(-rotation,expand=True)
        im.save(d/(name+'.png'))
        out = fitz.open();p=out.new_page(width=im.width,height=im.height);p.insert_image(p.rect,filename=str(d/(name+'.png')));out.save(d/(name+'.pdf'));out.close()
        mappings.append({'derived':name+'.pdf','original_source':src.name,'original_sha256':sha256(src),'original_pdf_page':number,'clockwise_rotation':rotation,'scale':2,'derived_sha256':sha256(d/(name+'.pdf'))})
        original.close()
    im=Image.open(d/'guide16-upright.png')
    crops=[('guide16-label',im,[.20,.285,.80,.355]),
           ('cefr-source-region',Image.open(BASE/'data/dataset/images/sample21.png'),[.442,.302,.613,.560])]
    for name,im,box in crops:
        region=im.crop((int(box[0]*im.width),int(box[1]*im.height),int(box[2]*im.width),int(box[3]*im.height)))
        # Upsampling cannot recover missing source pixels; preserve original crop.
        region.save(d/(name+'.png'))
        out=fitz.open();p=out.new_page(width=region.width,height=region.height);p.insert_image(p.rect,filename=str(d/(name+'.png')));out.save(d/(name+'.pdf'));out.close()
        mappings.append({'derived':name+'.pdf','source':'guide16-upright.png' if name.startswith('guide') else 'sample21.png','source_crop_normalized':box,'derived_sha256':sha256(d/(name+'.pdf')),'source_sha256':sha256(BASE/'data/dataset/images/sample21.png') if name.startswith('cefr') else None})
    dump(ROOT/'source-derived-mappings.json',mappings)
    return d


def main():
    global ROOT
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--run-name',default='',help='fresh isolated probe subdirectory')
    cli.add_argument('--engine',choices=('mineru','region-text'),default='mineru')
    cli.add_argument('--seconds',type=int,default=600)
    cli.add_argument('--cases',default='guide16-label,cefr-source-region,chapter1,guide16-upright')
    cli.add_argument('--runtime',choices=('wheel','native'),default='wheel')
    a=cli.parse_args()
    if sys.platform != 'linux': cli.error('Ubuntu only')
    if a.run_name:
        if not a.run_name.replace('-','').replace('_','').isalnum():cli.error('simple fresh run-name required')
        ROOT=ROOT/a.run_name
        ROOT.mkdir(exist_ok=False)
    else:
        ROOT.mkdir(exist_ok=True)
    before=snapshot();dump(ROOT/'baseline.json',before)
    quota()
    if 'node 0 size: 31372 MB' not in before['numa']['stdout'] or 'node 1 size: 0 MB' not in before['numa']['stdout']:
        raise RuntimeError('NUMA layout differs; recheck before binding')
    with socket.socket() as s:
        s.bind(('127.0.0.1',18893))
    inputs=prepare()
    exe = PILOT/'.venv/lib/python3.12/site-packages/mineru_llama_cpp/bin/llama-server' if a.runtime=='wheel' else BASE/'runtime/bin/llama-server'
    model=PILOT/'mineru-home/models/MinerU2.5-Pro-2605-1.2B-GGUF'
    env={k:v for k,v in os.environ.items() if not k.startswith('LLAMA_')}
    env.update(CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4',HF_HUB_OFFLINE='1',LD_LIBRARY_PATH=str(BASE/'native-libs/usr/lib/x86_64-linux-gnu')+':/home/adminz/llm/toolchains/cuda-12.8/lib')
    args=['numactl','--cpunodebind=0','--membind=0','nice','-n','10',str(exe),'-m',str(model/'MinerU2.5-Pro-2605-1.2B-Q8_0.gguf'),'--mmproj',str(model/'mmproj-MinerU2.5-Pro-2605-1.2B-Q8_0.gguf'),'--alias','mineru-doc','--host','127.0.0.1','--port','18893','-ngl','0','--device','none','--no-mmproj-offload','--no-kv-offload','--no-op-offload','--parallel','1','--ctx-size','8192','--no-kv-unified','--cache-ram','0','--special','--grammar','root ::= .*','--skip-chat-parsing','--no-warmup','--batch-size','512','--ubatch-size','256','--threads','8','--threads-batch','16','--flash-attn','auto']
    receipt={'status':'running','runtime':str(exe),'args':args,'cuda_visible_devices':'','cases':[],'samples':[],'quality_accepted':False}
    server=child=None;start=time.monotonic();deadline=start+a.seconds
    signal.signal(signal.SIGTERM,lambda s,f: (_ for _ in ()).throw(KeyboardInterrupt('owned probe terminated')))
    try:
        with (ROOT/'cpu-server.log').open('w') as log:
            server=subprocess.Popen(args,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        receipt['server_pid']=server.pid
        ready=time.monotonic()+90
        while time.monotonic()<ready:
            if server.poll() is not None: raise RuntimeError('CPU server exited; inspect cpu-server.log')
            try:
                status=json.load(urllib.request.urlopen('http://127.0.0.1:18893/health',timeout=2))
                if status.get('status')=='ok': break
            except Exception: pass
            time.sleep(.5)
        else: raise TimeoutError('CPU server startup90s')
        receipt['startup_seconds']=time.monotonic()-start
        dump(ROOT/'cpu-ready.json',snapshot())
        for name in a.cases.split(','):
            quota()
            if time.monotonic()>=deadline: break
            cmd=['numactl','--cpunodebind=0','--membind=0','nice','-n','10',str(PYTHON),str(Path(__file__).with_name('parser_worker.py')),'--input',str(inputs/(name+'.pdf')),'--output',str(ROOT/'bundles'/name),'--engine',a.engine,'--vlm-url','http://127.0.0.1:18893','--models',str(PILOT/'mineru-home/models'),'--dpi','144','--deadline-seconds',str(max(1,int(deadline-time.monotonic())))]
            if a.engine=='region-text':cmd+=['--regions','{"1":[[0,0,1,1]]}']
            began=time.monotonic();row={'case':name,'command':cmd}
            print(json.dumps({'case':name,'status':'started'}),flush=True)
            with (ROOT/(name+'.log')).open('w') as log:
                child=subprocess.Popen(cmd,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                while child.poll() is None:
                    point=sample([server.pid,child.pid]);receipt['samples'].append(point)
                    dump(ROOT/'probe-receipt.json',receipt)
                    quota()
                    if point['available_mib']<6144: raise MemoryError('reserved6GiB available breached')
                    if time.monotonic()>deadline or time.monotonic()-began>240:
                        row['bounded_stop']=True;stop_owned(child);break
                    time.sleep(2)
            row.update(returncode=child.returncode,seconds=time.monotonic()-began)
            manifest=ROOT/'bundles'/name/'manifest.json'
            if child.returncode==0: row['validation']=validate_bundle(manifest.parent)
            receipt['cases'].append(row);dump(ROOT/'probe-receipt.json',receipt)
            print(json.dumps(row),flush=True)
            if row.get('bounded_stop'): break
        receipt['status']='bounded_completed'
    except BaseException as exc:
        receipt.update(status='failed',error_type=type(exc).__name__,error=str(exc))
    finally:
        stop_owned(child);stop_owned(server)
        after=snapshot();dump(ROOT/'after.json',after)
        # PIDs/config/units stable, worker health evaluated separately from uptime.
        receipt['protected_pids_unchanged']=set(s.split()[0] for s in before['protected_processes'])==set(s.split()[0] for s in after['protected_processes'])
        receipt['configs_unchanged']=before['configs']==after['configs']
        receipt['unit_state_unchanged']=before['units']==after['units'] and before['teaching_user_units']==after['teaching_user_units'] and before['teaching_lan_socket']==after['teaching_lan_socket']
        receipt['workers_healthy_after']=all(w['healthy'] for w in after['router']['workers'])
        receipt['gpu_usage_unchanged']=before['gpu']==after['gpu']
        receipt['owned_port_closed']='127.0.0.1:18893' not in after['listeners']['stdout']
        receipt['wall_seconds']=time.monotonic()-start
        dump(ROOT/'probe-receipt.json',receipt)
        print(json.dumps({k:v for k,v in receipt.items() if k not in ('samples','args')},ensure_ascii=False),flush=True)
    return 0 if receipt['status']=='bounded_completed' and receipt['owned_port_closed'] else 2


if __name__=='__main__': raise SystemExit(main())
