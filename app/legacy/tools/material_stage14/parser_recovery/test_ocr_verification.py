"""OCR evidence/state tests. Model responses here are fixtures, not accuracy proof."""
import copy,io,json,os,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'tools/document_stage12'),str(ROOT/'tools/material_stage13')]
from ocr_verification import CPUVerifier,compare_literal,recovery_tiles,duplicate_candidates,normalized
from parser_helpers import literal_response,observe_vlm_http,composite_embedded,sha256,validate_bundle


def line(text='Exact source text',box=(.1,.1,.8,.2),confidence=.99):
    return {'text':text,'bbox':list(box),'confidence':confidence,'polygon':[]}
def scan(lines=None):return {'status':'complete','lines':lines if lines is not None else [line()]}
def generation(reason='stop'):return {'events':[{'finish_reason':reason,'finish_metadata_available':True}]}


class LiteralTests(unittest.TestCase):
    def test_genuine_evidence_gate_exact_stop_only(self):
        p=compare_literal('Exact source text',scan(),generation());self.assertEqual(p['status'],'verified')
        self.assertIn('not graph/table semantics',p['scope'])
    def test_digits_punctuation_case_and_word_boundaries_not_fuzzy_approved(self):
        for text in ('Exact Source text','Exactsource text','Exact source text.','Exact source 1ext'):
            with self.subTest(text=text):self.assertEqual(compare_literal(text,scan(),generation())['status'],'unverified')
        self.assertNotEqual(normalized('1 5'),normalized('15'));self.assertNotEqual(normalized('O'),normalized('0'))
    def test_linebreak_whitespace_only_normalization_no_text_mutation(self):
        literal='Exact\nsource  text\n';self.assertEqual(compare_literal(literal,scan(),generation())['status'],'verified');self.assertEqual(literal,'Exact\nsource  text\n')
    def test_unknown_length_empty_and_lowconfidence_not_promoted(self):
        for g in ({},generation('length'),generation(None)):
            self.assertEqual(compare_literal('Exact source text',scan(),g)['status'],'unverified')
        self.assertEqual(compare_literal('Exact source text',scan([line(confidence=.93)]),generation())['status'],'unverified')
        self.assertEqual(compare_literal('Exact source text',scan([line(confidence=float('nan'))]),generation())['status'],'unverified')
        self.assertEqual(compare_literal('',scan([]),generation())['status'],'unverified')
    def test_nonlinear_graph_does_not_claim_reading_order(self):
        data=scan([line('TEST',(.1,.1,.3,.2)),line('Students',(.5,.1,.8,.2))])
        self.assertEqual(compare_literal('TEST\nStudents',data,generation())['status'],'unverified')
        tiles=recovery_tiles(data);self.assertEqual(len(tiles),2);self.assertTrue(all('no_relationship'in tile['scope']for tile in tiles))
    def test_long_linear_images_all_detected_lines_tiled_with_bound(self):
        data=scan([line('long source line '+str(i),(.05,i/120,.8,(i+.8)/120))for i in range(100)])
        tiles=recovery_tiles(data);self.assertLessEqual(len(tiles),8);self.assertEqual(recovery_tiles(data,0),[])
        indices=[i for tile in tiles for i in tile['cpu_line_indices']]
        self.assertEqual(len(indices),len(set(indices)));self.assertLess(len(indices),len(data['lines']))
        self.assertEqual(recovery_tiles({'status':'failed','lines':data['lines']}),[])
    def test_observed_multi_sentence_no_text_response_not_indexed(self):
        text='The image contains no discernible text or characters. It is a graphic design. Therefore, no OCR output can be generated.'
        self.assertEqual(literal_response(text),('', 'explicit_refusal_not_source_text'))
        self.assertEqual(literal_response('No text should be removed from this source passage.'),('No text should be removed from this source passage.','literal_candidate'))
    def test_realistic_facing_page_columns_recover_paragraphs_not_first8labels(self):
        data=scan([item for i in range(24)for item in (line(f'Left source line {i}',(.08,.05+i*.03,.44,.07+i*.03)),
                                                     line(f'Right source line {i}',(.55,.05+i*.03,.93,.07+i*.03)))])
        tiles=recovery_tiles(data);self.assertEqual(len(tiles),4)
        indices=[i for tile in tiles for i in tile['cpu_line_indices']];self.assertEqual(sorted(indices),list(range(48)))
        self.assertTrue(all(len(tile['cpu_line_indices'])==12 for tile in tiles))
        for index,left in enumerate(tiles):
            for right in tiles[index+1:]:
                a,b=left['bbox'],right['bbox']
                overlap=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
                self.assertEqual(overlap,0)
    def test_observed_repetition_receipt_detects_failure_without_inventing_finish(self):
        p=compare_literal('Prosservs\nEVIDENCE\n'*400,scan([line('EVIDENCE')]),{})
        self.assertIn('repetitive_generation_suspect',p['reasons']);self.assertIn('generation_finish_unknown',p['reasons'])
        self.assertNotIn('generation_truncated',p['reasons'])
    def test_http_actual_finish_reason_and_token_usage_sync_async(self):
        import asyncio,httpx
        counter,restore=observe_vlm_http('http://127.0.0.1:18894')
        transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'choices':[{'finish_reason':'length','message':{'content':'partial'}}],'usage':{'completion_tokens':4096}}))
        try:
            with httpx.Client(transport=transport)as client:client.post('http://127.0.0.1:18894/v1/chat/completions',json={})
            async def request():
                async with httpx.AsyncClient(transport=transport)as client:await client.post('http://127.0.0.1:18894/v1/chat/completions',json={})
            asyncio.run(request());self.assertEqual(counter['calls'],2)
            self.assertEqual(counter['events'],[{'finish_reason':'length','finish_metadata_available':True,'completion_tokens':4096}]*2)
        finally:restore()
    def test_softmask_preserves_black_source_strokes_and_white_transparency(self):
        from PIL import Image
        im=Image.new('RGB',(40,20),'black');mask=Image.new('L',im.size,0);mask.putpixel((10,10),255)
        a,b=io.BytesIO(),io.BytesIO();im.save(a,format='PNG');mask.save(b,format='PNG')
        result=composite_embedded(a.getvalue(),b.getvalue())
        self.assertEqual(result.getpixel((10,10)),(0,0,0));self.assertEqual(result.getpixel((0,0)),(255,255,255))
        c=io.BytesIO();Image.new('L',(1,1)).save(c,format='PNG')
        with self.assertRaisesRegex(ValueError,'mask dimensions'):composite_embedded(a.getvalue(),c.getvalue())
    def test_duplicate_exclusion_preserves_original_and_separate_occurrences(self):
        def block(id,text,box,issues,q='extracted'):return {'id':id,'text':text,'bbox':box,'issues':issues,'quality':q}
        native=block('p1-b0','Exact',[0,0,.4,.2],['source_transcription_native'])
        duplicate=block('p1-b1-vlm','Exact',[0,0,.4,.2],['source_transcription_ocr; fullpage_model_candidate'],'needs_review')
        other=block('p1-b2-vlm','Exact',[.5,.5,.9,.7],['source_transcription_ocr; fullpage_model_candidate'],'needs_review')
        different=block('p1-b3-vlm','Changed',[0,0,.4,.2],['source_transcription_ocr; fullpage_model_candidate'],'needs_review')
        blocks=[native,duplicate,other,different];before=copy.deepcopy(blocks);duplicate_candidates(blocks)
        self.assertEqual(duplicate['quality'],'excluded');self.assertEqual(other['quality'],'needs_review');self.assertEqual(different['quality'],'needs_review')
        self.assertEqual([b['text']for b in blocks],[b['text']for b in before]);self.assertEqual(native,before[0])
    def test_cpu_cancellation_not_swallowed_as_dependency_failure(self):
        from PIL import Image
        verifier=CPUVerifier();verifier.initialized=True;verifier.engine=lambda im:(_ for _ in ()).throw(InterruptedError('cancelled fixture'))
        with patch.dict(sys.modules,{'numpy':types.SimpleNamespace(asarray=lambda value:value)}):
            with self.assertRaises(InterruptedError):verifier.scan(Image.new('RGB',(2,2)))
    def test_unique_contained_paragraph_duplicate_only_from_verified_whole_span(self):
        source={'id':'p1-b9-region','text':'First paragraph. Second source paragraph. Final paragraph.','bbox':[0,0,1,1],
                'quality':'extracted','issues':['source_transcription_ocr','ocr_machine_verified_literal:raw/proof.json']}
        candidate={'id':'p1-b1-vlm','text':'Second source paragraph.','bbox':[.1,.2,.9,.4],'quality':'needs_review',
                   'issues':['source_transcription_ocr; fullpage_model_candidate']}
        duplicate_candidates([source,candidate]);self.assertEqual(candidate['quality'],'excluded')
        partial=copy.deepcopy(source);partial['issues'].append('targeted_literal_recovery; not_graph_relationships')
        candidate['quality']='needs_review';candidate['issues']=['source_transcription_ocr; fullpage_model_candidate']
        duplicate_candidates([partial,candidate]);self.assertEqual(candidate['quality'],'needs_review')


class WorkerRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']);self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def run_worker(self,responses,limit=4,repeat=1,fail_recovery=False,rotated=False,transparent=False,old_cpu_confidence=None):
        import pymupdf as fitz
        from PIL import Image,ImageDraw
        import parser_worker
        im=Image.new('RGBA'if transparent else 'RGB',(400,150),(0,0,0,0)if transparent else 'white')
        ImageDraw.Draw(im).text((20,40),'Exact source text',fill=(0,0,0,255)if transparent else 'black')
        if rotated:im=im.rotate(-90,expand=True)
        im.save(self.root/'im.png')
        pdf=fitz.open()
        for _ in range(repeat):
            page=pdf.new_page(width=400,height=150);page.insert_image(page.rect,filename=str(self.root/'im.png'))
        pdf.save(self.root/'source.pdf');pdf.close();(self.root/'models').mkdir()
        counter={'calls':0,'events':[]};calls=[]
        class Verifier:
            info={'available':True,'fixture':True}
            def __init__(self,*args):pass
            def scan(self,image):
                if old_cpu_confidence is not None and image.height>=150:return scan([line('Exact source t3xt',confidence=old_cpu_confidence)])
                return scan([])if rotated and image.width<image.height else scan()
        class Client:
            prompts={'[default]':'Text Recognition:'}
            def __init__(self,**kwargs):pass
            def content_extract(self,image,type):
                calls.append(image.size)
                if fail_recovery and len(calls)>1:raise InterruptedError('Targeted recovery cancelled fixture')
                text,reason=responses[min(len(calls)-1,len(responses)-1)]
                counter['calls']+=1;counter['events'].append({'finish_reason':reason,'finish_metadata_available':True})
                return text
            async def aclose(self):pass
        utils=types.ModuleType('mineru_vl_utils');utils.MinerUClient=Client
        client=types.ModuleType('mineru_vl_utils.vlm_client');client.SamplingParams=lambda **kw:kw
        out=self.root/'bundle'
        with patch.dict(sys.modules,{'mineru_vl_utils':utils,'mineru_vl_utils.vlm_client':client}),patch.object(parser_worker,'CPUVerifier',Verifier),patch.object(parser_worker,'observe_vlm_http',return_value=(counter,lambda:None)):
            rc=parser_worker.main(['--input',str(self.root/'source.pdf'),'--output',str(out),'--engine','region-text',
                '--models',str(self.root/'models'),'--vlm-url','http://127.0.0.1:18894','--ocr-recovery-call-limit',str(limit),'--deadline-seconds','40'])
        if rc==0:
            from backend.aicademiya.document_bundle import validate_bundle as app_validate
            app_validate(out,sha256(self.root/'source.pdf'),repeat)
        return rc,out,json.loads((out/'manifest.json').read_text()),json.loads((out/'receipt.json').read_text()),calls
    def test_exact_promoted_only_with_independent_proof(self):
        rc,out,m,r,calls=self.run_worker([('Exact source text','stop')]);self.assertEqual(rc,0);self.assertEqual(len(calls),1)
        block=next(b for b in m['pages'][0]['blocks']if 'source_transcription_ocr'in b['issues'])
        self.assertEqual(block['quality'],'extracted');self.assertTrue(any(i.startswith('ocr_machine_verified_literal:')for i in block['issues']))
        self.assertFalse(m['coverage']['semantic_accuracy_approved']);self.assertTrue(validate_bundle(out,m)['valid'])
    def test_real_worker_recovery_preserves_primary_refusal_and_occurrence_reuse(self):
        rc,out,m,r,calls=self.run_worker([('No readable text found.','stop'),('Exact source text','stop')],repeat=2)
        self.assertEqual(rc,0);self.assertEqual(len(calls),2);self.assertEqual(r['targeted_recovery_calls'],1)
        for page in m['pages']:
            recovered=[b for b in page['blocks']if any(i.startswith('targeted_literal_recovery')for i in b['issues'])]
            self.assertEqual(len(recovered),1);self.assertEqual(recovered[0]['quality'],'extracted');self.assertEqual(recovered[0]['parent_id'],f'p{page["number"]}-b0')
            raw=json.loads((out/f'raw/p{page["number"]:04}-region0.json').read_text());self.assertEqual(raw['raw_text'],'No readable text found.')
            self.assertEqual(raw['recovery'][0]['raw_text'],'Exact source text')
        self.assertEqual(r['page_timings'][1]['model_calls'],0);self.assertTrue(validate_bundle(out,m)['valid'])
    def test_truncated_same_text_not_promoted_and_zero_recovery_budget(self):
        rc,out,m,r,calls=self.run_worker([('Exact source text','length')],limit=0)
        self.assertEqual(rc,0);self.assertEqual(len(calls),1)
        block=next(b for b in m['pages'][0]['blocks']if 'source_transcription_ocr'in b['issues']);self.assertEqual(block['quality'],'needs_review')
        raw=json.loads((out/'raw/p0001-region0.json').read_text());self.assertIn('generation_truncated',raw['verification']['reasons'])
    def test_targeted_cancel_preserves_primary_and_failed_trial_not_deadline(self):
        rc,out,m,r,calls=self.run_worker([('Wrong text','stop')],fail_recovery=True)
        self.assertEqual(rc,2);self.assertEqual(r['error_type'],'InterruptedError')
        raw=json.loads((out/'raw/p0001-region0.json').read_text());self.assertEqual(raw['raw_text'],'Wrong text');self.assertEqual(raw['recovery'][0]['status'],'cancelled')
        self.assertEqual(r['targeted_recovery_calls'],1)
    def test_cpu_oriented_targeted_retry_keeps_original_occurrence_and_rotation(self):
        rc,out,m,r,calls=self.run_worker([('No readable text found.','stop'),('Exact source text','stop')],rotated=True)
        self.assertEqual(rc,0);self.assertEqual(len(calls),2)
        raw=json.loads((out/'raw/p0001-region0.json').read_text());self.assertEqual(len(raw['orientation_probes']),2)
        self.assertEqual(raw['recovery'][0]['source_input_rotation'],90)
        recovered=next(b for b in m['pages'][0]['blocks']if b['id'].endswith('-recovery0'))
        self.assertEqual(recovered['quality'],'extracted');self.assertEqual(recovered['bbox'],m['pages'][0]['blocks'][0]['bbox'])
    def test_actual_pdf_softmask_bytes_retained_and_ocr_not_uniform_black(self):
        import pymupdf as fitz
        from PIL import Image
        rc,out,m,r,calls=self.run_worker([('Exact source text','stop')],transparent=True)
        self.assertEqual(rc,0);self.assertEqual(len(calls),1)
        raw=json.loads((out/'raw/p0001-region0.json').read_text());self.assertTrue(raw['source_mask_asset'])
        with fitz.open(self.root/'source.pdf')as doc:original=doc[0].get_text('dict',sort=True)['blocks'][0]
        self.assertEqual((out/raw['source_image_asset']).read_bytes(),original['image'])
        self.assertEqual((out/raw['source_mask_asset']).read_bytes(),original['mask'])
        with Image.open(out/raw['ocr_input_asset'])as image:
            self.assertEqual(image.getpixel((0,0)),(255,255,255));self.assertFalse(raw['uniform_decorative'])
    def test_low_confidence_cpu_error_can_genuinely_improve_on_independent_crop_agreement(self):
        rc,out,m,r,calls=self.run_worker([('Wrong text','stop'),('Exact source text','stop')],old_cpu_confidence=.85)
        self.assertEqual(rc,0)
        raw=json.loads((out/'raw/p0001-region0.json').read_text());trial=raw['recovery'][0]
        self.assertEqual(raw['independent_ocr']['lines'][0]['text'],'Exact source t3xt')
        self.assertEqual(trial['raw_text'],'Exact source text');self.assertEqual(trial['verification']['status'],'verified')
        self.assertTrue(trial['verification']['observations'])
        self.assertEqual(next(b['quality']for b in m['pages'][0]['blocks']if b['id'].endswith('-recovery0')),'extracted')
    def test_high_confidence_original_cpu_disagreement_remains_unverified(self):
        rc,out,m,r,calls=self.run_worker([('Wrong text','stop'),('Exact source text','stop')],old_cpu_confidence=.99)
        self.assertEqual(rc,0)
        raw=json.loads((out/'raw/p0001-region0.json').read_text());self.assertEqual(raw['recovery'][0]['verification']['status'],'unverified')
        self.assertEqual(next(b['quality']for b in m['pages'][0]['blocks']if b['id'].endswith('-recovery0')),'needs_review')

if __name__=='__main__':unittest.main()
