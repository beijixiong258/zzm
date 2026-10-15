"""Trace supplied crest line work, replace marked lower centre with an open book.
The original reference remains untouched. Smaller marks use optical simplification.
"""
from pathlib import Path
import json
import cv2
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
PUBLIC=ROOT/'frontend/public'
OUT=ROOT/'artifacts/stage4/brand'
COLOR='#285f50'
SMALL='''<g fill="none" stroke="COLOR" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round">
<path d="M24 27 41 10 48 18 55 10 72 27M38 19q7 3 10 10 3-7 10-10"/>
<path d="M24 27C17 35 15 44 15 55l2 22c1 9-8 14-12 9-3-4 0-7 3-6M72 27c7 8 9 17 9 28l-2 22c-1 9 8 14 12 9 3-4 0-7-3-6"/>
<path d="m16 44-4 6 4 6 4-6-4-6m64 0-4 6 4 6 4-6-4-6"/>
<path d="m34 31 0-9 7 7 3-5 2 7c12-2 24 5 23 16 0 5-4 8-8 9M36 31c-10 0-13 13-11 23 1 8 6 13 9 16 3 5-4 8-6 5M61 46c-1 7 3 12 10 16-8 1-12-1-17-5M46 49c-1-6-7-6-8-1-2 7 3 12 8 16 4 3 10 5 11 9M46 48c4-5 10 0 5 4"/>
<path d="M22 78q13-6 26 2 13-8 26-2v13q-13-5-26 2-13-7-26-2V78Zm26 2v13M29 83q7-2 13 1m12 0q6-3 13-1"/>
</g>'''
BOOK='''<g fill="none" stroke="COLOR" stroke-width="5" stroke-linecap="round" stroke-linejoin="round">
<path d="M153 400Q206 377 265 408Q324 377 377 400V462Q320 438 265 472Q210 438 153 462Z"/>
<path d="M265 408V472M153 400l-9 8v64q61-22 121 9 60-31 121-9v-64l-9-8M169 408q37-10 78 10m-78 9q37-10 78 10m36-19q41-20 78-10m-78 29q41-20 78-10"/>
</g>'''
def svg(body,color,box='40 30 450 460',title='AIcademiya — knowledge and curiosity'):
 return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{box}" role="img"><title>{title}</title>'+body.replace('COLOR',color)+'</svg>\n'
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 im=np.asarray(Image.open(ROOT/'artifacts/stage4/references/logo-reference.png').convert('RGB')).astype(np.int16)
 r,g,b=im[:,:,0],im[:,:,1],im[:,:,2]
 mask=((g>65)&(g>r*1.12)&(g>b*1.3)).astype(np.uint8)*255
 # Keep outside flourishes; replace only the annotated lower centre.
 mask[376:,130:402]=0
 mask[360:390,247:282]=0  # Remove the old lower-centre crest tip above the new book.
 # Slight optical strengthening retains the original silhouette at logo scale.
 mask=cv2.dilate(mask,np.ones((2,2),np.uint8),iterations=1)
 contours,_=cv2.findContours(mask,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
 paths=[]
 for contour in contours:
  if abs(cv2.contourArea(contour))<3:continue
  pts=cv2.approxPolyDP(contour,0.5,True).reshape(-1,2)
  paths.append('M'+'L'.join(f'{x} {y}' for x,y in pts)+'Z')
 body='<path fill="COLOR" fill-rule="evenodd" d="'+' '.join(paths)+'"/>'+BOOK
 (PUBLIC/'aicademiya-mark.svg').write_text(svg(body,COLOR),encoding='utf-8')
 (PUBLIC/'aicademiya-mark-light.svg').write_text(svg(body,'#f7f6ed'),encoding='utf-8')
 (PUBLIC/'aicademiya-mark-small.svg').write_text(svg(SMALL,COLOR,box='0 4 96 92'),encoding='utf-8')
 favicon='<rect x="0" y="4" width="96" height="92" rx="17" fill="#f5f3e8"/>'+SMALL.replace('stroke-width="2.3"','stroke-width="2.8"')
 (PUBLIC/'favicon.svg').write_text(svg(favicon,COLOR,box='0 4 96 92',title='AIcademiya'),encoding='utf-8')
 result={'source':'artifacts/stage4/references/logo-reference.png','preserved_contours':len(paths),'variants':['aicademiya-mark.svg','aicademiya-mark-light.svg','aicademiya-mark-small.svg','favicon.svg'],'book_region':[130,376,402,490],'reference_modified':False}
 (OUT/'design.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
