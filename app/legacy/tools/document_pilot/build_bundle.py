"""Assemble portable, auditable document output; no parsing or production writes."""
from pathlib import Path,PurePosixPath
import collections,copy,hashlib,json,shutil,zipfile,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[2]/'artifacts/document-pilot'
DATA=ROOT.parent/'ocr-stage1/dataset'
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def case(name):return ROOT/'results'/name/PurePosixPath(load(ROOT/'results'/name/'latest.json')['directory']).name
def native_text(x):
 if isinstance(x,str):return x
 if isinstance(x,list):return '\n'.join(native_text(a)for a in x)
 return native_text(x.get('content',''))if isinstance(x,dict)else''
def assets(x):
 if isinstance(x,dict):
  for k,v in x.items():
   if k in ('image_source','image_path')and isinstance(v,str):yield v
   else:yield from assets(v)
 elif isinstance(x,list):
  for v in x:yield from assets(v)
def index(name):
 d=case(name);s=load(d/'document/structured_content.json');m=load(d/'document/middle_json.json');mp={p['page_idx']:p for p in m['pages']};old={b['locator']:b for b in load(d/'block-index.json')};result=[]
 for p in s['pages']:
  ns=mp[p['page_idx']].get('blocks',[]);assert len(ns)==len(p.get('blocks',[]))
  for n,b in zip(ns,p.get('blocks',[])):
   loc=f"{name}/pdf-page:{p['page_idx']+1}/block:{n['index']}";r=copy.deepcopy(old[loc]);r.update(bbox=b['bbox'],printed_page=r.get('printed_page'),evidence_kind=r.get('evidence_kind','machine_visual_description'if b.get('sub_type')=='natural_image'else'image_text_or_unresolved_visual'if b['type']=='image'else'source_text'))
   r['asset_urls']=[]
   for a in dict.fromkeys(assets(b)):
    q=d/'document'/a;assert q.is_file(),q;r['asset_urls'].append(q.relative_to(ROOT).as_posix())
   annotations=[]
   for child in n.get('content',[])if isinstance(n.get('content'),list)else[]:
    if isinstance(child,dict)and child.get('type')in('image_caption','table_caption','image_footnote','table_footnote'):
     annotations.append({'native_index':child.get('index'),'kind':child['type'],'bbox':child.get('bbox'),'text':native_text(child)})
   r['source_annotations']=annotations;result.append(r)
 assert len({b['locator']for b in result})==len(result)
 return result,s

def main():
 docs=[];corrections=load(ROOT/'curation.json');chapter,_=index('chapter10-advanced')
 for c in corrections['patches']:
  b=next(x for x in chapter if x['locator']==c['locator']);assert b['text']==c['old'];b.update(raw_text=b['text'],text=c['new'],curation_reason=c['reason'])
 loc='chapter10-advanced/pdf-page:6/block:15';b=next(x for x in chapter if x['locator']==loc)
 new='1. [A: Ever] since supermarkets first [B: appeared], they have been [C: take] over [D: the] world.\n2. [A: Supermarkets] have changed people’s life [B: styles], yet [C: and] at the same time, changes in people’s life [D: styles] have encouraged the opening of supermarkets.'
 corrections['patches'].append({'locator':loc,'old':b['text'],'new':new,'reason':'Source-verified underlined word/option mapping; bracket notation is an explicit transcription aid, not supplied answers','evidence_image':'review-pages/pdf-06-right.jpg'})
 b.update(raw_text=b['text'],text=new,curation_reason=corrections['patches'][-1]['reason'])
 save(ROOT/'curated/chapter/blocks.json',chapter);save(ROOT/'curated/corrections.json',corrections)
 docs.append({'id':'chapter','title':'Scanned chapter · 10 PDF spreads / printed 102–121','original':(case('chapter10-advanced')/'original.pdf').relative_to(ROOT).as_posix(),'pages':[{'page':i,'image':f'review-pages/pdf-{i:02}.jpg','blocks':[b for b in chapter if b['pdf_page_1based']==i]}for i in range(1,11)]})
 native,ns=index('guide317-native');vision,vs=index('guide317-image-pages');selected={p['page_idx']+1 for p in vs['pages']};assert len(selected)==16
 blank={x['pdf_page_1based']for x in load(case('guide317-native')/'empty-text-audit.json')if x['blank_with_no_native_text']}
 pages=[];combined=[]
 for i in range(1,318):
  blocks=[b for b in(vision if i in selected else native)if b['pdf_page_1based']==i];combined+=blocks
  has_text=any(b['text'].strip()and b['evidence_kind']=='source_text'for b in blocks)
  if i==16:
   for b in blocks:
    b.update(quality_warning='Complex rotated diagram: source says FIVE ESSENTIAL LEARNING EXPERIENCES; OCR includes NATIONAL LEARNING EXPERIENCES and loses visual hierarchy. Not accepted as authoritative structured teaching evidence.',evidence_kind='unverified_diagram_text')
  item={'page':i,'recipe':'advanced'if i in selected else'native','raster_blank_interior':i in blank,'has_source_text':has_text,'visual_review_required':i==16 or(not has_text and i not in blank and i not in (92,110,317)),'blocks':blocks}
  if i in (92,110):item['visual_classification']='Blank interior with marginal line artifacts; source-image reviewed';item['raster_blank_interior']=True
  if i==317:item['visual_classification']='Decorative back cover; no printed text; original image retained'
  image=ROOT/f'review-pages/guide-{i}.jpg'
  if image.exists():item['image']=image.relative_to(ROOT).as_posix()
  pages.append(item)
 assert {p['page']for p in pages}==set(range(1,318))
 save(ROOT/'curated/guide/blocks.json',combined);save(ROOT/'curated/guide/page-manifest.json',[{k:v for k,v in p.items()if k!='blocks'}for p in pages])
 docs.append({'id':'guide','title':'Curriculum guide · 317 PDF pages','original':(case('guide317-native')/'original.pdf').relative_to(ROOT).as_posix(),'pages':pages})
 for sample in ('sample18','sample16','sample21','sample23'):
  name='regression-'+sample;blocks,_=index(name)
  if sample=='sample21':
   b=next(b for b in blocks if b['block_index']==12);b.update(evidence_kind='unverified_diagram_reconstruction',quality_warning='Generated Role/Classification headers are not printed in the original; this table must not be treated as verbatim source.')
  if sample=='sample23':
   b=next(b for b in blocks if b['block_index']==4);new='1: n a j s e\n2: e s o h s\n3: c j t k e a'
   corrections['patches'].append({'locator':b['locator'],'old':b['text'],'new':new,'reason':'Recover source-image question-to-jumbled-letter mapping; do not solve the exercise','evidence_image':(case(name)/'original.png').relative_to(ROOT).as_posix()});b.update(raw_text=b['text'],text=new,curation_reason=corrections['patches'][-1]['reason'])
  if sample=='sample16':
   source=next(s for s in load(DATA/'sources.json')['sources']if s['id']=='src15');nsmap={'a':'http://schemas.openxmlformats.org/drawingml/2006/main','p':'http://schemas.openxmlformats.org/presentationml/2006/main'}
   with zipfile.ZipFile(source['path'])as z:tree=ET.fromstring(z.read('ppt/slides/slide23.xml'))
   labels=[''.join(t.text or''for t in sp.findall('.//a:t',nsmap))for sp in tree.findall('.//p:sp',nsmap)]
   save(ROOT/'curated/sample16/native-slide-text.json',{'source':source,'slide':23,'shape_text':labels,'not_a_visual_visibility_claim':True})
   blocks.append({'locator':'src15/slide:23/native-text','pdf_page_1based':1,'printed_page':None,'type':'native_supplement','evidence_kind':'source_native_text','bbox':None,'text':'\n'.join(labels),'source_annotations':[],'asset_urls':[]})
  save(ROOT/f'curated/{sample}/blocks.json',blocks)
  original=(case(name)/'original.png').relative_to(ROOT).as_posix();docs.append({'id':sample,'title':{'sample18':'MLAT · missing final line','sample16':'PPT · screenshots and native text','sample21':'Broken text layer · visual recovery','sample23':'Picture exercise · spatial relationships'}[sample],'original':original,'pages':[{'page':1,'image':original,'blocks':blocks}]})
 save(ROOT/'curated/corrections.json',corrections)
 for d in docs:
  lines=[]
  for p in d['pages']:
   lines.append(f"\n# PDF / image page {p['page']}\n")
   for b in p['blocks']:
    lines.append(f"\n[{b['locator']}] ({b['evidence_kind']})\n\n{b['text']}\n")
    for a in b['source_annotations']:lines.append(f"Printed {a['kind']}: {a['text']}\n")
    for a in b['asset_urls']:lines.append(f"![Original crop](../../{a})\n")
  dest=ROOT/'curated'/d['id']/'document.md';dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text('\n'.join(lines),encoding='utf-8')
 # Keep the earlier actual model input/response evidence unchanged.
 qa=load(ROOT/'evidence/reader-verification.json');assert qa['status']=='citation_checks_passed'
 verification={'documents':len(docs),'chapter_pdf_pages':len(docs[0]['pages']),'chapter_printed_pages':sorted({int(b['printed_page'])for b in chapter if b['printed_page']}),'guide_pages':len(pages),'guide_advanced_pages':sorted(selected),'raster_blank_pages':sorted(blank),'guide_known_flagged_visual_pages':[p['page']for p in pages if p['visual_review_required']],'guide_additional_visual_blank_pages':[92,110],'guide_decorative_no_text_pages':[317],'curation_patches':len(corrections['patches']),'recovered_image_captions':sum(len(b['source_annotations'])for d in docs for p in d['pages']for b in p['blocks']),'model_questions':len(qa['answers']),'model_citations':sum(len(a['citations'])for a in qa['answers']),'model_citations_exact':all(c['exact_source_match']for a in qa['answers']for c in a['citations']),'model_semantic_review':'Four answers checked against source; MELAB answer describes level bands, not individual plus/minus score assignment','all_317_pages_semantically_verified':False,'zero_error_certified':False,'production_deployed':False,'raw_outputs_preserved':True}
 assert verification['chapter_printed_pages']==list(range(102,122))
 save(ROOT/'curated/verification.json',verification)
 template=(Path(__file__).with_name('viewer.html')).read_text(encoding='utf-8');payload=json.dumps({'documents':docs,'verification':verification},ensure_ascii=False).replace('<','\\u003c')
 (ROOT/'review.html').write_text(template.replace('__DOCUMENT_DATA__',payload),encoding='utf-8')
 print(json.dumps(verification,ensure_ascii=False))

if __name__=='__main__':main()
