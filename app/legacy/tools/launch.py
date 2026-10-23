"""Local AIcademiya launcher. Owns only the server process it starts."""
from pathlib import Path
import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.aicademiya.deployment_config import load_config, config_environment


def get_json(url):
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url,timeout=2) as response:
        return json.load(response)


def main():
    parser=argparse.ArgumentParser(description='Start the local AIcademiya application')
    parser.add_argument('--config',type=Path,default=ROOT/'config.json')
    parser.add_argument('--host')
    parser.add_argument('--port',type=int)
    parser.add_argument('--data-dir',type=Path)
    parser.add_argument('--demo',action='store_true',help='Developer-only deterministic QA adapter and synthetic auth (loopback only)')
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--check',action='store_true',help='Check prerequisites without starting a service')
    parser.add_argument('--smoke-test',action='store_true',help='Start, check readiness, and stop the owned server without opening a browser')
    args=parser.parse_args()
    try:
        config=load_config(args.config)
    except ValueError as error:
        print(str(error));return 2
    args.host=args.host or config['server']['host']
    args.port=args.port if args.port is not None else config['server']['port']
    args.no_browser=args.no_browser or not config['server']['open_browser']
    if (args.demo or config['auth']['demo_enabled']) and args.host not in {'127.0.0.1','localhost','::1'}:
        raise SystemExit('Demo sign-in is local-only. Disable demo mode before exposing real student accounts.')
    python=ROOT/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    required=[python,Path(config['storage']['frontend_dir'])/'index.html',ROOT/'backend/aicademiya/main.py']
    missing=[str(p) for p in required if not p.exists()]
    if missing:
        print('Missing prerequisites. Run setup.cmd first:')
        print('\n'.join(missing));return 2
    probe=subprocess.run([str(python),'-c','import fastapi, uvicorn, httpx, fitz, docx, pptx, openpyxl'],capture_output=True,text=True)
    if probe.returncode:
        print('Python dependencies are not ready. Run setup.cmd first.');return 2
    if args.check:
        print(json.dumps({'status':'ready','frontend_built':True,'configuration':str(args.config.resolve()),'sample_catalog':Path(config['storage']['catalog_path']).is_file(),'python_environment':str(python)},ensure_ascii=False));return 0
    url_host=f'[{args.host}]' if ':' in args.host else args.host
    url=f'http://{url_host}:{args.port}'
    with socket.socket(socket.AF_INET6 if ':' in args.host else socket.AF_INET) as sock:
        in_use=sock.connect_ex((args.host,args.port))==0
    if in_use:
        try:
            existing=get_json(url+'/api/bootstrap')
        except (OSError,ValueError):existing={}
        if existing.get('app_name')!='AIcademiya':
            print(f'Port {args.port} is in use by another service; nothing was stopped.');return 2
        print('AIcademiya is already running: '+url)
        if not args.no_browser:webbrowser.open(url)
        return 0
    env=config_environment(config)
    if args.demo:
        env['AICADEMIYA_DEMO_ENABLED']='true'
        env['AICADEMIYA_AI_MODE']='demo'
    if args.data_dir:env['AICADEMIYA_DATA_DIR']=str(args.data_dir.resolve())
    # This affects only our child service, not shared model/OS proxy settings.
    current_no_proxy=env.get('NO_PROXY','')
    env['NO_PROXY']=','.join(x for x in (current_no_proxy,'127.0.0.1','localhost','::1') if x)
    command=[str(python),'-m','uvicorn','backend.aicademiya.main:app','--host',args.host,'--port',str(args.port),'--no-proxy-headers']
    proc=subprocess.Popen(command,cwd=ROOT,env=env)
    try:
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            if proc.poll() is not None:return proc.returncode or 1
            try:
                if get_json(url+'/api/health').get('status')=='ok':break
            except (OSError,ValueError):time.sleep(0.2)
        else:
            print('Startup did not become ready within 30 seconds.');return 1
        print('\nAIcademiya is ready: '+url,flush=True)
        print('Keep this window open. Press Ctrl+C to stop this server.',flush=True)
        if args.smoke_test:
            bootstrap=get_json(url+'/api/bootstrap')
            print(json.dumps({'status':'smoke_passed','app_name':bootstrap.get('app_name'),
                              'ai_mode':bootstrap.get('ai',{}).get('mode'),
                              'model':bootstrap.get('ai',{}).get('model'),
                              'web_search':bootstrap.get('ai',{}).get('web_search')},ensure_ascii=False))
            return 0
        if not args.no_browser:webbrowser.open(url)
        return proc.wait()
    except KeyboardInterrupt:
        print('\nStopping AIcademiya. Saved work remains in the data directory.');return 0
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:proc.wait(timeout=10)
            except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)

if __name__=='__main__':raise SystemExit(main())
