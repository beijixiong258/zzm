"""Exercise merged application through an owned tunnel to installed GPU router."""
from pathlib import Path
import json,os,subprocess,sys,time,urllib.request
APP=Path(__file__).resolve().parents[2];OUT=APP/'artifacts/stage15/installed-app-r1'
def main():
 assert not OUT.exists();tunnel=None;report={'installed_router':True,'fresh_material_processing':False}
 try:
  tunnel=subprocess.Popen(['ssh.exe','-4','-N','-o','BatchMode=yes','-o','ExitOnForwardFailure=yes','-L','127.0.0.1:18280:127.0.0.1:18280','ubuntu-gpu'],stdin=subprocess.DEVNULL)
  end=time.monotonic()+15;opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
  while time.monotonic()<end:
   assert tunnel.poll()is None,'Owned tunnel could not start; do not touch another listener'
   try:
    with opener.open('http://127.0.0.1:18280/status',timeout=2)as r:s=json.load(r)
    assert s['vision_teaching_capacity']==1 and s['teaching_capacity']==3 and not s['queue']and all(not w['busy']for w in s['workers']);break
   except OSError:time.sleep(.2)
  else:raise TimeoutError('Owned forwarding readiness')
  report['before']=s
  result=subprocess.run([sys.executable,str(APP/'tools/teaching_stage15/run_live_app.py'),'--output',str(OUT),'--resume',str(APP/'artifacts/stage15/live-app-r1'),'--tasks','table,generation','--installed-router'],cwd=APP,timeout=1500)
  report['returncode']=result.returncode
  with opener.open('http://127.0.0.1:18280/status',timeout=5)as r:report['after']=json.load(r)
  assert result.returncode==0,'Read retained application result'
 finally:
  if tunnel is not None:
   tunnel.terminate();tunnel.wait(timeout=15);report['owned_tunnel_closed']=tunnel.poll()is not None
  (APP/'artifacts/stage15/installed-app-r1-supervisor.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
