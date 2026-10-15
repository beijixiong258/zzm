"""Ephemeral document job supervisor; optionally serve one SSH stdio job.

No listening daemon or existing service control. CUDA is explicit administrator
configuration, with CPU layout processing and no silent device fallback. The SSH
connection must remain alive (heartbeats) while the job runs; disconnect cancels
only this job's model/parser children. Production does not depend on Codex quota.
"""
from pathlib import Path
import argparse,fcntl,hashlib,json,os,re,select,signal,socket,subprocess,sys,tarfile,threading,time,uuid
import urllib.request
import shutil
from gpu_lease import DocumentLease, LeaseError
BASE=Path(os.getenv('AICADEMIYA_DOCUMENT_BASE','/home/adminz/llm/ocr-stage1-20261009'))
PILOT=Path(os.getenv('AICADEMIYA_DOCUMENT_RUNTIME',str(BASE/'whole-document-pilot')))
HOME=Path(os.getenv('AICADEMIYA_DOCUMENT_HOME',str(BASE/'stage12-worker')))
STOP=threading.Event()

def runtime_spec():
 gpu=os.getenv('AICADEMIYA_DOCUMENT_GPU_UUID','')
 if gpu and not re.fullmatch(r'GPU-[0-9a-fA-F-]{36}',gpu):raise ValueError('Invalid configured document GPU UUID')
 profile=os.getenv('AICADEMIYA_DOCUMENT_VISION_PROFILE','')
 if profile:
  if not gpu:raise ValueError('Page vision requires the fixed leased CUDA UUID')
  from page_vision_runtime import fixed_vision_profile
  return {'device':'cuda','gpu_uuid':gpu,**fixed_vision_profile(profile,os.getenv('AICADEMIYA_DOCUMENT_VISION_PROFILE_SHA256',''))}
 if gpu:
  runtime=Path(os.getenv('AICADEMIYA_DOCUMENT_CUDA_RUNTIME',str(BASE/'cuda-runtime')))
  libs=Path(os.getenv('AICADEMIYA_DOCUMENT_CUDA_LIBS',str(BASE/'cuda-libs')))
  return {'device':'cuda','gpu_uuid':gpu,'exe':runtime/'bin/llama-server',
          'libraries':os.pathsep.join(map(str,[runtime/'bin',libs,BASE/'native-libs/usr/lib/x86_64-linux-gnu'])),
          'offload':['-ngl','99','--device','CUDA0']}
 return {'device':'cpu','gpu_uuid':'','exe':PILOT/'.venv/lib/python3.12/site-packages/mineru_llama_cpp/bin/llama-server',
         'libraries':str(BASE/'native-libs/usr/lib/x86_64-linux-gnu'),
         'offload':['-ngl','0','--device','none','--no-mmproj-offload','--no-kv-offload','--no-op-offload']}

def gpu_free_mib(gpu):
 p=subprocess.run(['nvidia-smi','--id='+gpu,'--query-gpu=memory.free','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=8,check=True)
 return int(p.stdout.strip())

def terminate(p):
 if p is None or p.poll()is not None:return
 try:os.killpg(p.pid,signal.SIGTERM)
 except ProcessLookupError:return
 try:p.wait(timeout=15)
 except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=10)

def available_mib():return int(next(s for s in Path('/proc/meminfo').read_text().splitlines()if s.startswith('MemAvailable:')).split()[1])//1024

def numa_node():
 nodes=[]
 for p in Path('/sys/devices/system/node').glob('node[0-9]*/meminfo'):
  m=re.search(r'MemTotal:\s+(\d+)',p.read_text())
  if m:nodes.append((int(m[1]),int(p.parent.name[4:])))
 return max(nodes)[1]

def budget_ok():
 d=json.loads((BASE/'budget-status.json').read_text())
 return d['remaining_min_percent']>=1 and not d['paused']and time.time()-d['checked_epoch']<150

def cpu_prefix():
 node=numa_node()
 return node,['numactl',f'--cpunodebind={node}',f'--membind={node}','nice','-n','15']

def runtime_python():return PILOT/'.venv/bin/python'

def ensure_model_port_available(port=18893):
 # A closed prior server can leave TIME_WAIT sockets. REUSEADDR ignores those,
 # but still refuses a live listener; never treat kernel TIME_WAIT as a model.
 with socket.socket()as probe:
  probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
  probe.bind(('127.0.0.1',port))

def run_job(source,out,timeout=3600,quota_guard=False):
 from parser_helpers import validate_bundle
 source,out=Path(source),Path(out)
 if not source.is_file() or source.is_symlink() or any(p.is_symlink()for p in source.parents):raise ValueError('Safe original source required')
 if out.exists()or out.is_symlink():raise ValueError('Output must be a fresh directory')
 if source.stat().st_size>64*1024*1024:raise ValueError('Input exceeds64MiB')
 suffix=source.suffix.lower()
 if suffix not in ('.pdf','.pptx','.ppt','.docx','.doc','.xls','.xlsx','.txt','.md','.png','.jpg','.jpeg','.webp'):raise ValueError('Unsupported complete document format')
 HOME.mkdir(parents=True,exist_ok=True,mode=0o700)
 lock=(HOME/'serial.lock').open('a')
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:
  lock.close();raise RuntimeError('Document worker is busy; retry after the active job')
 server=worker=lease=None;prepared=None;spec=None;lease_error=None;cleanup_error=None
 started=time.monotonic();deadline=started+timeout
 with source.open('rb')as stream:source_hash=hashlib.file_digest(stream,'sha256').hexdigest()
 scratch=HOME/'jobs'/uuid.uuid4().hex;scratch.mkdir(parents=True,mode=0o700)
 report={'status':'running','phase':'native_preparation','device':'cpu','layout_device':'cpu',
         'gpu_uuid':None,'minimum_available_mib':available_mib(),'fresh_inference':False,
         'source_sha256':source_hash,'gpu_lease_required':True,'gpu_lease_used':False}
 def guard(check_gpu=False):
  if lease is not None and lease.gpu_uuid is not None:lease.check()
  free=available_mib();report['minimum_available_mib']=min(report['minimum_available_mib'],free)
  if STOP.is_set():raise RuntimeError('Client disconnected or job cancelled')
  if time.monotonic()>deadline:raise TimeoutError('Document job deadline reached')
  if free<6144:raise MemoryError('Document worker preserves6GiB available memory')
  if check_gpu:
   free_gpu=gpu_free_mib(spec['gpu_uuid']);report['minimum_gpu_free_mib']=min(report.get('minimum_gpu_free_mib',free_gpu),free_gpu)
   if free_gpu<(2100 if server is None else 512 if spec.get('page_markdown')else 256):raise MemoryError('Document GPU has insufficient free memory; retry later. No CPU fallback was started.')
  if quota_guard and not budget_ok():raise RuntimeError('Development quota guard stopped job')
 def wait_worker(check_gpu=False):
  while worker.poll()is None:
   guard(check_gpu);STOP.wait(.25)
  guard(check_gpu)
  if worker.returncode:raise RuntimeError('Parser failed; partial output and receipt are retained')
 def parse_command(target,engine,extra=()):
  entry=Path(__file__).with_name('parser_worker.py')if suffix=='.pdf'else Path(__file__).resolve().parents[1]/'material_stage13/parse_material.py'
  return prefix+[str(runtime_python()),str(entry),'--input',str(source),'--output',str(target),
        '--engine',engine,'--dpi','144','--deadline-seconds',str(max(1,int(deadline-time.monotonic())))]+list(extra)
 try:
  node,prefix=cpu_prefix();report['numa_node']=node
  env={k:v for k,v in os.environ.items()if not k.startswith('LLAMA_')}
  env.update(CUDA_VISIBLE_DEVICES='',CUDA_DEVICE_ORDER='PCI_BUS_ID',HF_HUB_OFFLINE='1',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4')
  prepared=scratch/'native';guard()
  with(scratch/'native.log').open('w')as log:
   worker=subprocess.Popen(parse_command(prepared,'native'),env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  report['native_parser_pid']=worker.pid;wait_worker();worker=None
  manifest=json.loads((prepared/'manifest.json').read_text())
  native_receipt=json.loads((prepared/'receipt.json').read_text())
  validate_bundle(prepared,manifest)
  if manifest['source_sha256']!=source_hash or native_receipt.get('status')!='complete':raise ValueError('Native preparation identity or completion mismatch')
  sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'material_stage13'))
  from prepared_material import visual_plan
  plan=visual_plan(manifest,native_receipt);report['visual_plan']=plan
  report['native_preparation_seconds']=time.monotonic()-started
  if not plan['needs_gpu']:
   shutil.move(str(prepared),str(out));prepared=None
   report.update(status='complete',phase='complete',execution_kind='native_only',model_processed_pages=0,validation=validate_bundle(out))
  else:
   spec=runtime_spec()
   socket_path=os.getenv('AICADEMIYA_DOCUMENT_GPU_LEASE_SOCKET','')
   if spec['device']!='cuda' or not socket_path:raise LeaseError('Visual document work requires the configured exclusive GPU lease; no co-residency or CPU fallback')
   ensure_model_port_available()
   report['phase']='waiting_for_gpu'
   lease=DocumentLease(socket_path,scratch.name,STOP,expected_gpu=spec['gpu_uuid'],
         expected_uid=int(os.getenv('AICADEMIYA_DOCUMENT_GPU_OWNER_UID','1000')),
         reserve_timeout=min(855,max(1,deadline-time.monotonic())))
   begun=time.monotonic();gpu=lease.reserve()
   report.update(gpu_lease_used=True,gpu_wait_seconds=time.monotonic()-begun,device='cuda',gpu_uuid=gpu,phase='model_startup')
   spec['gpu_uuid']=gpu

   env.update(spec.get('environment',{}));env.update(CUDA_VISIBLE_DEVICES=gpu,LD_LIBRARY_PATH=spec['libraries'])
   models=PILOT/'mineru-home/models';weights=models/'MinerU2.5-Pro-2605-1.2B-GGUF'
   if spec.get('page_markdown'):
    args=prefix+spec['command'];report['visual_backend']='native+live-page-markdown'
   else:
    args=prefix+[str(spec['exe']),'-m',str(weights/'MinerU2.5-Pro-2605-1.2B-Q8_0.gguf'),
        '--mmproj',str(weights/'mmproj-MinerU2.5-Pro-2605-1.2B-Q8_0.gguf'),'--alias','mineru-doc',
        '--host','127.0.0.1','--port','18893']+spec['offload']+['--parallel','1','--ctx-size','8192',
        '--no-kv-unified','--cache-ram','0','--special','--grammar','root ::= .*','--skip-chat-parsing',
        '--no-warmup','--batch-size','512','--ubatch-size','256','--threads','8','--threads-batch','16','--flash-attn','auto']
   guard(True)
   begun=time.monotonic()
   with(scratch/'model.log').open('w')as log:server=subprocess.Popen(args,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
   report['model_pid']=server.pid;ready=time.monotonic()+90
   opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
   while True:
    guard(True)
    if server.poll()is not None:raise RuntimeError('Configured document model failed to start; inspect its retained log')
    try:
     with opener.open('http://127.0.0.1:18893/health',timeout=2)as r:healthy=json.load(r).get('status')=='ok'
     if healthy:
      if spec.get('page_markdown'):
       with opener.open('http://127.0.0.1:18893/props',timeout=2)as r:props=json.load(r)
       if props.get('modalities',{}).get('vision')is not True:raise RuntimeError('Fixed page-vision model did not load its projector')
      break
    except(OSError,ValueError):pass
    if time.monotonic()>ready:raise TimeoutError('Document model readiness timeout')
    STOP.wait(.25)
   report.update(model_load_seconds=time.monotonic()-begun,phase='visual_processing')
   extra=['--vlm-url','http://127.0.0.1:18893','--vlm-device','cuda','--models',str(models),
          '--layout-pages',','.join(map(str,plan['fullpage_pages']))]
   if suffix!='.pdf':extra+=['--prepared-dir',str(prepared)]
   parser_args=parse_command(out,'hybrid',extra)
   if spec.get('page_markdown'):
    page_entry=Path(__file__).resolve().parents[1]/'material_stage15/page_worker.py'
    parser_args=prefix+[str(runtime_python()),str(page_entry),'--prepared-dir',str(prepared),'--output',str(out),
       '--vlm-url','http://127.0.0.1:18893','--model',spec['model_alias'],'--pages',','.join(map(str,plan['visual_pages'])),
       '--ctx-size',str(spec['context_size']),'--deadline-seconds',str(max(1,int(deadline-time.monotonic())))]
   with(scratch/'parser.log').open('w')as log:worker=subprocess.Popen(parser_args,env={**env,'CUDA_VISIBLE_DEVICES':''},stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
   report['parser_pid']=worker.pid;wait_worker(True)
   report['validation']=validate_bundle(out)
   parser_receipt=json.loads((out/'receipt.json').read_text())
   report['model_processed_pages']=sum(bool(x.get('model_processed',False))for x in parser_receipt['page_timings'])
   if spec.get('page_markdown'):
    report.update(representation_complete=True,visual_transcription_complete=parser_receipt.get('visual_transcription_complete',False),
      model_calls=parser_receipt.get('model_calls',0),visual_failed_pages=parser_receipt.get('visual_failed_pages',[]))
   report.update(status='complete',phase='complete',execution_kind='leased_gpu',fresh_inference=report['model_processed_pages']>0)
 except BaseException as e:
  report.update(status='failed',error_type=type(e).__name__,error=str(e));raise
 finally:
  cleanup_failures=[]
  for owned in (worker,server):
   try:terminate(owned)
   except Exception as error:cleanup_failures.append(type(error).__name__)
  try:
   report['owned_processes_closed']=all(p is None or p.poll()is not None for p in [server,worker])
   if cleanup_failures or not report['owned_processes_closed']:
    cleanup_error=RuntimeError('Owned document process cleanup failed; GPU remains held')
    report.update(status='failed',cleanup_errors=cleanup_failures,error_type='CleanupError',error=str(cleanup_error))
   # Return ownership ONLY after every owned GPU process is positively closed.
   if lease is not None:
    try:
     if not report['owned_processes_closed']:raise LeaseError('Owned processes not closed; GPU return remains held')
     report['gpu_return']=lease.release()
    except LeaseError as error:
     report['gpu_return']={'acknowledged':False,'error':str(error)}
     if report['status']=='complete':
      report.update(status='failed',error_type='LeaseError',error='Document parsed but GPU return was not acknowledged')
      lease_error=error
    report['gpu_lease']=lease.evidence()
   out.mkdir(parents=True,exist_ok=True);(out/'raw').mkdir(exist_ok=True)
   if prepared is not None and(prepared/'receipt.json').exists():
    shutil.copyfile(prepared/'receipt.json',out/'raw/native-preparation-receipt.json')
    if(prepared/'manifest.json').exists():shutil.copyfile(prepared/'manifest.json',out/'raw/native-preparation-manifest.json')
   report['wall_seconds']=time.monotonic()-started
   (out/'raw/supervisor.json').write_text(json.dumps(report,indent=2)+'\n')
   (scratch/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
  finally:lock.close()
  if cleanup_error is not None:raise cleanup_error
  if lease_error is not None:raise lease_error
 return report

def stdio_job():
 raw=sys.stdin.buffer.readline(8193)
 if len(raw)>8192:raise ValueError('Oversized job header')
 header=json.loads(raw);size=header.get('bytes');digest=header.get('sha256');suffix=header.get('suffix','.pdf')
 if type(size)is not int or not 0<size<=64*1024*1024 or not isinstance(digest,str)or not re.fullmatch('[a-f0-9]{64}',digest)or suffix not in ('.pdf','.pptx','.ppt','.docx','.doc','.xls','.xlsx','.txt','.md','.png','.jpg','.jpeg','.webp'):raise ValueError('Invalid job header')
 workspace=HOME/'incoming'/uuid.uuid4().hex;workspace.mkdir(parents=True,mode=0o700)
 source=workspace/('input'+suffix);remaining=size
 with source.open('xb')as f:
  while remaining:
   b=sys.stdin.buffer.read(min(1048576,remaining))
   if not b:raise ValueError('Incomplete input')
   f.write(b);remaining-=len(b)
 with source.open('rb')as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
 if actual!=digest:raise ValueError('Source checksum mismatch')
 watch_done=threading.Event()
 def watch():
  # Do not hold BufferedReader's lock in a daemon at interpreter shutdown.
  # The real completed transfer reproduced _enter_buffered_busy on stdin.
  fd=sys.stdin.fileno()
  try:
   while not watch_done.is_set():
    if select.select([fd],[],[],.2)[0]:
     data=os.read(fd,80)
     if not data or any(c not in (46,10) for c in data):STOP.set();return
  except OSError:STOP.set()
 watcher=threading.Thread(target=watch,daemon=True);watcher.start()
 out=workspace/'bundle';rc=0
 try:run_job(source,out)
 except BaseException:rc=2
 finally:watch_done.set();watcher.join(timeout=1)
 if out.is_dir():
  archive=workspace/'result.tar.gz'
  with tarfile.open(archive,'w:gz')as t:t.add(out,arcname='.',recursive=True)
  with archive.open('rb')as f:
   while b:=f.read(1048576):sys.stdout.buffer.write(b)
  sys.stdout.buffer.flush()
 return rc

def main():
 for signum in [signal.SIGTERM,signal.SIGINT,signal.SIGHUP]:signal.signal(signum,lambda *_:STOP.set())
 p=argparse.ArgumentParser();p.add_argument('--stdio',action='store_true');p.add_argument('--input');p.add_argument('--output');p.add_argument('--timeout',type=int,default=3600);p.add_argument('--quota-guard',action='store_true');a=p.parse_args()
 if a.stdio:return stdio_job()
 if not a.input or not a.output:p.error('--input and --output required')
 try:print(json.dumps(run_job(Path(a.input),Path(a.output),a.timeout,a.quota_guard)));return 0
 except BaseException as e:print(json.dumps({'status':'failed','error_type':type(e).__name__,'error':str(e)}));return 2
if __name__=='__main__':raise SystemExit(main())
