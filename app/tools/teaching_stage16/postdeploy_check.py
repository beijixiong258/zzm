"""Read back the exact Stage16 production target and exercise its real configured
worker command on an isolated synthetic XLSX, without production DB writes."""
from pathlib import Path
import hashlib,json,os,pwd,sqlite3,subprocess,urllib.request
NEW=Path('/opt/aicademiya/releases/AIcademiya_V2-stage16-workflow-r4')
QA=Path('/var/lib/aicademiya-qa/stage16-release-r4');BASE='http://192.168.32.55:18773'
ROOT=QA/'production-native-smoke'
def sha(p):
 with Path(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 assert os.geteuid()==0 and Path('/opt/aicademiya/current').resolve()==NEW and not ROOT.exists()
 manifest=json.loads((QA/(NEW.name+'.manifest.json')).read_text());assert all(sha(NEW/n)==r['sha256']for n,r in manifest['files'].items())
 pid=int(subprocess.check_output(['systemctl','show','aicademiya.service','--property=MainPID','--value'],text=True));assert Path(f'/proc/{pid}/cwd').resolve()==NEW
 env=dict(x.split(b'=',1)for x in Path(f'/proc/{pid}/environ').read_bytes().split(bytes([0]))if b'='in x)
 command=json.loads(env[b'AICADEMIYA_DOCUMENT_WORKER_COMMAND']);formats=env[b'AICADEMIYA_DOCUMENT_FORMATS'].decode().split(',');assert {'doc','ppt','xls','xlsx'}<=set(formats)
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 with opener.open(BASE+'/api/health',timeout=5)as r:assert json.load(r)['status']=='ok'
 with opener.open(BASE+'/api/bootstrap',timeout=5)as r:assert json.load(r)['demo_enabled']is False
 checked=[]
 for name,row in manifest['files'].items():
  if not name.startswith('frontend/dist/'):continue
  url=BASE+'/'+name.removeprefix('frontend/dist/')
  with opener.open(url,timeout=10)as response:assert hashlib.sha256(response.read()).hexdigest()==row['sha256']
  checked.append(name)
 with sqlite3.connect('file:/var/lib/aicademiya/aicademiya.sqlite3?mode=ro',uri=True)as db:
  assert not db.execute("select 1 from document_jobs where status in ('queued','running')limit 1").fetchone(),'A live document job is active; do not compete'
  assert db.execute('pragma integrity_check').fetchone()[0]=='ok'
  counts={name:db.execute('select count(*)from '+name).fetchone()[0]for name in ['users','courses','materials','messages','attempts','document_jobs','document_revisions']}
 proof=json.loads((QA/'worker-app-result.json').read_text());case=next(x for x in proof['cases']if x['format']=='xlsx')
 with sqlite3.connect('file:'+proof['qa']+'/data/aicademiya.sqlite3?mode=ro',uri=True)as db:source=Path(db.execute('select file_path from materials where id=?',(case['material_id'],)).fetchone()[0])
 assert sha(source)==case['source_sha256'];user=pwd.getpwnam('aicademiya');assert user.pw_uid==999
 ROOT.mkdir(mode=0o700);os.chown(ROOT,user.pw_uid,user.pw_gid);original=ROOT/'synthetic.xlsx';original.write_bytes(source.read_bytes());os.chown(original,user.pw_uid,user.pw_gid)
 out=ROOT/'bundle';r=subprocess.run(['runuser','-u',user.pw_name,'--',*command,'--input',str(original),'--output',str(out)],capture_output=True,text=True,timeout=180)
 (ROOT/'bridge.log').write_text(r.stdout+r.stderr);assert r.returncode==0,'Actual configured worker smoke failed; log retained'
 m=json.loads((out/'manifest.json').read_text());s=json.loads((out/'raw/supervisor.json').read_text());assert m['complete']and m['source_format']=='xlsx'and m['source_sha256']==sha(original)
 assert s['status']=='complete'and s['owned_processes_closed']and not s['gpu_lease_used']
 result={'status':'passed','release':str(NEW),'pid':pid,'all_release_files_match':len(manifest['files']),'public_files_http_match':len(checked),'formats':formats,'demo_disabled':True,'production_counts':counts,'configured_UID999_worker_xlsx':True,'gpu_used_by_smoke':False,'production_data_writes':False}
 (QA/'postdeploy-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
