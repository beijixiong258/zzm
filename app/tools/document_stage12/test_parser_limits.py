"""Linux-only pre-allocation boundary checks; synthetic inputs, no model call."""
from pathlib import Path
import json,subprocess,sys,tempfile
import pymupdf as fitz
from PIL import Image

root=Path(sys.argv[1]);root.mkdir(parents=True,exist_ok=False)
worker=Path(__file__).with_name('parser_worker.py')

def run(name,expected_ok):
 p=subprocess.run([sys.executable,str(worker),'--input',str(root/(name+'.pdf')),'--output',str(root/(name+'-out')),'--engine','native','--deadline-seconds','45'],capture_output=True,text=True,timeout=55)
 receipt=json.loads((root/(name+'-out')/'receipt.json').read_text())
 assert(p.returncode==0)==expected_ok,(name,p.returncode,p.stderr,receipt)
 return {'case':name,'returncode':p.returncode,'receipt':receipt}

p=fitz.open();page=p.new_page(width=100000,height=100000);p.save(root/'giant-page.pdf');p.close()
rows=[run('giant-page',True)];manifest=json.loads((root/'giant-page-out/manifest.json').read_text());assert manifest['page_count']==1
page=manifest['pages'][0];assert page['width']*page['height']<=4000000
with Image.open(root/'giant-page-out'/page['image'])as im:assert im.size==(page['width'],page['height'])
rows[0]['bounded_pixels']=page['width']*page['height']
p=fitz.open()
for _ in range(1001):p.new_page(width=100,height=100)
p.save(root/'over-pages.pdf');p.close();rows.append(run('over-pages',False));assert '1000pages'in rows[-1]['receipt']['error']
im=Image.new('RGB',(4001,4000),'white');im.save(root/'oversize.png');p=fitz.open();page=p.new_page(width=400,height=400);page.insert_image(page.rect,filename=str(root/'oversize.png'));p.save(root/'over-raster.pdf',deflate=True);p.close()
rows.append(run('over-raster',False));assert '16million'in rows[-1]['receipt']['error']
result={'status':'passed','cases':rows,'model_calls':0,'original_sources_touched':False};(root/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
