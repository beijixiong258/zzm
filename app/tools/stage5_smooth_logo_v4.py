"""Smooth user-selected LOGO_V4 with cubic vector contours, not a redesign."""
from pathlib import Path
import json,hashlib
import cv2,numpy as np,potrace
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path('D:/中转站/Z/LOGO_V4.png')
OUT=ROOT/'artifacts/stage5/logo-v4-smooth'
def point(p):return f'{p.x:.3f} {p.y:.3f}'
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 before=SOURCE.read_bytes();image=Image.open(SOURCE).convert('RGB');pixels=np.asarray(image,dtype=np.float32)
 background=pixels[0,0];ink=pixels[np.mean(pixels,axis=2)<125];foreground=np.median(ink,axis=0)
 delta=background-foreground;alpha=np.clip(np.sum((background-pixels)*delta,axis=2)/np.sum(delta*delta),0,1)
 smooth=cv2.GaussianBlur(alpha,(0,0),0.55)
 mask=smooth>=0.5
 trace=potrace.Bitmap(Image.fromarray(np.where(mask,0,255).astype('uint8'))).trace(turdsize=2,alphamax=1.0,opticurve=True,opttolerance=0.18)
 paths=[];corners=curves=0
 for contour in trace:
  commands=['M'+point(contour.start_point)]
  for segment in contour:
   if segment.is_corner:
    commands += ['L'+point(segment.c),'L'+point(segment.end_point)];corners+=1
   else:
    commands.append('C'+point(segment.c1)+' '+point(segment.c2)+' '+point(segment.end_point));curves+=1
  commands.append('Z');paths.append(' '.join(commands))
 yy,xx=np.where(mask);box=[int(xx.min())-9,int(yy.min())-9,int(xx.max()-xx.min()+1)+18,int(yy.max()-yy.min()+1)+18]
 colour='#'+''.join(f'{round(float(v)):02x}' for v in foreground)
 body='<path fill="COLOR" fill-rule="evenodd" d="'+' '.join(paths)+'"/>'
 for name,color in [('green',colour),('white','#f7f6ed')]:
  text=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{" ".join(map(str,box))}" role="img"><title>AIcademiya — LOGO V4, smooth vector edition</title>'+body.replace('COLOR',color)+'</svg>\n'
  (OUT/f'logo-v4-{name}.svg').write_text(text,encoding='utf-8')
 # Full original-coordinate SVG allows a fair 1:1 raster/mask comparison.
 comparison=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {image.width} {image.height}">'+body.replace('COLOR',colour)+'</svg>'
 (OUT/'logo-v4-comparison.svg').write_text(comparison,encoding='utf-8')
 Image.fromarray(np.uint8(alpha*255)).save(OUT/'source-alpha.png')
 assert SOURCE.read_bytes()==before
 report={'status':'vector_created','source':str(SOURCE),'source_size':list(image.size),'stroke_colour':colour,'viewbox':box,'contours':len(paths),'cubic_segments':curves,'corner_segments':corners,'source_sha256':hashlib.sha256(before).hexdigest(),'source_unchanged':True,'method':'0.55px alpha smoothing + Potrace cubic contour fitting; preserve V4 shapes and page lines','retained_page_lines':True,'production_changed':False}
 (OUT/'design.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
