"""Synthetic bounded provider repair tests; no actual-model calls."""
import json
import pytest
from backend.aicademiya.ai import ModelFailure
from backend.aicademiya.guided_director import SourceDecision, pure_help
from backend.aicademiya.guided_reading import checked_source_feedback
from backend.aicademiya.reading_context import validate_citations, QuotationMismatch


class RepairTutor:
    def __init__(self, response):self.response=response;self.calls=[]
    def uses_aicademiya_router(self, settings):return True
    def kv_scope(self, user, activity, phase):return 'synthetic-server-owned-scope'
    def complete(self, settings, messages, **options):
        self.calls.append((messages,options))
        if isinstance(self.response,Exception):raise self.response
        return self.response if isinstance(self.response,str)else json.dumps(self.response)


def fixture():
    blocks=[{'ref':ref,'material_id':'synthetic-material','revision_id':'frozen-revision','source_label':'Synthetic source','page':8,'printed_label':'116 / 117','block_id':bid,'visibility':visibility,'text':text}
            for ref,bid,visibility,text in [('D9','p8-b7','student','4- Highly fluent and involved.'),('D12','p8-b13','student','2 Talk is quite slow and vocabulary is limited.'),('D13','p8-b14','student','2- Overall, the pace of talk is slow. Vocabulary knowledge is limited.'),('D14','p8-b15','student','1+ Poor speaker'),('D15','p8-b16','teacher','PRIVATE SOURCE SENTINEL')]]
    evidence={'blocks':blocks,'notices':[],'included_characters':sum(len(b['text'])for b in blocks)}
    original=SourceDecision(schema_version=1,text='The source says “quite slow.”',intent='ask',question_id='q1',outcome='unknown',document_citations=[{'ref':'D13','quote':'Talk is quite slow and vocabulary is limited.'},{'ref':'D14','quote':'Overall, the pace of talk is slow.'}])
    return original,evidence


def run(tutor,original,evidence,**options):
    return checked_source_feedback(tutor,{}, {'user':{'id':'synthetic','role':'student'}},{'id':'s','_version_id':'edition-old'},{'phase':'worksheet'},{'message':'Compare the source bands.'},original,evidence,**options)


def valid_reply():return {'text':'The lower band describes slow talk and limited vocabulary.','document_citations':[{'ref':'D13','quote':'Overall, the pace of talk is slow.'}]}


def test_real_failure_shape_two_wrong_refs_needs_provider_revision_not_local_rebinding():
    original,evidence=fixture();before=original.model_dump();tutor=RepairTutor(valid_reply())
    assert original.document_citations[0].quote in evidence['blocks'][1]['text']
    assert original.document_citations[1].quote in evidence['blocks'][2]['text']
    with pytest.raises(QuotationMismatch):validate_citations([q.model_dump()for q in original.document_citations],evidence)
    result,cites=run(tutor,original,evidence)
    assert original.model_dump()==before
    assert (result.intent,result.question_id,result.outcome)==('ask','q1','unknown')
    assert result.text==valid_reply()['text']and cites[0]['quote']==valid_reply()['document_citations'][0]['quote']
    assert cites[0]['block_id']=='p8-b14'and cites[0]['revision_id']=='frozen-revision'and cites[0]['version_id']=='edition-old'
    assert len(tutor.calls)==1
    messages,options=tutor.calls[0];envelope=json.loads(messages[1]['content'])
    assert envelope['previous_feedback']==before
    assert [e['ref']for e in envelope['validation_errors']]==['D13','D14']
    assert envelope['validation_errors'][1]['supplied_text_at_ref']=='1+ Poor speaker'
    assert all(b['visibility']=='student'for b in envelope['document_reads']['blocks'])
    assert 'PRIVATE SOURCE SENTINEL'not in json.dumps(messages)
    assert options['response_format']['json_schema']['name']=='aicademiya_document_quote_revision'
    assert options['kv_scope']=='synthetic-server-owned-scope'and options['max_tokens']==1800


@pytest.mark.parametrize('bad',[
    {'text':'Still invalid','document_citations':[{'ref':'D14','quote':'Overall, the pace of talk is slow.'}]},
    {'text':'Still a paraphrase','document_citations':[{'ref':'D13','quote':'Talk is quite slow.'}]},
    {'text':'Ungrounded replacement','document_citations':[]},
    {'text':'Wrong identity','document_citations':[{'ref':'D99','quote':'Overall, the pace of talk is slow.'}]},
    {'text':'Private source','document_citations':[{'ref':'D15','quote':'PRIVATE SOURCE SENTINEL'}]},
    {'text':'Invent progress','document_citations':[{'ref':'D13','quote':'Overall, the pace of talk is slow.'}],'intent':'answer','outcome':'sufficient'},
    'not JSON',
    ModelFailure('Actual provider 503: no fabricated result'),
])
def test_second_failure_remains_visible_without_a_third_call(bad):
    original,evidence=fixture();tutor=RepairTutor(bad)
    with pytest.raises(ModelFailure):run(tutor,original,evidence)
    assert len(tutor.calls)==1


@pytest.mark.parametrize('gate',['unknown_ref','private','withheld','later_private','later_unknown'])
def test_identity_privacy_reference_failures_are_not_repair_permission(gate):
    original,evidence=fixture();kwargs={}
    if gate=='unknown_ref':original.document_citations[0].ref='D99'
    elif gate=='private':original.document_citations[0].ref='D15'
    elif gate=='withheld':
        original.document_citations[0].quote='WITHHELD REFERENCE SENTINEL'
        kwargs['withheld_reference']={'reference':'WITHHELD REFERENCE SENTINEL'}
    elif gate=='later_private':original.document_citations[1].ref='D15'
    else:original.document_citations[1].ref='D99'
    tutor=RepairTutor(valid_reply())
    with pytest.raises(ModelFailure):run(tutor,original,evidence,**kwargs)
    assert not tutor.calls


@pytest.mark.parametrize('where',['text','quote'])
def test_repaired_feedback_cannot_leak_withheld_reference(where):
    original,evidence=fixture();reply=valid_reply();reference='Vocabulary knowledge is limited.'
    reply['text']='Feedback'
    if where=='text':reply['text']=reference
    else:reply['document_citations']=[{'ref':'D13','quote':reference}]
    tutor=RepairTutor(reply)
    with pytest.raises(ModelFailure):run(tutor,original,evidence,withheld_reference={'reference':reference})
    assert len(tutor.calls)==1


def test_valid_feedback_passes_without_revision():
    original,evidence=fixture();original.document_citations=[];tutor=RepairTutor(valid_reply())
    result,cites=run(tutor,original,evidence)
    assert result is original and cites==[]and not tutor.calls


@pytest.mark.parametrize('message',[
    'My answer is that the chapter is useful because it gives evidence. List the source steps too.',
    'According to the chapter, I think the purpose is validation. What else matters?',
    'List validity and reliability because both support my answer.',
    'The source shows slow speech; therefore I would compare the bands.',
])
def test_mixed_assertions_are_not_silently_downgraded(message):assert not pure_help(message)
