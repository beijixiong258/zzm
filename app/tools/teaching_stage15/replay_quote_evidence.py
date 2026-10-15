"""CPU validation replay of retained REAL model output; no provider call."""
from pathlib import Path
import copy,json,sys
APP=Path(__file__).resolve().parents[2];sys.path.insert(0,str(APP))
from backend.aicademiya.reading_context import citation_quote_match,validate_citations,normalized_quote

def main():
 root=APP/'artifacts/stage15/fresh-app-r1';rows=json.loads((root/'failed-model-exchanges-r1.json').read_text());proof=[]
 for index in (2,3):
  row=rows[index];response=json.loads(row['response']['choices'][0]['message']['content']);evidence=None
  for message in row['request']['messages']:
   if not isinstance(message['content'],str):continue
   try:value=json.loads(message['content'])
   except ValueError:continue
   if isinstance(value,dict)and 'document_reads'in value:evidence=value['document_reads']
  assert evidence is not None;before=copy.deepcopy(evidence);quotes=response['document_citations'];refs={b['ref']:b for b in evidence['blocks']}
  assert all(normalized_quote(q['quote'])not in normalized_quote(refs[q['ref']]['text'])for q in quotes)
  checked=validate_citations(quotes,evidence);assert len(checked)==3 and all(q['quote_basis']=='rendered_html_cell_line_breaks'for q in checked);assert evidence==before
  proof.append({'actual_call_index':index,'raw_inference_unchanged':True,'source_evidence_unchanged':True,'old_raw_only_rejected':True,'format_aware_source_spans':checked})
 result={'status':'passed','scope':'CPU replay of retained actual requests/responses, not new model/GPU calls','calls':proof};(root/'quote-format-replay.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'status':'passed','actual_response_replays':len(proof),'validated_quotes':sum(len(p['format_aware_source_spans'])for p in proof)}))
if __name__=='__main__':main()
