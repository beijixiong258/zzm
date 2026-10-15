"""Read-only real PDF/native/OCR inspection; writes only this lane's evidence."""
import collections, hashlib, json, shutil, sys, unicodedata
from pathlib import Path
import pymupdf as fitz
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'artifacts/stage14/native-text-recovery'
SOURCE=Path('D:/中转站/Z/Session 2/Program level curriculum Examples-20261006/Macau ELE Curriculum Guide English1_guide_e.pdf')
SUBSET=ROOT/'artifacts/stage14/r6-final-inputs/src03-pages126-127.pdf'
RETAINED=ROOT/'artifacts/stage14/r6-final-inputs/readback/mask-bundle'
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(name,value):
 p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 snapshots={}
 for name in ('tools/document_stage12/parser_worker.py','tools/document_stage12/parser_helpers.py','tools/material_stage13/ocr_verification.py'):
  src=ROOT/name;dest=OUT/'before-code'/src.name
  if not dest.exists():dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
  snapshots[name]=digest(dest)
 m=json.loads((RETAINED/'manifest.json').read_text(encoding='utf-8'))
 doc=fitz.open(SOURCE);sub=fitz.open(SUBSET)
 result={'original_sha256':digest(SOURCE),'subset_sha256':digest(SUBSET),'before_code_sha256':snapshots,
         'retained_manifest_sha256':digest(RETAINED/'manifest.json'),'pages':[],'pymupdf':fitz.VersionBind}
 for n,physical in enumerate((126,127),1):
  p=doc[physical-1];raw=p.get_text('rawdict',sort=True);d=p.get_text('dict',sort=True)
  pix=p.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False);sp=sub[n-1].get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
  pix.save(OUT/f'original-p{physical}.png')
  assert (pix.width,pix.height,pix.samples)==(sp.width,sp.height,sp.samples)
  font_records=[]
  for font in p.get_fonts(full=True):
   xref=font[0];font_bytes=doc.extract_font(xref)[3]
   font_digest=hashlib.sha256(font_bytes).hexdigest()if font_bytes else None
   asset=None
   if font_bytes:
    asset=f'source-fonts/{font_digest}.{font[1]}';(OUT/'source-fonts').mkdir(exist_ok=True);(OUT/asset).write_bytes(font_bytes)
   kind,value=doc.xref_get_key(xref,'ToUnicode');cmap=None
   if kind=='xref':
    cmap_xref=int(value.split()[0]);cmap_bytes=doc.xref_stream(cmap_xref)
    cmap_digest=hashlib.sha256(cmap_bytes).hexdigest();cmap_asset=f'source-fonts/{cmap_digest}.cmap'
    (OUT/cmap_asset).write_bytes(cmap_bytes)
    cmap={'xref':cmap_xref,'sha256':cmap_digest,'asset':cmap_asset,'bytes':len(cmap_bytes)}
   font_records.append({'resource':list(font),'dictionary':doc.xref_object(xref),'font_sha256':font_digest,
                        'font_asset':asset,'font_embedded':bool(font_bytes),'to_unicode':cmap})
  blocks=[]
  for i,b in enumerate(d['blocks']):
   if b['type']!=0:continue
   chars=[];spans=[];offset=0
   for li,(line,rl) in enumerate(zip(b['lines'],raw['blocks'][i]['lines'])):
    if li:offset+=1
    for si,(span,rs) in enumerate(zip(line['spans'],rl['spans'])):
     spans.append({k:v for k,v in span.items()if k!='text'}|{'text':span['text'],'line':li,'span':si,'text_range':[offset,offset+len(span['text'])]})
     for ch in rs['chars']:
      chars.append(ch|{'text_offset':offset,'line':li,'span':si,'font':span['font'],'unicode_category':unicodedata.category(ch['c'])});offset+=1
   text='\n'.join(''.join(s['text']for s in l['spans'])for l in b['lines'])
   suspicious=[ch for ch in chars if ch['c']=='\ufffd'or ch['unicode_category']in ('Co','Cn')]
   blocks.append({'index':i,'text':text,'bbox_points':b['bbox'],'spans':spans,'characters':chars,'suspicious_characters':suspicious})
  checks=json.loads((RETAINED/f'raw/p{n:04}-text-verification.json').read_text(encoding='utf-8'))
  manifest_blocks=m['pages'][n-1]['blocks']
  result['pages'].append({'subset_page':n,'original_physical_page':physical,'pixel_sha256':hashlib.sha256(pix.samples).hexdigest(),
   'subset_pixels_exact':True,'fonts':font_records,'blocks':blocks,
   'retained_quality_counts':dict(collections.Counter(b['quality']for b in manifest_blocks)),
   'retained_issue_counts':dict(collections.Counter(issue for b in manifest_blocks for issue in b['issues'])),
   'retained_checks':checks})
 save('source-inspection.json',result)
 print(json.dumps({k:v for k,v in result.items()if k!='pages'},ensure_ascii=False))
 for page in result['pages']:
  print('PAGE',page['original_physical_page'],'native_text_blocks',len(page['blocks']),'quality',page['retained_quality_counts'])
  for b in page['blocks']:
   bad=b['suspicious_characters'];check=next((c for c in page['retained_checks']['checks']if c['block_id']==f'p{page["subset_page"]}-b{b["index"]}'),None)
   if bad or (check and not check['verification']['exact_nonwhitespace_agreement']):
    print(json.dumps({'id':f'p{page["subset_page"]}-b{b["index"]}','text':b['text'],'bad':[{'c':c['c'],'font':c['font'],'bbox':c['bbox']}for c in bad],
       'cpu_texts':[l['text']for l in check['verification']['cpu_lines']]if check else [],'reasons':check['verification']['reasons']if check else []},ensure_ascii=False))
if __name__=='__main__':main()
