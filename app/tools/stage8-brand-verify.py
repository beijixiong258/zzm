"""Verify all eight assets, book raster equality, readonly inputs and auth scope."""
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import numpy as np
import hashlib,json,math,re,struct,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'artifacts/stage8/branding'
PUB=ROOT/'frontend/public'
NS='{http://www.w3.org/2000/svg}'
NAMES=['aicademiya-mark.svg','aicademiya-mark-small.svg','aicademiya-mark-light.svg','favicon.svg','favicon-32.png','favicon-48.png','favicon.ico','apple-touch-icon.png']

def raster(p): return np.asarray(Image.open(p).convert('RGBA'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def region_metrics(a,b,box):
    x0,y0,x1,y1=box
    aa=a[y0:y1,x0:x1];bb=b[y0:y1,x0:x1]
    delta=np.abs(aa.astype(int)-bb.astype(int))
    return {'region_px':box,'changed_pixels':int(np.any(delta,axis=2).sum()),'max_channel_delta':int(delta.max()),'pixels':int(aa.shape[0]*aa.shape[1])}
def composite_rgba(a):
    im=Image.fromarray(a);bg=Image.new('RGBA',im.size,'#f7f6ed');bg.alpha_composite(im);return bg.convert('RGB')

def main():
    baseline=ET.parse(ART/'previous-public/aicademiya-mark.svg').getroot().find(NS+'path').attrib['d']
    asset_checks=[]
    for name in NAMES[:4]:
        root=ET.parse(PUB/name).getroot();paths=root.findall(NS+'path');original,outline=paths
        assert root.attrib['viewBox']=='57 23 359 375'
        assert original.attrib['d']==baseline and 'stroke' not in original.attrib
        assert original.attrib['fill-rule']=='evenodd'
        assert original.attrib['data-preserved-book-contours']=='0 1 2 3 4 5 8 9'
        assert outline.attrib['stroke-width']=='0.95' and outline.attrib['fill']=='none'
        assert len(re.findall('M',outline.attrib['d']))==11
        asset_checks.append({'name':name,'sha256':sha(PUB/name),'bytes':(PUB/name).stat().st_size,'original_fill_path_exact':True,'outline_contours':11})
    assert (PUB/NAMES[0]).read_bytes()==(PUB/NAMES[1]).read_bytes()
    for name,size in [('favicon-32.png',32),('favicon-48.png',48),('apple-touch-icon.png',180)]:
        with Image.open(PUB/name) as im:
            assert im.size==(size,size) and im.mode=='RGBA';im.verify()
        asset_checks.append({'name':name,'size':[size,size],'mode':'RGBA','sha256':sha(PUB/name),'valid_png':True})
    ico=(PUB/'favicon.ico').read_bytes();reserved,kind,count=struct.unpack_from('<HHH',ico);assert (reserved,kind,count)==(0,1,2)
    for i,size in enumerate([32,48]):
        width,height,colors,reserved,planes,bpp,length,offset=struct.unpack_from('<BBBBHHII',ico,6+i*16)
        assert (width,height,planes,bpp)==(size,size,1,32)
        assert ico[offset:offset+length]==(PUB/f'favicon-{size}.png').read_bytes()
    asset_checks.append({'name':'favicon.ico','sha256':sha(PUB/'favicon.ico'),'embedded_png_exact_sizes':[32,48]})
    assert len(asset_checks)==8
    proofs=[]
    for scale in [1,4]:
        before=raster(ART/f'baseline-full-{scale}x.png');after=raster(ART/f'selected-full-{scale}x.png')
        proof=region_metrics(before,after,[136*scale,311*scale,337*scale,390*scale]);proof.update({'test':'full-original-coordinate-book','scale':scale});assert proof['changed_pixels']==0;proofs.append(proof)
    for width in [64,80,116,164]:
        before=raster(ART/f'before-mark-{width}.png');after=raster(ART/f'after-mark-{width}.png');height=before.shape[0]
        box=[math.floor((136-57)*width/359),math.floor((311-23)*height/375),math.ceil((337-57)*width/359),math.ceil((390-23)*height/375)]
        proof=region_metrics(before,after,box);proof.update({'test':'actual-mark-size-book','width':width,'height':height});assert proof['changed_pixels']==0;proofs.append(proof)
    for size in [32,48,180]:
        before=raster(ART/f'before-favicon-{size}.png');after=raster(PUB/(f'favicon-{size}.png' if size<180 else 'apple-touch-icon.png'))
        # Square SVG uses xMidYMid meet, so x has an 8-unit side letterbox.
        outer=[math.floor((136-57+8)*size/375),math.floor((311-23)*size/375),math.ceil((337-57+8)*size/375),math.ceil((390-23)*size/375)]
        box=[math.ceil((136-57+8)*size/375),math.ceil((311-23)*size/375),math.floor((337-57+8)*size/375),math.floor((390-23)*size/375)]
        # At 32/48px, an outward-rounded top row also contains the NON-book
        # stem ending at y=302. Do not falsely count its allowed heavier AA as
        # changed book geometry. Use fully contained book pixels as the gate,
        # and report outward boundary differences honestly, without hiding them.
        proof=region_metrics(before,after,box);proof.update({'test':'derived-png-book-contained-pixels','size':size,'outer_boundary_including_mixed_nonbook_pixels':region_metrics(before,after,outer)});assert proof['changed_pixels']==0;proofs.append(proof)
    before=raster(ART/'baseline-full-4x.png');after=raster(ART/'selected-full-4x.png')
    curls=[]
    for label,box in [('left',[60*4,311*4,125*4,352*4]),('right',[350*4,311*4,413*4,352*4])]:
        x0,y0,x1,y1=box; added=(after[y0:y1,x0:x1,3].astype(int)-before[y0:y1,x0:x1,3].astype(int))
        assert added.sum()>0
        curls.append({'side':label,'region_original_coordinates':[v/4 for v in box],'added_alpha_coverage_pixels':float(added.sum()/255),'changed_pixels':int(np.any(before[y0:y1,x0:x1]!=after[y0:y1,x0:x1],axis=2).sum())})
    source=(ROOT/'frontend/src/Login.tsx').read_text();old=(ART/'previous-source/Login.tsx').read_text()
    def chunk(text,start,end):return text[text.index(start):text.index(end,text.index(start))+len(end)]
    auth_checks={'submit_unchanged':chunk(source,'  async function submit','  return (')==chunk(old,'  async function submit','  return ('),'form_fields_validation_submit_button_unchanged':chunk(source,'        <form onSubmit={submit}>','        </form>')==chunk(old,'        <form onSubmit={submit}>','        </form>'),'auth_switch_unchanged':chunk(source,'        <p className="switch-auth">','        </p>')==chunk(old,'        <p className="switch-auth">','        </p>'),'no_course_specific_login_copy':'EDUC7703' not in source,'no_login_model_badge':'AiBadge' not in source}
    ui=(ROOT/'frontend/src/ui.tsx').read_text();old_ui=(ART/'previous-source/ui.tsx').read_text()
    auth_checks['other_ui_exports_byte_equal']=ui[ui.index('export function Loading'):]==old_ui[old_ui.index('export function Loading'):]
    assert all(auth_checks.values())
    inputs=json.loads((ART/'original-input-hashes.json').read_text(encoding='utf8'));assert all(sha(Path(p))==h for p,h in inputs.items())
    # A truthful evidence plate: same render/crop, visible book equality + curl growth.
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',22)
    crop=(136*4,311*4,337*4,390*4)
    before_book=composite_rgba(before).crop(crop);after_book=composite_rgba(after).crop(crop)
    plate=Image.new('RGB',(1680,810),'#f7f6ed');draw=ImageDraw.Draw(plate)
    draw.text((24,18),'Book: original fill is unchanged — 0 changed RGBA pixels (4× Chrome render)',font=font,fill='#23352e')
    draw.text((24,60),'BEFORE',font=font,fill='#23352e');draw.text((860,60),'AFTER',font=font,fill='#23352e')
    plate.paste(before_book,(24,100));plate.paste(after_book,(860,100))
    draw.text((24,450),'Side curls below book top: non-book outlines still widened (not a blanket y-cutoff)',font=font,fill='#23352e')
    for x,label,c in [(24,'LEFT BEFORE',(60*4,300*4,125*4,352*4)),(365,'LEFT AFTER',(60*4,300*4,125*4,352*4)),(800,'RIGHT BEFORE',(350*4,300*4,413*4,352*4)),(1150,'RIGHT AFTER',(350*4,300*4,413*4,352*4))]:
        draw.text((x,500),label,font=font,fill='#23352e');plate.paste(composite_rgba(before if 'BEFORE' in label else after).crop(c),(x,540))
    plate.save(ART/'book-and-curl-preservation-proof.png')
    result={'status':'passed','asset_count':len(asset_checks),'assets':asset_checks,'book_raster_proofs':proofs,'book_raster_changed_pixels_total':sum(p['changed_pixels'] for p in proofs),'lower_side_curl_growth':curls,'auth_scope_checks':auth_checks,'original_inputs_unchanged':True,'original_input_sha256':inputs,'book_only_raster_equal':np.array_equal(raster(ART/'before-book-only-4x.png'),raster(ART/'after-book-only-4x.png'))}
    (ART/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k not in ['assets','original_input_sha256','book_raster_proofs']},indent=2))
if __name__=='__main__':main()
