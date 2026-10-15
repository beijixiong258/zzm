"""Stage13 focused synthetic tests; protocol fixtures are not GPU/semantic proof."""
import io
import json
import os
import re
import struct
import sys
import tempfile
import types
import unittest
import zipfile
import zlib
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'document_stage12'))
from parser_helpers import convert_middle,coverage_of,merge_native_visual,validate_bundle,literal_response,observe_vlm_http,sha256
from office_inventory import inventory,preflight
from archive_guard import office_guard


def docx(path,text='Text',extra=None):
    parts={'[Content_Types].xml':'<Types/>','word/document.xml':
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>'+text+'</w:t></w:r></w:p></w:body></w:document>'}
    parts.update(extra or {})
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in parts.items():archive.writestr(name,data)


class OfficeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def test_office_native_not_truncated(self):
        src=self.root/'large.docx';docx(src,'a'*70000)
        result=inventory(src,'docx',self.root/'raw')
        self.assertEqual(result['native_text_chars'],70000)
    def test_notes_retained_not_injected(self):
        src=self.root/'notes.docx';docx(src,'body',{'word/comments.xml':'<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:t>Private comment</w:t></w:comments>'})
        result=inventory(src,'docx',self.root/'raw')
        self.assertEqual(result['native_text_chars'],4)
        self.assertEqual(result['notes'][0]['text'],'Private comment')
        self.assertTrue(any('comments.xml'==Path(p['part']).name for p in result['auxiliary_parts']))
    def test_xml_entities_rejected(self):
        src=self.root/'bad.docx';docx(src,extra={'word/comments.xml':'<!DOCTYPE foo [<!ENTITY x "y">]><foo/>'})
        with self.assertRaisesRegex(ValueError,'entities'):preflight(src,'docx')
    def test_external_content_rejected(self):
        src=self.root/'bad.docx';docx(src,extra={'word/_rels/document.xml.rels':'<Relationships><Relationship Id="x" Type="image" TargetMode="External" Target="http://invalid/image.png"/></Relationships>'})
        with self.assertRaisesRegex(ValueError,'linked content'):preflight(src,'docx')
    def test_hyperlink_does_not_fetch(self):
        src=self.root/'link.docx';docx(src,extra={'word/_rels/document.xml.rels':'<Relationships><Relationship Id="x" Type="urn/test/hyperlink" TargetMode="External" Target="http://invalid/"/></Relationships>'})
        self.assertEqual(preflight(src,'docx'),[])
    def test_archive_symlink_rejected(self):
        src=self.root/'symlink.docx';docx(src)
        with zipfile.ZipFile(src,'a') as archive:
            info=zipfile.ZipInfo('word/link');info.create_system=3;info.external_attr=(0o120777<<16);archive.writestr(info,'outside')
        with self.assertRaisesRegex(ValueError,'Unsafe'):preflight(src,'docx')
    def test_archive_traversal_rejected(self):
        src=self.root/'traversal.docx';docx(src,extra={'../bad.xml':'<x/>'})
        with self.assertRaisesRegex(ValueError,'Unsafe'):preflight(src,'docx')
    def test_forged_deflate_expansion_rejected(self):
        src=self.root/'forged.docx';docx(src,extra={'word/large.bin':b'x'*100000})
        data=bytearray(src.read_bytes());marker=b'word/large.bin';end=data.index(b'PK\x01\x02',data.index(marker)+len(marker))
        offset=data.index(b'PK\x01\x02',end)
        while data[offset+46:offset+46+len(marker)]!=marker:
            offset=data.index(b'PK\x01\x02',offset+4)
        local=struct.unpack_from('<L',data,offset+42)[0]
        struct.pack_into('<L',data,offset+24,16);struct.pack_into('<L',data,local+22,16)
        struct.pack_into('<L',data,offset+16,zlib.crc32(b'x'*16));struct.pack_into('<L',data,local+14,zlib.crc32(b'x'*16))
        src.write_bytes(data)
        with self.assertRaisesRegex(ValueError,'exceeds its declared'):office_guard(src)
    def test_oversized_image_header_preflight(self):
        from PIL import Image
        # Construct valid header cheaply; Pillow opens dimensions before decode.
        buf=io.BytesIO();Image.new('RGB',(1,1),'white').save(buf,format='PNG')
        data=bytearray(buf.getvalue());struct.pack_into('>II',data,16,4001,4000)
        struct.pack_into('>I',data,29,zlib.crc32(bytes(data[12:29])))
        src=self.root/'image.docx';docx(src,extra={'word/media/image.png':bytes(data)})
        with self.assertRaisesRegex(ValueError,'16million'):preflight(src,'docx')
    def test_duplicate_zip_member_rejected(self):
        src=self.root/'dup.docx';docx(src)
        with zipfile.ZipFile(src,'a') as archive:archive.writestr('word/document.xml','<x/>')
        with self.assertRaisesRegex(ValueError,'duplicate'):preflight(src,'docx')


class PDFTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def test_refusal_is_not_source_text_and_regular_text_is_exact(self):
        response='The image is too blurry to recognize any text content.'
        self.assertEqual(literal_response(response),('', 'explicit_refusal_not_source_text'))
        text='TEST\nStudents\nLearning\n'
        self.assertEqual(literal_response(text),(text,'literal_candidate'))
    def test_fresh_model_http_metadata_sync_async_empty_and_other_port(self):
        import asyncio,httpx
        counts,restore=observe_vlm_http('http://127.0.0.1:18894')
        transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'choices':[{'message':{'content':''}}]}))
        try:
            with httpx.Client(transport=transport) as client:
                client.get('http://127.0.0.1:18894/models')
                client.post('http://127.0.0.1:18280/v1/chat/completions',json={})
                self.assertEqual(counts['calls'],0)
                client.post('http://127.0.0.1:18894/v1/chat/completions',json={})
                self.assertEqual(counts['calls'],1)
            async def call():
                async with httpx.AsyncClient(transport=transport) as client:
                    await client.post('http://127.0.0.1:18894/v1/chat/completions',json={})
            asyncio.run(call());self.assertEqual(counts['calls'],2)
        finally:restore()
    def test_native_merge_preserves_ids_text_parentage(self):
        native=convert_middle({'blocks':[{'index':0,'type':'text','bbox':[0,0,1,.2],'content':'Exact native'},
            {'index':1,'type':'image','bbox':[0,.2,1,1],'content':''}]},1,lambda i,b:'assets/'+i+'.png')
        visual=convert_middle({'blocks':[{'index':0,'type':'text','bbox':[.1,.3,.9,.4],'content':'OCR labels'},
            {'index':1,'type':'table','bbox':[.1,.5,.9,.9],'content':'Unverified graph interpretation'}]},1,lambda i,b:'assets/'+i+'.png')
        merged=merge_native_visual(native,visual)
        self.assertEqual(merged[0]['id'],'p1-b0');self.assertEqual(merged[0]['text'],'Exact native')
        self.assertEqual(merged[2]['parent_id'],'p1-b1');self.assertEqual(merged[3]['quality'],'needs_review')
        self.assertTrue(any('not_literal' in i for i in merged[3]['issues']))
        self.assertEqual(len({b['id'] for b in merged}),4)
    def test_full_text_preserved_above50k(self):
        text='x'*70000
        result=convert_middle({'blocks':[{'index':0,'type':'text','bbox':[0,0,1,1],'content':text}]},1,lambda *a:'none')
        self.assertEqual(result[0]['text'],text)
    @unittest.skipUnless(sys.platform=='linux','Ubuntu-only imported-evidence integration')
    def test_imported_visual_assets_do_not_overwrite_native_crop(self):
        import pymupdf as fitz
        from PIL import Image
        from parser_worker import main
        Image.new('RGB',(200,100),'red').save(self.root/'source.png')
        doc=fitz.open();page=doc.new_page(width=200,height=100)
        page.insert_image(page.rect,filename=str(self.root/'source.png'));doc.save(self.root/'source.pdf');doc.close()
        (self.root/'evidence').mkdir()
        (self.root/'evidence/middle_json.json').write_text(json.dumps({'pages':[{'page_idx':0,'blocks':[{'index':0,'type':'image','bbox':[.25,.25,.75,.75],'content':'Unverified interpretation'}]}]}))
        rc=main(['--input',str(self.root/'source.pdf'),'--output',str(self.root/'bundle'),'--engine','native',
            '--evidence-dir',str(self.root/'evidence'),'--evidence-source-sha256',sha256(self.root/'source.pdf'),'--deadline-seconds','30'])
        self.assertEqual(rc,0)
        m=json.loads((self.root/'bundle/manifest.json').read_text());b=m['pages'][0]['blocks']
        self.assertEqual(b[0]['assets'],['assets/p1-b0.png'])
        self.assertEqual(b[1]['assets'],['assets/p1-b0-vlm.png'])
        with Image.open(self.root/'bundle'/b[0]['assets'][0]) as original,Image.open(self.root/'bundle'/b[1]['assets'][0]) as visual:
            self.assertGreater(original.width,visual.width)
        receipt=json.loads((self.root/'bundle/receipt.json').read_text())
        self.assertFalse(receipt['page_timings'][0]['model_processed'])
        self.assertTrue(receipt['page_timings'][0]['imported_evidence'])
    @unittest.skipUnless(sys.platform=='linux','Ubuntu-only real PDF parser protocol fixture')
    def test_whole_vlm_does_not_suppress_literal_image_ocr(self):
        import pymupdf as fitz
        from PIL import Image,ImageDraw
        from parser_worker import main
        im=Image.new('RGB',(400,150),'white');ImageDraw.Draw(im).text((10,30),'SOURCE LABEL',fill='black');im.save(self.root/'label.png')
        doc=fitz.open();page=doc.new_page(width=400,height=150);page.insert_image(page.rect,filename=str(self.root/'label.png'));doc.save(self.root/'scan.pdf');doc.close()
        calls=[]
        class Client:
            prompts={'[default]':'Text Recognition:'}
            def __init__(self,**kwargs):pass
            def content_extract(self,image,type):calls.append(image.size);return 'SOURCE LABEL'
            async def aclose(self):pass
        class Writer:
            def __init__(self,root):self.root=Path(root)
        class Parsed:
            def save(self,writer):
                writer.root.mkdir(parents=True)
                (writer.root/'middle_json.json').write_text(json.dumps({'pages':[{'page_idx':0,'blocks':[
                    {'index':0,'type':'image','bbox':[0,0,1,1],'content':'UNVERIFIED INTERPRETATION FIXTURE'}]}]}))
        mineru=types.ModuleType('mineru');mineru.__path__=[]
        parser=types.ModuleType('mineru.parser');parser.__path__=[];parser.parse=lambda *args,**kwargs:Parsed()
        writer=types.ModuleType('mineru.parser.writer');writer.FileBasedDataWriter=Writer
        utils=types.ModuleType('mineru_vl_utils');utils.MinerUClient=Client
        client=types.ModuleType('mineru_vl_utils.vlm_client');client.SamplingParams=lambda **kwargs:kwargs
        (self.root/'models').mkdir()
        with patch.dict(sys.modules,{'mineru':mineru,'mineru.parser':parser,'mineru.parser.writer':writer,
            'mineru_vl_utils':utils,'mineru_vl_utils.vlm_client':client}):
            rc=main(['--input',str(self.root/'scan.pdf'),'--output',str(self.root/'bundle'),'--engine','hybrid',
                '--models',str(self.root/'models'),'--vlm-url','http://127.0.0.1:18894','--deadline-seconds','29.75'])
        self.assertEqual(rc,0);self.assertEqual(len(calls),1)
        m=json.loads((self.root/'bundle/manifest.json').read_text());b=m['pages'][0]['blocks']
        self.assertEqual(m['coverage']['image_untranscribed'],0)
        literal=[x for x in b if 'source_transcription_ocr' in x['issues']]
        self.assertEqual(literal[0]['text'],'SOURCE LABEL');self.assertEqual(literal[0]['parent_id'],'p1-b0')
        interpreted=[x for x in b if any('visual_interpretation_unverified' in i for i in x['issues'])]
        self.assertEqual(interpreted[0]['quality'],'needs_review')

    @unittest.skipUnless(sys.platform=='linux','Ubuntu-only real PDF parser protocol fixture')
    def test_auto_mixed_ocr_reuse_and_decorative(self):
        import pymupdf as fitz
        from PIL import Image,ImageDraw
        from parser_worker import main
        im=Image.new('RGB',(400,150),'white');ImageDraw.Draw(im).text((10,30),'SOURCE LABEL',fill='black');im.save(self.root/'label.png')
        Image.new('RGB',(100,100),'white').save(self.root/'uniform.png')
        d=fitz.open();native='Original native prose over forty characters must never be replaced.'
        for _ in range(2):
            p=d.new_page(width=400,height=300);p.insert_text((10,30),native,fontsize=9)
            p.insert_image(fitz.Rect(10,80,390,200),filename=str(self.root/'label.png'))
            p.insert_image(fitz.Rect(10,80,390,200),filename=str(self.root/'label.png'))
            p.insert_image(fitz.Rect(10,210,80,280),filename=str(self.root/'uniform.png'))
        d.save(self.root/'mixed.pdf');d.close()
        calls=[]
        class Client:
            prompts={'[default]':'Text Recognition:'}
            def __init__(self,**kwargs):
                config=json.loads(Path(os.environ['MINERU_CONFIG']).read_text())
                timeout=config['model']['vlm']['http_timeout']
                assert type(timeout) is int and timeout==int(29.75),timeout
            def content_extract(self,image,type):calls.append(image.size);return 'SOURCE LABEL'
            async def aclose(self):pass
        utils=types.ModuleType('mineru_vl_utils');utils.MinerUClient=Client
        client=types.ModuleType('mineru_vl_utils.vlm_client');client.SamplingParams=lambda **kwargs:kwargs
        mineru=types.ModuleType('mineru');mineru.__path__=[]
        parser=types.ModuleType('mineru.parser');parser.__path__=[]
        def unexpected_parse(*args,**kwargs):raise AssertionError('Native mixed pages must add image OCR, not replace all native content')
        parser.parse=unexpected_parse
        writer=types.ModuleType('mineru.parser.writer');writer.FileBasedDataWriter=object
        (self.root/'models').mkdir()
        with patch.dict(sys.modules,{'mineru_vl_utils':utils,'mineru_vl_utils.vlm_client':client,
            'mineru':mineru,'mineru.parser':parser,'mineru.parser.writer':writer}):
            rc=main(['--input',str(self.root/'mixed.pdf'),'--output',str(self.root/'bundle'),'--engine','hybrid',
                '--models',str(self.root/'models'),'--vlm-url','http://127.0.0.1:18894','--deadline-seconds','29.75'])
        self.assertEqual(rc,0)
        m=json.loads((self.root/'bundle/manifest.json').read_text())
        self.assertEqual(len(calls),1)
        self.assertEqual(m['coverage']['image_ocr_text'],4)
        self.assertEqual(m['coverage']['image_decorative_uniform'],2)
        self.assertEqual(m['coverage']['image_reused_occurrences'],4)
        for p in m['pages']:
            self.assertEqual(p['blocks'][0]['text'],native)
            for b in p['blocks']:self.assertRegex(b['id'],r'^p\d+-b\d+(?:-[A-Za-z0-9_-]+)?$')
            children=[b for b in p['blocks'] if 'source_transcription_ocr' in b['issues'] and b['text']]
            self.assertEqual({b['parent_id'] for b in children},{f'p{p["number"]}-b1',f'p{p["number"]}-b2'})
        self.assertTrue(validate_bundle(self.root/'bundle',m)['valid'])
        self.assertFalse(m['coverage']['semantic_accuracy_approved'])


if __name__=='__main__':unittest.main(verbosity=2)
