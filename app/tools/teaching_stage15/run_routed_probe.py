"""Actual candidate router + leased vision endpoint; private QA cache only.
No production router/config/cache changes. Full image token endpoint, cache
bypass, real SSE and downstream cancellation are exercised against real GPU.
"""
from pathlib import Path
import base64,json,os,signal,sqlite3,subprocess,sys,time,urllib.request,uuid
ROOT=Path(__file__).resolve().parent
URL='http://127.0.0.1:18284'
def request(base,path,body=None,timeout=180):
 req=urllib.request.Request(base+path,data=json.dumps(body).encode()if body is not None else None,headers={'Content-Type':'application/json'})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=timeout)as r:return json.load(r),dict(r.headers)
def stop(p):
 if p is None or p.poll()is not None:return
 p.terminate()
 try:p.wait(timeout=45)
 except subprocess.TimeoutExpired:p.kill();p.wait(timeout=10)
def wait_ready(base,child,timeout=180):
 until=time.monotonic()+timeout
 while time.monotonic()<until:
  if child.poll()is not None:raise RuntimeError('Owned QA process exited before readiness')
  try:
   value,_=request(base,'/health',timeout=3)
   if value.get('status')=='ok'or value.get('teaching_capacity')==1:return value
  except OSError:pass
  time.sleep(.3)
 raise TimeoutError('Owned QA endpoint readiness')
def main():
 assert os.getuid()==1000
 report={'status':'running','actual_GPU':True,'production_changed':False,'checks':[],'responses':[]};runtime=router=None
 def save():(ROOT/'routed-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 try:
  with(ROOT/'runtime-launch.log').open('w')as log:runtime=subprocess.Popen([sys.executable,str(ROOT/'lease_vision_server.py'),'--timeout','1000'],stdout=log,stderr=subprocess.STDOUT)
  wait_ready('http://127.0.0.1:18896',runtime)
  props,_=request('http://127.0.0.1:18896','/props');assert props['modalities']['vision']is True
  cache=ROOT/'runtime/cache';cache.chmod(0o700)
  existing=json.loads(Path('/home/adminz/llm/aicademiya-router/config-materials.json').read_text());model=next(w for w in existing['workers']if w['name']=='t10b')['identity']['model'];projector=str(Path(model).parent/'mmproj-Qwen3.8-27B-BF16.gguf')
  # No command: the owned lease launcher, not this QA router, owns the model.
  config={'port':18284,'cache_dir':str(cache),'cache_quota_bytes':2*1024**3,'queue_limit':8,'workers':[{'name':'t10b','url':'http://127.0.0.1:18896','identity':{'scope':'isolated-stage15-real-routing','model':model,'projector':projector},'env':{'LLAMA_ARG_MMPROJ':projector,'LLAMA_ARG_CTX_SIZE':'65536','LLAMA_ARG_N_PARALLEL':'1','LLAMA_ARG_IMAGE_MAX_TOKENS':'3072'}}]}
  (ROOT/'router.json').write_text(json.dumps(config,indent=2)+'\n')
  with(ROOT/'router.log').open('w')as log:router=subprocess.Popen([sys.executable,str(ROOT/'code/router.py'),'--config',str(ROOT/'router.json')],stdout=log,stderr=subprocess.STDOUT)
  ready=wait_ready(URL,router);assert ready['vision_teaching_capacity']==1 and ready['workers'][0]['context_window']==65536
  def catalog():
   db=sqlite3.connect('file:'+str(cache/'catalog.sqlite3')+'?mode=ro',uri=True);rows=db.execute('select * from entries order by id').fetchall();db.close();return rows
  # Real text request establishes one private snapshot in this run's cache.
  text={'model':'AIcademiya-64kx3-Qwen3.8-27B','messages':[{'role':'system','content':'Synthetic cache baseline. '+('No student data. '*100)},{'role':'user','content':'Reply OK.'}],'user':'stage15-routed-text-'+uuid.uuid4().hex,'max_tokens':8,'temperature':0,'stream':False}
  plain,headers=request(URL,'/v1/chat/completions',text);assert plain['choices'];before=catalog();assert before,'No actual text snapshot created';report['text_cache_rows_before']=len(before)
  files={row[4]:[ (cache/row[4]).stat().st_size,(cache/row[4]).stat().st_mtime_ns]for row in before}
  def payload(names,stream=False,long=False):
   content=[{'type':'text','text':'Return only one main visible heading, no explanation.'if not long else 'Transcribe the visible source paragraphs faithfully and in full.'}]
   for name in names:content.append({'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode((ROOT/'input'/name).read_bytes()).decode()}})
   result={'model':'AIcademiya-64kx3-Qwen3.8-27B','messages':[{'role':'system','content':'Read visible source content only.'},{'role':'user','content':content}],'user':'stage15-routed-same-image-scope','temperature':0,'max_tokens':512 if long else 64,'stream':stream,'chat_template_kwargs':{'enable_thinking':False}}
   if stream:result['stream_options']={'include_usage':True}
   return result
  names=json.loads((ROOT/'inputs.json').read_text())
  for name in names:
   response,headers=request(URL,'/v1/chat/completions',payload([name]));state,_=request(URL,'/status');metrics=state['workers'][0]['metrics']
   assert headers.get('X-AIcademiya-Worker')=='t10b'and headers.get('X-KV-Restored')=='false'
   assert metrics['cache_mode']=='bypass-multimodal'and metrics['counted_prompt_tokens']==response['usage']['prompt_tokens']
   assert response['usage']['prompt_tokens_details']['cached_tokens']==0
   assert catalog()==before
   report['responses'].append({'source':name,'headers':headers,'response':response,'metrics':metrics});save()
  assert report['responses'][0]['response']['choices'][0]['message']['content']!=report['responses'][1]['response']['choices'][0]['message']['content']
  report['checks'].append('Different real images with identical text/scope bypass text cache; actual input_tokens equals actual generation usage')
  opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));body=payload(names,stream=True)
  req=urllib.request.Request(URL+'/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
  with opener.open(req,timeout=180)as r:wire=r.read();stream_headers=dict(r.headers)
  (ROOT/'stream-response.sse').write_bytes(wire);assert b'[DONE]'in wire;usage=None
  for line in wire.splitlines():
   if line.startswith(b'data:')and line[5:].strip()!=b'[DONE]':
    event=json.loads(line[5:])
    if isinstance(event.get('usage'),dict):usage=event['usage']
  state,_=request(URL,'/status');metrics=state['workers'][0]['metrics'];assert usage and metrics['backend_usage']==usage and metrics['counted_prompt_tokens']==usage['prompt_tokens'];assert metrics['image_count']==2
  report['stream']={'headers':stream_headers,'usage':usage,'metrics':metrics};report['checks'].append('Actual two-image SSE retained wire bytes and actual usage')
  req=urllib.request.Request(URL+'/v1/chat/completions',data=json.dumps(payload([names[1]],stream=True,long=True)).encode(),headers={'Content-Type':'application/json'})
  with opener.open(req,timeout=180)as r:
   while True:
    line=r.readline()
    if not line:raise RuntimeError('Stream ended before a cancellation point')
    if line.startswith(b'data:')and b'content'in line:report['cancel_first_line']=line.decode();break
  until=time.monotonic()+45
  while time.monotonic()<until:
   state,_=request(URL,'/status');slots,_=request('http://127.0.0.1:18896','/slots')
   if not state['workers'][0]['busy']and not slots[0]['is_processing']:break
   time.sleep(.25)
  else:raise RuntimeError('Cancelled image generation did not positively become idle')
  assert catalog()==before
  assert all([(cache/name).stat().st_size,(cache/name).stat().st_mtime_ns]==values for name,values in files.items())
  report['checks'].append('Actual downstream cancellation released only after backend idle; private text snapshot rows/files unchanged')
  report.update(status='passed',final_router=state,private_text_cache_preserved=True);save()
 except BaseException as e:report.update(status='failed',error_type=type(e).__name__,error=str(e));save();raise
 finally:
  stop(router)
  if runtime is not None:
   (ROOT/'stop').write_text('Routed probe complete; return owned GPU.')
   try:runtime.wait(timeout=100)
   except subprocess.TimeoutExpired:stop(runtime)
  if (ROOT/'runtime/result.json').is_file():report['runtime']=json.loads((ROOT/'runtime/result.json').read_text())
  report['qa_router_closed']=router is None or router.poll()is not None;save();print(json.dumps({k:report[k]for k in ('status','checks','error')if k in report}),flush=True)
if __name__=='__main__':main()
