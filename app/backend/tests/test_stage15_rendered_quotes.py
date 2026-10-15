"""Observed Stage15 HTML cell <br> quotation failure; CPU evidence checks only."""
import copy
import pytest
from backend.aicademiya.reading_context import validate_citations,QuotationMismatch

def block(text,fmt='markdown',visibility='student'):
 return {'ref':'D1','material_id':'m','revision_id':'r','source_label':'Source','page':1,'printed_label':None,'block_id':'p1-b0','visibility':visibility,'text':text,'text_format':fmt,'char_start':23}
def cite(b,q):return validate_citations([{'ref':'D1','quote':q}],{'blocks':[b]})

@pytest.mark.parametrize('break_tag',['<br>','<br/>','<br />','<BR>'])
def test_cell_display_line_breaks_map_to_exact_raw_span(break_tag):
 raw='paragraph-level “select'+break_tag+'the coherent sentence”'+break_tag+'exercise (29 items)'
 b=block('<table><tr><td>'+raw+'</td></tr></table>');before=copy.deepcopy(b);q='paragraph-level “select the coherent sentence” exercise (29 items)'
 row=cite(b,q)[0];assert row['quote']==q and row['quote_basis']=='rendered_html_cell_line_breaks'
 assert b==before
 assert b['text'][row['quote_char_start']-23:row['quote_char_end']-23]==raw

@pytest.mark.parametrize('q',['Exercise 29 items','exercise 28 items','exercise 29 tasks','exercise 29 items.'])
def test_case_numbers_words_punctuation_are_not_normalized(q):
 with pytest.raises(QuotationMismatch):cite(block('<table><tr><td>exercise<br>29 items</td></tr></table>'),q)

def test_other_markup_cells_code_and_plain_text_remain_literal():
 for raw,fmt in [('<table><tr><td>exercise</td><td>29 items</td></tr></table>','markdown'),
                 ('<table><tr><td>exercise<strong>29</strong> items<br>remain</td></tr></table>','markdown'),
                 ('```html\n<table><tr><td>exercise<br>29 items</td></tr></table>\n```','markdown'),
                 ('<table><tr><td>exercise<br>29 items</td></tr></table>','plain')]:
  with pytest.raises(QuotationMismatch):cite(block(raw,fmt),'exercise 29 items')

def test_unknown_or_private_ref_cannot_use_rendered_matching():
 b=block('<table><tr><td>exercise<br>29 items</td></tr></table>',visibility='teacher')
 with pytest.raises(ValueError,match='Private'):cite(b,'exercise 29 items')
 with pytest.raises(ValueError,match='supplied'):
  validate_citations([{'ref':'D2','quote':'exercise 29 items'}],{'blocks':[b]})

def test_ordinary_literal_citation_metadata_unchanged():
 row=cite(block('Actual source sentence.','plain'),'source sentence.')[0]
 assert 'quote_basis'not in row and row['quote']=='source sentence.'
