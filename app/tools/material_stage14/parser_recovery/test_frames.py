"""Actual Pillow APNG/WebP complete-frame decoding and source preservation."""
import copy,io,json,os,struct,sys,tempfile,unittest,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'tools/document_stage12'),str(ROOT/'tools/material_stage13')]
from simple_material import image_pdf,main
from parser_helpers import sha256


class FrameTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']);self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def assert_frame_pixels(self,source,info):
        from PIL import Image,ImageOps
        with Image.open(source)as original:
            self.assertEqual(info['frames'],original.n_frames)
            for row in info['frame_map']:
                original.seek(row['frame_index']);original.load()
                rgba=ImageOps.exif_transpose(original).convert('RGBA')
                with Image.open(self.root/row['decoded_rgba_asset'])as retained:
                    self.assertEqual(retained.tobytes(),rgba.tobytes());self.assertEqual(retained.mode,'RGBA')
                self.assertEqual(row['original_source_sha256'],sha256(source))
                self.assertEqual(row['decoded_rgba_sha256'],sha256(self.root/row['decoded_rgba_asset']))
    def test_apng_every_composited_frame_duration_alpha_and_disposal(self):
        import pymupdf as fitz
        from PIL import Image
        source=self.root/'animation.png'
        frames=[Image.new('RGBA',(60,40),(255,0,0,255)),Image.new('RGBA',(60,40),(0,255,0,128)),Image.new('RGBA',(60,40),(0,0,255,64))]
        frames[0].save(source,save_all=True,append_images=frames[1:],duration=[70,120,180],disposal=[0,1,2],blend=[0,1,1],loop=2)
        original=source.read_bytes();info=image_pdf(source,self.root/'preview.pdf','png')
        self.assertEqual(info['frames'],3);self.assertEqual([f['duration_ms']for f in info['frame_map']],[70,120,180]);self.assertEqual(info['loop'],2)
        self.assert_frame_pixels(source,info)
        with fitz.open(self.root/'preview.pdf')as doc:self.assertEqual(len(doc),3)
        self.assertEqual(source.read_bytes(),original)
    def test_apng_default_poster_retained_as_page_not_silently_dropped(self):
        from PIL import Image
        source=self.root/'poster.png';Image.new('RGBA',(24,24),'red').save(source,save_all=True,
            append_images=[Image.new('RGBA',(24,24),'blue'),Image.new('RGBA',(24,24),'green')],default_image=True,duration=[80,90],loop=0)
        info=image_pdf(source,self.root/'preview.pdf','png')
        self.assertEqual(info['frames'],3);self.assertTrue(info['default_image']);self.assertTrue(info['frame_map'][0]['is_default_image'])
        self.assertIsNone(info['frame_map'][0]['duration_ms']);self.assertEqual([r['duration_ms']for r in info['frame_map'][1:]],[80,90])
        self.assert_frame_pixels(source,info)
    def test_webp_every_lossless_frame_pixels_and_duration(self):
        from PIL import Image
        source=self.root/'animation.webp';Image.new('RGBA',(36,36),(10,20,30,100)).save(source,format='WEBP',save_all=True,lossless=True,
            append_images=[Image.new('RGBA',(36,36),(50,60,70,120)),Image.new('RGBA',(36,36),(80,90,100,130))],duration=[100,200,300],loop=3)
        info=image_pdf(source,self.root/'preview.pdf','webp')
        self.assertEqual([r['duration_ms']for r in info['frame_map']],[100,200,300]);self.assert_frame_pixels(source,info)
    def test_1001_frames_explicit_fail_before_inference(self):
        from PIL import Image
        source=self.root/'many.png';frames=[Image.new('RGB',(2,2),(i%256,(i//256)%256,0))for i in range(1001)]
        frames[0].save(source,save_all=True,append_images=frames[1:],duration=20)
        with self.assertRaisesRegex(ValueError,'1000frames'):image_pdf(source,self.root/'preview.pdf','png')
        self.assertFalse((self.root/'preview.pdf').exists())
    def test_corrupt_late_frame_explicit_failed_receipt_no_inference(self):
        from PIL import Image
        source=self.root/'corrupt.png';Image.new('RGB',(32,32),'red').save(source,save_all=True,append_images=[Image.new('RGB',(32,32),'blue')],duration=50)
        data=source.read_bytes();offset=data.rindex(b'fdAT');source.write_bytes(data[:offset+10]);digest=sha256(source)
        out=self.root/'failed';rc=main(['--input',str(source),'--output',str(out),'--source-format','png'])
        self.assertEqual(rc,2);receipt=json.loads((out/'receipt.json').read_text());self.assertEqual(receipt['status'],'failed')
        self.assertFalse((out/'pdf-work').exists());self.assertEqual(sha256(source),digest)
    def test_16mp_source_limit_checked_before_pixel_decode(self):
        from PIL import Image
        source=self.root/'huge.png';buffer=io.BytesIO();Image.new('RGB',(1,1)).save(buffer,format='PNG')
        data=bytearray(buffer.getvalue());struct.pack_into('>II',data,16,4001,4000);struct.pack_into('>I',data,29,zlib.crc32(bytes(data[12:29])));source.write_bytes(data)
        with self.assertRaisesRegex(ValueError,'16million'):image_pdf(source,self.root/'preview.pdf','png')

if __name__=='__main__':unittest.main()
