"""Bounded source-pixel tests; no OCR/model/network execution."""
import io, struct, sys, unittest, zlib
from pathlib import Path
from unittest.mock import patch
from PIL import Image
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools/document_stage12'))
from parser_helpers import composite_embedded

def png(image):
    data=io.BytesIO();image.save(data,format='PNG');return data.getvalue()
def declared_size(data,width,height):
    body=struct.pack('>II',width,height)+data[24:29]
    return data[:16]+body+struct.pack('>I',zlib.crc32(b'IHDR'+body)&0xffffffff)+data[33:]

class MaskTests(unittest.TestCase):
    def test_same_grid_black_strokes(self):
        base=Image.new('RGB',(40,20),'black');mask=Image.new('L',base.size,0);mask.putpixel((10,10),255)
        evidence={};got=composite_embedded(png(base),png(mask),evidence=evidence)
        self.assertEqual(got.getpixel((10,10)),(0,0,0));self.assertEqual(got.getpixel((0,0)),(255,255,255))
        self.assertEqual(evidence['operation'],'same_grid_softmask')
    def test_generic_unequal_grids_require_pdf_opt_in(self):
        with self.assertRaisesRegex(ValueError,'mask dimensions'):
            composite_embedded(png(Image.new('RGB',(2,2),'black')),png(Image.new('L',(287,112),0)))
    def test_constant_base_preserves_every_detailed_mask_sample(self):
        base=png(Image.new('RGB',(2,2),'black'));mask=Image.new('L',(287,112))
        mask.putdata([(x*37+y*13)%256 for y in range(112) for x in range(287)])
        evidence={}
        with patch.object(Image.Image,'resize',side_effect=AssertionError('mask/base resampling prohibited')):
            got=composite_embedded(base,png(mask),pdf_softmask=True,evidence=evidence)
        self.assertEqual(got.size,mask.size)
        self.assertEqual(list(got.getdata()),[(255-v,)*3 for v in mask.getdata()])
        self.assertEqual(evidence['source_image_size'],[2,2]);self.assertEqual(evidence['source_mask_size'],[287,112])
        self.assertFalse(evidence['includes_page_overlays'])
    def test_nonuniform_base_rejected_instead_of_resampled(self):
        base=Image.new('RGB',(2,2),'black');base.putpixel((1,1),(255,0,0));evidence={}
        with self.assertRaisesRegex(ValueError,'not opaque constant'):
            composite_embedded(png(base),png(Image.new('L',(7,5),255)),pdf_softmask=True,evidence=evidence)
        self.assertNotIn('decode_status',evidence)
    def test_nonopaque_constant_base_rejected_for_unequal_mask(self):
        with self.assertRaisesRegex(ValueError,'not opaque constant'):
            composite_embedded(png(Image.new('RGBA',(2,2),(0,0,0,128))),png(Image.new('L',(7,5),255)),pdf_softmask=True)
    def test_smaller_crossed_and_colour_mask_grids_rejected(self):
        for mode,size in [('L',(1,1)),('L',(1,5)),('L',(5,1)),('RGB',(7,5))]:
            with self.subTest(mode=mode,size=size),self.assertRaisesRegex(ValueError,'mask dimensions'):
                composite_embedded(png(Image.new('RGB',(2,2),'black')),png(Image.new(mode,size)),pdf_softmask=True)
    def test_png_transparent_alpha_not_erased(self):
        base=Image.new('RGBA',(3,1),(0,0,0,0));base.putpixel((1,0),(0,0,0,255));base.putpixel((2,0),(0,0,0,128))
        got=composite_embedded(png(base));self.assertEqual(list(got.getdata()),[(255,)*3,(0,)*3,(127,)*3])
    def test_same_grid_mask_multiplies_existing_png_alpha(self):
        base=Image.new('RGBA',(2,1),(0,0,0,128));mask=Image.new('L',(2,1),128);mask.putpixel((0,0),0)
        got=composite_embedded(png(base),png(mask));self.assertEqual(list(got.getdata()),[(255,)*3,(191,)*3])
    def test_source_pixel_cap_before_decode_or_allocation(self):
        oversized=declared_size(png(Image.new('RGB',(1,1))),4001,4000)
        with patch.object(Image.Image,'convert',side_effect=AssertionError('decode happened before cap')):
            with self.assertRaisesRegex(ValueError,'raster exceeds16million'):
                composite_embedded(oversized)
    def test_mask_pixel_cap_before_either_decode_or_allocation(self):
        base=png(Image.new('RGB',(2,2)));oversized=declared_size(png(Image.new('L',(1,1))),4001,4000)
        with patch.object(Image.Image,'convert',side_effect=AssertionError('decode happened before mask cap')):
            with self.assertRaisesRegex(ValueError,'softmask exceeds16million'):
                composite_embedded(base,oversized,pdf_softmask=True)
    def test_invalid_empty_and_truncated_mask_fail_not_blank_success(self):
        base=png(Image.new('RGB',(2,2)))
        good=png(Image.new('L',(7,5),255))
        for bad in (b'',b'not a raster',good[:45],declared_size(good,287,112)):
            evidence={}
            with self.subTest(length=len(bad)),self.assertRaises((OSError,ValueError,SyntaxError)):
                composite_embedded(base,bad,pdf_softmask=True,evidence=evidence)
            self.assertNotIn('decode_status',evidence)
    def test_invalid_source_fails_not_blank_success(self):
        for bad in (b'',b'not a raster',png(Image.new('RGB',(2,2)))[:45]):
            with self.subTest(length=len(bad)),self.assertRaises((OSError,ValueError,SyntaxError)):
                composite_embedded(bad)

if __name__=='__main__':unittest.main(verbosity=2)
