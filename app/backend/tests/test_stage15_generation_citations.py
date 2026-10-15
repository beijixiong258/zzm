"""Regression for observed real quiz-key leakage during quote repair.
Synthetic repair protocol only; no model/network.
"""
import json
from backend.aicademiya.guided_director import SourceQuizGeneration
from backend.aicademiya.guided_reading import checked_source_feedback


def test_generated_items_never_enter_citation_repair_or_replace_public_intro():
    result=SourceQuizGeneration(schema_version=1,text='Practice is ready.',items=[
        {'prompt':f'Synthetic question {i}?','options':['PRIVATE_KEY_MARKER','Other','Third'],'correct_index':0,
         'explanation':'PRIVATE_EXPLANATION_MARKER'}for i in range(5)],
        document_citations=[{'ref':'D1','quote':'wrong quote'}])
    evidence={'blocks':[{'ref':'D1','material_id':'m','revision_id':'r','source_label':'Source','page':1,
                         'printed_label':None,'block_id':'p1-b0','visibility':'student','text':'Source fact.'}]}
    class Repair:
        def uses_aicademiya_router(self,settings):return True
        def kv_scope(self,*args):return 'synthetic-scope'
        def complete(self,settings,messages,**kwargs):
            payload=json.loads(messages[1]['content'])
            assert 'items'not in payload['previous_feedback']
            assert 'PRIVATE_KEY_MARKER'not in json.dumps(messages)
            assert 'PRIVATE_EXPLANATION_MARKER'not in json.dumps(messages)
            schema=kwargs['response_format']['json_schema']['schema']
            assert set(schema['properties'])=={'document_citations','visual_citations'}
            return json.dumps({'document_citations':[{'ref':'D1','quote':'Source fact.'}],'visual_citations':[]})
    fixed,refs=checked_source_feedback(Repair(),{}, {'user':{'role':'student'}},{'id':'s'},
        {'phase':'quiz'},{'message':'Create questions.'},result,evidence)
    assert fixed.text==result.text and fixed.items==result.items
    assert refs[0]['quote']=='Source fact.'
