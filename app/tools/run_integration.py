"""Run API and real browser acceptance on an owned fresh, disposable QA server.

QA artifacts are retained; this never resets/deletes the user's working database.
"""
from pathlib import Path
import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--password',action='store_true',help='Also exercise first-login password-change API/UI integration')
    args=parser.parse_args()
    artifacts=ROOT/'artifacts'; artifacts.mkdir(exist_ok=True)
    qa=Path(tempfile.mkdtemp(prefix='qa-run-',dir=artifacts))
    env=os.environ.copy()
    env.update(AICADEMIYA_DATA_DIR=str(qa),AICADEMIYA_DEMO_ENABLED='true',AICADEMIYA_AI_MODE='demo',AICADEMIYA_AI_BASE_URL='',AICADEMIYA_AI_MODEL='',AICADEMIYA_AI_API_KEY='',AICADEMIYA_WEB_SEARCH_ENABLED='false',TAVILY_API_KEY='')
    # Keep the isolated loopback QA traffic out of Windows/system proxies.
    env['NO_PROXY']='127.0.0.1,localhost,::1'
    with socket.socket() as s:
        s.bind(('127.0.0.1',0)); port=s.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    env['AICADEMIYA_TEST_URL']=base
    log=(qa/'server.log').open('w',encoding='utf-8')
    proc=subprocess.Popen([sys.executable,'-m','uvicorn','backend.aicademiya.main:app','--host','127.0.0.1','--port',str(port)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
    result={'qa_data_directory':str(qa),'base_url':base}
    try:
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            if proc.poll() is not None: raise RuntimeError(f'QA server exited; see {qa / "server.log"}')
            try:
                with urllib.request.urlopen(base+'/api/health',timeout=1) as response:
                    if response.status==200:break
            except (OSError,TimeoutError):time.sleep(0.15)
        else:raise RuntimeError('QA server readiness timed out')
        api=subprocess.run([sys.executable,'tools/api_acceptance.py','--base-url',base,'--confirm-test-database'],cwd=ROOT,env=env,timeout=180)
        result['api_exit_code']=api.returncode
        if api.returncode:raise RuntimeError('API acceptance failed')
        import shutil
        node=shutil.which('node')
        if not node:raise RuntimeError('Node.js is required for browser acceptance')
        browser=subprocess.run([node,'tools/browser_acceptance.mjs'],cwd=ROOT,env=env,timeout=180)
        result['browser_exit_code']=browser.returncode
        if browser.returncode:raise RuntimeError('Browser acceptance failed')
        if args.password:
            password=subprocess.run([node,'tools/password_browser_check.mjs'],cwd=ROOT,env=env,timeout=120)
            result['password_exit_code']=password.returncode
            if password.returncode:raise RuntimeError('Password integration failed')
        result['status']='passed'
    except Exception as exc:
        result['status']='failed'; result['error']=str(exc)
        raise
    finally:
        proc.terminate()
        try:proc.wait(timeout=10)
        except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
        log.close()
        result['owned_server_stopped']=proc.poll() is not None
        (artifacts/'integration-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
