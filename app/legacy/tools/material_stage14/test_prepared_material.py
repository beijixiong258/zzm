"""Actual native-parser subprocess reuse tests; Office container is synthetic.

No LibreOffice or model call is made here. Formal Office conversion acceptance
is remote/installed-user work, not represented by this prepared-bundle fixture.
"""
from pathlib import Path
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools/document_stage12'),str(ROOT/'tools/material_stage13')]
from parser_helpers import sha256
from prepared_material import reuse_office,visual_plan


class PreparedOfficeTests(unittest.TestCase):
    def setUp(self):
        import pymupdf as fitz
        self.tmp=tempfile.TemporaryDirectory(prefix='s14-prepared-',dir=os.environ['TMPDIR']);self.root=Path(self.tmp.name)
        self.source=self.root/'synthetic.docx'
        with zipfile.ZipFile(self.source,'w')as archive:
            archive.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
            archive.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Synthetic native phase fixture.</w:t></w:r></w:p></w:body></w:document>')
        pdf=self.root/'derived-fixture.pdf';d=fitz.open();p=d.new_page();p.insert_text((40,50),'Synthetic rendered Office fixture with a sufficiently long source paragraph.');d.save(pdf);d.close()
        self.prepared=self.root/'prepared'
        subprocess.run([sys.executable,str(ROOT/'tools/document_stage12/parser_worker.py'),'--input',str(pdf),'--output',str(self.prepared),'--engine','native'],check=True,capture_output=True,text=True,timeout=30)
        shutil.copyfile(pdf,self.prepared/'preview.pdf')
        self.manifest=json.loads((self.prepared/'manifest.json').read_text())
        self.manifest.update(source_format='docx',source_sha256=sha256(self.source),preview_pdf='preview.pdf')
        self.manifest['coverage'].update(rendered_pdf_sha256=sha256(pdf),rendered_pdf_pages=1)
        self.save_manifest()
        r=json.loads((self.prepared/'receipt.json').read_text());r.update(source_format='docx',source_sha256=sha256(self.source),conversion=[{'target_format':'pdf','returncode':0,'seconds':.001,'synthetic_fixture':True}]);self.receipt=r;self.save_receipt()
        native={'source_format':'docx','native_units':[{'unit':1,'part':'word/document.xml','paragraphs':[{'ordinal':0,'text':'Synthetic native phase fixture.'}],'hidden':False}],
                'notes':[],'notes_text_chars':0,'media_count':0,'image_references':[],
                'auxiliary_parts':[],'warnings':['Synthetic test only'],'native_text_chars':31}
        (self.prepared/'raw/office-inventory.json').write_text(json.dumps(native))
    def tearDown(self):self.tmp.cleanup()
    def save_manifest(self):(self.prepared/'manifest.json').write_text(json.dumps(self.manifest))
    def save_receipt(self):(self.prepared/'receipt.json').write_text(json.dumps(self.receipt))
    def test_actual_parser_reuses_prepared_pdf_no_office_binary(self):
        out=self.root/'out'
        env={**os.environ,'PATH':'/nonexistent-synthetic-fixture-bin'}
        p=subprocess.run([sys.executable,str(ROOT/'tools/material_stage13/parse_material.py'),'--input',str(self.source),'--output',str(out),
                          '--prepared-dir',str(self.prepared),'--engine','native'],env=env,capture_output=True,text=True,timeout=30)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        receipt=json.loads((out/'receipt.json').read_text());manifest=json.loads((out/'manifest.json').read_text())
        self.assertTrue(receipt['conversion_reused_from_native_phase']);self.assertEqual(receipt['conversion'],self.receipt['conversion'])
        self.assertEqual(manifest['source_sha256'],sha256(self.source));self.assertEqual(manifest['source_format'],'docx')
        self.assertEqual((out/'preview.pdf').read_bytes(),(self.prepared/'preview.pdf').read_bytes())
        self.assertEqual(manifest['page_count'],1);self.assertFalse(any(x['model_processed']for x in receipt['page_timings']))
    def test_original_mismatch_refused(self):
        self.source.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'original/native'):reuse_office(self.prepared,self.source,'docx',self.root/'out')
    def test_rendered_pdf_mutation_refused(self):
        with(self.prepared/'preview.pdf').open('ab')as f:f.write(b'changed')
        with self.assertRaisesRegex(ValueError,'identity changed'):reuse_office(self.prepared,self.source,'docx',self.root/'out')
    def test_non_native_preparation_refused(self):
        self.receipt['engine']='hybrid';self.save_receipt()
        with self.assertRaisesRegex(ValueError,'original/native'):reuse_office(self.prepared,self.source,'docx',self.root/'out')
    def test_hidden_model_calls_refused(self):
        self.receipt['page_timings'][0]['model_calls']=1;self.save_receipt()
        with self.assertRaisesRegex(ValueError,'original/native'):reuse_office(self.prepared,self.source,'docx',self.root/'out')
    def test_format_mismatch_refused(self):
        with self.assertRaisesRegex(ValueError,'original/native'):reuse_office(self.prepared,self.source,'pptx',self.root/'out')
    def test_unsafe_raw_symlink_refused(self):
        path=self.prepared/'raw/office-media';path.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ValueError):reuse_office(self.prepared,self.source,'docx',self.root/'out')
    def test_pure_native_plan_not_semantic_approval(self):
        result=visual_plan(self.manifest,self.receipt);self.assertFalse(result['needs_gpu']);self.assertIn('not_semantic_approval',result['classification'])
    def test_font_anomaly_fullpage(self):
        m=copy.deepcopy(self.manifest);m['pages'][0]['blocks'][0]['issues'].append('native_font_mapping_unusable')
        result=visual_plan(m,self.receipt);self.assertTrue(result['needs_gpu']);self.assertEqual(result['fullpage_pages'],[1])

if __name__=='__main__':unittest.main()
