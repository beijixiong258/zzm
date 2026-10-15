"""Real native text/image adapters and app bundle validation; no GPU/OCR calls."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools/document_stage12'),str(ROOT/'tools/material_stage13')]
from source_text import decode_text
from parser_helpers import sha256
from prepared_material import visual_plan
from backend.aicademiya.document_bundle import source_identity,validate_bundle,BundleError


class SimpleMaterialTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='s14-simple-',dir=os.environ['TMPDIR']);self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def parse(self,source,extra=(),success=True,app_verify=True):
        out=self.root/(source.stem+'-out-'+str(len(list(self.root.iterdir()))))
        p=subprocess.run([sys.executable,str(ROOT/'tools/material_stage13/parse_material.py'),'--input',str(source),'--output',str(out),
                          '--engine','native','--deadline-seconds','60',*extra],capture_output=True,text=True,timeout=70)
        if success:
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)
            if app_verify:
                digest,count=source_identity(source);manifest=validate_bundle(out,digest,count)
            else:
                # Parent owns multi-frame admission; verify the worker only.
                from parser_helpers import validate_bundle as worker_validate
                manifest=json.loads((out/'manifest.json').read_text());worker_validate(out,manifest)
                self.assertEqual(manifest['source_sha256'],sha256(source))
            receipt=json.loads((out/'receipt.json').read_text());self.assertEqual(receipt['status'],'complete')
            self.assertFalse(any(x.get('model_calls',0)or x.get('model_processed')for x in receipt['page_timings']))
            return out,manifest,receipt
        self.assertNotEqual(p.returncode,0);return out
    def text(self,name,literal,encoding='utf-8'):
        source=self.root/name;source.write_bytes(literal.encode(encoding));return source
    def assert_exact(self,manifest,literal):
        text=''.join(b['text']for p in manifest['pages']for b in p['blocks']);self.assertEqual(text,literal)
        self.assertTrue(manifest['coverage']['exact_decoded_text_complete']);self.assertEqual(manifest['coverage']['exact_decoded_character_count'],len(literal))
    def test_utf8_all_characters_beyond_old50k(self):
        literal='Source line with spaces   and\tUnicode 中文。\r\n'*1800+'EXACT_FINAL_SENTINEL'
        source=self.text('long.txt',literal);original=source.read_bytes();_,m,r=self.parse(source)
        self.assertGreater(len(literal),50000);self.assertGreater(m['page_count'],1);self.assert_exact(m,literal)
        self.assertEqual(source.read_bytes(),original);self.assertFalse(visual_plan(m,r)['needs_gpu'])
    def test_markdown_is_literal_no_remote_fetch_or_html_execution(self):
        literal='# Heading\n![remote](http://127.0.0.1:1/private)\n<script>never execute</script>\n**Exact**  end\n'
        _,m,_=self.parse(self.text('source.md',literal));self.assert_exact(m,literal)
    def test_short_plain_text_never_requests_visual_model(self):
        _,m,r=self.parse(self.text('short.txt','Yes\n'));self.assert_exact(m,'Yes\n');self.assertFalse(visual_plan(m,r)['needs_gpu'])
    def test_utf16_with_bom(self):
        literal='日本語の資料。\r\n中文与 English\n';_,m,r=self.parse(self.text('utf16.txt',literal,'utf-16'))
        self.assert_exact(m,literal);self.assertEqual(r['text_encoding'],'utf-16')
    def test_gb18030_strict(self):
        literal='中文原文，不替换乱码。\n';_,m,r=self.parse(self.text('gb.txt',literal,'gb18030'))
        self.assert_exact(m,literal);self.assertEqual(r['text_encoding'],'gb18030')
    def test_invalid_binary_text_rejected_by_upload_and_worker(self):
        source=self.root/'binary.txt';source.write_bytes(b'hello\x00world')
        with self.assertRaises(BundleError):source_identity(source)
        out=self.parse(source,success=False);self.assertEqual(json.loads((out/'receipt.json').read_text())['status'],'failed')
    def test_whitespace_preserved_without_ocr(self):
        literal='\t  \r\n\r\n  \n';_,m,r=self.parse(self.text('spaces.txt',literal));self.assert_exact(m,literal);self.assertFalse(visual_plan(m,r)['needs_gpu'])
    def test_every_static_image_suffix_and_prepared_reuse(self):
        from PIL import Image,ImageDraw
        for suffix,fmt in [('png','PNG'),('jpg','JPEG'),('jpeg','JPEG'),('webp','WEBP')]:
            with self.subTest(suffix=suffix):
                source=self.root/('image.'+suffix);im=Image.new('RGB',(240,100),'white');ImageDraw.Draw(im).text((10,20),'SYNTHETIC IMAGE SOURCE',fill='black');im.save(source,format=fmt)
                original=source.read_bytes();out,m,r=self.parse(source)
                self.assertEqual(m['source_format'],suffix);self.assertEqual(m['page_count'],1);self.assertTrue(visual_plan(m,r)['needs_gpu'])
                again,m2,r2=self.parse(source,extra=['--prepared-dir',str(out)])
                self.assertTrue(r2['preparation_reused']);self.assertEqual((out/'preview.pdf').read_bytes(),(again/'preview.pdf').read_bytes())
                self.assertEqual(m['pages'],m2['pages']);self.assertEqual(source.read_bytes(),original)
    def test_image_suffix_mismatch_denied(self):
        from PIL import Image
        source=self.root/'false.jpg';Image.new('RGB',(16,16),'red').save(source,format='PNG')
        with self.assertRaises(BundleError):source_identity(source)
        self.parse(source,success=False)
    def test_animated_webp_all_frames_not_silently_first_frame(self):
        from PIL import Image
        source=self.root/'animated.webp';Image.new('RGB',(16,16),'red').save(source,format='WEBP',save_all=True,append_images=[Image.new('RGB',(16,16),'blue')],duration=100,loop=0)
        out,m,r=self.parse(source)
        self.assertEqual(m['page_count'],2)
        frames=m['coverage']['original_image']['frame_map']
        self.assertEqual([f['frame_index']for f in frames],[0,1]);self.assertEqual([f['duration_ms']for f in frames],[100,100])
        with Image.open(out/frames[0]['decoded_rgba_asset'])as first,Image.open(out/frames[1]['decoded_rgba_asset'])as last:
            self.assertNotEqual(first.tobytes(),last.tobytes())
        again,m2,r2=self.parse(source,extra=['--prepared-dir',str(out)])
        self.assertTrue(r2['preparation_reused']);self.assertEqual(m['pages'],m2['pages'])
        self.assertEqual((out/'preview.pdf').read_bytes(),(again/'preview.pdf').read_bytes())
    def test_image_exif_orientation_bound_to_original(self):
        from PIL import Image
        source=self.root/'rotated.jpg';im=Image.new('RGB',(80,40),'blue');exif=im.getexif();exif[274]=6;im.save(source,exif=exif)
        _,m,_=self.parse(source);info=m['coverage']['original_image']
        self.assertEqual(info['exif_orientation'],6);self.assertEqual((info['normalized_width'],info['normalized_height']),(40,80))
        self.assertEqual(m['source_sha256'],sha256(source))

if __name__=='__main__':unittest.main()
