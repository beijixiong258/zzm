"""Compile measured dataset metadata, final visual index and baseline summary."""
from pathlib import Path
import collections,json,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.ocr_stage1 import budget
from tools.ocr_stage1.prepare_samples import OUT,dump,absolute,sha

def finalize():
    import pymupdf
    from PIL import Image,ImageDraw,ImageFont
    budget.check()
    inv=json.loads((OUT/'inventory.json').read_text(encoding='utf-8'))
    exports=json.loads((OUT/'office_exports.json').read_text(encoding='utf-8'))['exports'];last={e['source_id']:e for e in exports}
    for source in inv['sources']:
        budget.check()
        export=last.get(source['id'])
        if not export:continue
        source['office_render_status']=export['status'];source['office_attempt_count']=sum(e['source_id']==source['id'] for e in exports)
        if export['status']=='ok':
            source['rendered_pdf_path']=export['pdf_path'];source['rendered_page_count']=export['page_count'];source['rendered_pages']=[]
            with pymupdf.open(export['pdf_path']) as doc:
                for n,page in enumerate(doc,1):
                    budget.check();text=page.get_text(sort=True);images=page.get_image_info()
                    source['rendered_pages'].append({'page_1based':n,'text_chars':len(text),'image_occurrences':len(images),'width_points':page.rect.width,'height_points':page.rect.height,'native_text_path':absolute(OUT/'native'/source['id']/f'rendered_page_{n:04d}.txt')})
            source['office_render_note']='Independent local Office COM export: macros disabled; opened read-only; original never saved. Existing Office instance safety gate. Slide PDF excludes notes; original slide/notes native text saved separately.'
    dump(OUT/'inventory.json',inv)
    manifest=json.loads((OUT/'samples.json').read_text(encoding='utf-8'));samples=manifest['samples'];assert manifest['count']==24 and len(samples)==24
    ids=[s['id'] for s in samples];assert len(set(ids))==24
    assert {s['source_id'] for s in samples}=={s['id'] for s in inv['sources']}
    checks=[]
    for s in samples:
        budget.check()
        with Image.open(s['image_path']) as im:
            checks.append({'id':s['id'],'width':im.width,'height':im.height,'pixels':im.width*im.height,'long_edge':max(im.width,im.height),'sha256_matches':sha(Path(s['image_path']))==s['image_sha256'],'within_4MP':im.width*im.height<=4000000,'native_reference_exists':s['native_text_path'] is None or Path(s['native_text_path']).is_file()})
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',17)
    for start in (0,12):
        budget.check();sheet=Image.new('RGB',(1800,1950),'#ddd');draw=ImageDraw.Draw(sheet)
        for k,s in enumerate(samples[start:start+12]):
            with Image.open(s['image_path']) as im:
                im.thumbnail((430,610));x=(k%4)*450;y=(k//4)*650;sheet.paste(im,(x+(450-im.width)//2,y+32));draw.text((x+8,y+7),f"{s['id']} {s['source_id']} p{s['page_1based']}",font=font,fill='black')
        target=OUT/'contacts'/f'selected_{start//12+1:02d}.jpg';sheet.save(target,quality=91)
    summary={'source_count':len(inv['sources']),'source_type_counts':dict(collections.Counter(s['type'] for s in inv['sources'])),'pdf_page_count':sum(s.get('page_count',0) for s in inv['sources']),'source_session_counts':dict(collections.Counter(s['session'] for s in inv['sources'])),'sample_count':len(samples),'unique_sample_source_count':len({s['source_id'] for s in samples}),'sample_session_counts':dict(collections.Counter(next(src['session'] for src in inv['sources'] if src['id']==s['source_id']) for s in samples)),'unit_kind_counts':dict(collections.Counter(s['unit_kind'] for s in samples)),'reference_kind_counts':dict(collections.Counter(s['reference_kind'] for s in samples)),'category_counts':dict(collections.Counter(s['category'] for s in samples)),'office_successful_sources':sum(e['status']=='ok' for e in last.values()),'office_failed_attempts_retained':sum(e['status']!='ok' for e in exports),'image_checks':checks,'all_images_verified':all(c['within_4MP'] and c['sha256_matches'] and c['native_reference_exists'] and 1800<=c['long_edge']<=2201 for c in checks),'visual_review_note':'Contact-sheet and exact-gutter inspection were AI review, not human reference transcription or accuracy evaluation. No OCR used as gold.'}
    dump(OUT/'dataset-summary.json',summary);print(json.dumps({k:v for k,v in summary.items() if k not in {'image_checks','category_counts'}},ensure_ascii=False,indent=2))

if __name__=='__main__':finalize()
