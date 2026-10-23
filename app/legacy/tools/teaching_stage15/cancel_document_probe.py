"""Real installed Stage15 worker cancellation by SSH EOF, owned QA job only."""
from pathlib import Path
import hashlib,json,os,subprocess,time,urllib.request,tarfile
ROOT=Path('/var/lib/aicademiya-qa/stage15-fresh-r1');OUT=ROOT/'cancel-stage15-r1'
def status():
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://192.168.32.5:18280/status',timeout=5)as r:return json.load(r)
def main():
 assert os.geteuid()==999;OUT.mkdir(mode=0o700,exist_ok=False)
 before=status();assert before['resources']['phase']=='teaching'and before['teaching_capacity']==3
 data=(ROOT/'lesson-source.pdf').read_bytes();assert hashlib.sha256(data).hexdigest()=='40c673816624b815e2b7c1633801db3b5fb7c6a5fb73aacd3de0cc62b7463fb1'
 args=['ssh','-T','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','-o','ForwardAgent=no','-o','ClearAllForwardings=yes','-o','IdentitiesOnly=yes','-i','/var/lib/aicademiya/worker-ssh-stage14/id_ed25519','-o','UserKnownHostsFile=/var/lib/aicademiya/worker-ssh-stage14/known_hosts','aicademiya-docs@192.168.32.5','stage15-cancel-proof']
 report={'status':'running','transport':'restricted SSH stdin EOF, output retained','samples':[]};start=time.monotonic();leased_at=None;heartbeat=start
 try:
  with(OUT/'bundle.tar.gz').open('xb')as archive,(OUT/'ssh.log').open('xb')as log:
   p=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=archive,stderr=log)
   try:
    p.stdin.write(json.dumps({'schema':1,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'suffix':'.pdf'}).encode()+b'\n'+data+b'.\n');p.stdin.flush()
    while time.monotonic()-start<180:
     s=status();phase=s['resources']['phase'];report['samples'].append({'seconds':time.monotonic()-start,'phase':phase,'capacity':s['teaching_capacity'],'epoch':s['resources']['epoch']})
     if phase=='leased':
      assert s['resources']['epoch']>before['resources']['epoch']and s['teaching_capacity']==2
      if leased_at is None:leased_at=time.monotonic()
      if time.monotonic()-leased_at>=20:p.stdin.close();p.stdin=None;report['cancel_at_seconds']=time.monotonic()-start;break
     if p.poll()is not None:raise RuntimeError('Job exited before cancellation')
     if time.monotonic()-heartbeat>3:p.stdin.write(b'.\n');p.stdin.flush();heartbeat=time.monotonic()
     time.sleep(.3)
    else:raise TimeoutError('No owned active lease to cancel')
    rc=p.wait(timeout=100);report['returncode']=rc;assert rc==2
   finally:
    if p.stdin:p.stdin.close()
    if p.poll()is None:p.wait(timeout=100)
  with tarfile.open(OUT/'bundle.tar.gz','r:gz')as t:
   members={m.name.lstrip('./'):m for m in t}
   supervisor=json.load(t.extractfile(members['raw/supervisor.json']));page=json.load(t.extractfile(members['receipt.json']))
  assert supervisor['status']=='failed'and 'cancel'in supervisor['error'].lower()
  assert supervisor['visual_backend']=='native+live-page-markdown'and supervisor['gpu_lease_used']and supervisor['model_pid']and supervisor['parser_pid']
  assert supervisor['owned_processes_closed']and supervisor['gpu_return']['teaching_ready']
  assert page['status']=='cancelled'and page['model_calls']>=1 and not page['fresh_completed_transcription']
  after=status();assert after['resources']['phase']=='teaching'and after['teaching_capacity']==3 and after['vision_teaching_capacity']==1
  report.update(status='passed',supervisor=supervisor,page_worker=page,teaching_returned=True,wall_seconds=time.monotonic()-start)
 except BaseException as e:report.update(status='failed',error_type=type(e).__name__,error=str(e));raise
 finally:(OUT/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items()if k not in ('samples','page_worker','supervisor')}),flush=True)
if __name__=='__main__':main()
