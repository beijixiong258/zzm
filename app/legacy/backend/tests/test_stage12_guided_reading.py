"""Actual app/model-protocol HTTP integration; deliberately synthetic extraction/model."""
import json
import httpx
import pytest
from .test_stage12_document_api import docenv,complete,endpoint
from .conftest import expect,publish

class SourceProtocol:
    def __init__(self):self.requests=[];self.bad_quote=False;self.bad_plan=False;self.repair_success=False;self.answer_intent=False;self.repair_error=False
    def __call__(self,request):
        body=json.loads(request.content);self.requests.append(body);system=body['messages'][0]['content']
        if system.startswith('Revise source-grounded') and self.repair_error:return httpx.Response(503,json={'error':'Synthetic repair-provider unavailable'})
        if system.startswith('Plan bounded reads'):
            value=json.loads(body['messages'][1]['content']);doc=value['directory'][0]
            result={'requests':[{'material_id':'unavailable'if self.bad_plan else doc['material_id'],'pages':[doc['pdf_pages']],'block_ids':[],'query':''}]}
        else:
            envelope=json.loads(body['messages'][1]['content']);blocks=envelope.get('document_reads',{}).get('blocks',[])
            citations=[]
            if blocks:
                b=blocks[-1];bad=self.bad_quote and not(system.startswith('Revise source-grounded')and self.repair_success);citations=[{'ref':b['ref'],'quote':'NOT IN THE SOURCE'if bad else b['text']}]
            text='SYNTHETIC protocol response based on the supplied source.'
            if system.startswith('You are the AIcademiya guided'):
                data=json.loads(system[system.index('{"task":'):]);opening=data['task']=='start'
                result={'schema_version':1,'text':text,'intent':'none'if opening else'ask','question_id':None if opening else(data.get('current_question')or{}).get('id'),'outcome':'unknown','document_citations':citations}
                if not opening and self.answer_intent:result.update(intent='answer',outcome='sufficient')
            else:result={'text':text,'document_citations':citations}
        return httpx.Response(200,json={'choices':[{'message':{'role':'assistant','content':json.dumps(result)}}]})

@pytest.fixture
def sourceenv(docenv,monkeypatch):
    app,teacher,student,processor=docenv
    mid,rid,_=complete(teacher,count=3)
    detail=expect(teacher.get('/api/sessions/s4'))
    questions=detail['questions']
    for q in questions:q['source_material_ids']=[mid];q['source_links']=[]
    expect(teacher.patch('/api/sessions/s4',json={'questions':questions,'teaching_profile':{**detail['teaching_profile'],'phases':['worksheet','wrap_up']}}))
    vid=publish(teacher)['id']
    provider=SourceProtocol();app.state.tutor.transport=httpx.MockTransport(provider)
    monkeypatch.setenv('AICADEMIYA_AI_PROVIDER','aicademiya-router')
    with app.state.database.connect()as conn:
        for key,value in [('ai_mode','openai'),('ai_base_url','http://127.0.0.1:18280/v1'),('ai_model','AIcademiya-64kx3-Qwen3.8-27B')]:conn.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(key,value))
    return app,teacher,student,processor,provider,mid,rid,vid

def start(env):
    _,_,student,_,_,_,_,vid=env
    return expect(student.post('/api/sessions/s4/tutor/start',params={'version_id':vid},json={'request_id':'source-start'}))

def turn(env,request='source-turn'):
    return env[2].post('/api/sessions/s4/tutor/turn',params={'version_id':env[-1]},json={'request_id':request,'message':'What does the source say on its last page?'})

def test_guided_late_page_quote_and_authorized_original_link(sourceenv):
    start(sourceenv);app,teacher,student,_,provider,mid,rid,vid=sourceenv
    result=expect(turn(sourceenv));citation=result['messages'][-1]['citations'][0]
    assert citation['kind']=='document'and citation['material_id']==mid and citation['revision_id']==rid
    assert citation['page']==3 and citation['block_id']=='p3-b0'and citation['quote']=='SYNTHETIC complete fixture text on page 3'
    assert citation['url'].endswith('version_id='+vid+'#page=3')
    assert student.get(citation['url'].split('#')[0]).status_code==200
    assert any(r['messages'][0]['content'].startswith('Plan bounded reads')for r in provider.requests)
    final=provider.requests[-1];assert citation['quote']not in final['messages'][0]['content']
    assert citation['quote']in final['messages'][1]['content']
    assert 'document_dir'not in json.dumps(provider.requests)and 'uploads'not in json.dumps(provider.requests)
    assert 'manifest'not in json.dumps(result)
    with app.state.database.connect()as conn:
        stored=json.loads(conn.execute("SELECT citations_json FROM messages WHERE id=?",(result['messages'][-1]['id'],)).fetchone()[0])
        assert stored==result['messages'][-1]['citations']

@pytest.mark.parametrize('failure',['bad_quote','bad_plan'])
def test_invalid_read_or_quote_fails_visibly_without_assistant_commit(sourceenv,failure):
    start(sourceenv);setattr(sourceenv[4],failure,True)
    r=turn(sourceenv);assert r.status_code==502,r.text
    work=expect(sourceenv[2].get('/api/sessions/s4/workspace',params={'version_id':sourceenv[-1]}))
    assert work['messages'][-1]['role']=='user'
    assert work['messages'][-1]['content']=='What does the source say on its last page?'
    assert work['tutor']['pending_request_id']is None
    repairs=[r for r in sourceenv[4].requests if r['messages'][0]['content'].startswith('Revise source-grounded')]
    assert len(repairs)==(1 if failure=='bad_quote'else 0)


def test_old_published_revision_remains_read_after_draft_source_correction(sourceenv):
    start(sourceenv);_,teacher,_,_,_,mid,rid,vid=sourceenv
    review=expect(teacher.post(endpoint(mid)+'/reviews',json={'request_id':'source-correction','expected_revision':rid,'changes':[{'block_id':'p3-b0','text':'NEW DRAFT CONTENT','quality':'approved','reason':'SYNTHETIC source check'}]}))
    assert review['document']['revision_id']!=rid
    result=expect(turn(sourceenv));c=result['messages'][-1]['citations'][0]
    assert c['revision_id']==rid and 'NEW DRAFT'not in c['quote']
    assert c['version_id']==vid


def test_unverified_last_page_is_not_sent_as_authoritative_evidence(sourceenv):
    _,teacher,_,_,provider,mid,rid,_=sourceenv
    expect(teacher.post(endpoint(mid)+'/reviews',json={'request_id':'exclude-unsafe','expected_revision':rid,'changes':[{'block_id':'p3-b0','quality':'excluded','reason':'SYNTHETIC region cannot be verified'}]}))
    new=publish(teacher)['id'];env=(*sourceenv[:-1],new);start(env)
    response=turn(env);assert response.status_code==502,response.text
    assert 'no usable verified extraction'in response.json()['detail']
    assert provider.requests[-1]['messages'][0]['content'].startswith('Plan bounded reads')


def test_legacy_chat_also_reads_complete_document_without_silent_preview_fallback(sourceenv):
    _,_,student,_,provider,mid,rid,vid=sourceenv
    result=expect(student.post('/api/sessions/s4/chat',params={'version_id':vid},json={'request_id':'legacy-document','question_id':'q1','intent':'ask','message':'What does the last source page say?','web_search':False}))
    c=result['messages'][-1]['citations'][0]
    assert c['material_id']==mid and c['revision_id']==rid and c['page']==3
    assert any(r['messages'][0]['content'].startswith('Plan bounded reads')for r in provider.requests)


def test_source_review_reports_complete_document_without_claiming_live_reads(sourceenv):
    _,teacher,_,_,provider,mid,_,_=sourceenv
    before=len(provider.requests)
    result=expect(teacher.post('/api/teacher/sessions/s4/source-review',json={'question_id':'q1','phase':'worksheet'}))
    row=next(x for x in result['materials']if x['id']==mid)
    assert row['document']['page_count']==3 and row['available_chars']>0 and row['included_chars']==0
    assert 'planned from each learner request'in row['reason']
    assert len(provider.requests)==before

def test_one_actual_adapter_quote_revision_and_completed_retry_no_more_calls(sourceenv):
    start(sourceenv);provider=sourceenv[4];provider.bad_quote=True;provider.repair_success=True
    work=expect(turn(sourceenv));assert work['messages'][-1]['citations'][0]['quote']=='SYNTHETIC complete fixture text on page 3'
    repairs=[r for r in provider.requests if r['messages'][0]['content'].startswith('Revise source-grounded')]
    assert len(repairs)==1
    dynamic=json.loads(repairs[0]['messages'][1]['content'])
    assert dynamic['previous_feedback']['document_citations'][0]['quote']=='NOT IN THE SOURCE'
    assert repairs[0]['response_format']['json_schema']['name']=='aicademiya_document_quote_revision'
    before=len(provider.requests);expect(turn(sourceenv));assert len(provider.requests)==before

def test_revision_provider_error_is_visible_and_raw_request_retained(sourceenv):
    start(sourceenv);provider=sourceenv[4];provider.bad_quote=True;provider.repair_error=True
    failed=turn(sourceenv);assert failed.status_code==502 and '503'in failed.json()['detail']
    work=expect(sourceenv[2].get('/api/sessions/s4/workspace',params={'version_id':sourceenv[-1]}))
    assert work['messages'][-1]['role']=='user'and work['attempts']=={}
    assert work['tutor']['pending_request_id']is None

@pytest.mark.parametrize('message',[
    'List the six numbered steps for developing a standardized test, in source order, with source citations.',
    'According to Table 5.1, what four advantages of standardized tests are listed? Cite the source.',
    'According to the speaking rubric, how do the level4 and level2 bands differ? Cite the source; do not grade anyone.',
    'Does the paragraph after the rubric say standardized tests exclude human judgments? Explain with an exact source citation.',
    'On printed page121, what is the final annotated bibliography entry and what does its annotation say? Quote the source; do not correct source typos.',
])
def test_source_requests_do_not_fabricate_answers_or_progress(sourceenv,message):
    start(sourceenv);sourceenv[4].answer_intent=True
    work=expect(sourceenv[2].post('/api/sessions/s4/tutor/turn',params={'version_id':sourceenv[-1]},json={'request_id':'source-ask','message':message}))
    assert work['attempts']=={}and work['progress']['answered']==0
    assert work['tutor']['phase']=='worksheet'and work['messages'][-1]['intent']=='ask'
    assert all(q['answer_count']==0 and q['last_outcome']=='unknown'for q in work['tutor']['question_states'].values())
