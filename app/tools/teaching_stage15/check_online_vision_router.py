"""Real installed router: heterogeneous queue, decoded SSE cancel, source image.
Synthetic scopes only. No services/models started or stopped; no cache edits.
"""
from pathlib import Path
import asyncio,base64,hashlib,json,sqlite3,subprocess,time,uuid
import aiohttp
ROOT=Path('/home/adminz/llm/operations/stage15-deploy-r1')
OUT=ROOT/'online-check-r1';INPUT=Path('/home/adminz/llm/operations/stage15-routed-r1/input');BASE='http://127.0.0.1:18280'
def cache_state():
 cfg=json.loads(Path('/home/adminz/llm/aicademiya-router/config-materials-vision-stage15-r1.json').read_text());root=Path(cfg['cache_dir'])
 with sqlite3.connect('file:'+str(root/'catalog.sqlite3')+'?mode=ro',uri=True)as db:rows=db.execute('select * from entries order by id').fetchall()
 return rows,{r[4]:[(root/r[4]).stat().st_size,(root/r[4]).stat().st_mtime_ns]for r in rows}
def inventory():return subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid','--format=csv,noheader,nounits'],text=True).splitlines()
async def main():
 assert not OUT.exists();OUT.mkdir(mode=0o700)
 report={'status':'running','actual_GPU':True,'installed_router':True,'synthetic_scope_only':True,'services_changed':False,'checks':[]};first=None;second=None
 before=cache_state();pids=inventory();wire=[];tag='stage15-live-'+uuid.uuid4().hex
 async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300),trust_env=False)as session:
  async def get(path,base=BASE):
   async with session.get(base+path)as r:r.raise_for_status();return await r.json()
  async def post(body):
   async with session.post(BASE+'/v1/chat/completions',json=body)as r:r.raise_for_status();return {'response':await r.json(),'headers':dict(r.headers)}
  def payload(name,scope,stream=False):
   raw=(INPUT/name).read_bytes();report.setdefault('inputs',{})[name]=hashlib.sha256(raw).hexdigest()
   text='Transcribe the entire visible page faithfully as Markdown, retaining every heading and table cell.'if stream else 'Return only one main visible heading, no explanation.'
   b={'model':'AIcademiya-64kx3-Qwen3.8-27B','user':tag+scope,'temperature':0,'max_tokens':1024 if stream else 64,'stream':stream,'chat_template_kwargs':{'enable_thinking':False},'messages':[{'role':'system','content':'Read visible source content only.'},{'role':'user','content':[{'type':'text','text':text},{'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(raw).decode()}}]}]}
   if stream:b['stream_options']={'include_usage':True}
   return b
  try:
   start=await get('/status');assert start['vision_teaching_capacity']==1 and start['teaching_capacity']==3 and not start['queue']and all(not w['busy']for w in start['workers'])
   first=await session.post(BASE+'/v1/chat/completions',json=payload('01-native-page126.png','-cancel',True));first.raise_for_status();assert first.headers['X-AIcademiya-Worker']=='t10b'
   # The former probe cancelled at an initial role/content:null event. Here
   # actual nonempty decoded content is required before declaring cancellation.
   while True:
    line=await first.content.readline();assert line,'Stream ended before decoded content';wire.append(line)
    if not line.startswith(b'data:')or line[5:].strip()==b'[DONE]':continue
    event=json.loads(line[5:]);content=event.get('choices',[{}])[0].get('delta',{}).get('content')
    if isinstance(content,str)and content:report['decoded_content_before_cancel']=content;break
   second=asyncio.create_task(post(payload('07-sample14.png','-queued')))
   end=time.monotonic()+10
   while time.monotonic()<end:
    queued=await get('/status')
    if queued['queue']>=1:break
    assert not second.done(),'Image wait did not overlap active source decoding';await asyncio.sleep(.05)
   else:raise RuntimeError('Second image was not observed in queue')
   assert next(w for w in queued['workers']if w['name']=='t10b')['busy']
   t=time.monotonic();text=await post({'model':'AIcademiya-64kx3-Qwen3.8-27B','user':tag+'-text','messages':[{'role':'user','content':'Reply with the single word READY.'}],'temperature':0,'max_tokens':8,'stream':False,'chat_template_kwargs':{'enable_thinking':False}})
   report['text_while_image_waited']={**text,'wall_seconds':time.monotonic()-t};assert text['headers']['X-AIcademiya-Worker']in ('v100','t10a')and not second.done()
   slots=await get('/slots','http://127.0.0.1:18332');assert slots[0]['is_processing']is True
   report['checks'].append('Text-only GPU served a real text completion while an earlier image waited for busy vision GPU')
   first.close();first=None;report['cancel_after_decoded_content']=True
   report['queued_image']=await second;second=None
   image=report['queued_image'];assert image['headers']['X-AIcademiya-Worker']=='t10b'and image['headers']['X-KV-Restored']=='false'
   assert 'MELAB'in image['response']['choices'][0]['message']['content'];assert image['response']['usage']['prompt_tokens_details']['cached_tokens']==0
   end=time.monotonic()+45
   while time.monotonic()<end:
    final=await get('/status');slots=await get('/slots','http://127.0.0.1:18332')
    if not final['queue']and all(not w['busy']for w in final['workers'])and slots[0]['is_processing']is False:break
    await asyncio.sleep(.1)
   else:raise RuntimeError('Installed router did not return idle')
   metric=next(w for w in final['workers']if w['name']=='t10b')['metrics'];assert metric['cache_mode']=='bypass-multimodal'and metric['counted_prompt_tokens']==image['response']['usage']['prompt_tokens']
   assert cache_state()==before and sorted(inventory())==sorted(pids)
   report.update(status='passed',final_vision_metrics=metric,cache_rows_preserved=len(before[0]),cache_files_preserved=True,model_pids_preserved=True,final_router=final)
   report['checks'].extend(['Nonempty decoded SSE was cancelled; the waiting source image then completed on the same vision worker','Actual source heading, image token budget/usage, cache bypass, final idle and unchanged cache/PIDs verified'])
  except BaseException as e:report.update(status='failed',error_type=type(e).__name__,error=str(e));raise
  finally:
   if first is not None:first.close()
   if second is not None and not second.done():second.cancel();await asyncio.gather(second,return_exceptions=True)
   (OUT/'cancel-response-prefix.sse').write_bytes(b''.join(wire));(OUT/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report[k]for k in ('status','checks','error')if k in report}),flush=True)
if __name__=='__main__':asyncio.run(main())
