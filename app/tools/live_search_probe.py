"""Real fast-model + Tavily probes via an isolated AIcademiya server.

Requires explicit resource-window confirmation. No model-service configuration changes.
"""
from datetime import datetime
from pathlib import Path
import argparse
import json
import os
import socket
import sys
import tempfile
import threading
import time
import uuid

import httpx
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.aicademiya.main import create_app
from backend.aicademiya.web_search import TavilySearch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resource-window-confirmed', action='store_true')
    parser.add_argument('--model', default='qwen27b-fast-v100')
    parser.add_argument('--base-url', default='http://192.168.32.5:8027/v1')
    args = parser.parse_args()
    if not args.resource_window_confirmed:
        raise SystemExit('Confirm model resource availability before real inference.')
    if not args.model.startswith('qwen27b-fast-'):
        raise SystemExit('This probe targets the user-requested qwen27b-fast-* family only.')
    out = ROOT/'artifacts/live-search'
    out.mkdir(parents=True, exist_ok=True)
    with httpx.Client(trust_env=False, timeout=10) as client:
        response = client.get(args.base_url.rstrip('/')+'/models')
        response.raise_for_status()
        entries = response.json()['data']
        models = [{'id':m['id'], 'status':m.get('status',{}).get('value')} for m in entries]
    (out/'models.json').write_text(json.dumps(models, indent=2)+'\n', encoding='utf-8')
    if args.model not in {m['id'] for m in entries}:
        raise SystemExit('Requested fast model is not advertised: '+json.dumps(models))
    chosen = next(m for m in entries if m['id']==args.model)
    config = json.loads((ROOT/'local-settings.json').read_text(encoding='utf-8-sig'))
    key = config.get('TAVILY_API_KEY','')
    if not key:raise SystemExit('TAVILY_API_KEY is not configured.')
    os.environ.update(AICADEMIYA_AI_MODE='openai', AICADEMIYA_AI_BASE_URL=args.base_url, AICADEMIYA_AI_MODEL=args.model,
                      AICADEMIYA_AI_API_KEY='aicademiya-local', AICADEMIYA_WEB_SEARCH_ENABLED='true', TAVILY_API_KEY=key)
    qa = Path(tempfile.mkdtemp(prefix='qa-run-live-search-', dir=ROOT/'artifacts'))
    calls=[]; searches=[]; turns=[]
    result={'status':'running','model':args.model,'base_url':args.base_url,'real_model':True,'real_search':True,
            'context_budget_tokens':65536,'qa_data_directory':str(qa),'started_at':datetime.now().astimezone().isoformat(),
            'advertised_models':models,'model_preset':chosen.get('status',{}).get('preset'),'automatic_quality_score':None}

    def save():
        result.update(model_calls=calls, searches=searches, turns=turns)
        encoded=json.dumps(result,ensure_ascii=False,indent=2)
        assert key not in encoded
        (out/'result.json').write_text(encoded+'\n',encoding='utf-8')

    class LiveRecordingTransport(httpx.BaseTransport):
        def handle_request(self,request):
            # JSON UTF-8 size is a conservative preflight bound for these short tests;
            # actual provider usage is recorded and checked after each real response.
            payload=json.loads(request.content)
            if len(request.content)>58000:raise RuntimeError('Probe payload exceeds conservative 64k budget')
            if datetime.now().hour>=21:raise RuntimeError('21:00 deadline reached')
            started=time.monotonic()
            with httpx.Client(trust_env=False,timeout=httpx.Timeout(65,connect=10)) as network:
                response=network.request(request.method,str(request.url),headers=dict(request.headers),content=request.content)
            try:body=response.json()
            except ValueError:body={'response_text':response.text[:1000]}
            usage=body.get('usage',{})
            assert usage.get('prompt_tokens',0)+usage.get('completion_tokens',0)<=65536
            record={'status':response.status_code,'seconds':round(time.monotonic()-started,2),
                    'stage':'search_query' if isinstance(payload.get('tool_choice'),dict) else 'feedback',
                    'request_bytes':len(request.content),'usage':usage,'response':body}
            calls.append(record);save()
            return httpx.Response(response.status_code,headers=response.headers,content=response.content)

    class LiveSearch(TavilySearch):
        def search(self,query):
            if len(searches)>=4:raise RuntimeError('Probe search budget exceeded')
            start=time.monotonic(); found=super().search(query)
            searches.append({**found,'seconds':round(time.monotonic()-start,2)});save()
            return found

    # Tiny real generation first, including possible lazy-load time.
    start=time.monotonic()
    with httpx.Client(trust_env=False,timeout=90) as direct:
        response=direct.post(args.base_url.rstrip('/')+'/chat/completions',json={
            'model':args.model,'messages':[{'role':'user','content':'Reply with exactly OK.'}],
            'max_tokens':16,'temperature':0,'stream':False})
        result['availability']={'status':response.status_code,'seconds':round(time.monotonic()-start,2),'response':response.json()}
        save();response.raise_for_status()
        if not response.json()['choices'][0]['message'].get('content','').strip():raise RuntimeError('Tiny generation was empty')
        props=direct.get(args.base_url.removesuffix('/v1')+'/props',params={'model':args.model})
        if props.is_success:
            data=props.json();result['reported_context']=data.get('default_generation_settings',{}).get('n_ctx')
            result['reported_slots']=data.get('total_slots')
            save()
    app=create_app(data_dir=qa,demo_enabled=True,ai_transport=LiveRecordingTransport())
    app.state.tutor.search=LiveSearch()
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='warning'))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    result['app_base_url']=base
    try:
        with httpx.Client(base_url=base,trust_env=False,timeout=210) as student, httpx.Client(base_url=base,trust_env=False,timeout=210) as teacher:
            until=time.monotonic()+25
            while time.monotonic()<until:
                try:
                    if student.get('/api/health').status_code==200:break
                except httpx.RequestError:pass
                time.sleep(.1)
            else:raise RuntimeError('QA app did not start')
            student.post('/api/auth/demo',json={'role':'student','student_index':1}).raise_for_status()
            teacher.post('/api/auth/demo',json={'role':'teacher'}).raise_for_status()
            assert student.post('/api/sessions/session-4/references/S4-T1-Q01').status_code==409

            def turn(client,name,message,search=False,qid='S4-T1-Q01',intent='ask'):
                before_search=len(searches);before_calls=len(calls);start=time.monotonic()
                response=client.post('/api/sessions/session-4/chat',json={
                    'message':message,'question_id':qid,'intent':intent,'web_search':search,'request_id':str(uuid.uuid4())})
                record={'case':name,'input':message,'search_enabled':search,'status':response.status_code,
                        'seconds':round(time.monotonic()-start,2),'new_model_calls':len(calls)-before_calls,
                        'new_search_calls':len(searches)-before_search}
                if response.is_success:
                    work=response.json();answer=work['messages'][-1]
                    record.update(output=answer['content'],citations=answer['citations'],mode=answer['mode'])
                else:record['error']=response.text[:2000]
                turns.append(record);save();print(json.dumps(record,ensure_ascii=False),flush=True)
                response.raise_for_status()
                assert answer['mode']=='openai' and answer['content'].strip()
                if search:
                    assert record['new_search_calls']>=1
                    assert any(c.get('kind')=='web' and c.get('url','').startswith(('https://','http://')) for c in answer['citations'])
                else:assert record['new_search_calls']==0 and record['new_model_calls']==1
                return work

            attempted='I think the answer is reliability because the test takes little time and uses few resources. Give a short hint without revealing the answer.'
            turn(student,'student_off_hint',attempted,intent='answer')
            work=turn(student,'student_on_search','Find an official Cambridge English source explaining validity and reliability in assessment. Cite source links and summarise the distinction briefly.',True,qid=None)
            assert work['attempts']['S4-T1-Q01']['answer']==attempted
            turn(student,'student_off_again','Without another search, give one short hint about the time/resources question, without revealing its answer.')
            student.post('/api/sessions/session-4/references/S4-T1-Q01').raise_for_status()
            turn(student,'after_reference_reveal','I opened the reference using the button. Explain briefly why practicality differs from reliability here.')
            turn(teacher,'teacher_on_search','Find official Cambridge English guidance on good language assessment, then suggest two discussion prompts with source links. Keep the response concise.',True,qid=None)
            export=student.get('/api/sessions/session-4/export');export.raise_for_status()
            (out/'student-export.json').write_text(json.dumps(export.json(),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            result.update(status='passed',reference_gate_verified=True,follow_up_preserved_answer=True,turn_count=len(turns))
    except Exception as exc:
        result.update(status='failed',error=str(exc));raise
    finally:
        server.should_exit=True;thread.join(timeout=10)
        result['owned_app_server_stopped']=not thread.is_alive()
        result['finished_at']=datetime.now().astimezone().isoformat();save()
        print(json.dumps({k:v for k,v in result.items() if k not in {'model_calls','searches','turns','model_preset','availability'}},ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':main()
