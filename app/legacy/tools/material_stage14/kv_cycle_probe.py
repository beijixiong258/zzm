"""Real teaching runtime disk-state proof across one owned document cycle.
Direct slot API under the closed/drained router gate, not router cache selection.
"""
from pathlib import Path
import argparse,asyncio,json,shutil,subprocess,sys,urllib.request
ROOT=Path('/home/adminz/llm/operations/stage14-kv-cycle-r1')
sys.path.insert(0,'/opt/aicademiya-gpu-scheduler/releases/stage14-runtime-r2')
from maintenance_control import client
SOCKET='/home/adminz/llm/material-gpu-state/maintenance.sock'
def control(op):return asyncio.run(client(SOCKET,op))
def api(base,path,body=None):
 req=urllib.request.Request(base+path,data=json.dumps(body).encode()if body is not None else None,headers={'Content-Type':'application/json'})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=240)as r:return json.load(r)
def pids():return subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid','--format=csv,noheader,nounits'],text=True).splitlines()
def main():
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','restore']);a=p.parse_args();ROOT.mkdir(exist_ok=True,mode=0o700)
 cfg=json.loads(Path('/home/adminz/llm/aicademiya-router/config-materials.json').read_text());w=next(x for x in cfg['workers']if x['name']=='t10b');base=w['url'];assert base.startswith('http://127.0.0.1:')
 statefile=ROOT/'prepared.json';out=ROOT/(a.mode+'-result.json');assert not out.exists();report={'status':'running','direct_runtime_test':True,'router_cache_selection_tested':False,'disk_cold_or_reboot_tested':False}
 s=api('http://127.0.0.1:18280','/status');assert s['resources']['phase']=='teaching'and s['teaching_capacity']==3
 try:
  control('close');d=control('drain');assert not d['busy']and not d['accepted_requests'];before=pids()
  if a.mode=='prepare':
   assert not statefile.exists();filename='stage14-kv-cycle-r1.bin';file=Path(cfg['cache_dir'])/filename;assert not file.exists();assert shutil.disk_usage(file.parent).free>4*1024**3
   messages=[{'role':'system','content':'Isolated synthetic cache test; no student data.\n'+''.join(f'Synthetic record {n}: formative feedback identifies what to practice next.\n'for n in range(100))},{'role':'user','content':'Reply with READY.'}]
   rendered=api(base,'/apply-template',{'messages':messages,'reasoning_effort':'none'})['prompt'];tokens=api(base,'/tokenize',{'content':rendered,'add_special':False})['tokens'];assert 256<=len(tokens)<8192
   generated=api(base,'/completion',{'prompt':tokens,'id_slot':0,'n_predict':1,'cache_prompt':False,'temperature':0})
   saved=api(base,'/slots/0?action=save',{'filename':filename});assert saved.get('n_saved',0)>=len(tokens)and file.is_file()and not file.is_symlink()
   st=file.stat();state={'tokens':tokens,'file':str(file),'file_identity':[st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns],'pids':before,'saved':saved};statefile.write_text(json.dumps(state)+'\n');statefile.chmod(0o600)
   report.update(status='prepared',prompt_tokens=len(tokens),saved=saved,bytes=st.st_size,pids=before,initial_generation={k:generated.get(k)for k in ('timings','tokens_cached','tokens_evaluated','stop_type')})
  else:
   state=json.loads(statefile.read_text());file=Path(state['file']);assert file.parent==Path(cfg['cache_dir'])and file.name=='stage14-kv-cycle-r1.bin';st=file.stat();assert[st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns]==state['file_identity']
   elastic='GPU-105b82fb-41db-d6a1-13f0-ceddf5bed313';old=[x for x in state['pids']if x.startswith(elastic)];new=[x for x in before if x.startswith(elastic)];assert len(old)==len(new)==1 and old!=new
   assert sorted(x for x in before if not x.startswith(elastic))==sorted(x for x in state['pids']if not x.startswith(elastic))
   restored=api(base,'/slots/0?action=restore',{'filename':file.name});assert restored.get('n_restored',0)>=len(state['tokens'])
   extra=api(base,'/tokenize',{'content':' Recovery check. Reply OK.','add_special':False})['tokens']
   generated=api(base,'/completion',{'prompt':state['tokens']+extra,'id_slot':0,'n_predict':8,'cache_prompt':True,'temperature':0})
   report.update(restored=restored,completion=generated,old_t10b=old,new_t10b=new,anchor_pids_preserved=True,prompt_tokens=len(state['tokens']))
   cached=generated.get('timings',{}).get('cache_n');report['actual_cached_tokens']=cached;report['cache_metric']='completion.timings.cache_n';report['post_completion_tokens_cached']=generated.get('tokens_cached')
   assert isinstance(cached,int)and cached>=len(state['tokens'])-8,'Actual cache reuse not established'
   report.update(status='passed',new_process_disk_state_restore=True,actual_cache_reuse=True,filesystem_page_cache_may_be_warm=True)
 finally:
  report['inlet_after']=control('open');out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items()if k!='inlet_after'}))
if __name__=='__main__':main()
