"""Actual Linux worker negative paths with rejecting in-process clients.

No model/OCR output is generated. Synthetic PDFs are bounded and never include
classroom data. Tests require failures to remain failures, not blank success.
"""
import io, json, os, sys, tempfile, types, unittest, contextlib
from pathlib import Path
from unittest.mock import patch
import pymupdf as fitz
from PIL import Image
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools/document_stage12'))
import parser_worker
RECEIPTS=[]

class WorkerMaskNegativeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']);self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def source(self,kind):
        base=Image.new('RGB',(2,2),'black')
        if kind=='nonuniform':base.putpixel((1,1),(255,0,0))
        data=io.BytesIO();base.save(data,format='PNG')
        doc=fitz.open();page=doc.new_page(width=72,height=72);xref=page.insert_image(page.rect,stream=data.getvalue())
        mask=doc.get_new_xref();doc.update_object(mask,'<< /Type /XObject /Subtype /Image /Width 7 /Height 5 /BitsPerComponent 8 /ColorSpace /DeviceGray >>');doc.update_stream(mask,bytes(range(35)))
        doc.xref_set_key(xref,'SMask',f'{mask} 0 R')
        if kind=='huge':doc.xref_set_key(mask,'Width','4001');doc.xref_set_key(mask,'Height','4000')
        elif kind=='invalid':doc.xref_set_key(mask,'Width','0')
        elif kind=='matte':doc.xref_set_key(mask,'Matte','[0 0 0]')
        elif kind=='nonuniform':pass
        else:raise AssertionError(kind)
        source=self.root/'source.pdf';doc.save(source);doc.close();return source
    def check(self,kind,message,before_render):
        source=self.source(kind);model_calls=[];counter={'calls':0,'events':[]}
        class NoOCR:
            info={'available':False,'test_double':True}
            def __init__(self,*args):pass
            def scan(self,image):return {'status':'unavailable','lines':[]}
        class NoModel:
            prompts={'[default]':'Text Recognition:'}
            def __init__(self,**kwargs):pass
            def content_extract(self,*args,**kwargs):model_calls.append('forbidden');raise AssertionError('no model call allowed')
            async def aclose(self):pass
        utils=types.ModuleType('mineru_vl_utils');utils.MinerUClient=NoModel
        client=types.ModuleType('mineru_vl_utils.vlm_client');client.SamplingParams=lambda **kw:kw
        (self.root/'models').mkdir();out=self.root/'bundle'
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.dict(sys.modules,{'mineru_vl_utils':utils,'mineru_vl_utils.vlm_client':client}))
            stack.enter_context(patch.object(parser_worker,'CPUVerifier',NoOCR))
            stack.enter_context(patch.object(parser_worker,'observe_vlm_http',return_value=(counter,lambda:None)))
            guard=stack.enter_context(patch.object(fitz.Page,'get_pixmap',side_effect=AssertionError('allocation before softmask guard'))) if before_render else None
            rc=parser_worker.main(['--input',str(source),'--output',str(out),'--engine','region-text','--models',str(self.root/'models'),
                '--vlm-url','http://127.0.0.1:18894','--deadline-seconds','40'])
            if guard is not None:self.assertEqual(guard.call_count,0)
        receipt=json.loads((out/'receipt.json').read_text());manifest=json.loads((out/'manifest.json').read_text())
        self.assertEqual(rc,2);self.assertEqual(receipt['status'],'failed');self.assertEqual(receipt['error_type'],'ValueError')
        self.assertIn(message,receipt['error']);self.assertFalse(manifest['complete']);self.assertFalse(model_calls)
        if kind=='nonuniform':self.assertEqual(len(list((out/'raw/source-images').glob('*.bin'))),2)
        RECEIPTS.append({'kind':kind,'returncode':rc,'manifest_complete':manifest['complete'],'guard_before_render':before_render,
            'raw_source_bytes_retained':kind=='nonuniform','model_calls':0,'receipt':receipt})
    def test_oversize_mask_rejected_before_page_decode(self):self.check('huge','softmask exceeds16million',True)
    def test_invalid_mask_dimensions_rejected_before_page_decode(self):self.check('invalid','softmask has invalid source dimensions',True)
    def test_unequal_matte_mask_rejected_before_page_decode(self):self.check('matte','unequal Matte softmask unsupported',True)
    def test_unequal_nonuniform_base_fails_not_blank_success(self):self.check('nonuniform','base is not opaque constant colour',False)

if __name__=='__main__':
    if sys.platform!='linux':raise SystemExit('Actual worker acceptance is Linux-only')
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(WorkerMaskNegativeTests);result=unittest.TextTestRunner(verbosity=2).run(suite)
    report={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'receipts':RECEIPTS,'gpu_calls':0,'model_service_calls':0}
    target=Path(os.environ['MASK_RECOVERY_OUT'])/'linux-negative-worker-receipts.json';target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(not result.wasSuccessful())
