"""Read-only real PDF object/pixel/renderer investigation; CPU only."""
import argparse, hashlib, io, json, sys
from pathlib import Path
import pymupdf as fitz
from PIL import Image

APP = Path(__file__).resolve().parents[3]
SOURCE = Path('D:/中转站/Z/Session 2/Program level curriculum Examples-20261006/Macau ELE Curriculum Guide English1_guide_e.pdf')
EXPECTED = 'c9406dc6f68ddbefeb9e8680691e09557baf62b428e43f6bd40c5c06da8430c1'
def sha(data): return hashlib.sha256(data).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,default=SOURCE);ap.add_argument('--out',type=Path,default=APP/'artifacts/stage14/mask-recovery/investigation');a=ap.parse_args()
    before=sha(a.source.read_bytes());assert before==EXPECTED
    a.out.mkdir(parents=True,exist_ok=True)
    result={'source_path':str(a.source),'source_sha256':before,'pymupdf':fitz.__doc__,'pages':[],'gpu_calls':0}
    with fitz.open(a.source) as doc:
        for number in (126,127):
            page=doc[number-1];images=page.get_images(full=True)
            data={'page':number,'xref':page.xref,'images':images,'page_object':doc.xref_object(page.xref),'objects':{},'occurrences':[]}
            for xref,mask,*_ in images:
                for ref in (xref,mask):
                    if not ref:continue
                    obj=doc.xref_object(ref);stream=doc.xref_stream(ref);raw=doc.xref_stream_raw(ref)
                    data['objects'][str(ref)]={'dictionary':obj,'stream_length':len(stream),'stream_sha256':sha(stream),'raw_stream_sha256':sha(raw)}
                    (a.out/f'object-{ref}.txt').write_text(obj,encoding='utf-8')
            for ref in page.get_contents():
                stream=doc.xref_stream(ref);(a.out/f'p{number}-content-{ref}.bin').write_bytes(stream)
            for index,b in enumerate(page.get_text('dict',sort=True)['blocks']):
                if b['type']!=1:continue
                im=Image.open(io.BytesIO(b['image']));mask=Image.open(io.BytesIO(b['mask'])) if b.get('mask') else None
                row={'id':f'p{number}-b{index}','number':b['number'],'bbox':b['bbox'],'transform':b['transform'],'image_size':im.size,'image_mode':im.mode,'image_extrema':im.getextrema(),'image_sha256':sha(b['image']),'mask_size':mask.size if mask else None,'mask_extrema':mask.getextrema() if mask else None,'mask_sha256':sha(b['mask']) if mask else None}
                (a.out/'original-image.png').write_bytes(b['image']);(a.out/'original-mask.png').write_bytes(b['mask'])
                rect=fitz.Rect(b['bbox']);pix=page.get_pixmap(matrix=fitz.Matrix(8,8),clip=rect,alpha=False);pix.save(a.out/f'{row["id"]}-page-clip.png')
                texts=[]
                for t in page.get_text('dict')['blocks']:
                    if t['type']==0 and fitz.Rect(t['bbox']).intersects(rect):
                        texts.append({'bbox':t['bbox'],'text':'\n'.join(''.join(s['text'] for s in l['spans']) for l in t['lines'])})
                row['native_text_overlaps']=texts;data['occurrences'].append(row)
            result['pages'].append(data)
    result['source_sha256_after']=sha(a.source.read_bytes());assert result['source_sha256_after']==before
    (a.out/'objects-and-pixels.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
