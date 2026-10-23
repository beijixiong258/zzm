"""Read-only source inventory and controlled visual sampling (phase 1)."""
from pathlib import Path
import argparse, hashlib, json, math, os, subprocess, sys, time, zipfile
from xml.etree import ElementTree as ET
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.ocr_stage1 import budget
OUT = ROOT / 'artifacts/ocr-stage1/dataset'
SOURCES = [Path('D:/中转站/Z/Session 2'), Path('D:/中转站/Z/Session 4')]

def gate():
    budget.check()

def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''): h.update(chunk)
    return h.hexdigest()

def absolute(path): return str(path.resolve()).replace('\\', '/')

def inventory():
    import fitz
    from docx import Document
    from pptx import Presentation
    from backend.aicademiya.material_extraction import _word_text, _slide_text, _Extraction
    gate()
    files = sorted([p for root in SOURCES for p in root.rglob('*') if p.is_file()], key=lambda p:str(p))
    assert len(files) == 23, len(files)
    inv = {'count':len(files), 'read_only_sources':True, 'max_input_bytes':25*1024*1024, 'sources':[]}
    for n, path in enumerate(files, 1):
        gate()
        sid = f'src{n:02d}'
        item = {'id':sid,'path':absolute(path),'bytes':path.stat().st_size,'sha256':sha(path),'type':path.suffix.lower().lstrip('.'), 'session':path.relative_to(Path('D:/中转站/Z')).parts[0], 'input_gate': 'blocked_unsupported' if path.suffix.lower()=='.doc' else 'blocked_oversize' if path.stat().st_size>25*1024*1024 else 'accepted'}
        native = OUT / 'native' / sid
        native.mkdir(parents=True,exist_ok=True)
        try:
            if path.suffix.lower()=='.pdf':
                with fitz.open(path) as doc:
                    item.update(page_count=len(doc), encrypted=doc.needs_pass, pages=[])
                    for i,page in enumerate(doc):
                        if i%10==0: gate()
                        text = page.get_text(sort=True)
                        target = native / f'page_{i+1:04d}.txt'
                        target.write_text(text,encoding='utf-8')
                        images = page.get_image_info()
                        area = max(1,page.rect.get_area())
                        item['pages'].append({'page_1based':i+1,'text_chars':len(text),'nonspace_chars':len(''.join(text.split())), 'image_occurrences':len(images),'image_pixels_total':sum(x['width']*x['height'] for x in images), 'largest_image_area_fraction':max([((fitz.Rect(x['bbox']) & page.rect).get_area()/area) for x in images] or [0]),'width_points':page.rect.width,'height_points':page.rect.height,'native_text_path':absolute(target)})
            elif path.suffix.lower()=='.pptx':
                pres = Presentation(path)
                item.update(slide_count=len(pres.slides),slide_width_emu=pres.slide_width,slide_height_emu=pres.slide_height,slides=[])
                for i,slide in enumerate(pres.slides):
                    if i%10==0: gate()
                    text='\n'.join(_slide_text(slide.shapes,_Extraction()))
                    notes = slide.notes_slide.notes_text_frame.text if slide.has_notes_slide and slide.notes_slide.notes_text_frame else ''
                    target=native/f'slide_{i+1:04d}.txt'; target.write_text(text,encoding='utf-8')
                    nt=native/f'notes_{i+1:04d}.txt';nt.write_text(notes,encoding='utf-8')
                    item['slides'].append({'page_1based':i+1,'text_chars':len(text),'notes_chars':len(notes),'shape_count':len(slide.shapes),'image_references':len(slide._element.xpath('.//a:blip')),'native_text_path':absolute(target),'notes_text_path':absolute(nt)})
                item['notes_slides_nonempty']=sum(s['notes_chars']>0 for s in item['slides'])
            elif path.suffix.lower()=='.docx':
                doc=Document(path)
                text='\n'.join(_word_text(doc.element.body)); target=native/'body.txt';target.write_text(text,encoding='utf-8')
                with zipfile.ZipFile(path) as z:
                    item.update(paragraph_count=len(doc.paragraphs),table_count=len(doc.tables),section_count=len(doc.sections),text_chars=len(text),media_parts=sum(s.startswith('word/media/') for s in z.namelist()),native_text_path=absolute(target), pagination='requires_Office_rendering')
            else:
                item.update(native_text_path=None,legacy_doc=True,pagination='requires_Office_rendering',note='Legacy binary DOC is not supported by current platform; not an OCR failure.')
        except Exception as exc:
            item.update(inventory_error_type=type(exc).__name__,inventory_error=str(exc))
        inv['sources'].append(item);dump(OUT/'inventory.json',inv)
        print(sid,item['type'],item.get('page_count',item.get('slide_count','Office')),item['input_gate'],flush=True)
    return inv

def office():
    gate()
    inv=json.loads((OUT/'inventory.json').read_text(encoding='utf-8'))
    manifest=json.loads((OUT/'office_exports.json').read_text(encoding='utf-8'))['exports'] if (OUT/'office_exports.json').is_file() else []
    for item in inv['sources']:
        if item['type'] not in {'pptx','docx','doc'}:continue
        gate()
        dest=OUT/'office'/f"{item['id']}.pdf";dest.parent.mkdir(parents=True,exist_ok=True)
        cmd=['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(ROOT/'tools/ocr_stage1/sample_office_export.ps1'),'-Source',item['path'],'-Destination',absolute(dest)]
        started=time.perf_counter()
        try:
            p=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
            row={'source_id':item['id'],'source_path':item['path'],'pdf_path':absolute(dest) if dest.is_file() else None,'status':'ok' if p.returncode==0 and dest.is_file() else 'failed','stdout':p.stdout,'stderr':p.stderr,'returncode':p.returncode,'elapsed_seconds':time.perf_counter()-started}
        except subprocess.TimeoutExpired as exc:
            # The export script refuses pre-existing Office instances. Kill only
            # the instance it identified as owned, not any user Office process.
            pidfile=Path(str(dest)+'.owned-pid.json')
            cleanup=None
            if pidfile.is_file():
                pid=json.loads(pidfile.read_text(encoding='utf-8'))['pid']
                cleanup=subprocess.run(['taskkill.exe','/PID',str(pid),'/T','/F'],capture_output=True,text=True).stdout
            row={'source_id':item['id'],'source_path':item['path'],'pdf_path':None,'status':'timeout','elapsed_seconds':time.perf_counter()-started,'stdout':str(exc.stdout),'stderr':str(exc.stderr),'owned_cleanup':cleanup,'note':'Timed-out export retained; exact owned Office PID cleanup attempted.'}
        manifest.append(row);dump(OUT/'office_exports.json',{'exports':manifest})
        if row['status']=='ok':
            import fitz
            with fitz.open(dest) as doc:
                row['page_count']=len(doc)
                for i,page in enumerate(doc):
                    if i%10==0:gate()
                    target=OUT/'native'/item['id']/f'rendered_page_{i+1:04d}.txt';target.write_text(page.get_text(sort=True),encoding='utf-8')
            dump(OUT/'office_exports.json',{'exports':manifest})
        print(item['id'],row['status'],row.get('page_count'),row['stdout'][-500:],row['stderr'][-300:],flush=True)

def candidates():
    import fitz
    from PIL import Image, ImageDraw, ImageFont
    gate();inv=json.loads((OUT/'inventory.json').read_text(encoding='utf-8'))
    exports=json.loads((OUT/'office_exports.json').read_text(encoding='utf-8'))['exports'] if (OUT/'office_exports.json').is_file() else []
    lookup={e['source_id']:e for e in exports if e['status']=='ok'}
    entries=[]
    for item in inv['sources']:
        gate()
        if item['type']=='pdf': path=item['path'];count=item['page_count']
        elif item['id'] in lookup: path=lookup[item['id']]['pdf_path'];count=lookup[item['id']]['page_count']
        else:continue
        # Metadata-guided distribution: front, middle, late plus table/image clues.
        choices={min(count,2),max(1,round(count*.25)),max(1,round(count*.55)),max(1,round(count*.85)),count}
        if item['type']=='pdf':
            pages=item['pages']
            choices.add(max(pages,key=lambda p:p['image_occurrences'])['page_1based'])
            choices.add(max(pages,key=lambda p:p['nonspace_chars'])['page_1based'])
        with fitz.open(path) as doc:
            for number in sorted(choices):
                gate()
                page=doc[number-1];scale=620/max(page.rect.width,page.rect.height)
                pix=page.get_pixmap(matrix=fitz.Matrix(scale,scale),alpha=False,colorspace=fitz.csRGB)
                dest=OUT/'candidates'/f"{item['id']}_p{number:04d}.png";dest.parent.mkdir(parents=True,exist_ok=True);pix.save(dest)
                entries.append({'source_id':item['id'],'page_1based':number,'image_path':absolute(dest),'render_source':path,'source_type':item['type']})
    dump(OUT/'candidates.json',{'candidates':entries,'count':len(entries)})
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',17)
    # Compact per-session sheets, 12 pages per sheet.
    for start in range(0,len(entries),12):
        gate();batch=entries[start:start+12];sheet=Image.new('RGB',(4*450,3*650),'#ddd');draw=ImageDraw.Draw(sheet)
        for k,e in enumerate(batch):
            im=Image.open(e['image_path']);im.thumbnail((430,610));x=(k%4)*450;y=(k//4)*650
            sheet.paste(im,(x+(450-im.width)//2,y+32));draw.text((x+8,y+7),f"{e['source_id']} p{e['page_1based']} ({e['source_type']})",font=font,fill='black')
        dest=OUT/'contacts'/f'candidates_{start//12+1:02d}.jpg';dest.parent.mkdir(parents=True,exist_ok=True);sheet.save(dest,quality=90)
        print(absolute(dest),flush=True)

def render():
    import fitz
    gate();inv=json.loads((OUT/'inventory.json').read_text(encoding='utf-8'));lookup={s['id']:s for s in inv['sources']}
    exports=json.loads((OUT/'office_exports.json').read_text(encoding='utf-8'))['exports']; exp={e['source_id']:e for e in exports if e['status']=='ok'}
    selections=json.loads((OUT/'selection_plan.json').read_text(encoding='utf-8'))['selections'];assert len(selections)==24
    samples=[]
    for n,sel in enumerate(selections,1):
        gate();source=lookup[sel['source_id']];num=sel['page_1based'];path=source['path'] if source['type']=='pdf' else exp[source['id']]['pdf_path']
        with fitz.open(path) as doc:
            page=doc[num-1];clip=fitz.Rect(sel['crop_points']) if sel.get('crop_points') else page.rect
            scale=min(2200/max(clip.width,clip.height),math.sqrt(3950000/clip.get_area()))
            pix=page.get_pixmap(matrix=fitz.Matrix(scale,scale),clip=clip,alpha=False,colorspace=fitz.csRGB)
            assert pix.width*pix.height<=4000000
            sid=f'sample{n:02d}';target=OUT/'images'/f'{sid}.png';target.parent.mkdir(parents=True,exist_ok=True);pix.save(target)
            nativepath=OUT/'native'/source['id']/(f'page_{num:04d}.txt' if source['type']=='pdf' else f'rendered_page_{num:04d}.txt')
            text=page.get_text(sort=True,clip=clip)
            if sel.get('crop_points'):
                nativepath=OUT/'native'/source['id']/f'crop_{sid}.txt';nativepath.write_text(text,encoding='utf-8')
            reliable=bool(text.strip()) and len(''.join(text.split()))>=40
            row={'id':sid,'image_path':absolute(target),'source_path':source['path'],'source_id':source['id'],'page_1based':num,'unit_kind':'pdf_page' if source['type']=='pdf' else 'ppt_slide' if source['type']=='pptx' else 'doc_page','category':sel['category'],'selection_reason':sel['selection_reason'],'native_text_path':absolute(nativepath) if reliable else None,'reference_kind':'native_pdf_text' if reliable and source['type']=='pdf' else 'native_Office_export_pdf_text' if reliable else 'none','render_source_path':absolute(Path(path)),'render':{'renderer':'PyMuPDF','long_edge_target':2200,'pixel_limit':4000000,'actual_width':pix.width,'actual_height':pix.height,'scale':scale,'crop_points':list(clip),'original_page_points':list(page.rect),'colorspace':'RGB','alpha':False},'image_sha256':sha(target),'visual_review':'AI review of contact sheets, not human ground truth'}
            samples.append(row);dump(OUT/'samples.json',{'samples':samples,'count':len(samples),'target_count':24,'reference_note':'Original native text only; no OCR-as-gold. Native text may itself have ordering/encoding defects.'})
            print(sid,source['id'],num,pix.width,pix.height,flush=True)

def verify():
    gate();inv=json.loads((OUT/'inventory.json').read_text(encoding='utf-8'));rows=[]
    for source in inv['sources']:
        gate();p=Path(source['path']);actual=sha(p);rows.append({'source_id':source['id'],'path':source['path'],'expected_sha256':source['sha256'],'actual_sha256':actual,'bytes':p.stat().st_size,'unchanged':actual==source['sha256'] and p.stat().st_size==source['bytes']})
    dump(OUT/'source_hash_verification.json',{'count':len(rows),'all_unchanged':all(r['unchanged'] for r in rows),'sources':rows});print('ALL_UNCHANGED',all(r['unchanged'] for r in rows))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['inventory','office','candidates','render','verify']);args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True);globals()[args.action]()
