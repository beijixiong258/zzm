"""Final local artifact checks. Does not call any inference service."""
from pathlib import Path
from datetime import datetime
from urllib.parse import unquote, urlsplit
import json
import re
import socket
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT.parent

def main():
    core=json.loads((ROOT/'artifacts/browser-integration/browser-result.json').read_text(encoding='utf-8'))
    auth=json.loads((ROOT/'artifacts/password-integration/result.json').read_text(encoding='utf-8'))
    api=json.loads((ROOT/'artifacts/api-acceptance.json').read_text(encoding='utf-8'))
    integration=json.loads((ROOT/'artifacts/integration-result.json').read_text(encoding='utf-8'))
    search=json.loads((ROOT/'artifacts/web-search/browser-result.json').read_text(encoding='utf-8'))
    search_integration=json.loads((ROOT/'artifacts/web-search/integration-result.json').read_text(encoding='utf-8'))
    for value in (core,auth,api,integration,search,search_integration):assert value['status']=='passed'
    assert integration['owned_server_stopped']
    assert search_integration['owned_server_stopped'] and search_integration['real_model_requests']==0
    shots=core['screenshots']+auth['screenshots']+search['screenshots']
    assert len(shots)==len(set(shots))
    assert all(Path(p).is_file() for p in shots)
    assert not core['page_errors'] and not auth['page_errors'] and not search['page_errors']
    assert not core['unexpected_api_errors']
    assert len(core['expected_api_errors'])==1 and core['expected_api_errors'][0]['status']==502
    config=json.loads((ROOT/'local-settings.json').read_text(encoding='utf-8'))
    assert config['AICADEMIYA_AI_MODE']=='demo' and config['AICADEMIYA_AI_MODEL']=='qwen27b-q8'
    guard=subprocess.run([sys.executable,'tools/live_model_probe.py'],cwd=ROOT,capture_output=True,text=True)
    assert guard.returncode!=0 and 'Confirm resource availability first' in guard.stderr
    required=['../README.md','VERIFICATION.md','DEPLOYMENT.md','../docs/history/CONTRACT.md','AUTH_CHANGE.md','AGENTS.md','start.cmd','setup.cmd','Dockerfile','compose.yaml','frontend/dist/index.html','backend/requirements.txt','sample_data/catalog.json']
    assert all((ROOT/name).is_file() for name in required)
    documents=[PROJECT/'README.md',*sorted((PROJECT/'docs').glob('*.md')),
               *sorted((PROJECT/'research').glob('*.md')),PROJECT/'research/course-analysis/README.md',PROJECT/'research/course-analysis/worksheet-map.md',
               *sorted(ROOT.glob('*.md')),ROOT/'backend/README.md',ROOT/'sample_data/README.md',ROOT/'artifacts/live-model/review.md']
    checked=0;broken=[]
    for document in documents:
        text=document.read_text(encoding='utf-8')
        for target in re.findall(r'\]\(([^)]+)\)',text):
            if urlsplit(target).scheme or target.startswith('#'):continue
            checked+=1
            dest=(document.parent/unquote(target.split('#',1)[0])).resolve()
            if not dest.exists():broken.append({'file':str(document),'target':target})
    assert not broken,broken
    inv=json.loads((PROJECT/'research/course-analysis/inventory.json').read_text(encoding='utf-8'))
    for item in inv['originals']:
        original=PROJECT/item['source']
        assert original.stat().st_size==item['bytes'] and original.stat().st_mtime_ns==item['mtime_ns'],item['source']
    now=datetime.now().astimezone();deadline=now.replace(hour=21,minute=0,second=0,microsecond=0)
    ports={}
    for port in (18773,18774,18775,18776):
        with socket.socket() as s:ports[port]=s.connect_ex(('127.0.0.1',port))==0
    result={'verified_at':now.isoformat(),'before_21_00':now<deadline,'backend_tests':132,'frontend_tests':33,
            'unit_test_counts_source':'Parent real pytest/npm terminal runs documented in VERIFICATION.md',
            'api_requests':api['request_count'],'browser_core_checks':len(core['checks']),'password_checks':len(auth['checks']),
            'web_search_browser_checks':len(search['checks']),
            'browser_total_checks':sum(len(x['checks']) for x in (core,auth,search)),
            'web_search_real_provider':True,'web_search_model_protocol_only':True,
            'screenshot_files_verified':len(shots),'browser_page_errors':0,
            'local_document_links_checked':checked,'broken_links':broken,'original_course_files_unchanged':len(inv['originals']),
            'default_ai_mode':config['AICADEMIYA_AI_MODE'],'live_inference_guard_verified':True,'inference_called_during_this_check':False,
            'app_ports_in_use':ports,'default_user_database_exists':(ROOT/'data/aicademiya.sqlite3').exists(),'docker_pve_deployed':False}
    (ROOT/'artifacts/delivery-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
