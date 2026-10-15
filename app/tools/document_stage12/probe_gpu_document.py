"""Bounded GPU document probe alongside existing teaching; owns only its children."""
from pathlib import Path
import concurrent.futures,datetime,hashlib,json,os,signal,socket,subprocess,sys,threading,time,urllib.request
BASE=Path('/home/adminz/llm/ocr-stage1-20261009')
PILOT=BASE/'whole-document-pilot'
GPU='GPU-105b82fb-41db-d6a1-13f0-ceddf5bed313'
ROOT=Path(sys.argv[1]);ROOT.mkdir(parents=True,exist_ok=False,mode=0o700)
SOURCE=BASE/'data/dataset/sources/src14.pdf'
CFG=Path('/home/adminz/llm/aicademiya-router/config.json')
report={'status':'running','started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'gpu_uuid':GPU,'teaching_interrupted':False,'quality_accepted':False,'samples':[]}
server=parser=None;start=time.monotonic();load_pool=load_future=None
def get(url):
 with urllib.request.urlopen(url,timeout=5)as r:return json.load(r)
def gpu():
 p=subprocess.run(['nvidia-smi','--query-gpu=uuid,memory.used,memory.free','--format=csv,noheader,nounits'],capture_output=True,text=True,check=True,timeout=8)
 rows=[]
 for line in p.stdout.splitlines():
  u,used,free=(s.strip()for s in line.split(','));rows.append({'uuid':u,'used_mib':int(used),'free_mib':int(free)})
 return next(x for x in rows if x['uuid']==GPU)
def stop(p):
 if p is None or p.poll()is not None:return
 os.killpg(p.pid,signal.SIGTERM)
 try:p.wait(timeout=15)
 except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=10)
def sample():
 row=gpu();row['elapsed']=round(time.monotonic()-start,3);report['samples'].append(row)
 if server and server.poll()is not None:raise RuntimeError('Owned GPU server exited; inspect model.log')
 if time.monotonic()-start>900:raise TimeoutError('Bounded GPU probe timeout')
def interrupted(sig,frame):raise KeyboardInterrupt('Probe interrupted')
def teaching_smoke():
 deadline=time.monotonic()+60
 while time.monotonic()<deadline:
  try:
   receipt=json.loads((ROOT/'bundle/receipt.json').read_text())
   if receipt['page_timings'] and receipt['status']=='running':break
  except (OSError,ValueError):pass
  if parser.poll()is not None:return {'status':'not_run_parser_ended'}
  time.sleep(.2)
 else:return {'status':'not_run_no_first_page'}
 barrier=threading.Barrier(3)
 def call(i):
  text='\n'.join(f'Record {j}: This synthetic reference entry only exercises prefill memory alongside document OCR. It is not a learner record.'for j in range(90))
  body={'model':'AIcademiya-64kx3-Qwen3.8-27B','messages':[{'role':'user','content':'Read the test data and reply only READY.\n'+text}],'temperature':0,'max_tokens':8,'stream':False}
  barrier.wait(timeout=10);t=time.monotonic()
  req=urllib.request.Request('http://127.0.0.1:18280/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
  try:
   with urllib.request.urlopen(req,timeout=90)as r:return {'worker':r.headers.get('X-AIcademiya-Worker'),'http':r.status,'seconds':time.monotonic()-t,'response':json.load(r)}
  except Exception as e:return {'error':str(e),'seconds':time.monotonic()-t}
 with concurrent.futures.ThreadPoolExecutor(max_workers=3)as pool:rows=list(pool.map(call,range(3)))
 passed={x.get('worker')for x in rows}=={'v100','t10a','t10b'}and all(x.get('http')==200 and x['response']['choices'][0]['message']['content'].strip()=='READY'for x in rows)
 return {'status':'passed'if passed else'failed','label':'synthetic simultaneous prefill memory smoke, not answer-quality benchmark','document_pages_at_start':len(receipt['page_timings']),'responses':rows}
for sig in [signal.SIGTERM,signal.SIGINT,signal.SIGHUP]:signal.signal(sig,interrupted)
try:
 report['before_status']=get('http://127.0.0.1:18280/status')
 assert report['before_status']['queue']==0 and not any(w['busy']for w in report['before_status']['workers'])
 assert all(w['healthy']for w in report['before_status']['workers'])
 report['config_sha256']=hashlib.file_digest(CFG.open('rb'),'sha256').hexdigest()
 report['source_sha256']=hashlib.file_digest(SOURCE.open('rb'),'sha256').hexdigest()
 report['before_gpu']=gpu()
 assert report['before_gpu']['free_mib']>=1800,'Insufficient room even for bounded co-residency probe'
 with socket.socket()as s:s.bind(('127.0.0.1',18894))
 # Current server has memory on node0 only; no stale node1 binding.
 prefix=['numactl','--cpunodebind=0','--membind=0','nice','-n','10']
 weights=PILOT/'mineru-home/models/MinerU2.5-Pro-2605-1.2B-GGUF'
 args=prefix+[str(BASE/'runtime/bin/llama-server'),'-m',str(weights/'MinerU2.5-Pro-2605-1.2B-Q8_0.gguf'),'--mmproj',str(weights/'mmproj-MinerU2.5-Pro-2605-1.2B-Q8_0.gguf'),'--alias','mineru-doc','--host','127.0.0.1','--port','18894','-ngl','99','--parallel','1','--ctx-size','8192','--no-kv-unified','--cache-ram','0','--special','--grammar','root ::= .*','--skip-chat-parsing','--no-warmup','--batch-size','512','--ubatch-size','256','--threads','4','--threads-batch','8','--flash-attn','auto']
 env={k:v for k,v in os.environ.items()if not k.startswith('LLAMA_')};env.update(CUDA_VISIBLE_DEVICES=GPU,CUDA_DEVICE_ORDER='PCI_BUS_ID',LD_LIBRARY_PATH='/home/adminz/llm/toolchains/cuda-12.8/lib')
 with (ROOT/'model.log').open('w')as f:server=subprocess.Popen(args,env=env,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
 report['model_pid']=server.pid;deadline=time.monotonic()+90
 while True:
  sample()
  try:
   if get('http://127.0.0.1:18894/health').get('status')=='ok':break
  except (OSError,ValueError):pass
  if time.monotonic()>deadline:raise TimeoutError('GPU VLM readiness timeout')
  time.sleep(.25)
 # Keep native/layout models on CPU; the separate VLM process uses CUDA.
 penv=dict(os.environ,CUDA_VISIBLE_DEVICES='',HF_HUB_OFFLINE='1',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',LD_LIBRARY_PATH=str(BASE/'native-libs/usr/lib/x86_64-linux-gnu'))
 command=prefix+[str(PILOT/'.venv/bin/python'),str(BASE/'stage12-parser/parser_worker.py'),'--input',str(SOURCE),'--output',str(ROOT/'bundle'),'--engine','hybrid','--vlm-url','http://127.0.0.1:18894','--vlm-device','cuda','--models',str(PILOT/'mineru-home/models'),'--dpi','144','--deadline-seconds','780']
 with (ROOT/'parser.log').open('w')as f:parser=subprocess.Popen(command,env=penv,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
 report['parser_pid']=parser.pid
 if '--teaching-load' in sys.argv[2:]:
  load_pool=concurrent.futures.ThreadPoolExecutor(max_workers=1);load_future=load_pool.submit(teaching_smoke)
 while parser.poll()is None:sample();time.sleep(.2)
 assert parser.returncode==0,'Parser failed; raw evidence retained'
 receipt=json.loads((ROOT/'bundle/receipt.json').read_text());report['parser_receipt']=receipt
 assert receipt['status']=='complete'and len(receipt['page_timings'])==10
 assert all(x['mode']=='mineru-cuda-local-vlm'for x in receipt['page_timings'])
 if load_future:
  report['concurrent_teaching']=load_future.result(timeout=105)
  assert report['concurrent_teaching']['status']=='passed','Concurrent teaching smoke did not pass'
 report['status']='passed'
except BaseException as e:
 report.update(status='failed',error_type=type(e).__name__,error=str(e))
finally:
 stop(parser);stop(server)
 if load_pool:load_pool.shutdown(wait=True)
 report['seconds']=time.monotonic()-start
 report['owned_processes_closed']=all(p is None or p.poll()is not None for p in [parser,server])
 if report['samples']:
  report['observed_peak_total_used_mib']=max(x['used_mib']for x in report['samples'])
  report['observed_minimum_free_mib']=min(x['free_mib']for x in report['samples'])
 try:
  report['after_status']=get('http://127.0.0.1:18280/status');report['after_gpu']=gpu()
  report['config_unchanged']=hashlib.file_digest(CFG.open('rb'),'sha256').hexdigest()==report.get('config_sha256')
 except Exception as e:report['readback_error']=str(e)
 (ROOT/'result.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items()if k not in ['samples','parser_receipt','before_status','after_status']}))
raise SystemExit(0 if report['status']=='passed'else 1)
