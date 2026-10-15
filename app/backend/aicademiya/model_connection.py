"""On-demand, shared30s lightweight AI reachability cache; no generation.
Ordinary bootstrap/status reads stay network-free. Authenticated UI polling uses
this explicit endpoint; credentials/bindings and exception bodies stay private.
"""
from datetime import datetime,timezone,timedelta
import json,threading,time
import httpx
from fastapi import Depends
from .ai import use_environment_proxy
from .service_settings import check_snapshot

class ModelConnectionMonitor:
 interval=30
 def __init__(self,db,tutor):self.db=db;self.tutor=tutor;self.lock=threading.Lock();self.saved=None
 def settings(self):
  with self.db.connect()as c:
   config=self.tutor.settings(c);binding=check_snapshot(c,'ai',self.tutor.check_config(config))
  return config,binding
 def result(self,status,model,message,kind,**extra):
  now=datetime.now(timezone.utc)
  return {'status':status,'model':model,'message':message,'check_kind':kind,'checked_at':now.isoformat(),'expires_at':(now+timedelta(seconds=60)).isoformat(),'poll_interval_seconds':self.interval,**extra}
 def check(self):
  with self.lock:
   config,binding=self.settings();model=config['model']
   if config['mode']!='openai' or not(config['base_url'].strip()and model.strip()):return self.result('not_configured',model,'No real model endpoint configured.','configuration')
   if self.saved and self.saved['binding']==binding and time.monotonic()-self.saved['time']<self.interval:return dict(self.saved['result'])
   base=config['base_url'].rstrip('/');router=self.tutor.uses_aicademiya_router(config);endpoint=base[:-3]+'/health'if router else base+('/models'if base.endswith('/v1')else'/v1/models');kind='router_health'if router else'model_listing'
   headers={'Accept-Encoding':'identity'}
   if config['api_key']:headers['Authorization']='Bearer '+config['api_key']
   try:
    with httpx.Client(timeout=httpx.Timeout(5,connect=3),transport=self.tutor.transport,follow_redirects=False,trust_env=use_environment_proxy(base))as client:
     with client.stream('GET',endpoint,headers=headers)as response:
      response.raise_for_status()
      if response.headers.get('content-encoding','identity').lower()!='identity':raise ValueError('Unexpected compressed health response')
      chunks=[];size=0
      for chunk in response.iter_bytes():
       size+=len(chunk)
       if size>512*1024:raise ValueError('Oversized health response')
       chunks.append(chunk)
    data=json.loads(b''.join(chunks))
    if not isinstance(data,dict):raise ValueError('Invalid health response')
    if router:
     capacity=data.get('teaching_capacity');vision=data.get('vision_teaching_capacity',0)
     if type(capacity)is not int or capacity<=0 or data.get('model')!=model:raise ValueError('No healthy configured teaching capacity')
     result=self.result('connected',model,'Teaching endpoint is reachable.','router_health',teaching_capacity=capacity,vision_teaching_capacity=vision)
    else:
     if not isinstance(data.get('data'),list)or model not in {x.get('id')for x in data['data']if isinstance(x,dict)}:raise ValueError('Configured model unavailable')
     result=self.result('connected',model,'Endpoint is reachable and lists the configured model.','model_listing')
   except (httpx.HTTPError,ValueError,TypeError,KeyError):result=self.result('error',model,'Configured model endpoint is unavailable.','endpoint_health')
   current,current_binding=self.settings()
   if binding!=current_binding:return self.result('checking',current['model'],'Settings changed; checking the current model.','configuration')
   self.saved={'binding':binding,'time':time.monotonic(),'result':result};return dict(result)

def register_model_connection(app,db,tutor,current_user):
 monitor=ModelConnectionMonitor(db,tutor);app.state.model_connection_monitor=monitor
 @app.get('/api/ai/connection')
 def connection(user=Depends(current_user)):
  return monitor.check()
