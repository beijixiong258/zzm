"""Exercise the real HTTP workflow against an isolated QA server.

Run only against a fresh test data directory, not the user's working database.
This script intentionally creates submitted demo-student learning records.
"""
from pathlib import Path
import argparse
import json
import time
import uuid
import httpx

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--base-url',default='http://127.0.0.1:18773')
    parser.add_argument('--confirm-test-database',action='store_true')
    parser.add_argument('--out',default=str(ROOT/'artifacts/api-acceptance.json'))
    args=parser.parse_args()
    if not args.confirm_test_database:
        raise SystemExit('Use an isolated QA database and pass --confirm-test-database; this test writes demo records.')
    evidence=[]
    started=time.monotonic()

    def call(client,method,path,body=None,status=200):
        response=client.request(method,args.base_url+path,json=body,timeout=120)
        evidence.append({'method':method,'path':path,'status':response.status_code,'expected':status})
        assert response.status_code==status,(path,response.status_code,response.text[:500])
        return response.json()

    teacher=httpx.Client(); student=httpx.Client(); other=httpx.Client(); anonymous=httpx.Client()
    try:
        call(anonymous,'GET','/api/health')
        call(anonymous,'GET','/api/auth/me',status=401)
        teacher_user=call(teacher,'POST','/api/auth/demo',{'role':'teacher'})['user']
        student_user=call(student,'POST','/api/auth/demo',{'role':'student','student_index':1})['user']
        other_user=call(other,'POST','/api/auth/demo',{'role':'student','student_index':2})['user']
        assert len({teacher_user['id'],student_user['id'],other_user['id']})==3
        courses=call(student,'GET','/api/courses')
        assert any(c['id']=='educ7703' for c in courses)
        sessions=call(student,'GET','/api/courses/educ7703/sessions')
        assert {'session-4','session-2'}<=set(s['id'] for s in sessions)
        workspace=call(student,'GET','/api/sessions/session-4/workspace')
        assert len(workspace['session']['questions'])==22
        assert workspace['progress']['total']==22
        assert 'reference_answers' not in workspace['session']
        assert all(m['visibility']=='student' for m in workspace['session']['materials'])
        first=workspace['session']['questions'][0]['id']
        call(student,'POST',f'/api/sessions/session-4/references/{first}',status=409)
        call(student,'POST','/api/sessions/session-4/submit',{},status=409)
        ask=call(student,'POST','/api/sessions/session-4/chat',{'message':'Can you give me a hint without the answer?','question_id':first,'intent':'ask','request_id':str(uuid.uuid4())})
        assert first not in ask['attempts'],'A clarification was incorrectly saved as an answer'
        assert ask['messages'][-1]['mode'] in {'demo','openai'}
        answer=call(student,'POST',f'/api/sessions/session-4/answers/{first}',{'answer':'practicality'})
        assert answer['attempts'][first]['answer']=='practicality'
        ref=call(student,'POST',f'/api/sessions/session-4/references/{first}')
        assert ref['reference'].strip()
        revised=call(student,'POST',f'/api/sessions/session-4/answers/{first}',{'answer':'Practicality: the assessment can be administered with the available resources.'})
        assert revised['attempts'][first]['revision_count']>=answer['attempts'][first]['revision_count']
        restored=call(student,'GET','/api/sessions/session-4/workspace')
        assert restored['attempts'][first]['answer']==revised['attempts'][first]['answer']
        other_workspace=call(other,'GET','/api/sessions/session-4/workspace')
        assert first not in other_workspace['attempts']
        teacher_read_path=f'/api/teacher/sessions/session-4/students/{student_user["id"]}/workspace'
        call(other,'GET',teacher_read_path,status=403)
        call(student,'GET','/api/teacher/settings',status=403)
        graphs=[im for q in workspace['session']['questions'] for im in q['images']]
        assert len({g['url'] for g in graphs})==3
        for url in sorted({g['url'] for g in graphs}):
            response=student.get(args.base_url+url)
            assert response.status_code==200 and response.headers.get('content-type','').startswith('image/')
            evidence.append({'method':'GET','path':url,'status':response.status_code,'check':'real image bytes'})
        for question in workspace['session']['questions']:
            if question['id']==first: continue
            call(student,'POST',f'/api/sessions/session-4/answers/{question["id"]}',{'answer':'QA test response for '+question['id']+'; not a model or real student answer.'})
        submitted=call(student,'POST','/api/sessions/session-4/submit',{})
        assert submitted['submission']['status']=='submitted'
        teacher_view=call(teacher,'GET',teacher_read_path)
        assert teacher_view['attempts'][first]['answer']==revised['attempts'][first]['answer']
        assert teacher_view['submission']['status']=='submitted'
        students=call(teacher,'GET','/api/teacher/sessions/session-4/students')
        assert any(s['user']['id']==student_user['id'] and s['status']=='submitted' for s in students)
        reviewed=call(teacher,'POST',f'/api/teacher/sessions/session-4/students/{student_user["id"]}/review',{'status':'confirmed','note':'QA-only teacher confirmation. No formal grade.'})
        assert reviewed['submission']['status']=='confirmed'
        s2=call(other,'POST','/api/sessions/session-2/reading',{'group_id':'II-Pong'})
        assert s2['progress']['total']==14
        assert len(s2['progress']['active_question_ids'])==14
        assert not any('II-Bray' in q for q in s2['progress']['active_question_ids'])
        s2b=call(other,'POST','/api/sessions/session-2/reading',{'group_id':'II-Bray'})
        assert s2b['progress']['total']==14
        assert not any('II-Pong' in q for q in s2b['progress']['active_question_ids'])
        export=call(student,'GET','/api/sessions/session-4/export')
        assert export,'Empty export'
        result={'status':'passed','base_url':args.base_url,'seconds':round(time.monotonic()-started,2),'request_count':len(evidence),'checks':evidence,'ai_mode':workspace['ai']['mode'],'llm_quality_evaluated':False,'synthetic_data_only':True}
    except Exception as exc:
        result={'status':'failed','error':str(exc),'checks':evidence,'seconds':round(time.monotonic()-started,2)}
        raise
    finally:
        for client in (teacher,student,other,anonymous): client.close()
        if 'result' in locals():
            dest=Path(args.out); dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print(json.dumps({k:v for k,v in result.items() if k!='checks'},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
