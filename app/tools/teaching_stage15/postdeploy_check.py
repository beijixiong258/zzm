"""Post-cutover CT readback plus native-only isolated command smoke.
Uses the real service's worker argv as UID999; no production DB writes or model.
"""
from pathlib import Path
import hashlib,json,os,pwd,sqlite3,subprocess,urllib.request,re
BASE='http://192.168.32.55:18773';NEW=Path('/opt/aicademiya/releases/AIcademiya_V2-20261013-multimodal-r3');ROOT=Path('/var/lib/aicademiya-qa/stage15-production-command-smoke')
def main():
 assert os.geteuid()==0 and Path('/opt/aicademiya/current').resolve()==NEW and not ROOT.exists()
 pid=int(subprocess.check_output(['systemctl','show','aicademiya.service','--property=MainPID','--value'],text=True));env=dict(x.split(b'=',1)for x in Path(f'/proc/{pid}/environ').read_bytes().split(bytes([0]))if b'='in x);command=json.loads(env[b'AICADEMIYA_DOCUMENT_WORKER_COMMAND']);formats=env[b'AICADEMIYA_DOCUMENT_FORMATS'].decode()
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));checks=[]
 with opener.open(BASE+'/api/health')as r:assert json.load(r)['status']=='ok';checks.append('health')
 with opener.open(BASE+'/api/bootstrap')as r:boot=json.load(r)
 assert not boot['demo_enabled'];checks.append('demo_disabled')
 with opener.open(BASE+'/')as r:html=r.read()
 assert html==(NEW/'frontend/dist/index.html').read_bytes()
 for url in sorted(set(re.findall(r'(?:src|href)="(/[^"?#]+)"',html.decode()))):
  with opener.open(BASE+url)as r:assert r.read()==(NEW/'frontend/dist'/url.lstrip('/')).read_bytes();checks.append(url)
 with sqlite3.connect('file:/var/lib/aicademiya/aicademiya.sqlite3?mode=ro',uri=True)as db:assert not db.execute("select 1 from document_jobs where status in ('queued','running')limit 1").fetchone(),'Live document job active; do not compete'
 user=pwd.getpwnam('aicademiya');ROOT.mkdir(mode=0o700);os.chown(ROOT,user.pw_uid,user.pw_gid)
 text='POST-CUTOVER SYNTHETIC CHECK. Exact native text is retained: 45 / 29 / 28.\nNo real account, teaching record or model request is created.\n';source=ROOT/'synthetic-native.txt';source.write_text(text);os.chown(source,user.pw_uid,user.pw_gid);output=ROOT/'bundle'
 r=subprocess.run(['runuser','-u',user.pw_name,'--',*command,'--input',str(source),'--output',str(output)],capture_output=True,text=True,timeout=90);(ROOT/'bridge.log').write_text(r.stdout+r.stderr);assert r.returncode==0,'Configured command failed; retained log'
 manifest=json.loads((output/'manifest.json').read_text());supervisor=json.loads((output/'raw/supervisor.json').read_text());assert manifest['source_sha256']==hashlib.sha256(source.read_bytes()).hexdigest()and ''.join(b['text']for p in manifest['pages']for b in p['blocks'])==text
 assert supervisor['status']=='complete'and supervisor['execution_kind']=='native_only'and not supervisor['gpu_lease_used']and supervisor['owned_processes_closed']
 result={'status':'passed','production_release':str(NEW),'service_pid':pid,'http_checks':checks,'configured_formats':formats,'actual_configured_worker_uid999_native_check':True,'worker_used_GPU':False,'production_data_mutations':False,'synthetic_output':str(output)};(ROOT/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
