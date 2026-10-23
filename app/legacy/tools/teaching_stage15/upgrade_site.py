"""Data-preserving Stage15 CT255 rehearsal/cutover, never operates GPU units.
Preflight copies/restores live data and checks every prior named-column row after
new DB initialization. Activate takes a fresh stopped-site backup before switch.
"""
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
import argparse,hashlib,json,os,pwd,shlex,shutil,sqlite3,subprocess,sys,time,urllib.request
NEW=Path('/opt/aicademiya/releases/AIcademiya_V2-20261013-multimodal-r3')
OLD=Path('/opt/aicademiya/releases/AIcademiya_V2-20261011-documents')
CURRENT=Path('/opt/aicademiya/current');DATA=Path('/var/lib/aicademiya');CONF=Path('/etc/aicademiya/aicademiya.conf')
GATE=Path('/run/systemd/system/aicademiya.service.d/90-material-migration.conf')
QA=Path('/var/lib/aicademiya-qa/stage15-exact-r3');PY=NEW/'.venv/bin/python';TOOL=NEW/'tools/backup_data.py'
REHEARSAL=Path('/var/backups/aicademiya-stage15-r3-rehearsal');RESTORE=QA/'production-restore-rehearsal';CUTOVER=Path('/var/backups/aicademiya-stage15-r3-cutover')
BASE='http://192.168.32.55:18773';INITIAL_CONFIG_SHA='cd40a2d47eebde7e43d7114ff0af98a8648e1f7ebbb0dcfc5dbd52aa964f3b37'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(args,timeout=180):return subprocess.run(args,check=True,capture_output=True,text=True,timeout=timeout).stdout
def quoted(name):return '"'+name.replace('"','""')+'"'
def state(path,prior=None):
 with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True)as db:
  names=[x[0]for x in db.execute("select name from sqlite_master where type='table'and name not like 'sqlite_%'")];result={}
  for name in names:
   columns=prior[name]['columns']if prior and name in prior else[x[1]for x in db.execute('pragma table_info('+quoted(name)+')')]
   records=db.execute('select '+','.join(map(quoted,columns))+' from '+quoted(name)).fetchall()
   hashes=Counter(hashlib.sha256(json.dumps(list(row),ensure_ascii=False,separators=(',',':'),default=lambda b:{'bytes':b.hex()}).encode()).hexdigest()for row in records)
   result[name]={'columns':columns,'count':len(records),'row_hashes':dict(hashes)}
  assert db.execute('pragma integrity_check').fetchone()[0]=='ok'and not db.execute('pragma foreign_key_check').fetchall()
  return result
def preserved(before,after):
 for name,row in before.items():assert name in after and not(Counter(row['row_hashes'])-Counter(after[name]['row_hashes'])),'Previous named-column rows changed: '+name
 return {'all_previous_named_column_rows_preserved':True,'tables_checked':len(before),'counts_before':{n:x['count']for n,x in before.items()},'counts_after':{n:x['count']for n,x in after.items()}}
def backup(destination):return json.loads(run([str(PY),str(TOOL),'backup','--data-dir',str(DATA),'--materials-root','/opt/aicademiya/releases','--destination',str(destination)],timeout=180))
def ready():
 end=time.monotonic()+45;opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 while time.monotonic()<end:
  try:
   with opener.open(BASE+'/api/health',timeout=2)as r:
    if json.load(r).get('status')=='ok':return
  except OSError:pass
  time.sleep(.25)
 raise RuntimeError('Site health did not return')
def atomic_config(blob,st):
 temp=CONF.with_name('aicademiya.conf.stage15');assert not temp.exists();temp.write_bytes(blob);temp.chmod(st.st_mode&0o777);os.chown(temp,st.st_uid,st.st_gid);os.replace(temp,CONF)
def link(target):
 temp=CURRENT.with_name('current.stage15');assert not temp.exists()and not temp.is_symlink();temp.symlink_to(target,target_is_directory=True);os.replace(temp,CURRENT)
def preflight():
 assert CURRENT.resolve()==OLD and sha(CONF)==INITIAL_CONFIG_SHA and GATE.is_file()and not REHEARSAL.exists()and not RESTORE.exists()
 report={'status':'running','production_modified':False,'provider_calls':0}
 report['backup']=backup(REHEARSAL);report['restore']=json.loads(run([str(PY),str(TOOL),'restore','--source',str(REHEARSAL),'--destination',str(RESTORE)],timeout=180));assert report['restore']['records_match']and report['restore']['files_match']
 user=pwd.getpwnam('aicademiya')
 for p in [RESTORE,*RESTORE.rglob('*')]:os.chown(p,user.pw_uid,user.pw_gid)
 before=state(RESTORE/'aicademiya.sqlite3')
 code='from backend.aicademiya.db import Database;Database('+repr(str(RESTORE/'aicademiya.sqlite3'))+').initialize('+repr(str(NEW/'sample_data/catalog.json'))+',demo_enabled=False);print("existing_copy_initialized_without_demo_or_provider")'
 run(['runuser','-u','aicademiya','--','env','PYTHONPATH='+str(NEW),'PYTHONDONTWRITEBYTECODE=1',str(PY),'-B','-c',code])
 after=state(RESTORE/'aicademiya.sqlite3',before);report['database']=preserved(before,after);assert CURRENT.resolve()==OLD and sha(CONF)==INITIAL_CONFIG_SHA and GATE.is_file()
 report.update(status='passed',old_release=str(OLD),new_release=str(NEW),config_sha256=INITIAL_CONFIG_SHA,backup_path=str(REHEARSAL),restore_path=str(RESTORE));(QA/'production-rehearsal.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
def activate():
 assert json.loads((QA/'production-rehearsal.json').read_text())['status']=='passed';assert CURRENT.resolve()==OLD and sha(CONF)==INITIAL_CONFIG_SHA and GATE.is_file()and not CUTOVER.exists()
 assert run(['systemctl','is-active','aicademiya.service']).strip()=='active'
 with sqlite3.connect('file:'+str(DATA/'aicademiya.sqlite3')+'?mode=ro',uri=True)as db:
  for table in ('chat_requests','tutor_requests'):assert not db.execute('select 1 from '+table+" where status in ('pending','running') limit 1").fetchone(),'An accepted teaching request is active'
  assert not db.execute("select 1 from document_jobs where status in ('queued','running')limit 1").fetchone(),'An accepted document job is active'
 old_config=CONF.read_bytes();stat=CONF.stat();gate=GATE.read_bytes();switched=False;report={'status':'running','old_release':str(OLD),'new_release':str(NEW),'GPU_services_changed':False}
 grace=GATE.parent/'91-stage15-cutover-grace.conf';assert not grace.exists()
 try:
  # The live unit has a30s stop limit but accepted teaching can run up to600s.
  # Extend only this cutover's graceful stop, not the user manager or GPU units.
  grace.write_text('[Service]\nTimeoutStopSec=660\n');run(['systemctl','daemon-reload'])
  run(['systemctl','stop','aicademiya.service'],timeout=660)
  before=state(DATA/'aicademiya.sqlite3');report['backup']=backup(CUTOVER);(CUTOVER/'config.before').write_bytes(old_config);(CUTOVER/'config.before').chmod(0o600);(CUTOVER/'gate.before').write_bytes(gate)
  worker=['/opt/aicademiya/current/.venv/bin/python','/opt/aicademiya/current/tools/document_stage12/document_ssh_bridge.py','--ssh-host','aicademiya-docs@192.168.32.5','--ssh-key','/var/lib/aicademiya/worker-ssh-stage14/id_ed25519','--known-hosts','/var/lib/aicademiya/worker-ssh-stage14/known_hosts','--timeout','3600']
  updates={'AICADEMIYA_DOCUMENT_WORKER_COMMAND':"'"+json.dumps(worker,separators=(',',':'))+"'",'AICADEMIYA_DOCUMENT_FORMATS':'pdf,pptx,docx,doc,txt,md,png,jpg,jpeg,webp','AICADEMIYA_DOCUMENT_WORKER_TIMEOUT':'3700'}
  lines=old_config.decode().splitlines();seen=set()
  for i,line in enumerate(lines):
   key=line.split('=',1)[0]
   if key in updates:lines[i]=key+'='+updates[key];seen.add(key)
  lines.extend(k+'='+v for k,v in updates.items()if k not in seen);new_config=('\n'.join(lines)+'\n').encode();atomic_config(new_config,stat);switched=True;link(NEW)
  shutil.move(str(GATE),str(CUTOVER/'90-material-migration.conf'));run(['systemctl','daemon-reload']);run(['systemctl','start','aicademiya.service']);ready()
  assert CURRENT.resolve()==NEW and CONF.read_bytes()==new_config and not GATE.exists();after=state(DATA/'aicademiya.sqlite3',before);report['database']=preserved(before,after)
  pid=int(run(['systemctl','show','aicademiya.service','--property=MainPID','--value']).strip());assert Path(f'/proc/{pid}/cwd').resolve()==NEW
  env=dict(x.split(b'=',1)for x in Path(f'/proc/{pid}/environ').read_bytes().split(bytes([0]))if b'='in x)
  assert json.loads(env[b'AICADEMIYA_DOCUMENT_WORKER_COMMAND'])==worker and env[b'AICADEMIYA_DOCUMENT_FORMATS'].decode()==updates['AICADEMIYA_DOCUMENT_FORMATS']
  opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
  with opener.open(BASE+'/api/bootstrap',timeout=5)as r:boot=json.load(r)
  assert boot['demo_enabled']is False
  with opener.open(BASE+'/',timeout=5)as r:html=r.read()
  assert html==(NEW/'frontend/dist/index.html').read_bytes()
  report.update(status='promoted_verified',backup_path=str(CUTOVER),config_after_sha256=sha(CONF),document_worker_available_in_actual_process=True,document_gate_removed=True,demo_disabled=True,site_pid=pid,index_html_matches_release=True)
 except BaseException as e:
  report.update(status='failed',error_type=type(e).__name__,error=str(e))
  if switched:
   run(['systemctl','stop','aicademiya.service'],timeout=660);link(OLD);atomic_config(old_config,stat)
   if not GATE.exists():GATE.parent.mkdir(parents=True,exist_ok=True);GATE.write_bytes(gate)
   run(['systemctl','daemon-reload'])
  run(['systemctl','start','aicademiya.service']);ready();report['old_service_configuration_restored']=True;raise
 finally:
  if grace.exists():shutil.move(str(grace),str(QA/'cutover-grace-retired.conf'));run(['systemctl','daemon-reload'])
  report['completed_at']=datetime.now(timezone.utc).isoformat();(QA/'cutover-result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)
def main():
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['preflight','activate']);p.add_argument('--activate-before',help='Explicit timezone-aware latest safe cutover start');a=p.parse_args();assert os.geteuid()==0
 if a.mode=='activate':
  if not a.activate_before:p.error('Supply --activate-before from the current authorized work window')
  boundary=datetime.fromisoformat(a.activate_before)
  if boundary.tzinfo is None:p.error('--activate-before requires an explicit timezone')
  if datetime.now(timezone.utc)>=boundary:raise RuntimeError('Cutover start boundary reached; leave the current site unchanged')
 manifest=json.loads((QA/(NEW.name+'.manifest.json')).read_text());assert manifest['release']==NEW.name and all(sha(NEW/n)==x['sha256']for n,x in manifest['files'].items())
 (preflight if a.mode=='preflight'else activate)()
if __name__=='__main__':main()
