"""Real local-model teaching probes through the actual AIcademiya HTTP API.

Synthetic learning records only, separate QA database. Does not modify the model service.
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
import uuid
import httpx

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/live-model'
MODEL_BASE='http://192.168.32.5:8027/v1'
MODEL_ID='qwen27b-q8'


def main():
    parser=argparse.ArgumentParser(description='Run real inference only in an agreed available resource window')
    parser.add_argument('--resource-window-confirmed',action='store_true')
    args=parser.parse_args()
    if not args.resource_window_confirmed:
        raise SystemExit('Model optimization/benchmarking may be active in another session. Confirm resource availability first, then pass --resource-window-confirmed.')
    OUT.mkdir(parents=True,exist_ok=True)
    data=Path(tempfile.mkdtemp(prefix='qa-live-',dir=ROOT/'artifacts'))
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    env=os.environ.copy();env.update(AICADEMIYA_DATA_DIR=str(data),AICADEMIYA_DEMO_ENABLED='true',AICADEMIYA_AI_MODE='openai',AICADEMIYA_AI_BASE_URL=MODEL_BASE,AICADEMIYA_AI_MODEL=MODEL_ID,AICADEMIYA_AI_API_KEY='aicademiya-local',NO_PROXY='127.0.0.1,localhost,::1,192.168.32.5')
    log=(data/'server.log').open('w',encoding='utf-8')
    process=subprocess.Popen([sys.executable,'-m','uvicorn','backend.aicademiya.main:app','--host','127.0.0.1','--port',str(port)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
    turns=[];result={'model':MODEL_ID,'model_base_url':MODEL_BASE,'qa_data_directory':str(data),'synthetic_learning_records':True,'real_model':True}
    try:
        with httpx.Client(base_url=base,trust_env=False,timeout=100) as client:
            until=time.monotonic()+30
            while time.monotonic()<until:
                if process.poll() is not None:raise RuntimeError('QA service exited')
                try:
                    if client.get('/api/health').status_code==200:break
                except httpx.RequestError:time.sleep(0.2)
            else:raise RuntimeError('QA readiness timed out')
            client.post('/api/auth/demo',json={'role':'student','student_index':1}).raise_for_status()
            denied=client.post('/api/sessions/session-4/references/S4-T1-Q01')
            assert denied.status_code==409
            def turn(label,sid,qid,intent,message):
                start=time.monotonic()
                response=client.post(f'/api/sessions/{sid}/chat',json={'message':message,'question_id':qid,'intent':intent,'request_id':str(uuid.uuid4())})
                record={'case':label,'session_id':sid,'question_id':qid,'intent':intent,'input':message,'seconds':round(time.monotonic()-start,2),'http_status':response.status_code}
                if response.status_code==200:
                    work=response.json();answer=work['messages'][-1]
                    record.update(output=answer['content'],mode=answer['mode'],citations=answer.get('citations',[]),progress=work['progress'])
                    assert answer['role']=='assistant' and answer['mode']=='openai' and answer['content'].strip()
                else:record['error']=response.text[:2000]
                turns.append(record)
                (OUT/'turns.json').write_text(json.dumps(turns,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
                print(json.dumps(record,ensure_ascii=False),flush=True)
                response.raise_for_status()
            turn('wrong_concept_hint','session-4','S4-T1-Q01','answer','I think the answer is reliability, because the test takes little time and uses few resources. Am I on the right track?')
            turn('follow_up_without_answer_replacement','session-4','S4-T1-Q01','ask','Give me one short hint about what to reconsider, but do not tell me the answer yet.')
            reveal=client.post('/api/sessions/session-4/references/S4-T1-Q01');reveal.raise_for_status()
            turn('explain_after_explicit_reveal','session-4','S4-T1-Q01','ask','I have now viewed the reference using the button. Explain briefly how that concept differs from reliability.')
            turn('accept_contextual_open_answer','session-4','S4-T4-Q02','answer','Reading aloud is not necessarily inauthentic. A train employee reading an actual safety announcement to passengers has a real communicative purpose. I would put the task in that context instead of asking students to read isolated sentences.')
            turn('fixed_diagram_feedback','session-4','S4-T3-Q01','answer','I choose graph A for positive correlation because its points generally rise from left to right.')
            client.post('/api/sessions/session-2/reading',json={'group_id':'II-Bray'}).raise_for_status()
            turn('source_supported_alternative_to_old_key','session-2','S2-II-Bray-Q05','answer','Some students do not receive tutoring because they can solve their own learning problems independently or with classmates. This is the strongest reason reported on printed page 615 of Bray and Kwok.')
            turn('sample_denominator_correction_hint','session-2','S2-II-Bray-Q04','answer','63.6% of all 630 students received private tutoring to prepare for examinations. Is my interpretation of the denominator accurate?')
            result.update(status='passed',turn_count=len(turns),reference_gate_verified=True,model_calls_all_real=True,automatic_content_score=None)
    except Exception as exc:
        result.update(status='failed',error=str(exc),turn_count=len(turns));raise
    finally:
        process.terminate()
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        log.close();result['owned_server_stopped']=process.poll() is not None
        (OUT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
