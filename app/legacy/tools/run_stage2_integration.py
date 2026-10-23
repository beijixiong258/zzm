"""Run independent stage-2 acceptance groups on fresh owned local QA servers."""
from pathlib import Path
import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

import httpx

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/stage2'


def run_group(name,command):
    qa=Path(tempfile.mkdtemp(prefix=f'qa-run-stage2-{name}-',dir=ROOT/'artifacts'))
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    env=os.environ.copy()
    if env.get('HERMES_HOME'):
        scratch=Path(env['HERMES_HOME'])/'cache'/'scratch'
        scratch.mkdir(parents=True,exist_ok=True)
        env.update(TMPDIR=str(scratch),TEMP=str(scratch),TMP=str(scratch))
    env.update(AICADEMIYA_DATA_DIR=str(qa),AICADEMIYA_DEMO_ENABLED='true',AICADEMIYA_AI_MODE='demo',AICADEMIYA_AI_PROVIDER='',
               AICADEMIYA_AI_BASE_URL='',AICADEMIYA_AI_MODEL='',AICADEMIYA_AI_API_KEY='',AICADEMIYA_WEB_SEARCH_ENABLED='false',
               TAVILY_API_KEY='',NO_PROXY='127.0.0.1,localhost,::1',AICADEMIYA_TEST_URL=base)
    record={'name':name,'base_url':base,'data_dir':str(qa),'status':'failed'}
    with (qa/'server.log').open('w',encoding='utf-8') as log:
        proc=subprocess.Popen([sys.executable,'-m','uvicorn','backend.aicademiya.main:app','--host','127.0.0.1','--port',str(port)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        try:
            with httpx.Client(trust_env=False,timeout=1) as client:
                deadline=time.monotonic()+40
                while time.monotonic()<deadline:
                    if proc.poll() is not None:raise RuntimeError(f'QA app exited; see {qa / "server.log"}')
                    try:
                        if client.get(base+'/api/health').status_code==200:break
                    except httpx.RequestError:pass
                    time.sleep(.15)
                else:raise RuntimeError('QA app readiness timed out')
            actual=[part.replace('{BASE}',base) for part in command]
            completed=subprocess.run(actual,cwd=ROOT,env=env,timeout=600)
            record['exit_code']=completed.returncode
            if completed.returncode:raise RuntimeError(name+' acceptance failed')
            record['status']='passed'
        except Exception as exc:
            record['error']=str(exc)
            raise
        finally:
            proc.terminate()
            try:proc.wait(timeout=10)
            except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
            record['owned_server_stopped']=proc.poll() is not None
            (OUT/f'{name}-runner.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print(json.dumps(record,ensure_ascii=False,indent=2))
    return record


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--browser',action='store_true',help='Run the stage2 browser suite on its own fresh DB')
    parser.add_argument('--migration',action='store_true',help='Run the genuine baseline-data migration check first')
    parser.add_argument('--skip-api',action='store_true')
    args=parser.parse_args();OUT.mkdir(parents=True,exist_ok=True)
    if args.migration:
        subprocess.run([sys.executable,'tools/stage2_migration_check.py'],cwd=ROOT,check=True,timeout=180)
    results=[]
    if not args.skip_api:
        results.append(run_group('api',[sys.executable,'tools/stage2_api_acceptance.py','--base-url','{BASE}','--confirm-test-database']))
    if args.browser:
        path=ROOT/'tools/stage2_browser_acceptance.mjs'
        if not path.is_file():raise SystemExit('Stage2 browser suite is not ready yet; do not claim browser acceptance.')
        node=shutil.which('node')
        if not node:raise SystemExit('Node.js is required')
        results.append(run_group('browser',[node,str(path)]))
    summary={'status':'passed','groups':results,'real_model_requests':0,'default_data_touched':False}
    (OUT/'integration-result.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':main()
