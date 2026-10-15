"""Cancel a real restricted r6 SSH job by input EOF after lease/model startup."""
from pathlib import Path
import hashlib,json,subprocess,time,urllib.request,tarfile
ROOT=Path('/var/lib/aicademiya-qa/stage14-r6-final');OUT=ROOT/'cancel-r1';OUT.mkdir(mode=0o700,exist_ok=False)
def status():
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://192.168.32.5:18280/status',timeout=5)as r:return json.load(r)
def main():
 before=status();assert before['resources']['phase']=='teaching'and before['teaching_capacity']==3
 source=ROOT/'src03-pages126-127.pdf';data=source.read_bytes();assert hashlib.sha256(data).hexdigest()=='40c673816624b815e2b7c1633801db3b5fb7c6a5fb73aacd3de0cc62b7463fb1'
 args=['ssh','-T','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','-o','ForwardAgent=no','-o','ClearAllForwardings=yes','-o','IdentitiesOnly=yes','-i','/var/lib/aicademiya/worker-ssh-stage14/id_ed25519','-o','UserKnownHostsFile=/var/lib/aicademiya/worker-ssh-stage14/known_hosts','aicademiya-docs@192.168.32.5','stage14-cancel-proof']
 report={'status':'running','cancellation_transport':'SSH stdin EOF, stdout retained','before_epoch':before['resources']['epoch'],'samples':[]};start=time.monotonic();leased_at=None;heartbeat=start
 with(OUT/'bundle.tar.gz').open('xb')as archive,(OUT/'ssh.log').open('xb')as log:
  p=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=archive,stderr=log)
  try:
   p.stdin.write(json.dumps({'schema':1,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'suffix':'.pdf'}).encode()+b'\n'+data+b'.\n');p.stdin.flush()
   while time.monotonic()-start<120:
    s=status();phase=s['resources']['phase'];report['samples'].append({'seconds':time.monotonic()-start,'phase':phase,'capacity':s['teaching_capacity'],'epoch':s['resources']['epoch']})
    if phase=='leased':
     assert s['resources']['epoch']>before['resources']['epoch']and s['teaching_capacity']==2
     if leased_at is None:leased_at=time.monotonic()
     if time.monotonic()-leased_at>=8:
      p.stdin.close();p.stdin=None;report['cancel_at_seconds']=time.monotonic()-start;break
    if p.poll()is not None:raise RuntimeError('Job exited before cancellation')
    if time.monotonic()-heartbeat>3:p.stdin.write(b'.\n');p.stdin.flush();heartbeat=time.monotonic()
    time.sleep(.25)
   else:raise TimeoutError('No owned lease to cancel')
   rc=p.wait(timeout=90);assert rc==2,rc;report['returncode']=rc
  finally:
   if p.stdin:p.stdin.close()
   if p.poll()is None:p.wait(timeout=90)
 with tarfile.open(OUT/'bundle.tar.gz','r:gz')as t:
  member=next(m for m in t if m.name.lstrip('./')=='raw/supervisor.json');supervisor=json.load(t.extractfile(member))
 assert supervisor['status']=='failed'and 'cancelled'in supervisor['error']
 assert supervisor['gpu_lease_used']and supervisor['model_pid']and supervisor['parser_pid']and supervisor['model_load_seconds']>0
 assert supervisor['owned_processes_closed']and supervisor['gpu_return']['teaching_ready']
 after=status();assert after['resources']['phase']=='teaching'and after['teaching_capacity']==3
 report.update(status='passed',supervisor=supervisor,after_epoch=after['resources']['epoch'],teaching_returned=True,wall_seconds=time.monotonic()-start)
 (OUT/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items()if k!='samples'}))
if __name__=='__main__':main()
