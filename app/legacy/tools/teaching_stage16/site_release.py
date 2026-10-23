"""Stage16 exact app release staging/rehearsal/cutover on CT255 only.
Preserves all prior named-column records and files. No GPU unit operations.
"""
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
import argparse,hashlib,json,os,pwd,shutil,sqlite3,subprocess,time,urllib.request

NAME='AIcademiya_V2-stage16-workflow-r4'
QA=Path('/var/lib/aicademiya-qa/stage16-release-r4');SRC=QA/'extracted'/NAME
NEW=Path('/opt/aicademiya/releases')/NAME;OLD=Path('/opt/aicademiya/releases/AIcademiya_V2-20261013-multimodal-r3')
CURRENT=Path('/opt/aicademiya/current');DATA=Path('/var/lib/aicademiya');CONF=Path('/etc/aicademiya/aicademiya.conf')
PY=NEW/'.venv/bin/python';BACKUP=NEW/'tools/backup_data.py';BASE='http://192.168.32.55:18773'
REHEARSAL=Path('/var/backups/aicademiya-stage16-r4-rehearsal');RESTORE=QA/'restore-rehearsal';CUTOVER=Path('/var/backups/aicademiya-stage16-r4-cutover')
FORMATS='pdf,pptx,ppt,docx,doc,xls,xlsx,txt,md,png,jpg,jpeg,webp'
def sha(p):
 with Path(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def run(args,timeout=180):return subprocess.run(list(map(str,args)),capture_output=True,text=True,check=True,timeout=timeout).stdout
def save(name,value):
 (QA/name).write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value,indent=2),flush=True)
def manifest(root):
 m=json.loads((QA/(NAME+'.manifest.json')).read_text());assert m['release']==NAME
 for n,v in m['files'].items():assert sha(root/n)==v['sha256'],n
 return m

def pyinfo(py):
 code="import sys,sysconfig,importlib.metadata as m,json;print(json.dumps({'version':list(sys.version_info[:3]),'purelib':sysconfig.get_path('purelib'),'packages':{d.metadata['Name'].lower():d.version for d in m.distributions()if d.metadata['Name']}}))"
 return json.loads(run([py,'-B','-c',code]))
def stage():
 assert CURRENT.resolve()==OLD and not NEW.exists();m=manifest(SRC);user=pwd.getpwnam('aicademiya');assert user.pw_uid==999
 assert sha(SRC/'backend/requirements.txt')==sha(OLD/'backend/requirements.txt')
 previous=pyinfo(OLD/'.venv/bin/python');site=Path(previous['purelib']);assert not any(p.is_symlink()for p in site.rglob('*'))and not list(site.glob('*.pth'))
 size=sum(p.stat().st_size for p in site.rglob('*')if p.is_file());assert shutil.disk_usage(NEW.parent).free>size*2+1024**3
 shutil.copytree(SRC,NEW)
 for p in [NEW,*NEW.rglob('*')]:
  os.chown(p,0,user.pw_gid);p.chmod(0o750 if p.is_dir()else m['files'][p.relative_to(NEW).as_posix()]['mode']|0o040)
 run(['/usr/bin/python3','-m','venv','--without-pip',NEW/'.venv']);own=pyinfo(PY);assert own['version']==previous['version']
 shutil.copytree(site,Path(own['purelib']),dirs_exist_ok=True);copied=pyinfo(PY);assert copied['packages']==previous['packages']
 for p in [NEW/'.venv',*(NEW/'.venv').rglob('*')]:
  if p.is_symlink():continue
  os.chown(p,0,user.pw_gid);mode=p.stat().st_mode&0o777;p.chmod((mode&~0o022)|0o040|(0o010 if p.is_dir()or mode&0o111 else 0))
 check_staged()

def check_staged():
 assert CURRENT.resolve()==OLD
 m=manifest(NEW);user=pwd.getpwnam('aicademiya');previous=pyinfo(OLD/'.venv/bin/python');copied=pyinfo(PY)
 assert previous['version']==copied['version'] and previous['packages']==copied['packages']
 assert sha(NEW/'backend/requirements.txt')==sha(OLD/'backend/requirements.txt')
 os.chown(QA,0,user.pw_gid);QA.chmod(0o750)  # Owned QA traversal, not public/private-source access.
 check=run([PY,'-m','pip','check']);assert 'No broken requirements found'in check
 smoke=QA/'staged-smoke';smoke.mkdir(mode=0o700,exist_ok=True);os.chown(smoke,user.pw_uid,user.pw_gid)
 catalog={'schema_version':1,'course':{'id':'s16-smoke','code':'SYNTHETIC','title':'Synthetic archive smoke','description':'No real classroom data'},'sessions':[]}
 (smoke/'catalog.json').write_text(json.dumps(catalog));os.chown(smoke/'catalog.json',user.pw_uid,user.pw_gid)
 code="from pathlib import Path;from backend.aicademiya.main import create_app;import backend.aicademiya.main as m;from fastapi.testclient import TestClient;assert Path(m.__file__).is_relative_to(Path("+repr(str(NEW))+"));\nwith TestClient(create_app(data_dir=Path("+repr(str(smoke/'data'))+"),catalog_path=Path("+repr(str(smoke/'catalog.json'))+"),demo_enabled=True))as c:\n assert c.get('/api/health').status_code==200;assert c.post('/api/auth/demo',json={'role':'teacher'}).status_code==200;assert c.get('/api/ai/connection').json()['status']=='not_configured';print('UID999 Stage16 app boot verified')"
 text=run(['runuser','-u','aicademiya','--','env','PYTHONPATH='+str(NEW),'PYTHONDONTWRITEBYTECODE=1','AICADEMIYA_AI_MODE=demo','AICADEMIYA_WEB_SEARCH_ENABLED=false','AICADEMIYA_DOCUMENT_WORKER_COMMAND=',PY,'-B','-c',code]);assert 'UID999 Stage16 app boot verified'in text
 assert CURRENT.resolve()==OLD
 save('stage-result.json',{'status':'staged_not_promoted','release':str(NEW),'files':len(m['files']),'requirements_unchanged':True,'packages_unchanged':True,'package_count':len(copied['packages']),'python_version':copied['version'],'pip_check':check.strip(),'uid999_boot':True,'production_unchanged':True})

def quoted(name):return '"'+name.replace('"','""')+'"'
def state(path,prior=None):
 with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True)as db:
  result={}
  for (name,)in db.execute("select name from sqlite_master where type='table'and name not like 'sqlite_%'"):
   columns=prior[name]['columns']if prior and name in prior else[x[1]for x in db.execute('pragma table_info('+quoted(name)+')')]
   rows=db.execute('select '+','.join(map(quoted,columns))+' from '+quoted(name)).fetchall()
   result[name]={'columns':columns,'count':len(rows),'hashes':dict(Counter(hashlib.sha256(json.dumps(list(row),ensure_ascii=False,separators=(',',':'),default=lambda b:{'bytes':b.hex()}).encode()).hexdigest()for row in rows))}
  assert db.execute('pragma integrity_check').fetchone()[0]=='ok'and not db.execute('pragma foreign_key_check').fetchall()
  return result

def preserved(before,after):
 for name,row in before.items():assert name in after and not(Counter(row['hashes'])-Counter(after[name]['hashes'])),'Existing rows changed: '+name
 return {'all_previous_named_column_rows_preserved':True,'tables':len(before),'counts_before':{k:v['count']for k,v in before.items()},'counts_after':{k:v['count']for k,v in after.items()}}
def backup(dest):return json.loads(run([PY,BACKUP,'backup','--data-dir',DATA,'--materials-root','/opt/aicademiya/releases','--destination',dest],timeout=240))
def rehearsal():
 assert CURRENT.resolve()==OLD and not REHEARSAL.exists()and not RESTORE.exists();manifest(NEW);initial=sha(CONF)
 result={'backup':backup(REHEARSAL)};result['restore']=json.loads(run([PY,BACKUP,'restore','--source',REHEARSAL,'--destination',RESTORE],timeout=240));assert result['restore']['records_match']and result['restore']['files_match']
 user=pwd.getpwnam('aicademiya')
 for p in [RESTORE,*RESTORE.rglob('*')]:os.chown(p,user.pw_uid,user.pw_gid)
 before=state(RESTORE/'aicademiya.sqlite3')
 code='from backend.aicademiya.db import Database;Database('+repr(str(RESTORE/'aicademiya.sqlite3'))+').initialize('+repr(str(NEW/'sample_data/catalog.json'))+',demo_enabled=False)'
 run(['runuser','-u','aicademiya','--','env','PYTHONPATH='+str(NEW),'PYTHONDONTWRITEBYTECODE=1',PY,'-B','-c',code])
 result['database']=preserved(before,state(RESTORE/'aicademiya.sqlite3',before));assert CURRENT.resolve()==OLD and sha(CONF)==initial
 result.update(status='passed',config_sha256=initial,production_unchanged=True,provider_calls=0);save('rehearsal-result.json',result)

def idle():
 with sqlite3.connect('file:'+str(DATA/'aicademiya.sqlite3')+'?mode=ro',uri=True)as db:
  for table in ['chat_requests','tutor_requests']:assert not db.execute('select 1 from '+table+" where status in ('pending','running') limit 1").fetchone(),'Accepted teaching request active'
  assert not db.execute("select 1 from document_jobs where status in ('queued','running')limit 1").fetchone(),'Accepted document job active'
def ready():
 end=time.monotonic()+45;opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 while time.monotonic()<end:
  try:
   with opener.open(BASE+'/api/health',timeout=2)as r:
    if json.load(r)['status']=='ok':return
  except OSError:pass
  time.sleep(.25)
 raise RuntimeError('Website did not return healthy')
def link(target):
 temp=CURRENT.with_name('current.stage16');assert not temp.exists()and not temp.is_symlink();temp.symlink_to(target,target_is_directory=True);os.replace(temp,CURRENT)
def config(blob,st):
 temp=CONF.with_name('aicademiya.conf.stage16');assert not temp.exists();temp.write_bytes(blob);temp.chmod(st.st_mode&0o777);os.chown(temp,st.st_uid,st.st_gid);os.replace(temp,CONF)
def activate():
 assert json.loads((QA/'stage-result.json').read_text())['status']=='staged_not_promoted'
 proof=json.loads((QA/'worker-app-result.json').read_text());assert proof['status']=='passed'and proof['installed_worker_uid']==999
 r=json.loads((QA/'rehearsal-result.json').read_text());assert r['status']=='passed'and sha(CONF)==r['config_sha256']
 assert CURRENT.resolve()==OLD and not CUTOVER.exists();manifest(NEW);idle();old_config=CONF.read_bytes();st=CONF.stat()
 grace=Path('/run/systemd/system/aicademiya.service.d/91-stage16-cutover.conf');assert not grace.exists();grace.parent.mkdir(parents=True,exist_ok=True)
 changed=False;report={'status':'running','old_release':str(OLD),'new_release':str(NEW),'GPU_services_changed':False}
 try:
  grace.write_text('[Service]\nTimeoutStopSec=660\n');run(['systemctl','daemon-reload']);run(['systemctl','stop','aicademiya.service'],timeout=660)
  before=state(DATA/'aicademiya.sqlite3');report['backup']=backup(CUTOVER);(CUTOVER/'config.before').write_bytes(old_config);(CUTOVER/'config.before').chmod(0o600)
  worker=['/opt/aicademiya/current/.venv/bin/python','/opt/aicademiya/current/tools/document_stage12/document_ssh_bridge.py','--ssh-host','aicademiya-docs@192.168.32.5','--ssh-key','/var/lib/aicademiya/worker-ssh-stage14/id_ed25519','--known-hosts','/var/lib/aicademiya/worker-ssh-stage14/known_hosts','--timeout','3600']
  updates={'AICADEMIYA_DOCUMENT_FORMATS':FORMATS,'AICADEMIYA_DOCUMENT_WORKER_COMMAND':"'"+json.dumps(worker,separators=(',',':'))+"'",'AICADEMIYA_DOCUMENT_WORKER_TIMEOUT':'3700'}
  lines=old_config.decode().splitlines();seen=set()
  for i,line in enumerate(lines):
   key=line.split('=',1)[0]
   if key in updates:lines[i]=key+'='+updates[key];seen.add(key)
  lines.extend(k+'='+v for k,v in updates.items()if k not in seen);new_config=('\n'.join(lines)+'\n').encode();changed=True;config(new_config,st);link(NEW)
  run(['systemctl','start','aicademiya.service']);ready();assert CURRENT.resolve()==NEW and CONF.read_bytes()==new_config
  report['database']=preserved(before,state(DATA/'aicademiya.sqlite3',before));pid=int(run(['systemctl','show','aicademiya.service','--property=MainPID','--value']).strip());assert Path(f'/proc/{pid}/cwd').resolve()==NEW
  env=dict(x.split(b'=',1)for x in Path(f'/proc/{pid}/environ').read_bytes().split(bytes([0]))if b'='in x);assert env[b'AICADEMIYA_DOCUMENT_FORMATS'].decode()==FORMATS and json.loads(env[b'AICADEMIYA_DOCUMENT_WORKER_COMMAND'])==worker
  opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
  with opener.open(BASE+'/api/bootstrap')as response:assert json.load(response)['demo_enabled']is False
  with opener.open(BASE+'/')as response:assert response.read()==(NEW/'frontend/dist/index.html').read_bytes()
  report.update(status='promoted_verified',backup_path=str(CUTOVER),site_pid=pid,demo_disabled=True,index_matches=True,formats=FORMATS)
 except BaseException as exc:
  report.update(status='failed',error_type=type(exc).__name__,error=str(exc))
  if changed:run(['systemctl','stop','aicademiya.service'],timeout=660);link(OLD);config(old_config,st)
  run(['systemctl','start','aicademiya.service']);ready();report['old_site_restored']=True;raise
 finally:
  if grace.exists():shutil.move(str(grace),str(QA/'cutover-grace-retired.conf'));run(['systemctl','daemon-reload'])
  report['finished_at']=datetime.now(timezone.utc).isoformat();save('cutover-result.json',report)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['stage','check-staged','rehearsal','activate']);a=p.parse_args();assert os.geteuid()==0;{'stage':stage,'check-staged':check_staged,'rehearsal':rehearsal,'activate':activate}[a.mode]()
