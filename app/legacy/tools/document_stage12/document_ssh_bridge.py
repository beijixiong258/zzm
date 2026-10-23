"""One SSH document job; private input, heartbeat cancellation, bounded bundle.

Trusted configuration only; no shell=True, agent forwarding or public listener.
Usage: python ... --ssh-host ubuntu-gpu --input source.pdf --output fresh-dir
"""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json,os,shlex,subprocess,tarfile,tempfile,threading,time
REMOTE_PY='/home/adminz/llm/ocr-stage1-20261009/whole-document-pilot/.venv/bin/python'
REMOTE_SERVICE='/home/adminz/llm/ocr-stage1-20261009/stage12-parser/document_worker_service.py'

def unpack(archive,out):
 count=total=0
 with tarfile.open(archive,'r:gz')as t:
  for m in t:
   p=PurePosixPath(m.name)
   if p.is_absolute()or'..'in p.parts or'\\'in m.name or':'in m.name or not(m.isdir()or m.isfile()):raise ValueError('Unsafe worker bundle member')
   count+=1;total+=m.size
   if count>100000 or total>4*1024**3 or m.size>64*1024**2:raise ValueError('Worker bundle exceeds limits')
   dest=out.joinpath(*p.parts)
   if not dest.resolve().is_relative_to(out.resolve()):raise ValueError('Unsafe worker bundle path')
   if m.isdir():dest.mkdir(parents=True,exist_ok=True);continue
   dest.parent.mkdir(parents=True,exist_ok=True)
   with t.extractfile(m)as src,dest.open('xb')as f:
    remaining=m.size
    while remaining:
     b=src.read(min(1048576,remaining))
     if not b:raise ValueError('Incomplete worker file')
     f.write(b);remaining-=len(b)

def main():
 p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True);p.add_argument('--ssh-host',default=os.getenv('AICADEMIYA_DOCUMENT_SSH_HOST','ubuntu-gpu'));p.add_argument('--ssh-key',default=os.getenv('AICADEMIYA_DOCUMENT_SSH_KEY'));p.add_argument('--known-hosts',default=os.getenv('AICADEMIYA_DOCUMENT_KNOWN_HOSTS'));p.add_argument('--remote-python',default=REMOTE_PY);p.add_argument('--remote-service',default=REMOTE_SERVICE);p.add_argument('--timeout',type=int,default=3600);a=p.parse_args()
 source,out=Path(a.input),Path(a.output)
 if out.exists():raise ValueError('Output must be fresh')
 if not source.is_file()or source.stat().st_size>64*1024**2:raise ValueError('Invalid or oversized source')
 suffix=source.suffix.lower()
 if suffix not in ('.pdf','.pptx','.ppt','.docx','.doc','.xls','.xlsx','.txt','.md','.png','.jpg','.jpeg','.webp'):raise ValueError('Unsupported complete document format')
 if a.ssh_host.startswith('-')or any(c.isspace()for c in a.ssh_host):raise ValueError('Invalid SSH target')
 args=['ssh','-T','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10','-o','ForwardAgent=no','-o','ClearAllForwardings=yes']
 if a.ssh_key:args+=['-i',a.ssh_key,'-o','IdentitiesOnly=yes']
 if a.known_hosts:args+=['-o','UserKnownHostsFile='+a.known_hosts]
 args += [a.ssh_host,shlex.join([a.remote_python,a.remote_service,'--stdio'])]
 out.parent.mkdir(parents=True,exist_ok=True);failures=[];bytes_received=0
 with tempfile.TemporaryDirectory(prefix='document-transfer-',dir=out.parent)as temporary:
  tmp=Path(temporary);archive=tmp/'bundle.tar.gz'
  with (tmp/'ssh.log').open('wb')as log:
   child=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,shell=False)
   def receive():
    nonlocal bytes_received
    try:
     with archive.open('xb')as f:
      while b:=child.stdout.read(1048576):
       bytes_received+=len(b)
       if bytes_received>512*1024**2:raise ValueError('Compressed worker output exceeds512MiB')
       f.write(b)
    except BaseException as e:failures.append(str(e));child.kill()
   thread=threading.Thread(target=receive,daemon=True);thread.start();started=time.monotonic()
   try:
    with source.open('rb')as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    header={'schema':1,'bytes':source.stat().st_size,'sha256':digest,'suffix':suffix}
    child.stdin.write(json.dumps(header).encode()+b'\n')
    with source.open('rb')as f:
     while b:=f.read(1048576):child.stdin.write(b)
    child.stdin.write(b'.\n');child.stdin.flush();heartbeat=time.monotonic()
    while child.poll()is None:
     if time.monotonic()-started>a.timeout:raise TimeoutError('Remote document job deadline reached')
     if time.monotonic()-heartbeat>15:
      child.stdin.write(b'.\n');child.stdin.flush();heartbeat=time.monotonic()
     time.sleep(.2)
    thread.join(timeout=30)
    if thread.is_alive():raise RuntimeError('Worker output did not finish')
    out.mkdir(mode=0o700)
    if failures:raise RuntimeError('Worker transfer failed')
    if bytes_received:unpack(archive,out)
    if child.returncode or not(out/'manifest.json').is_file():raise RuntimeError('Remote document processing failed')
   finally:
    if child.poll()is None:child.kill();child.wait(timeout=15)
    if child.stdin:
     try:child.stdin.close()
     except OSError:pass
    thread.join(timeout=5);out.mkdir(parents=True,exist_ok=True);(out/'raw').mkdir(exist_ok=True)
    (out/'raw/ssh-job.json').write_text(json.dumps({'returncode':child.returncode,'bytes_received':bytes_received,'seconds':time.monotonic()-started,'heartbeat_cancellation':True},indent=2)+'\n')
    (out/'raw/ssh.log').write_bytes((tmp/'ssh.log').read_bytes())
if __name__=='__main__':main()
