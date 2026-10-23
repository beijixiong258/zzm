"""Stage11 built UI/API/SQLite acceptance with owned synthetic servers and real restart."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,os,sqlite3,subprocess,sys,uuid
import httpx
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from run_stage4_integration import free_port,ready,stop,listener_closed
from run_stage9_integration import serve

def catalog(folder):
 from PIL import Image
 (folder/'assets').mkdir();Image.new('RGB',(160,100),(42,94,73)).save(folder/'assets/diagram.png')
 (folder/'materials').mkdir();(folder/'materials/reading.txt').write_text('Synthetic public reading only.');(folder/'materials/key.txt').write_text('Synthetic private reference; do not expose.')
 description='Synthetic multi-course learning space. This authored description uses the available banner width instead of a narrow fixed column.\n\n(1) Preserve this first teaching objective on its own line.\n(2) Preserve this second objective and all intentional blank lines.'
 q={'id':'s11-q','group_id':'core','ordinal':1,'type':'open_response','prompt':'Explain a synthetic concept with evidence.','options':[],'answer_slots':1,'images':[{'label':'A','url':'/api/assets/diagram.png','alt':'Synthetic diagram'}],'source_label':'Synthetic worksheet','hint':'Use a concrete example.'}
 s={'id':'s11-session','course_id':'s11-course','number':1,'title':'Synthetic first session','subtitle':'Isolated QA only','status':'published','estimated_minutes':30,'learning_objectives':['Explain with evidence'],'instructions':'Synthetic instructions, no real model required.','reference_policy':'after_attempt','teaching_language':'en','groups':[{'id':'core','title':'Core','kind':'core'}],'questions':[q],'reference_answers':{'s11-q':'Synthetic teacher reference.'},'materials':[{'id':'s11-public','title':'Synthetic reading','kind':'reading','visibility':'student','source_label':'Synthetic','status':'ready','excerpt':'Synthetic public context.','file_path':'materials/reading.txt'},{'id':'s11-private','title':'Synthetic key','kind':'answer_key','visibility':'teacher','source_label':'Synthetic private','status':'ready','excerpt':'Synthetic private reference.','file_path':'materials/key.txt'}]}
 (folder/'catalog.json').write_text(json.dumps({'schema_version':1,'course':{'id':'s11-course','code':'EDUC7703','title':'Synthetic multi-course seminar','description':description},'sessions':[s]}),encoding='utf-8')

def evidence(folder):
 with sqlite3.connect(folder/'data/aicademiya.sqlite3')as c:
  tables=[x[0]for x in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")];r={'schema':c.execute('PRAGMA user_version').fetchone()[0],'integrity':c.execute('PRAGMA integrity_check').fetchone()[0],'fk_violations':len(c.execute('PRAGMA foreign_key_check').fetchall()),'counts':{t:c.execute('SELECT count(*) FROM "'+t+'"').fetchone()[0]for t in tables}}
  assert r['schema']==int(os.environ.get('AICADEMIYA_QA_TARGET_SCHEMA','8')) and r['integrity']=='ok'and r['fk_violations']==0
 return r

def main():
 p=argparse.ArgumentParser();p.add_argument('--serve',type=int);p.add_argument('--folder');p.add_argument('--skip-browser',action='store_true');p.add_argument('--skip-api',action='store_true');a=p.parse_args()
 if a.serve:
  f=Path(a.folder).resolve();assert f.is_relative_to(ROOT/'artifacts/stage11') and (f/'catalog.json').is_file();serve(a.serve,f);return 0
 assert not(a.skip_api and a.skip_browser)
 if not a.skip_browser:
  index=ROOT/'frontend/dist/index.html';assert index.is_file()and index.stat().st_mtime>=max(f.stat().st_mtime for n in ('src','public')for f in (ROOT/'frontend'/n).rglob('*')if f.is_file()),'Build current dist first'
 out=ROOT/'artifacts/stage11'/('integration-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]);out.mkdir(parents=True)
 env=os.environ.copy();scratch=os.environ['TMPDIR'];env.update(TMPDIR=scratch,TEMP=scratch,TMP=scratch,AICADEMIYA_DEMO_ENABLED='true',AICADEMIYA_AI_MODE='demo',AICADEMIYA_AI_PROVIDER='',AICADEMIYA_AI_BASE_URL='',AICADEMIYA_AI_MODEL='',AICADEMIYA_AI_API_KEY='',AICADEMIYA_WEB_SEARCH_ENABLED='false',TAVILY_API_KEY='',AICADEMIYA_ALLOWED_ORIGINS='',AICADEMIYA_COOKIE_SECURE='false',NODE_TLS_REJECT_UNAUTHORIZED='1',NO_PROXY='127.0.0.1,localhost,::1',no_proxy='127.0.0.1,localhost,::1')
 for n in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy'):env.pop(n,None)
 groups=[]
 for name,command in [('api',[sys.executable,'tools/stage11_api_acceptance.py']),('browser',['node','tools/stage11_browser_acceptance.mjs'])]:
  if(name=='api'and a.skip_api)or(name=='browser'and a.skip_browser):continue
  folder=out/name;folder.mkdir();(folder/'data').mkdir();catalog(folder);port=free_port();base=f'http://127.0.0.1:{port}';e=env.copy();e.update(AICADEMIYA_DATA_DIR=str(folder/'data'),AICADEMIYA_QA_DB=str(folder/'data/aicademiya.sqlite3'),AICADEMIYA_QA_PYTHON=sys.executable);rec={'name':name,'status':'failed'};proc=None;log=(folder/'server.log').open('w',encoding='utf-8')
  def start():
   pr=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--serve',str(port),'--folder',str(folder)],cwd=ROOT,env=e,stdout=log,stderr=subprocess.STDOUT);ready(pr,base);return pr
  try:
   proc=start();done=subprocess.run(command+['--base-url',base,'--artifact-dir',str(folder),'--confirm-test-data'],cwd=ROOT,env=e,capture_output=True,text=True,timeout=600);(folder/'harness.log').write_text(done.stdout+'\n'+done.stderr,encoding='utf-8');rec['acceptance']=json.loads((folder/'result.json').read_text());assert done.returncode==0 and rec['acceptance']['status']=='passed',done.stdout+done.stderr
   metrics=json.loads((folder/'provider-metrics.json').read_text());assert metrics['model_calls']==metrics['search_calls']==metrics['model_protocol_calls']==metrics['search_protocol_calls']==0;rec['provider_metrics']=metrics
   ids=rec['acceptance']['ids'];stop(proc);assert listener_closed(port);proc=start()
   with httpx.Client(base_url=base,trust_env=False,timeout=20)as c:
    assert c.post('/api/auth/demo',json={'role':'admin'}).status_code==200
    st=c.get('/api/courses/'+ids['course']+'/staff').json();assert st['course']['owner_id']==ids['primary'];assert sorted(x['user']['id']for x in st['staff'])==ids['staff_user_ids']
    if ids.get('import_id'):
     state=c.get('/api/admin/users/import/'+ids['import_id']).json();assert state['status']=='committed'and state['result']==ids['import_result']
    if ids.get('learner_answer'):
     c.post('/api/auth/demo',json={'role':'student','student_index':2}).raise_for_status();w=c.get('/api/sessions/'+ids['learner_session']+'/workspace',params={'version_id':ids['learner_version']}).json();assert w['attempts'][ids['learner_question']]['answer']==ids['learner_answer']
   rec['real_restart_staff_import_work_verified']=True;rec['status']='passed'
  except Exception as ex:rec['error']=str(ex)
  finally:
   if proc:stop(proc)
   log.close();rec['owned_server_stopped']=bool(proc and proc.poll()is not None);rec['owned_listener_closed']=listener_closed(port)
   if not rec['owned_server_stopped']or not rec['owned_listener_closed']:rec['status']='failed'
   try:rec['sqlite']=evidence(folder)
   except Exception as ex:rec['sqlite_error']=str(ex);rec['status']='failed'
   groups.append(rec);(out/'result.json').write_text(json.dumps({'status':'running','groups':groups},indent=2));print(json.dumps({'group':name,'status':rec['status'],'checks':len(rec.get('acceptance',{}).get('checks',[])),'error':rec.get('error')}),flush=True)
 r={'status':'passed'if all(g['status']=='passed'for g in groups)else'failed','final_acceptance':not a.skip_api and not a.skip_browser and all(g['status']=='passed'for g in groups),'groups':groups,'synthetic_only':True,'real_model_or_search_calls':0};(out/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'status':r['status'],'final_acceptance':r['final_acceptance'],'result':str(out/'result.json')}));return 0 if r['status']=='passed'else 1
if __name__=='__main__':raise SystemExit(main())
