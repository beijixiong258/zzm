"""Source-image selection and actual app transport via LABELED protocol fixtures.
No real model call: these tests verify bytes, authority and citations, not vision quality.
"""
import base64
import copy
import hashlib
import io
import json
import httpx
import pytest
from PIL import Image
from backend.aicademiya.reading_context import catalogue,execute_plan,validate_citations
from backend.aicademiya.visual_context import bind_image_inputs,attach_image_message,validate_image_citations
from backend.aicademiya.document_bundle import validate_manifest
from .test_stage12_reading_context import document
from .test_stage12_guided_reading import sourceenv,start,SourceProtocol
from .test_stage12_document_api import docenv,endpoint
from .conftest import expect,publish


def visual_document(tmp_path, *, mid='m1',visibility='student',count=3,empty=True):
    d=document(mid,visibility=visibility);d['manifest']['pages']=d['manifest']['pages'][:count]
    (tmp_path/'pages').mkdir(exist_ok=True)
    for p in d['manifest']['pages']:
        p.update(image=f"pages/p{p['number']}.png",status='needs_review',width=40,height=60)
        Image.new('RGB',(40,60),(p['number'],90,130)).save(tmp_path/p['image'])
        if empty:
            p['blocks']=[{'id':f"p{p['number']}-b0",'type':'image','quality':'needs_review','text':'',
                          'visual_description':'Synthetic diagram arrows','bbox':[0,0,1,1]}]
    return d,{'id':mid,'_document':d,'_document_asset_root':tmp_path}


def plan(**values):return {'requests':[{'material_id':'m1','include_images':True,**values}]}


def test_uncertain_text_does_not_remove_original_visual_evidence(tmp_path):
    d,m=visual_document(tmp_path);r=execute_plan([d],plan(pages=[1]))
    assert r['blocks']==[]and len(r['images'])==1
    inputs=bind_image_inputs(r,[m]);messages=attach_image_message([{'role':'user','content':'Read the diagram.'}],r,inputs)
    parts=messages[-1]['content'];image=base64.b64decode(parts[1]['image_url']['url'].split(',',1)[1],validate=True)
    assert image==(tmp_path/'pages/p1.png').read_bytes()
    refs=validate_image_citations(['V1'],r);assert refs[0]['page']==1 and refs[0]['quote']==''
    assert refs[0]['source_image_sha256']==hashlib.sha256(image).hexdigest()
    assert str(tmp_path)not in json.dumps(messages)and 'data:'not in json.dumps(r)
    with pytest.raises(ValueError):validate_citations([{'ref':'V1','quote':'Synthetic diagram arrows'}],r)


def test_visual_description_is_searchable_but_not_authoritative_text(tmp_path):
    d,m=visual_document(tmp_path);c=catalogue([d]);assert c[0]['visual_regions'][0]['description']=='Synthetic diagram arrows'
    r=execute_plan([d],plan(query='diagram arrows'));assert r['blocks']==[]and len(r['images'])==2
    assert 'Synthetic diagram arrows'not in json.dumps(r['blocks'])


@pytest.mark.parametrize('kind,private',[('reading',False),('answer_key',True),('worksheet',True)])
def test_image_access_obeys_existing_material_scope(tmp_path,kind,private):
    d,m=visual_document(tmp_path,visibility='teacher');d['kind']=kind
    with pytest.raises(ValueError):execute_plan([d],plan(pages=[1]),private=private)


def test_private_visual_citation_cannot_be_disclosed(tmp_path):
    d,m=visual_document(tmp_path,visibility='teacher');r=execute_plan([d],plan(pages=[1]),private=True)
    inputs=bind_image_inputs(r,[m]);attach_image_message([],r,inputs)
    with pytest.raises(ValueError):validate_image_citations(['V1'],r)
    assert validate_image_citations(['V1'],r,allow_private=True)


def test_visual_reference_requires_actual_binding_and_attachment(tmp_path):
    d,m=visual_document(tmp_path);r=execute_plan([d],plan(pages=[1]))
    with pytest.raises(ValueError):validate_image_citations(['V1'],r)
    inputs=bind_image_inputs(r,[m])
    with pytest.raises(ValueError):validate_image_citations(['V1'],r)
    attach_image_message([],r,inputs)
    with pytest.raises(ValueError):validate_image_citations(['V99'],r)
    m['_document']['revision_id']='changed'
    with pytest.raises(ValueError):bind_image_inputs(r,[m])


def test_sequential_visual_cursor_continues_without_fake_whole_document_read(tmp_path):
    d,m=visual_document(tmp_path);prior={};first=execute_plan([d],plan(mode='sequential'),progress=prior)
    assert prior=={} and [i['page']for i in first['images']]==[1,2]
    assert first['coverage'][0]['visual_read_complete']is False
    second=execute_plan([d],plan(mode='sequential'),progress=first['_progress_updates'])
    assert [i['page']for i in second['images']]==[3]
    assert second['coverage'][0]['visual_read_complete']is True
    assert second['coverage'][0]['visual_read_pages']==3
    # Text uncertainty is not changed into semantic approval.
    assert second['coverage'][0]['unresolved_blocks']==3


def test_original_images_have_separate_request_byte_budget(tmp_path,monkeypatch):
    import backend.aicademiya.visual_context as v
    d,m=visual_document(tmp_path);r=execute_plan([d],plan(pages=[1]));monkeypatch.setattr(v,'MAX_IMAGE_INPUT_BYTES',1)
    with pytest.raises(ValueError,match='budget'):bind_image_inputs(r,[m])


class ImageProtocol(SourceProtocol):
    def __init__(self):super().__init__();self.fail_images=False;self.image_requests=[]
    def __call__(self,request):
        body=json.loads(request.content);system=body['messages'][0]['content']
        if system.startswith('Plan bounded reads'):
            self.requests.append(body);d=json.loads(body['messages'][1]['content'])['directory'][0]
            response={'requests':[{'material_id':d['material_id'],'pages':[d['pdf_pages']],'include_images':True}]}
            return httpx.Response(200,json={'choices':[{'message':{'role':'assistant','content':json.dumps(response)}}]})
        image_parts=[p for m in body['messages']if isinstance(m.get('content'),list)for p in m['content']if p['type']=='image_url']
        if image_parts:
            self.image_requests.append(body);assert body['cache_prompt']is False
            blob=base64.b64decode(image_parts[0]['image_url']['url'].split(',',1)[1],validate=True)
            with Image.open(io.BytesIO(blob))as im:assert im.size==(32,48)
            if self.fail_images:return httpx.Response(503,json={'error':'SYNTHETIC visual transport failure'})
        response=super().__call__(request);data=response.json();value=json.loads(data['choices'][0]['message']['content'])
        if image_parts:value['visual_citations']=['V1']
        data['choices'][0]['message']['content']=json.dumps(value)
        return httpx.Response(200,json=data)


def install_protocol(env):
    provider=ImageProtocol();env[0].state.tutor.transport=httpx.MockTransport(provider);return provider


@pytest.mark.parametrize('guided',[True,False])
def test_actual_app_delivers_image_bytes_and_saves_only_citation_metadata(sourceenv,guided):
    provider=install_protocol(sourceenv);start(sourceenv)
    endpoint='/api/sessions/s4/tutor/turn'if guided else'/api/sessions/s4/chat'
    payload={'request_id':'image-turn','message':'Explain the original page diagram.'}
    if not guided:payload.update(question_id='q1',intent='ask',web_search=False)
    result=expect(sourceenv[2].post(endpoint,params={'version_id':sourceenv[-1]},json=payload))
    visual=next(c for c in result['messages'][-1]['citations']if c.get('evidence_kind')=='source_image')
    assert visual['material_id']==sourceenv[5]and visual['revision_id']==sourceenv[6]and visual['page']==3
    assert visual['quote']==''and visual['url'].endswith('#page=3')
    assert sourceenv[2].get(visual['url'].split('#')[0]).status_code==200
    assert len(provider.image_requests)==1
    assert 'data:image/'not in json.dumps(result)and '_document_asset_root'not in json.dumps(result)
    assert 'document_dir'not in json.dumps(provider.requests)and 'uploads'not in json.dumps(provider.requests)
    n=len(provider.requests);expect(sourceenv[2].post(endpoint,params={'version_id':sourceenv[-1]},json=payload));assert len(provider.requests)==n


def test_requested_original_image_survives_withheld_derived_text(sourceenv):
    provider=install_protocol(sourceenv);_,teacher,student,_,_,mid,rid,_=sourceenv
    expect(teacher.post(endpoint(mid)+'/reviews',json={'request_id':'synthetic-exclude-text','expected_revision':rid,
        'changes':[{'block_id':'p3-b0','quality':'excluded','reason':'SYNTHETIC wrong text transcription; original page remains the source'}]}))
    vid=publish(teacher)['id'];env=(*sourceenv[:-1],vid);start(env)
    result=expect(student.post('/api/sessions/s4/tutor/turn',params={'version_id':vid},json={'request_id':'original-image','message':'Look at the original page.'}))
    assert [c['evidence_kind']for c in result['messages'][-1]['citations']]==['source_image']
    evidence=json.loads(provider.image_requests[0]['messages'][1]['content'])['document_reads'];assert evidence['blocks']==[]


def test_failed_image_transport_preserves_raw_message_and_does_not_complete_turn(sourceenv):
    provider=install_protocol(sourceenv);start(sourceenv);provider.fail_images=True
    response=sourceenv[2].post('/api/sessions/s4/tutor/turn',params={'version_id':sourceenv[-1]},json={'request_id':'image-failure','message':'Read this source image.'})
    assert response.status_code==502 and '503'in response.json()['detail']
    work=expect(sourceenv[2].get('/api/sessions/s4/workspace',params={'version_id':sourceenv[-1]}))
    assert work['messages'][-1]['role']=='user'and work['attempts']=={}
    assert work['tutor']['pending_request_id']is None


def test_quote_revision_keeps_the_same_actual_source_images(sourceenv):
    provider=install_protocol(sourceenv);start(sourceenv);provider.bad_quote=True;provider.repair_success=True
    result=expect(sourceenv[2].post('/api/sessions/s4/tutor/turn',params={'version_id':sourceenv[-1]},
        json={'request_id':'image-and-quote-repair','message':'Explain the source and cite it.'}))
    assert len(provider.image_requests)==2
    def images(body):return [p['image_url']['url']for m in body['messages']if isinstance(m.get('content'),list)for p in m['content']if p['type']=='image_url']
    assert images(provider.image_requests[0])==images(provider.image_requests[1])
    assert any(c.get('evidence_kind')=='source_image'for c in result['messages'][-1]['citations'])


def test_completed_image_only_read_does_not_fail_as_missing_text(tmp_path):
    from backend.aicademiya.guided_reading import prepare_reads
    from .test_stage14_planner_repair import Planner
    d,m=visual_document(tmp_path,count=1)
    first=execute_plan([d],plan(mode='sequential'))
    tutor=Planner(plan(mode='sequential'))
    r=prepare_reads(tutor,{}, {'user':{'role':'student'}},{'id':'s','learning_objectives':[]},
        {'phase':'worksheet','document_read_progress':first['_progress_updates']},{'message':'Continue reading.'},None,[m],[])
    assert r['images']==[]and r['blocks']==[]and r['coverage'][0]['visual_read_complete']
