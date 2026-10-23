"""Create bounded synthetic APNG and an explicitly mapped real-PDF QA subset."""
from pathlib import Path
import hashlib,json
import pymupdf as fitz
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'artifacts/stage14/r6-final-inputs';OUT.mkdir(exist_ok=False)
source=Path('D:/中转站/Z/Session 2/Program level curriculum Examples-20261006/Macau ELE Curriculum Guide English1_guide_e.pdf')
def sha(p):
 with p.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
expected='c9406dc6f68ddbefeb9e8680691e09557baf62b428e43f6bd40c5c06da8430c1';assert sha(source)==expected
with fitz.open(source)as original,fitz.open()as subset:
 subset.insert_pdf(original,from_page=125,to_page=126);subset.save(OUT/'src03-pages126-127.pdf')
 with fitz.open(OUT/'src03-pages126-127.pdf')as reopened:
  for index,page in enumerate((126,127)):
   a=original[page-1].get_pixmap(matrix=fitz.Matrix(2,2),alpha=False);b=reopened[index].get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
   assert(a.width,a.height,a.samples)==(b.width,b.height,b.samples)
assert sha(source)==expected
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',32);frames=[]
texts=['POSTER source line alpha.','FRAME ONE source line beta.','FRAME TWO source line gamma.']
for text in texts:
 image=Image.new('RGBA',(800,180),'white');ImageDraw.Draw(image).text((30,60),text,font=font,fill='black');frames.append(image)
frames[0].save(OUT/'three-frames.png',save_all=True,append_images=frames[1:],default_image=True,duration=[120,240],loop=0,disposal=[0,0],blend=[0,0])
with Image.open(OUT/'three-frames.png')as image:
 assert image.n_frames==3 and image.info.get('default_image') is True
 for n in range(3):image.seek(n);image.load()
report={'source_pdf_original_sha256':expected,'subset_pages_mapping':{'1':126,'2':127},'subset_render_pixels_equal':True,'files':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size}for p in OUT.iterdir()if p.is_file()},'apng_expected_text_by_frame':texts,'apng_frames':3,'apng_default_poster_included':True,'synthetic_apng':True,'subset_not_entire_src03_acceptance':True}
(OUT/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False))
