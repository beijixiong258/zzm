"""Synthetic schema/adapter regression tests; never fixture answer substitution."""
import json
import tempfile
import unittest
from pathlib import Path
from parser_helpers import convert_middle, dump, rotate_bbox, validate_bundle


class BundleTests(unittest.TestCase):
    def fixture(self, root):
        (root/'pages').mkdir();(root/'pages/p1.png').write_bytes(b'fixture-image')
        return {'schema_version':1,'source_sha256':'a'*64,'parser':{'name':'test','version':'1','recipe':'native'},
                'page_count':1,'complete':True,'warnings':[], 'pages':[{'number':1,'printed_label':None,'rotation':0,
                'image':'pages/p1.png','width':2,'height':2,'status':'text','issues':[], 'blocks':[{'id':'p1-b0','type':'text',
                'bbox':[0,0,1,1],'text':'Complete fixture text.','quality':'extracted','issues':[],'assets':[],'parent_id':None}]}]}

    def test_nested_caption_and_native_heading(self):
        pg={'blocks':[{'type':'paragraph_title','index':1,'bbox':[0,0,1,.1],'content':'Title'},
                     {'type':'image','index':4,'bbox':[.1,.2,.9,.8],'content':[{'type':'image_body','index':4,'bbox':[.1,.2,.9,.8],'content':'visual text'},
                       {'type':'image_caption','index':5,'bbox':[.1,.85,.9,.9],'content':[{'type':'text','content':'nested label'}]}]}]}
        b=convert_middle(pg,16,lambda i,x:'assets/'+i+'.png')
        self.assertEqual(b[0]['type'],'heading')
        self.assertEqual(b[-1]['text'],'nested label')
        self.assertEqual(b[-1]['parent_id'],'p16-b4')
        self.assertEqual(b[1]['quality'],'needs_review')
        self.assertEqual(b[-1]['id'],'p16-b5')

    def test_rotation(self):
        self.assertEqual(rotate_bbox([.1,.2,.3,.4],90),[.6,.1,.8,.3])

    def test_complete_exact_set(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);m=self.fixture(p);m['page_count']=2
            with self.assertRaisesRegex(ValueError,'exact original'):validate_bundle(p,m)
            m['complete']=False
            self.assertFalse(validate_bundle(p,m)['complete'])

    def test_quality_not_approved(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);m=self.fixture(p);m['pages'][0]['blocks'][0]['quality']='approved'
            with self.assertRaisesRegex(ValueError,'quality'):validate_bundle(p,m)

    def test_parent_and_path(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);m=self.fixture(p);m['pages'][0]['image']='../outside.png'
            with self.assertRaisesRegex(ValueError,'unsafe'):validate_bundle(p,m)
            m['pages'][0]['image']='pages/p1.png';m['pages'][0]['blocks'][0]['parent_id']='p2-b4'
            with self.assertRaisesRegex(ValueError,'parent'):validate_bundle(p,m)

    def test_no_text_truncation(self):
        text='x'*70000
        b=convert_middle({'blocks':[{'type':'text','index':7,'bbox':[0,0,1,1],'content':text}]},1,lambda i,x:'unused')
        self.assertEqual(len(b[0]['text']),70000)


if __name__=='__main__':unittest.main()
