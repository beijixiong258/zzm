"""Logo preview only: retain reference line work; replace red-box motif with book.
Does not modify frontend/public or any deployed asset. No page ruling lines.
"""
from pathlib import Path
import hashlib,json
import cv2
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path('D:/中转站/3.png')
OUT=ROOT/'artifacts/stage5/logo-preview'
BOOK='''<g id="open-book" fill="none" stroke="COLOR" stroke-width="3.8" stroke-linecap="round" stroke-linejoin="round">
<path id="blank-open-pages" d="M153 401C189 382 231 382 265 405C299 382 341 382 377 401V464C339 448 300 449 265 476C230 449 191 448 153 464Z"/>
<path id="vertical-centre-fold" d="M265 405V476"/>
</g>'''
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 original_bytes=SOURCE.read_bytes()
 protected=[ROOT/'frontend/public'/name for name in ('aicademiya-mark.svg','aicademiya-mark-small.svg','aicademiya-mark-light.svg','favicon.svg')]
 before={str(p):digest(p) for p in protected}
 im=np.asarray(Image.open(SOURCE).convert('RGB')).astype(np.int16)
 r,g,b=im[:,:,0],im[:,:,1],im[:,:,2]
 red=(r>200)&(r>g*1.5)&(r>b*1.5)
 ys,xs=np.where(red);assert len(xs)>100
 roi=(int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1));x0,y0,x1,y1=roi
 original=((g>65)&(g>r*1.12)&(g>b*1.3)).astype(np.uint8)*255
 preserved=original.copy();preserved[y0:y1,x0:x1]=0
 # The old lower ornament crosses the top border: remove only its dangling tip.
 boundary_cleanup=(248,365,283,y0)
 preserved[365:y0,248:283]=0
 outside=np.ones(original.shape,dtype=bool);outside[y0:y1,x0:x1]=False
 outside[365:y0,248:283]=False
 assert np.array_equal(preserved[outside],original[outside])
 # No dilation and no hand-redrawn portrait/arch: keep reference stroke contours.
 contours,_=cv2.findContours(preserved,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
 paths=[]
 for contour in contours:
  if abs(cv2.contourArea(contour))<2:continue
  points=cv2.approxPolyDP(contour,0.2,True).reshape(-1,2)
  paths.append('M'+'L'.join(f'{x} {y}' for x,y in points)+'Z')
 body='<path id="preserved-reference" fill="COLOR" fill-rule="evenodd" d="'+' '.join(paths)+'"/>'+BOOK
 for name,color in [('green','#285f50'),('white','#f7f6ed'),('reference-green','#89a934')]:
  svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="40 30 450 465" role="img"><title>AIcademiya — reference crest with a blank open book</title>'+body.replace('COLOR',color)+'</svg>\n'
  (OUT/f'crest-book-{name}.svg').write_text(svg,encoding='utf-8')
 assert SOURCE.read_bytes()==original_bytes
 assert before=={str(p):digest(p) for p in protected}
 result={'status':'preview_created','source':str(SOURCE),'replacement_rectangle':roi,'preserved_reference_contours':len(paths),'stroke_hand_redrawn_outside_rectangle':False,'boundary_cleanup':boundary_cleanup,'outside_replacement_and_boundary_mask_unchanged':True,'page_ruling_lines':0,'centre_fold':'vertical only','production_deployed':False,'frontend_public_assets_unchanged':True,'outputs':[str(OUT/f'crest-book-{v}.svg') for v in ('green','white','reference-green')]}
 (OUT/'design.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
