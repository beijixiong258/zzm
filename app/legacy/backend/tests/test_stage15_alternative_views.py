"""CPU-only view-policy fixtures; no OCR/model call or accuracy claim.

Actual retained native/VLM evidence is replayed separately under
artifacts/stage15/alternative-views, not relabelled as fresh inference.
"""
import copy
import json
import httpx
import pytest
from fastapi.testclient import TestClient
from backend.aicademiya.db import issue_session
from backend.aicademiya.reading_context import (
    TEXT_VIEW_POLICY, all_blocks, catalogue, execute_plan, ranked_blocks,
    validate_citations, whole_page_markdown,
)
from .test_stage12_document_api import docenv,complete,endpoint
from .test_stage12_guided_reading import SourceProtocol
from .conftest import expect,publish


MARKERS = ['source_transcription_ocr; machine_extracted_vlm',
           'not_independently_verified', 'body_geometry_unlocalized; whole_source_locator',
           'model_uncertainty:Formatting note retained literally.']


def dual_document(count=1):
    pages=[]
    for n in range(1,count+1):
        pages.append({'number':n,'printed_label':str(n+100),'image':f'pages/p{n}.png',
            'status':'needs_review','blocks':[
                {'id':f'p{n}-b0','type':'heading','quality':'extracted','text':'Shared source heading',
                 'bbox':[0,0,1,.1],'issues':['source_transcription_native']},
                {'id':f'p{n}-b1','type':'text','quality':'extracted','text':'Shared native original, not a literal Markdown duplicate.',
                 'bbox':[0,.1,1,.8],'issues':['source_transcription_native']},
                {'id':f'p{n}-b2','type':'image','quality':'needs_review','text':'',
                 'bbox':[0,.8,1,1],'visual_description':'Shared unverified picture description','issues':[]},
                {'id':f'p{n}-b3','type':'text','quality':'extracted','text':'# Shared Markdown\n\nDifferent literal words, same source page.',
                 'text_format':'markdown','bbox':[0,0,1,1],'issues':list(MARKERS)},
            ]})
    return {'material_id':'m1','revision_id':'revision-old','title':'SYNTHETIC dual-view source',
            'source_label':'SYNTHETIC source','visibility':'student','kind':'reading','manifest':{'pages':pages}}


def read(d, *, progress=None, char_budget=24000, **selection):
    return execute_plan([d],{'requests':[{'material_id':'m1',**selection}]},progress=progress,char_budget=char_budget)


@pytest.mark.parametrize('selection',[{'pages':[1]},{'query':'Shared'},{'mode':'sequential'}],ids=['page','search','sequential'])
def test_default_reads_one_view_without_changing_source(selection):
    d=dual_document();before=copy.deepcopy(d);r=read(d,**selection)
    assert [b['block_id']for b in r['blocks']]==['p1-b3']
    assert r['blocks'][0]['text']==d['manifest']['pages'][0]['blocks'][3]['text']
    assert r['blocks'][0]['text_view_role']=='primary'
    assert r['blocks'][0]['text_format']=='markdown'
    assert r['blocks'][0]['source_notes']==['Formatting note retained literally.']
    assert r['blocks'][0]['transcription_source']=='vision_model; not independently verified'
    assert d==before
    assert [b['id']for _,b in all_blocks(d)]==['p1-b2','p1-b3']
    assert [b['id']for _,b in all_blocks(d,include_alternatives=True)]==['p1-b0','p1-b1','p1-b2','p1-b3']


def test_explicit_original_and_both_views_remain_distinct_literal_refs():
    d=dual_document();r=read(d,block_ids=['p1-b1','p1-b3'],pages=[1],query='Shared')
    assert [b['block_id']for b in r['blocks']]==['p1-b1','p1-b3']
    assert [b['text_view_role']for b in r['blocks']]==['alternative','primary']
    assert [b['page_text_view']for b in r['blocks']]==['source-blocks','whole-page-markdown:p1-b3']
    for b in r['blocks']:
        assert validate_citations([{'ref':b['ref'],'quote':b['text']}],r)[0]['block_id']==b['block_id']
    with pytest.raises(ValueError):validate_citations([{'ref':'D2','quote':r['blocks'][0]['text']}],r)
    assert r['included_characters']==sum(len(b['text'])for b in r['blocks'])


@pytest.mark.parametrize('candidate_quality',['extracted','approved'])
def test_approved_original_page_is_not_overridden(candidate_quality):
    d=dual_document();bs=d['manifest']['pages'][0]['blocks'];bs[1]['quality']='approved';bs[3]['quality']=candidate_quality
    r=read(d,pages=[1]);assert [b['block_id']for b in r['blocks']]==['p1-b0','p1-b1']
    assert all(b['primary_page_text_view']=='source-blocks'for b in r['blocks'])
    alt=read(d,block_ids=['p1-b3']);assert alt['blocks'][0]['text_view_role']=='alternative'
    assert catalogue([d])[0]['outline'][0]['block_id']=='p1-b0'


def test_approved_image_does_not_approve_original_text_or_block_markdown():
    d=dual_document();d['manifest']['pages'][0]['blocks'][2]['quality']='approved'
    assert [b['block_id']for b in read(d,pages=[1])['blocks']]==['p1-b3']


@pytest.mark.parametrize('quality',['needs_review','excluded'])
def test_rejected_candidates_do_not_replace_original_or_become_evidence(quality):
    d=dual_document();d['manifest']['pages'][0]['blocks'][3]['quality']=quality
    r=read(d,pages=[1]);assert [b['block_id']for b in r['blocks']]==['p1-b0','p1-b1']
    assert len(r['notices'])==2
    explicit=read(d,block_ids=['p1-b3']);assert explicit['blocks']==[]
    assert 'text_view_id'not in read(d,mode='sequential')['coverage'][0]


@pytest.mark.parametrize('mutation',['local-ocr','localized-body','plain','image-description','marker-suffix','generic-markdown'])
def test_non_whole_page_sources_never_trigger_alternative_policy(mutation):
    d=dual_document();b=d['manifest']['pages'][0]['blocks'][3]
    if mutation=='local-ocr':b['issues']=['source_transcription_ocr','machine_extracted_vlm']
    elif mutation=='localized-body':b['issues']=['source_transcription_ocr; machine_extracted_vlm','whole_source_locator']
    elif mutation=='plain':b['text_format']='plain'
    elif mutation=='image-description':b.update(type='image',text='',visual_description='Whole page story')
    elif mutation=='marker-suffix':b['issues']=['source_transcription_ocr_extra; machine_extracted_vlm','body_geometry_unlocalized; whole_source_locator']
    else:b['issues']=[]
    assert not whole_page_markdown(b)
    assert [b['id']for _,b in all_blocks(d)]==[b['id']for b in d['manifest']['pages'][0]['blocks']]
    assert 'text_view_id'not in read(d,mode='sequential')['coverage'][0]


def test_explicit_withheld_alternative_does_not_bypass_quality_gate():
    d=dual_document();bs=d['manifest']['pages'][0]['blocks'];bs[0]['quality']='needs_review';bs[1]['quality']='excluded'
    r=read(d,block_ids=['p1-b0','p1-b1','p1-b3'])
    assert [b['block_id']for b in r['blocks']]==['p1-b3']and len(r['notices'])==2
    coverage=read(d,mode='sequential')['coverage'][0]
    assert coverage['alternative_unresolved_blocks']==1 and coverage['alternative_excluded_blocks']==1
    assert coverage['unresolved_blocks']==1 and coverage['excluded_blocks']==0


def test_coverage_counts_only_chosen_codepoints_and_keeps_alternative_counts():
    d=dual_document();r=read(d,mode='sequential');c=r['coverage'][0];bs=d['manifest']['pages'][0]['blocks']
    assert c['read_characters']==c['available_characters']==len(bs[3]['text'])
    assert c['alternative_text_blocks']==2
    assert c['alternative_text_characters']==len(bs[0]['text'])+len(bs[1]['text'])
    assert c['text_view_policy']==TEXT_VIEW_POLICY
    assert 'not unique source characters or semantic verification'in c['coverage_basis']
    assert c['eligible_text_complete']and not c['all_stored_regions_read']
    assert c['unresolved_blocks']==1  # Original image still unresolved, not OCR-gated.
    assert catalogue([d])[0]['outline']==[]
    saved=catalogue([d],progress=r['_progress_updates'])[0]['sequential_reading']
    assert saved['text_view_id']==c['text_view_id']and saved['alternative_text_blocks']==2


def test_legacy_cursor_is_not_applied_to_changed_projection_but_survives_legacy_document():
    d=dual_document();legacy={'m1':{'revision_id':'revision-old','block_index':1,'char_offset':8}}
    r=read(d,mode='sequential',progress=legacy,char_budget=12)
    assert r['blocks'][0]['block_id']=='p1-b3'and r['blocks'][0]['char_start']==0
    assert 'sequential_reading'not in catalogue([d],progress=legacy)[0]
    d['manifest']['pages'][0]['blocks'].pop()
    unchanged=read(d,mode='sequential',progress=legacy,char_budget=12)
    assert unchanged['blocks'][0]['block_id']=='p1-b1'and unchanged['blocks'][0]['char_start']==8
    assert 'text_view_id'not in unchanged['_progress_updates']['m1']


def test_view_switch_even_same_revision_resets_text_position_and_catalogue():
    d=dual_document();first=read(d,mode='sequential',char_budget=12);old=copy.deepcopy(first['_progress_updates'])
    same=read(d,mode='sequential',progress=old,char_budget=12)
    assert same['blocks'][0]['char_start']==12
    d['manifest']['pages'][0]['blocks'][1]['quality']='approved'
    assert 'sequential_reading'not in catalogue([d],progress=old)[0]
    switched=read(d,mode='sequential',progress=old,char_budget=12)
    assert switched['blocks'][0]['block_id']=='p1-b0'and switched['blocks'][0]['char_start']==0
    assert switched['_progress_updates']['m1']['text_view_id']!=old['m1']['text_view_id']
    assert old==first['_progress_updates']


def test_cursor_restart_revision_and_policy_identity_gates():
    d=dual_document();first=read(d,mode='sequential',char_budget=12)
    bad=copy.deepcopy(first['_progress_updates']);bad['m1']['text_view_id']='other-policy:other-sequence'
    for changed,selection,progress in [(d,{},bad),(d,{'restart':True},first['_progress_updates']),
        ({**d,'revision_id':'revision-new'},{},first['_progress_updates'])]:
        r=read(changed,mode='sequential',progress=progress,char_budget=12,**selection)
        assert r['blocks'][0]['char_start']==0


def test_deterministic_multiple_full_page_candidates_select_one_without_deleting_any():
    d=dual_document();bs=d['manifest']['pages'][0]['blocks'];second=copy.deepcopy(bs[3]);second.update(id='p1-b4',text='Shared second full page literal')
    bs.append(second)
    assert [b['id']for _,b in ranked_blocks(d,'Shared')]==['p1-b3']
    first=read(d,mode='sequential',char_budget=12)
    bs[4]['quality']='approved'
    chosen=read(d,mode='sequential',progress=first['_progress_updates'],char_budget=12)
    assert chosen['blocks'][0]['block_id']=='p1-b4'and chosen['blocks'][0]['char_start']==0
    assert chosen['coverage'][0]['alternative_text_blocks']==3
    explicit=read(d,block_ids=['p1-b3','p1-b4']);assert len(explicit['blocks'])==2
    assert explicit['blocks'][0]['text_view_role']=='alternative'


def test_unicode_byte_windows_keep_exact_selected_body_without_gaps():
    d=dual_document();literal='源文本🙂\nMarkdown **原样** '*1000;d['manifest']['pages'][0]['blocks'][3]['text']=literal
    prior={};chunks=[];spans=[]
    for _ in range(100):
        r=execute_plan([d],{'requests':[{'material_id':'m1','mode':'sequential'}]},progress=prior,char_budget=1000,byte_budget=901)
        chunks.extend(b['text']for b in r['blocks']);spans.extend((b['char_start'],b['char_end'])for b in r['blocks'])
        prior.update(r['_progress_updates'])
        if r['coverage'][0]['eligible_text_complete']:break
    assert ''.join(chunks)==literal
    assert all(a[1]==b[0]for a,b in zip(spans,spans[1:]))
    assert prior['m1']['available_characters']==len(literal)


def test_source_images_keep_independent_cursor_across_text_projection_and_text_only_turns():
    d=dual_document(3);first=read(d,mode='sequential',include_images=True,char_budget=12)
    assert [i['page']for i in first['images']]==[1,2]
    text_only=read(d,mode='sequential',progress=first['_progress_updates'],char_budget=12)
    assert text_only['_progress_updates']['m1']['visual_page_index']==2
    d['manifest']['pages'][0]['blocks'][1]['quality']='approved'
    next_read=read(d,mode='sequential',include_images=True,progress=text_only['_progress_updates'],char_budget=12)
    assert next_read['blocks'][0]['char_start']==0 and next_read['blocks'][0]['block_id']=='p1-b0'
    assert [i['page']for i in next_read['images']]==[3]
    assert next_read['coverage'][0]['visual_read_complete']
    restarted=read(d,mode='sequential',include_images=True,restart=True,progress=next_read['_progress_updates'],char_budget=12)
    assert [i['page']for i in restarted['images']]==[1,2]


def test_private_and_supplement_boundaries_stay_independent_of_page_views():
    d=dual_document();secret='SYNTHETIC private auxiliary note'
    d['manifest']['supplements']=[{'id':'s1','kind':'comment','source_part':'word/comments.xml','page_hint':1,
        'text':secret,'quality':'extracted','visibility':'teacher'}]
    assert secret not in json.dumps(read(d,mode='sequential'))
    with pytest.raises(ValueError):read(d,supplement_ids=['s1'])
    staff=execute_plan([d],{'requests':[{'material_id':'m1','mode':'sequential'}]},include_staff_supplements=True)
    assert staff['blocks'][-1]['supplement_id']=='s1'and staff['blocks'][-1]['visibility']=='teacher'
    assert 'text_view_role'not in staff['blocks'][-1]
    student=read(d,mode='sequential',progress=staff['_progress_updates'],char_budget=12)
    assert student['blocks'][0]['char_start']==0
    d['visibility']='teacher'
    with pytest.raises(ValueError):read(d,pages=[1])
    r=execute_plan([d],{'requests':[{'material_id':'m1','pages':[1]}]},private=True)
    with pytest.raises(ValueError):validate_citations([{'ref':'D1','quote':r['blocks'][0]['text']}],r)


class DualSequentialProtocol(SourceProtocol):
    """Explicit provider fixture, not a real model or teaching-quality check."""
    def __call__(self,request):
        body=json.loads(request.content)
        if body['messages'][0]['content'].startswith('Plan bounded reads'):
            self.requests.append(body)
            mid=json.loads(body['messages'][1]['content'])['directory'][0]['material_id']
            value={'requests':[{'material_id':mid,'mode':'sequential'}]}
            return httpx.Response(200,json={'choices':[{'message':{'role':'assistant','content':json.dumps(value)}}]})
        return super().__call__(request)


@pytest.fixture
def dual_sourceenv(docenv,monkeypatch):
    import backend.aicademiya.guided_reading as reading
    app,teacher,student,processor=docenv
    def append_body(value):
        for p in value['pages']:
            p['blocks'].append({'id':f"p{p['number']}-b1",'type':'text','quality':'extracted',
                'bbox':[0,0,1,1],'text':'# SYNTHETIC complete-page Markdown\n'+('Shared alternative wording. '*8),
                'text_format':'markdown','issues':list(MARKERS),'assets':[],'parent_id':None})
    processor.mutate=append_body
    mid,rid,_=complete(teacher,count=1)
    detail=expect(teacher.get('/api/sessions/s4'));questions=detail['questions']
    for q in questions:q.update(source_material_ids=[mid],source_links=[])
    expect(teacher.patch('/api/sessions/s4',json={'questions':questions,
        'teaching_profile':{**detail['teaching_profile'],'phases':['worksheet','wrap_up']}}))
    vid=publish(teacher)['id'];provider=DualSequentialProtocol();app.state.tutor.transport=httpx.MockTransport(provider)
    monkeypatch.setenv('AICADEMIYA_AI_PROVIDER','aicademiya-router')
    with app.state.database.connect()as conn:
        for key,value in [('ai_mode','openai'),('ai_base_url','http://127.0.0.1:18280/v1'),('ai_model','AIcademiya-64kx3-Qwen3.8-27B')]:
            conn.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(key,value))
    original=reading.execute_plan
    def small_window(*args,**kwargs):kwargs['char_budget']=30;return original(*args,**kwargs)
    monkeypatch.setattr(reading,'execute_plan',small_window)
    return app,teacher,student,provider,mid,rid,vid


def start_run(client,vid):
    return expect(client.post('/api/sessions/s4/tutor/start',params={'version_id':vid},json={'request_id':'dual-start'}))


def post_dual(client,vid,rid, *, guided=True):
    payload={'request_id':rid,'message':'Continue reading the source.'}
    if not guided:payload.update(question_id='q1',intent='ask',web_search=False)
    return client.post('/api/sessions/s4/tutor/turn'if guided else'/api/sessions/s4/chat',params={'version_id':vid},json=payload)


@pytest.mark.parametrize('guided',[True,False],ids=['guided','legacy'])
def test_http_dual_view_cursor_persists_retry_and_failed_turn_does_not_consume(dual_sourceenv,guided):
    app,_,student,provider,mid,rid,vid=dual_sourceenv;start_run(student,vid)
    first=expect(post_dual(student,vid,'dual-first',guided=guided));coverage=first['messages'][-1]['metadata']['document_read_coverage'][0]
    assert coverage['read_characters']==30 and coverage['alternative_text_blocks']==1
    assert coverage['text_view_policy']==TEXT_VIEW_POLICY
    assert first['messages'][-1]['citations'][0]['block_id']=='p1-b1'
    calls=len(provider.requests);repeat=expect(post_dual(student,vid,'dual-first',guided=guided))
    assert len(provider.requests)==calls and repeat['messages'][-1]['metadata']['document_read_coverage'][0]==coverage
    provider.bad_quote=True
    assert post_dual(student,vid,'dual-failed',guided=guided).status_code==502
    provider.bad_quote=False
    second=expect(post_dual(student,vid,'dual-second',guided=guided))
    assert second['messages'][-1]['metadata']['document_read_coverage'][0]['read_characters']==60
    with app.state.database.connect()as conn:
        state=json.loads(conn.execute('SELECT state_json FROM tutor_runs WHERE session_id=? AND user_id=? AND version_id=?',
            ('s4','demo-student-1',vid)).fetchone()[0])
    assert state['document_read_progress'][mid]['read_characters']==60
    assert state['document_read_progress'][mid]['text_view_id']==coverage['text_view_id']
    assert state['document_read_progress'][mid]['revision_id']==rid


def test_http_approved_draft_changes_new_edition_view_not_old_edition_or_other_user(dual_sourceenv):
    app,teacher,student,provider,mid,rid,old=dual_sourceenv;start_run(student,old)
    first=expect(post_dual(student,old,'old-first'))
    old_view=first['messages'][-1]['metadata']['document_read_coverage'][0]['text_view_id']
    outcome=expect(teacher.post(endpoint(mid)+'/reviews',json={'request_id':'dual-approve-original','expected_revision':rid,
        'changes':[{'block_id':'p1-b0','quality':'approved','reason':'SYNTHETIC staff-reviewed original'}]}))
    newrid=outcome['document']['revision_id'];assert newrid!=rid
    # Draft approval does not replace the currently published source/view.
    older=expect(post_dual(student,old,'old-second'));oldcoverage=older['messages'][-1]['metadata']['document_read_coverage'][0]
    assert oldcoverage['read_characters']==60 and oldcoverage['text_view_id']==old_view and oldcoverage['revision_id']==rid
    assert older['messages'][-1]['citations'][0]['block_id']=='p1-b1'
    with app.state.database.connect()as conn:token=issue_session(conn,'demo-student-2')
    second=TestClient(app)
    try:
        second.cookies.set('aicademiya_session',token);start_run(second,old)
        other=expect(post_dual(second,old,'other-first'))
        assert other['messages'][-1]['metadata']['document_read_coverage'][0]['read_characters']==30
    finally:second.close()
    new=publish(teacher)['id'];start_run(student,new)
    recent=expect(post_dual(student,new,'new-first'));coverage=recent['messages'][-1]['metadata']['document_read_coverage'][0]
    assert coverage['revision_id']==newrid and coverage['read_characters']==30
    assert coverage['text_view_id']!=old_view
    assert recent['messages'][-1]['citations'][0]['block_id']=='p1-b0'
    # Historical editions remain read-only; their saved cursor is retained.
    expect(post_dual(student,old,'historical-must-not-advance'),409)
    expect(student.get('/api/sessions/s4/workspace',params={'version_id':old}))
    with app.state.database.connect()as conn:
        rows=conn.execute('SELECT user_id,version_id,state_json FROM tutor_runs WHERE session_id=?',('s4',)).fetchall()
    states={(row[0],row[1]):json.loads(row[2])['document_read_progress'][mid]for row in rows}
    assert states[('demo-student-1',old)]['read_characters']==60
    assert states[('demo-student-1',new)]['read_characters']==30
    assert states[('demo-student-2',old)]['read_characters']==30
