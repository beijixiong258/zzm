"""Exercise real Tavily via app/browser with a labelled model protocol fixture.

Never calls the user's model. Makes at most two real Tavily requests.
"""
from datetime import datetime
from pathlib import Path
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

import httpx
import uvicorn

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.aicademiya.main import create_app
from backend.aicademiya.web_search import TavilySearch


def main():
    config=json.loads((ROOT/'local-settings.json').read_text(encoding='utf-8-sig'))
    key=config.get('TAVILY_API_KEY')
    if not key:raise SystemExit('TAVILY_API_KEY is missing from local-settings.json; run the direct probe first')
    os.environ.update(TAVILY_API_KEY=key,AICADEMIYA_WEB_SEARCH_ENABLED='true',AICADEMIYA_AI_MODE='openai',
                      AICADEMIYA_AI_BASE_URL='http://model-fixture.invalid/v1',AICADEMIYA_AI_MODEL='search-protocol-fixture',AICADEMIYA_AI_API_KEY='')
    output=ROOT/'artifacts/web-search';output.mkdir(parents=True,exist_ok=True)
    qa=Path(tempfile.mkdtemp(prefix='qa-run-search-',dir=ROOT/'artifacts'))
    state={'model_protocol_requests':0,'real_model_requests':0,'search_requests':0,'search_results':[]}

    def model_fixture(request):
        assert request.url.host=='model-fixture.invalid'
        payload=json.loads(request.content)
        assert key not in json.dumps(payload)
        state['model_protocol_requests']+=1
        if isinstance(payload.get('tool_choice'),dict):
            assert payload['tool_choice']=={'type':'function','function':{'name':'web_search'}}
            public=json.loads(payload['messages'][1]['content'])
            assert set(public)=={'session_title','question','student_request','public_materials'}
            message={'content':None,'tool_calls':[{'id':'qa-public-search','type':'function','function':{'name':'web_search','arguments':json.dumps({'query':'Cambridge English validity reliability assessment principles good practice'})}}]}
        elif payload.get('tool_choice')=='none':
            evidence=json.loads(payload['messages'][-1]['content'])
            assert payload['messages'][-1]['role']=='tool' and evidence['results']
            message={'content':'[Protocol fixture — not a real model answer] Inline citations deliberately omitted to test mandatory source links supplied by the application.'}
        else:
            assert 'tools' not in payload
            message={'content':'[Protocol fixture — offline] No search was requested for this message.'}
        return httpx.Response(200,json={'choices':[{'message':message}]})

    class RecordedSearch(TavilySearch):
        def search(self,query):
            if state['search_requests']>=2:raise RuntimeError('QA real-search budget exceeded')
            state['search_requests']+=1
            result=super().search(query)
            state['search_results'].append(result)
            return result

    app=create_app(data_dir=qa,demo_enabled=True,ai_transport=httpx.MockTransport(model_fixture))
    app.state.tutor.search=RecordedSearch()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='warning'))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    result={'status':'failed','qa_data_directory':str(qa),'real_search':True,'real_model':False}
    try:
        with httpx.Client(trust_env=False,timeout=2) as client:
            until=time.monotonic()+20
            while time.monotonic()<until:
                try:
                    if client.get(base+'/api/health').status_code==200:break
                except httpx.RequestError:pass
                time.sleep(0.1)
            else:raise RuntimeError('Isolated QA server did not start')
        env=os.environ.copy();env['AICADEMIYA_TEST_URL']=base
        # Browser test only needs the app URL, not the provider secret.
        env.pop('TAVILY_API_KEY',None)
        proc=subprocess.run([shutil.which('node'),'tools/search_browser_check.mjs'],cwd=ROOT,env=env,timeout=120)
        if proc.returncode:raise RuntimeError('Web-search browser integration failed')
        assert state['model_protocol_requests']==6 and state['search_requests']==2
        with app.state.database.connect() as conn:
            rows=conn.execute("SELECT citations_json FROM messages WHERE role='assistant' AND citations_json!='[]' ORDER BY seq").fetchall()
            assert len(rows)==2
            for row,search in zip(rows,state['search_results']):
                citations=json.loads(row[0])
                assert [c['url'] for c in citations]==[r['url'] for r in search['results']]
        result.update(status='passed',**state,verified_at=datetime.now().astimezone().isoformat())
    finally:
        server.should_exit=True;thread.join(timeout=10)
        result.update(state)
        result['owned_server_stopped']=not thread.is_alive()
        encoded=json.dumps(result,ensure_ascii=False,indent=2)
        assert key not in encoded
        (output/'integration-result.json').write_text(encoded+'\n',encoding='utf-8')
        print(json.dumps({k:v for k,v in result.items() if k!='search_results'},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
