"""Constrained selector schema for observed material-only lookup failures.
Provider fixtures verify protocol/authority, not real model quality.
"""
import json
import pytest
from backend.aicademiya.ai import ModelFailure
from backend.aicademiya.guided_reading import prepare_reads
from backend.aicademiya.reading_context import ReadPlan,read_plan_schema
from .test_stage12_reading_context import document


def test_generation_requires_selector_fields_in_logical_order():
    schema=read_plan_schema(['m1']);selection=schema['$defs']['ReadSelection']
    expected=['material_id','mode','restart','include_images','pages','block_ids','supplement_ids','query']
    assert list(selection['properties'])==expected and selection['required']==expected
    assert selection['properties']['material_id']['enum']==['m1']
    assert schema['required']==['requests']


def test_generation_schema_does_not_change_legacy_server_defaults():
    read_plan_schema(['m1'])
    parsed=ReadPlan.model_validate({'requests':[{'material_id':'m1','pages':[1]}]})
    assert parsed.requests[0].mode=='lookup' and not parsed.requests[0].restart
    assert 'enum'not in ReadPlan.model_json_schema()['$defs']['ReadSelection']['properties']['material_id']

class Planner:
    def __init__(self,reply):self.reply=reply;self.calls=[]
    def uses_aicademiya_router(self,settings):return True
    def kv_scope(self,*args):return 'synthetic-scope'
    def complete(self,settings,messages,**kwargs):
        self.calls.append((messages,kwargs));return json.dumps(self.reply)

def run(reply):
    tutor=Planner(reply);d=document();d['manifest']['pages']=d['manifest']['pages'][:1]
    def action():return prepare_reads(tutor,{}, {'user':{'id':'qa','role':'student'}},{'id':'session','learning_objectives':[]},
        {'phase':'worksheet'},{'message':'Quote a passage from the last source page.'},None,[{'_document':d}],[])
    return tutor,action


def test_actual_planner_options_use_complete_selector_schema():
    tutor,action=run({'requests':[{'material_id':'m1','mode':'lookup','pages':[1]}]})
    assert action()['blocks'] and len(tutor.calls)==1
    schema=tutor.calls[0][1]['response_format']['json_schema']['schema']
    assert set(schema['$defs']['ReadSelection']['required'])==set(schema['$defs']['ReadSelection']['properties'])

@pytest.mark.parametrize('selection',[{'material_id':'not-authorized','mode':'lookup','pages':[1]},{'material_id':'m1','mode':'lookup'}])
def test_invalid_provider_output_is_not_invented_or_blindly_retried(selection):
    tutor,action=run({'requests':[selection]})
    with pytest.raises(ModelFailure):action()
    assert len(tutor.calls)==1
