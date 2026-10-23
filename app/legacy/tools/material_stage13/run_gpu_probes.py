"""Bounded real GPU probes. No teaching restart/drain/lease, only owned children."""
import argparse
import datetime
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

BASE=Path('/home/adminz/llm/ocr-stage1-20261009')
HERE=Path(__file__).resolve().parent
GPU='GPU-105b82fb-41db-d6a1-13f0-ceddf5bed313'
PORT=18894
PYTHON=BASE/'whole-document-pilot/.venv/bin/python'
MODELS=BASE/'whole-document-pilot/mineru-home/models'


def dump(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def get(url):
    with urllib.request.urlopen(url,timeout=5) as r:return json.load(r)
def command(args):return subprocess.run(args,capture_output=True,text=True,check=True,timeout=10).stdout

def snapshot():
    gpu=[]
    for line in command(['nvidia-smi','--query-gpu=uuid,memory.used,memory.free','--format=csv,noheader,nounits']).splitlines():
        uuid,used,free=[s.strip() for s in line.split(',')];gpu.append({'uuid':uuid,'used_mib':int(used),'free_mib':int(free)})
    processes=command(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,used_memory','--format=csv,noheader,nounits'])
    return {'router':get('http://127.0.0.1:18280/status'),'gpus':gpu,'gpu_processes':processes,
        'router_config_sha256':hashlib.file_digest((BASE.parent/'aicademiya-router/config.json').open('rb'),'sha256').hexdigest()}

def stop(process):
    if process is None or process.poll() is not None:return
    os.killpg(process.pid,signal.SIGTERM)
    try:process.wait(timeout=8)
    except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)


def main():
    cli=argparse.ArgumentParser();cli.add_argument('--output',required=True);cli.add_argument('--seconds',type=int,default=780)
    cli.add_argument('--cases',default='mixed_pdf,pptx,docx,doc,legacy_scanned_pdf')
    cli.add_argument('--office-hybrid-full',action='store_true',help='verify actual supervisor default across all Office pages')
    a=cli.parse_args();root=Path(a.output);root.mkdir(parents=True,exist_ok=False)
    report={'status':'running','started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'gpu_uuid':GPU,'semantic_quality_approved':False,'teaching_interrupted':False,'cases':[],'samples':[]}
    server=parser=None;begun=time.monotonic()
    def interrupted(*args):raise KeyboardInterrupt('Bounded probe interrupted')
    for s in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):signal.signal(s,interrupted)
    hard_stop=datetime.datetime(2026,10,11,4,30,tzinfo=datetime.timezone.utc).timestamp()
    def sample():
        if time.monotonic()-begun>a.seconds or time.time()>hard_stop:raise TimeoutError('Probe wall/deadline limit')
        state=snapshot();row=next(r for r in state['gpus'] if r['uuid']==GPU)
        report['samples'].append({'elapsed':time.monotonic()-begun,**row})
        if row['free_mib']<200:raise MemoryError('Document co-residency spare memory below200MiB')
        if not all(w['healthy'] for w in state['router']['workers']):raise RuntimeError('Teaching worker health changed')
        if server and server.poll() is not None:raise RuntimeError('Owned document model stopped')
    try:
        before=snapshot();report['before']=before
        assert before['router']['queue']==0 and not any(w['busy'] for w in before['router']['workers'])
        assert all(w['healthy'] for w in before['router']['workers'])
        assert next(r for r in before['gpus'] if r['uuid']==GPU)['free_mib']>=1800
        with socket.socket() as sock:sock.bind(('127.0.0.1',PORT))
        weights=MODELS/'MinerU2.5-Pro-2605-1.2B-GGUF'
        args=['numactl','--cpunodebind=0','--membind=0','nice','-n','10',str(BASE/'runtime/bin/llama-server'),
            '-m',str(weights/'MinerU2.5-Pro-2605-1.2B-Q8_0.gguf'),'--mmproj',str(weights/'mmproj-MinerU2.5-Pro-2605-1.2B-Q8_0.gguf'),
            '--alias','mineru-doc','--host','127.0.0.1','--port',str(PORT),'-ngl','99','--parallel','1','--ctx-size','8192',
            '--no-kv-unified','--cache-ram','0','--special','--grammar','root ::= .*','--skip-chat-parsing','--no-warmup',
            '--batch-size','512','--ubatch-size','256','--threads','4','--threads-batch','8','--flash-attn','auto']
        env={k:v for k,v in os.environ.items() if not k.startswith('LLAMA_')}
        env.update(CUDA_VISIBLE_DEVICES=GPU,CUDA_DEVICE_ORDER='PCI_BUS_ID',LD_LIBRARY_PATH='/home/adminz/llm/toolchains/cuda-12.8/lib')
        with (root/'model.log').open('w') as log:
            server=subprocess.Popen(args,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        report['server_pid']=server.pid;ready=time.monotonic()+90
        while True:
            sample()
            try:
                if get(f'http://127.0.0.1:{PORT}/health').get('status')=='ok':break
            except (OSError,ValueError):pass
            if time.monotonic()>ready:raise TimeoutError('Document model startup90s')
            time.sleep(.3)
        specs={
            'mixed_pdf':('src01.pdf','region-text','5,6,49'),
            'pptx':('src15.pptx','region-text','13,24'),
            'docx':('src17.docx','region-text',''),
            'doc':('src16.doc','region-text',''),
            'legacy_scanned_pdf':('src14.pdf','hybrid','')}
        if a.office_hybrid_full:
            for name in ('pptx','docx','doc'):
                specs[name]=(specs[name][0],'hybrid','')
        env=dict(os.environ,CUDA_VISIBLE_DEVICES='',HF_HUB_OFFLINE='1',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',
            LD_LIBRARY_PATH=str(BASE/'native-libs/usr/lib/x86_64-linux-gnu'))
        for name in a.cases.split(','):
            sample();source_name,engine,selected=specs[name];source=BASE/'data/dataset/sources'/source_name
            seconds=min(430 if name=='legacy_scanned_pdf' else 260,max(1,int(a.seconds-(time.monotonic()-begun))))
            cmd=['numactl','--cpunodebind=0','--membind=0','nice','-n','10',str(PYTHON),str(HERE/'parse_material.py'),
                '--input',str(source),'--output',str(root/name),'--engine',engine,'--vision-pages',selected,
                '--vlm-url',f'http://127.0.0.1:{PORT}','--vlm-device','cuda','--models',str(MODELS),
                '--dpi','120','--deadline-seconds',str(seconds)]
            t=time.monotonic()
            with (root/(name+'.log')).open('w') as log:
                parser=subprocess.Popen(cmd,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            report['parser_pid']=parser.pid
            while parser.poll() is None:
                sample();dump(root/'result.json',report);time.sleep(1)
            m=json.loads((root/name/'manifest.json').read_text(encoding='utf-8'))
            receipt=json.loads((root/name/'receipt.json').read_text(encoding='utf-8'))
            row={'case':name,'source':source_name,'returncode':parser.returncode,'seconds':time.monotonic()-t,
                 'status':receipt['status'],'source_sha256':m['source_sha256'],'page_count':m['page_count'],
                 'coverage':m.get('coverage'),'selected_vision_pages':selected,
                 'source_identity_preserved':m['source_sha256']==hashlib.file_digest(source.open('rb'),'sha256').hexdigest()}
            row['model_processed_pages']=sum(p.get('model_processed',False) for p in receipt['page_timings'])
            row['model_calls']=sum(p.get('model_calls',0) for p in receipt['page_timings'])
            row['selected_page_model_metadata']=[p for p in receipt['page_timings'] if str(p['page']) in selected.split(',')]
            # Independently compare every native block text/ID with raw extraction.
            row['all_native_blocks_retained']=True
            for page in m['pages']:
                raw=json.loads((root/name/f'raw/p{page["number"]:04}-native.json').read_text(encoding='utf-8'))
                by_id={b['id']:b for b in page['blocks']}
                for block in raw['blocks']:
                    ident=f'p{page["number"]}-b{block["index"]}'
                    if ident not in by_id or by_id[ident]['text']!=block['content']:
                        row['all_native_blocks_retained']=False
            report['cases'].append(row);dump(root/'result.json',report)
            print(json.dumps({k:v for k,v in row.items() if k!='coverage'}),flush=True)
            if parser.returncode:raise RuntimeError('Actual source parser failed; failure retained')
            assert row['source_identity_preserved'] and row['all_native_blocks_retained']
        report['status']='passed'
    except BaseException as exc:
        report.update(status='failed',error_type=type(exc).__name__,error=str(exc))
    finally:
        stop(parser);stop(server)
        report['owned_processes_closed']=all(p is None or p.poll() is not None for p in (parser,server))
        try:
            after=snapshot();report['after']=after
            report['teaching_workers_healthy_after']=all(w['healthy'] for w in after['router']['workers'])
            report['router_config_unchanged']=after['router_config_sha256']==report['before']['router_config_sha256']
            report['teaching_gpu_pids_unchanged']=set(report['before']['gpu_processes'].splitlines())==set(after['gpu_processes'].splitlines())
        except Exception as exc:report['readback_error']=str(exc)
        with socket.socket() as sock:report['owned_port_closed']=sock.connect_ex(('127.0.0.1',PORT))!=0
        report['wall_seconds']=time.monotonic()-begun
        if report['samples']:report['observed_min_free_mib']=min(s['free_mib'] for s in report['samples'])
        dump(root/'result.json',report)
        print(json.dumps({k:v for k,v in report.items() if k not in ('before','after','samples','cases')}),flush=True)
    return 0 if report['status']=='passed' and report['owned_port_closed'] else 2


if __name__=='__main__':raise SystemExit(main())
