"""Exact sequential source traversal and durable guided-turn cursor tests.

Provider replies in HTTP tests are explicitly synthetic; this verifies scope,
continuation and persistence, not real-model reading quality.
"""
import copy
import json
import httpx
import pytest
from backend.aicademiya.reading_context import execute_plan,catalogue,validate_citations
from .test_stage12_reading_context import document
from .test_stage12_guided_reading import sourceenv,start,SourceProtocol
from .test_stage12_document_api import docenv
from .conftest import expect


def sequential(mid='m1',restart=False):return {'requests':[{'material_id':mid,'mode':'sequential','restart':restart}]}


def test_every_character_of_oversized_block_can_be_read_without_gaps():
    d=document();literal='BEGIN:'+('中文 A\n'*14000)+':EXACT_LAST_CHAR'
    d['manifest']['pages']=d['manifest']['pages'][:1];d['manifest']['pages'][0]['blocks']=d['manifest']['pages'][0]['blocks'][1:]
    d['manifest']['pages'][0]['blocks'][0]['text']=literal
    progress={};chunks=[];ranges=[]
    for _ in range(100):
        r=execute_plan([d],sequential(),progress=progress,char_budget=8000,max_blocks=3)
        chunks.extend(b['text']for b in r['blocks']);ranges.extend((b['char_start'],b['char_end'])for b in r['blocks']);progress.update(r['_progress_updates'])
        if r['coverage'][0]['eligible_text_complete']:break
    assert ''.join(chunks)==literal
    assert ranges[0][0]==0 and ranges[-1][1]==len(literal)
    assert all(a[1]==b[0]for a,b in zip(ranges,ranges[1:]))
    assert progress['m1']['read_characters']==len(literal)and progress['m1']['all_stored_regions_read']


def test_all317_pages_reachable_sequentially():
    d=document();progress={};pages=set();delivered=[]
    for _ in range(400):
        r=execute_plan([d],sequential(),progress=progress,char_budget=5000,max_blocks=30)
        pages.update(b['page']for b in r['blocks']);delivered.extend(b['text']for b in r['blocks']);progress.update(r['_progress_updates'])
        if r['coverage'][0]['eligible_text_complete']:break
    expected=''.join(b['text']for p in d['manifest']['pages']for b in p['blocks'])
    assert pages==set(range(1,318))and ''.join(delivered)==expected
    assert progress['m1']['read_characters']==progress['m1']['available_characters']==len(expected)


def test_failed_or_uncommitted_read_does_not_mutate_saved_progress():
    d=document();progress={};before=copy.deepcopy(progress)
    result=execute_plan([d],sequential(),progress=progress,char_budget=100)
    assert progress==before and result['_progress_updates']['m1']['read_characters']==100


def test_revision_change_resets_cursor_not_rebind_old_position():
    d=document();first=execute_plan([d],sequential(),char_budget=100)
    newer=copy.deepcopy(d);newer['revision_id']='revision-new'
    result=execute_plan([newer],sequential(),progress=first['_progress_updates'],char_budget=100)
    assert result['blocks'][0]['page']==1 and result['blocks'][0]['char_start']==0
    assert result['_progress_updates']['m1']['revision_id']=='revision-new'


def test_explicit_restart_and_private_gate():
    d=document();first=execute_plan([d],sequential(),char_budget=100)
    restarted=execute_plan([d],sequential(restart=True),progress=first['_progress_updates'],char_budget=100)
    assert first['blocks']==restarted['blocks']
    secret=document('secret',visibility='teacher')
    with pytest.raises(ValueError):execute_plan([secret],sequential('secret'))
    assert 'secret'not in json.dumps(catalogue([d,secret],progress={'secret':{'revision_id':'revision-old','read_characters':1}}))


def test_unresolved_regions_never_disappear_behind_text_completion():
    d=document();d['manifest']['pages']=d['manifest']['pages'][:1]
    d['manifest']['pages'][0]['blocks'][0]['quality']='needs_review'
    r=execute_plan([d],sequential(),char_budget=10000)
    assert r['coverage'][0]['eligible_text_complete']and r['coverage'][0]['unresolved_blocks']==1
    assert not r['coverage'][0]['all_stored_regions_read']
    assert 'Section 1'not in ''.join(b['text']for b in r['blocks'])


@pytest.mark.parametrize('selection',[{'pages':[2]},{'block_ids':['p2-b1']},{'query':'hidden skip'}])
def test_sequential_cannot_smuggle_lookup_skip(selection):
    plan=sequential();plan['requests'][0].update(selection)
    with pytest.raises(ValueError):execute_plan([document()],plan)


def test_quote_must_match_current_continuation_not_another_part():
    d=document();d['manifest']['pages']=d['manifest']['pages'][:1]
    d['manifest']['pages'][0]['blocks']=d['manifest']['pages'][0]['blocks'][1:]
    d['manifest']['pages'][0]['blocks'][0]['text']='EARLY'*1200+'LATE literal quote'
    first=execute_plan([d],sequential(),char_budget=6000);later=execute_plan([d],sequential(),progress=first['_progress_updates'],char_budget=6000)
    assert validate_citations([{'ref':'D1','quote':'LATE literal quote'}],later)
    with pytest.raises(ValueError):validate_citations([{'ref':'D1','quote':'EARLY'}],later)


class SequentialProtocol(SourceProtocol):
    def __call__(self,request):
        body=json.loads(request.content)
        if body['messages'][0]['content'].startswith('Plan bounded reads'):
            self.requests.append(body);directory=json.loads(body['messages'][1]['content'])['directory']
            result=sequential(directory[0]['material_id'])
            return httpx.Response(200,json={'choices':[{'message':{'role':'assistant','content':json.dumps(result)}}]})
        return super().__call__(request)


def sequential_env(sourceenv,monkeypatch):
    import backend.aicademiya.guided_reading as reading
    app=sourceenv[0];provider=SequentialProtocol();app.state.tutor.transport=httpx.MockTransport(provider)
    original=reading.execute_plan
    def small_window(*args,**kwargs):kwargs['char_budget']=30;return original(*args,**kwargs)
    monkeypatch.setattr(reading,'execute_plan',small_window)
    start(sourceenv);return app,provider


def post(env,rid):return env[2].post('/api/sessions/s4/tutor/turn',params={'version_id':env[-1]},json={'request_id':rid,'message':'Continue reading the whole source in order.'})


def test_http_cursor_advances_only_once_for_completed_request(sourceenv,monkeypatch):
    app,provider=sequential_env(sourceenv,monkeypatch)
    first=expect(post(sourceenv,'seq1'));coverage=first['messages'][-1]['metadata']['document_read_coverage'][0]
    assert coverage['read_characters']==30 and not coverage['eligible_text_complete']
    calls=len(provider.requests);repeat=expect(post(sourceenv,'seq1'));assert len(provider.requests)==calls
    assert repeat['messages'][-1]['metadata']['document_read_coverage'][0]==coverage
    second=expect(post(sourceenv,'seq2'));assert second['messages'][-1]['metadata']['document_read_coverage'][0]['read_characters']==60
    assert second['attempts']=={}and second['progress']['answered']==0
    with app.state.database.connect()as conn:
        states=[json.loads(r[0])for r in conn.execute('SELECT state_json FROM tutor_runs').fetchall()]
    assert any(s.get('document_read_progress',{}).get(sourceenv[5],{}).get('read_characters')==60 for s in states)


def test_http_failed_quote_does_not_consume_next_source_span(sourceenv,monkeypatch):
    _,provider=sequential_env(sourceenv,monkeypatch)
    first=expect(post(sourceenv,'good1'));assert first['messages'][-1]['metadata']['document_read_coverage'][0]['read_characters']==30
    provider.bad_quote=True;assert post(sourceenv,'bad2').status_code==502
    provider.bad_quote=False
    second=expect(post(sourceenv,'recover3'));assert second['messages'][-1]['metadata']['document_read_coverage'][0]['read_characters']==60


def test_legacy_chat_continues_same_scoped_source_cursor(sourceenv,monkeypatch):
    _,provider=sequential_env(sourceenv,monkeypatch)
    def chat(rid):
        return sourceenv[2].post('/api/sessions/s4/chat',params={'version_id':sourceenv[-1]},json={'request_id':rid,'question_id':'q1','intent':'ask','message':'Continue reading the source in order.','web_search':False})
    first=expect(chat('legacy-seq1'));assert first['messages'][-1]['metadata']['document_read_coverage'][0]['read_characters']==30
    n=len(provider.requests);expect(chat('legacy-seq1'));assert len(provider.requests)==n
    second=expect(chat('legacy-seq2'));assert second['messages'][-1]['metadata']['document_read_coverage'][0]['read_characters']==60
    assert second['attempts']=={}


def test_unicode_byte_windows_continue_without_losing_a_codepoint():
    d=document();d['manifest']['pages']=d['manifest']['pages'][:1]
    d['manifest']['pages'][0]['blocks']=d['manifest']['pages'][0]['blocks'][1:]
    literal='中文🙂源材料'*1234;d['manifest']['pages'][0]['blocks'][0]['text']=literal
    progress={};parts=[]
    for _ in range(100):
        result=execute_plan([d],sequential(),progress=progress,char_budget=6000,byte_budget=1001)
        assert sum(len(b['text'].encode('utf-8'))for b in result['blocks'])<=1001
        parts.extend(b['text']for b in result['blocks']);progress.update(result['_progress_updates'])
        if result['coverage'][0]['eligible_text_complete']:break
    assert ''.join(parts)==literal and progress['m1']['read_characters']==len(literal)
