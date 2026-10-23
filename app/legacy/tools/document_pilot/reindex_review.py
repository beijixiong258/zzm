"""Rebuild locators from native MiddleJson IDs and materialize review pages."""
from pathlib import Path
import json,pymupdf as fitz
BASE=Path('/home/adminz/llm/ocr-stage1-20261009');ROOT=BASE/'whole-document-pilot'

def text(block):
    v=block.get('content','')
    if isinstance(v,str):return v
    if isinstance(v,list):return '\n'.join(x if isinstance(x,str)else str(x.get('content',''))for x in v)
    return str(v)if v else ''

report=[]
for latest in sorted((ROOT/'results').glob('*/latest.json')):
    out=Path(json.loads(latest.read_text())['directory']);name=out.parent.name
    s=json.loads((out/'document/structured_content.json').read_text());m=json.loads((out/'document/middle_json.json').read_text());mp={p['page_idx']:p for p in m['pages']}
    index=[]
    for pg in s['pages']:
        native=mp[pg['page_idx']].get('blocks',[]);assert len(native)==len(pg['blocks'])
        nums=[b for b in pg['blocks']if b['type']=='page_number']
        for ordinal,b in enumerate(pg['blocks']):
            n=native[ordinal]['index'];assert native[ordinal]['type']==b['type']
            role='source_text'
            if b['type']=='image':role='machine_visual_description'if b.get('sub_type')=='natural_image'else'image_text_or_unresolved_visual'
            print_page=None
            if name=='chapter10-advanced'and len(nums)==2:
                center=(b['bbox'][0]+b['bbox'][2])/2
                print_page=min(nums,key=lambda q:abs((q['bbox'][0]+q['bbox'][2])/2-center))['content']
            index.append({'locator':f"{name}/pdf-page:{pg['page_idx']+1}/block:{n}",'pdf_page_1based':pg['page_idx']+1,'printed_page':print_page,'block_index':n,'type':b['type'],'sub_type':b.get('sub_type'),'evidence_kind':role,'bbox':b.get('bbox'),'text':text(b),'block':b})
    assert len({x['locator']for x in index})==len(index)
    (out/'block-index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n')
    report.append({'name':name,'blocks':len(index),'locators_unique':True,'image_descriptions_separate':True})

source=BASE/'data/dataset/sources/src14.pdf';doc=fitz.open(source);dest=ROOT/'review-pages';dest.mkdir(exist_ok=True);pages=[]
for n,page in enumerate(doc,1):
    full=dest/f'pdf-{n:02}.jpg'
    if not full.exists():page.get_pixmap(matrix=fitz.Matrix(3,3),alpha=False).save(full,jpg_quality=92)
    for side,clip in [('left',fitz.Rect(0,0,page.rect.width*.56,page.rect.height)),('right',fitz.Rect(page.rect.width*.48,0,page.rect.width,page.rect.height))]:
        image=dest/f'pdf-{n:02}-{side}.jpg'
        if not image.exists():page.get_pixmap(matrix=fitz.Matrix(3,3),clip=clip,alpha=False).save(image,jpg_quality=92)
        pages.append({'pdf_page_1based':n,'side':side,'image':str(image),'clip_points':list(clip),'review_only_overlap':True})
(ROOT/'evidence/reindex-and-review.json').write_text(json.dumps({'indexes':report,'review_windows':pages},indent=2)+'\n');print(json.dumps({'indexes':report,'review_windows':len(pages)}))
