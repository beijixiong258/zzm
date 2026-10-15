"""Pure source-reading contract tests; no OCR, model or production calls."""
import copy
import json
import pytest
from pydantic import ValidationError
from backend.aicademiya.reading_context import ReadPlan, catalogue, eligible_documents, execute_plan, validate_citations

def document(mid="m1", *, visibility="student",kind="reading"):
    return {"material_id":mid,"revision_id":"revision-old","title":"Synthetic book","source_label":"Synthetic source","visibility":visibility,"kind":kind,"manifest":{"pages":[{"number":i,"printed_label":str(i+100),"blocks":[{"id":f"p{i}-b0","type":"heading","quality":"extracted","text":f"Section {i}"},{"id":f"p{i}-b1","type":"text","quality":"extracted","text":"Common background. "*30 if i!=269 else"Late source: water and oranges for the barbecue."}]}for i in range(1,318)]}}

def test_whole_corpus_search_reaches_late_page_not_first_excerpt():
    d=document();result=execute_plan([d],{"requests":[{"material_id":"m1","query":"barbecue oranges"}]})
    assert result["blocks"][0]["page"]==269
    assert result["blocks"][0]["revision_id"]=="revision-old"
    assert "oranges"in result["blocks"][0]["text"]

def test_explicit_page_and_block_identity_retained():
    result=execute_plan([document()],{"requests":[{"material_id":"m1","block_ids":["p317-b0"],"pages":[269]}]})
    assert [b["block_id"]for b in result["blocks"]]==["p317-b0","p269-b0","p269-b1"]
    assert result["blocks"][0]["printed_label"]=="417"

@pytest.mark.parametrize("selection",[{"material_id":"other-course"},{"material_id":"m1","pages":[318]},{"material_id":"m1","block_ids":["p1-fake"]},{"material_id":"m1","pages":[0]}])
def test_plan_cannot_invent_source_ids_or_pages(selection):
    with pytest.raises(ValueError):execute_plan([document()],{"requests":[selection]})

def test_private_rules_apply_before_catalogue_or_lookup():
    docs=[document(),document("secret",visibility="teacher"),document("key",kind="answer_key"),document("worksheet",visibility="teacher",kind="worksheet")]
    assert [x["material_id"]for x in eligible_documents(docs)]==["m1"]
    assert [x["material_id"]for x in eligible_documents(docs,private=True)]==["m1","secret"]
    assert "secret"not in json.dumps(catalogue(docs))
    with pytest.raises(ValueError):execute_plan(docs,{"requests":[{"material_id":"secret","pages":[1]}]})

def test_needs_review_and_excluded_regions_do_not_become_evidence():
    d=document();d["manifest"]["pages"][0]["blocks"][0]["quality"]="needs_review";d["manifest"]["pages"][0]["blocks"][1]["quality"]="excluded"
    r=execute_plan([d],{"requests":[{"material_id":"m1","pages":[1]}]})
    assert r["blocks"]==[]and len(r["notices"])==2
    assert all("Common background"not in str(n)for n in r["notices"])

def test_bounded_catalogue_keeps_material_identity_and_reports_omitted_outline():
    c=catalogue([document(),document("second")],char_budget=900)
    assert [x["material_id"]for x in c]==["m1","second"]
    assert len(json.dumps(c,ensure_ascii=False))<=900
    assert not all(x["outline_complete"]for x in c)
    assert all(x["full_document_search_available"]for x in c)

def test_read_budget_and_mid_block_lookup_preserve_exact_quote_evidence():
    d=document();d["manifest"]["pages"][0]["blocks"][1]["text"]="x "*35000+"MELAB late fact. "+"z "*3000
    result=execute_plan([d],{"requests":[{"material_id":"m1","query":"MELAB"}]},char_budget=1000)
    assert result["included_characters"]<=1000
    b=result["blocks"][0];assert "MELAB late fact."in b["text"]and b["char_start"]>50000 and b["block_truncated"]
    c=validate_citations([{"ref":b["ref"],"quote":"MELAB late fact."}],result)
    assert c[0]["revision_id"]=="revision-old"and c[0]["block_id"]=="p1-b1"
    with pytest.raises(ValueError):validate_citations([{"ref":b["ref"],"quote":"Common background."}],result)

def test_citations_require_supplied_block_and_literal_quote_and_private_gate():
    r=execute_plan([document()],{"requests":[{"material_id":"m1","pages":[269]}]})
    b=next(x for x in r["blocks"]if x["block_id"]=="p269-b1")
    exact={"ref":b["ref"],"quote":"water and oranges"}
    assert len(validate_citations([exact,exact],r))==1
    for wrong in [{"ref":"D99","quote":"water and oranges"},{"ref":b["ref"],"quote":"Water and apples"},{"ref":[],"quote":"water"}]:
        with pytest.raises(ValueError):validate_citations([wrong],r)
    private=copy.deepcopy(r);private["blocks"][1]["visibility"]="teacher"
    with pytest.raises(ValueError):validate_citations([exact],private)
    assert validate_citations([exact],private,allow_private=True)

def test_protocol_rejects_boolean_page_and_oversized_plan():
    with pytest.raises(ValidationError):ReadPlan.model_validate({"requests":[{"material_id":"m1","pages":[True]}]})
    with pytest.raises(ValidationError):ReadPlan.model_validate({"requests":[{"material_id":"m1"}]*5})
