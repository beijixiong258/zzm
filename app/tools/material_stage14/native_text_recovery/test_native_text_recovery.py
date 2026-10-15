"""Real source regressions; CPU/native only, no model or server lifecycle."""
import json, os, sys, tempfile
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'tools/document_stage12'),str(ROOT/'tools/material_stage13')]
import parser_worker
from parser_helpers import native_text_warning, sha256, validate_bundle
SUBSET=ROOT/'artifacts/stage14/r6-final-inputs/src03-pages126-127.pdf'

def test_real_local_wingdings_does_not_quarantine_ordinary_prose():
    with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR'])as tmp:
        out=Path(tmp)/'bundle'
        assert parser_worker.main(['--input',str(SUBSET),'--output',str(out),'--engine','native','--deadline-seconds','90'])==0
        manifest=json.loads((out/'manifest.json').read_text())
        assert validate_bundle(out,manifest)['valid']
        assert manifest['source_sha256']==sha256(SUBSET)
        first=next(b for b in manifest['pages'][0]['blocks']if b['id']=='p1-b1')
        assert first['quality']=='extracted', 'Local Wingdings must not quarantine ordinary Preparation prose'
        bad=next(b for b in manifest['pages'][0]['blocks']if b['id']=='p1-b13')
        assert bad['quality']=='needs_review'
        assert '\uf0e0'in bad['text']
        assert manifest['coverage']['semantic_accuracy_approved'] is False


def make_block(text, fonts):
    spans=[];start=0
    for index,(chunk,font)in enumerate(fonts):
        assert text[start:start+len(chunk)]==chunk
        spans.append({'text':chunk,'font':font,'line_index':0,'text_range':[start,start+len(chunk)],
                      'bbox':[index/10,.1,(index+1)/10,.2],
                      'characters':[{'text':c}for c in chunk]})
        start+=len(chunk)
    return {'index':0,'type':'text','content':text,'bbox':[0,.1,.9,.2],
            'source_text_spans':spans,'issues':['source_transcription_native'],'quality':'extracted'}


def test_local_special_glyph_and_safe_span_geometry_are_preserved():
    from parser_helpers import localize_native_warnings
    text='T \uf0e0 Ss'
    block=make_block(text,[('T ','Cambria'),('\uf0e0','Wingdings'),(' Ss','Cambria')])
    good=make_block('Normal body',[('Normal body','Cambria')]);good['index']=1
    assert localize_native_warnings([block,good],'raw/source.json')
    assert good['quality']=='extracted'
    assert block['content']==text and block['quality']=='needs_review'
    assert [child['content']for child in block['children']]==['T ',' Ss']
    for child in block['children']:
        start,end=child['source_text_range']
        assert child['content']==text[start:end]
        assert '\uf0e0'not in child['content']
        assert child['bbox']==child['source_text_spans'][0]['bbox']
        assert 'table_graph_relationships_unverified'in ';'.join(child['issues'])


@pytest.mark.parametrize('control',['\x1f','\x03','\x00','\r','\t'],ids=['unit-separator','ETX','NUL','glyph-CR','glyph-tab'])
def test_actual_glyph_controls_are_suspect_even_if_python_calls_them_whitespace(control):
    from parser_helpers import localize_native_warnings
    block=make_block(control,[(control,'Broken')])
    assert localize_native_warnings([block],'raw/source.json')
    assert block['quality']=='needs_review'and block['content']==control
    assert not block.get('children')


def test_same_implicated_font_fluent_fragment_is_not_accepted():
    from parser_helpers import localize_native_warnings
    block=make_block('bad\x1fFluent text VALID',[('bad\x1f','Broken'),('Fluent text ','Broken'),('VALID','Good')])
    localize_native_warnings([block],'raw/source.json')
    assert [child['content']for child in block['children']]==['VALID']


def test_density_trigger_remains_local_and_numeric_tables_not_declared_corrupt():
    from parser_helpers import localize_native_warnings
    bad=make_block(('ab12#!'*20),[(('ab12#!'*20),'Broken')])
    good=make_block('Ordinary text',[('Ordinary text','Good')]);good['index']=1
    localize_native_warnings([bad,good],'raw/source.json')
    assert bad['quality']=='needs_review'and good['quality']=='extracted'
    assert native_text_warning('123 . 456 '*30) is None
    assert native_text_warning('native\nlayout\twhitespace\r') is None


def line(text,box=(.1,.1,.8,.2),confidence=.99):
    return {'text':text,'bbox':list(box),'polygon':[],'confidence':confidence}


def test_native_exact_comparison_requires_actual_independent_evidence_not_vlm_finish():
    from ocr_verification import compare_native_literal
    data={'status':'complete','lines':[line('Exact O0 I1l text.') ]}
    proof=compare_native_literal('Exact O0 I1l text.',data,[line('Exact O0 I1l text.')])
    assert proof['status']=='verified'and proof['generation']=={}
    assert 'not graph/table semantics'in proof['scope']
    assert 'generation_finish_unknown'not in proof['reasons']
    assert compare_native_literal('Exact O0 I1l text.',{'status':'unavailable','lines':[]},[line('Exact O0 I1l text.')])['status']=='unverified'


@pytest.mark.parametrize('text',['Exact O0 I1l text','exact O0 I1l text.','Exact 00 I1l text.','Exact O0 IIl text.','ExactO0 I1l text.'])
def test_native_disagreement_is_strict_when_spatial_evidence_is_complete(text):
    from ocr_verification import compare_native_literal
    proof=compare_native_literal(text,{'status':'complete','lines':[line('Exact O0 I1l text.')]},[line(text)])
    assert proof['status']=='unverified'and proof['native_disagreement_actionable']


def test_partial_or_lowconfidence_independent_ocr_is_not_a_whole_block_disagreement():
    from ocr_verification import compare_native_literal
    source=[line('Heading',(.1,.1,.8,.2)),line('Body',(.1,.3,.8,.4))]
    proof=compare_native_literal('Heading\nBody',{'status':'complete','lines':[source[1]]},source)
    assert proof['status']=='unverified'and not proof['native_disagreement_actionable']
    assert not compare_native_literal('Heading',{'status':'complete','lines':[line('Changed',confidence=.939)]},[source[0]])['native_disagreement_actionable']
    shifted=line('Changed',(.5,.1,.8,.2))
    assert not compare_native_literal('Heading',{'status':'complete','lines':[shifted]},[source[0]])['native_disagreement_actionable']


def test_native_agreement_does_not_clear_mapping_warning_or_rewrite_text():
    from ocr_verification import apply_native_verification
    block={'text':'Bad\uf0e0','quality':'needs_review','issues':['source_transcription_native','native_font_mapping_unusable']}
    data={'status':'complete','lines':[line(block['text'])]}
    proof=apply_native_verification(block,data,[line(block['text'])],'raw/proof.json')
    assert proof['status']=='unverified'and block['quality']=='needs_review'
    assert block['text']=='Bad\uf0e0'and 'native_font_mapping_unusable'in block['issues']
    assert not any(i.startswith('native_machine_verified')for i in block['issues'])


@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_source_fragments_follow_real_cardinal_raster_geometry(rotation):
    import pymupdf as fitz
    from parser_helpers import rotate_bbox
    with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR'])as tmp:
        root=Path(tmp);doc=fitz.open();p=doc.new_page(width=300,height=200)
        p.insert_text((20,40),'Readable text');p.set_rotation(90)
        # A real U+FFFD glyph is deliberately embedded in a different source font.
        p.insert_text((20,70),'\ufffd',fontname='china-s');doc.save(root/'source.pdf');doc.close()
        assert parser_worker.main(['--input',str(root/'source.pdf'),'--output',str(root/'bundle'),
                                  '--rotations',json.dumps({'1':rotation}),'--engine','native'])==0
        raw=json.loads((root/'bundle/raw/p0001-native.json').read_text())
        m=json.loads((root/'bundle/manifest.json').read_text())
        by_id={b['id']:b for b in m['pages'][0]['blocks']}
        for parent in raw['blocks']:
            assert by_id[f'p1-b{parent["index"]}']['bbox']==rotate_bbox(parent['bbox'],rotation)
            for child in parent.get('children',[]):
                result=by_id[f'p1-b{child["index"]}']
                assert result['text']==parent['content'][slice(*child['source_text_range'])]
                assert result['bbox']==rotate_bbox(child['bbox'],rotation)
        assert validate_bundle(root/'bundle',m)['valid']

