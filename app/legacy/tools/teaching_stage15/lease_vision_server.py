"""Temporary real vision teaching endpoint under the existing exclusive lease.
Uses fixed teaching weights at64K with reduced microbatch/MTP disabled; no
production config writes. Stop via this run's stop file or bounded unit deadline.
"""
from pathlib import Path
import argparse,json,os,signal,socket,subprocess,sys,threading,time,urllib.request
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from gpu_lease import DocumentLease
STOP=threading.Event()
GPU='GPU-105b82fb-41db-d6a1-13f0-ceddf5bed313'
def api(port,path):
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(f'http://127.0.0.1:{port}'+path,timeout=5)as r:return json.load(r)
def inventory():return subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,used_memory','--format=csv,noheader,nounits'],text=True).splitlines()
def close(p):
 if p is None or p.poll()is not None:return
 try:os.killpg(p.pid,signal.SIGTERM)
 except ProcessLookupError:pass
 try:p.wait(timeout=20)
 except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=10)
def main():
 p=argparse.ArgumentParser();p.add_argument('--timeout',type=int,default=1700);a=p.parse_args()
 assert os.geteuid()==1000
 out=ROOT/'runtime';out.mkdir(exist_ok=False,mode=0o700);port=18896
 with socket.socket()as s:s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('127.0.0.1',port))
 cfg=json.loads(Path('/home/adminz/llm/aicademiya-router/config-materials.json').read_text());w=next(w for w in cfg['workers']if w['name']=='t10b');projector=Path(w['identity']['model']).parent/'mmproj-Qwen3.8-27B-BF16.gguf';assert projector.stat().st_size==931146528
 command=list(w['command'])
 def flag(name,value):
  if name in command:command[command.index(name)+1]=str(value)
  else:command.extend([name,str(value)])
 (out/'cache').mkdir();flag('--port',port);flag('--host','127.0.0.1');flag('--mmproj',projector)
 flag('--ctx-size',65536);flag('--batch-size',256);flag('--ubatch-size',128);flag('--spec-type','none');flag('--image-max-tokens',3072);flag('--slot-save-path',out/'cache');flag('--log-verbosity',4)
 env={k:v for k,v in os.environ.items()if not k.startswith('LLAMA_')};env.update(w['env']);env['CUDA_VISIBLE_DEVICES']=GPU
 for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP):signal.signal(sig,lambda *_:STOP.set())
 started=time.monotonic();lease=None;child=None;report={'status':'starting','source':'isolated vision teaching endpoint, not production router integration','command':command,'initial_allocations':inventory()}
 def save():(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
 try:
  lease=DocumentLease('/home/adminz/llm/material-gpu-state/maintenance.sock','stage15-teaching-'+str(os.getpid()),STOP,expected_uid=os.geteuid());lease.reserve();assert lease.gpu_uuid==GPU
  with(out/'model.log').open('w')as log:child=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
  report['model_pid']=child.pid;ready=False
  while not STOP.is_set()and time.monotonic()-started<a.timeout:
   if (ROOT/'stop').exists():report['status']='stopped_after_test';break
   lease.check()
   if child.poll()is not None:raise RuntimeError('Vision model exited; inspect retained model log')
   memory=int(next(x for x in Path('/proc/meminfo').read_text().splitlines()if x.startswith('MemAvailable:')).split()[1])//1024
   free=int(subprocess.check_output(['nvidia-smi','--id='+GPU,'--query-gpu=memory.free','--format=csv,noheader,nounits'],text=True).strip())
   report['minimum_ram_mib']=min(report.get('minimum_ram_mib',memory),memory);report['minimum_gpu_free_mib']=min(report.get('minimum_gpu_free_mib',free),free)
   if memory<6144 or free<512:raise MemoryError('Vision test memory reserve reached')
   if not ready:
    try:ready=api(port,'/health').get('status')=='ok'
    except OSError:pass
    if ready:
     report.update(status='ready',loaded_allocations=inventory(),props=api(port,'/props'));save();(ROOT/'ready.json').write_text(json.dumps({'port':port,'model_pid':child.pid,'ctx_size':65536,'mmproj_loaded_request':str(projector)})+'\n')
    elif time.monotonic()-started>180:raise TimeoutError('Vision endpoint did not become ready')
   STOP.wait(.5)
  else:report['status']='cancelled_or_deadline'
 except BaseException as e:report.update(status='failed',error_type=type(e).__name__,error=str(e));raise
 finally:
  close(child);report['owned_model_closed']=child is None or child.poll()is not None
  if lease:report['lease_return']=lease.release()
  report['final_allocations']=inventory();report['wall_seconds']=time.monotonic()-started;save();print(json.dumps({k:v for k,v in report.items()if k not in ['command','props']}),flush=True)
if __name__=='__main__':main()
