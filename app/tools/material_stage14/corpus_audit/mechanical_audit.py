"""全量CPU机械清点；原件只读、不运行解析器、不触发GPU/模型/服务。"""
import os
os.environ.update(CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',PYTHONDONTWRITEBYTECODE='1')
import hashlib,json,io,collections,re,zipfile,xml.etree.ElementTree as ET,math,platform
from pathlib import Path
import pymupdf as fitz
from PIL import Image,ImageStat
R=Path('/home/adminz/llm/ocr-stage1-20261009');O=R/'stage14-corpus-audit'
B=R/'stage13-parser/native-v2/bundles'
for name in ['assets','pages']: (O/name).mkdir(parents=True,exist_ok=True)
def digest(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def h(data):return hashlib.sha256(data).hexdigest()
def dump(name,d): (O/name).write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
def emit(f,d):f.write(json.dumps(d,ensure_ascii=False)+'\n')
def pixel_sha(im):return h(im.convert('RGB').tobytes()+str(im.size).encode())
def lname(tag):return tag.rsplit('}',1)[-1]
def meaningful(text):return bool(text.strip()) and not text.strip().isdigit()
inputs=json.loads((O/'inputs.json').read_text());sources=[];groups={};decode_cache={};errors=[];aux=[]
pages=[];occurrences=[];native_suspects=[];native_count=0;native_text_chars=0
pf=(O/'pages.jsonl').open('w',encoding='utf-8');of=(O/'occurrences.jsonl').open('w',encoding='utf-8');nf=(O/'native-suspects.jsonl').open('w',encoding='utf-8')
for s in inputs['sources']:
    sid=s['id'];fmt=s['type'];original=R/'data/dataset/sources'/f'{sid}.{fmt}'
    before=digest(original);assert before==s['sha256'],sid
    manifest_path=B/sid/'manifest.json';m=json.loads(manifest_path.read_text());assert m['source_sha256']==before
    pdf=original if fmt=='pdf' else B/sid/m['preview_pdf']
    pdf_sha=digest(pdf)
    if fmt!='pdf':assert pdf_sha==m['coverage']['rendered_pdf_sha256']
    row={**s,'remote_original_path':str(original),'remote_sha256_before':before,'remote_bytes':original.stat().st_size,
         'pdf_audit_path':str(pdf),'pdf_sha256':pdf_sha,'page_count_kind':'原始PDF物理页' if fmt=='pdf' else '历史LibreOffice预览PDF物理页（Office本身不固定分页）',
         'native_manifest_sha256':digest(manifest_path),'historical_parser':m['parser'],'semantic_approved':False}
    start_page=len(pages);start_occ=len(occurrences);source_native=0;source_chars=0;source_mask=0;source_vectors=0
    with fitz.open(pdf) as doc:
        row['actual_page_count']=len(doc);assert len(doc)==m['page_count']
        for pi,page in enumerate(doc):
            number=pi+1;blocks=page.get_text('dict',sort=True)['blocks'];textblocks=[b for b in blocks if b['type']==0];imageblocks=[(bi,b) for bi,b in enumerate(blocks) if b['type']==1]
            text='\n'.join('\n'.join(''.join(span['text'] for span in line['spans']) for line in b['lines']) for b in textblocks)
            bad_count=text.count('\ufffd');private=sum(0xE000<=ord(c)<=0xF8FF for c in text);controls=sum(ord(c)<32 and c not in '\n\r\t' for c in text)
            native_ids=[];source_native+=len(blocks);native_count+=len(blocks)
            # Stage13 character convention trims each text block and counts no join separators.
            chars=sum(len('\n'.join(''.join(sp['text'] for sp in ln['spans']) for ln in b['lines']).strip()) for b in textblocks)
            source_chars+=chars;native_text_chars+=chars
            for bi,b in enumerate(blocks):
                if b['type']!=0:continue
                bt='\n'.join(''.join(sp['text'] for sp in ln['spans']) for ln in b['lines']).strip()
                bbox=list(b['bbox']);out=not all(math.isfinite(v) for v in bbox) or bbox[0]<0 or bbox[1]<0 or bbox[2]>page.rect.width+.01 or bbox[3]>page.rect.height+.01
                f={'replacement_characters':bt.count('\ufffd'),'private_use_characters':sum(0xE000<=ord(c)<=0xF8FF for c in bt),'invalid_control_characters':sum(ord(c)<32 and c not in '\n\r\t' for c in bt),'bbox_out_of_page':out}
                if any(f.values()):
                    nr={'source_id':sid,'source_sha256':before,'page':number,'block_id':f'p{number}-b{bi}','bbox_points':bbox,'text_sha256':h(bt.encode()),'exact_native_text':bt,'flags':f,'判断':'仅为乱码/定位风险信号；不自动修正文或判失败'}
                    native_suspects.append(nr);emit(nf,nr);native_ids.append(nr['block_id'])
            drawings=page.get_drawings();axis_lines=0;rectangles=0
            for d in drawings:
                for item in d['items']:
                    if item[0]=='re':rectangles+=1
                    if item[0]=='l' and (abs(item[1].x-item[2].x)<1 or abs(item[1].y-item[2].y)<1):axis_lines+=1
            structural=axis_lines>=12 or rectangles>=8
            source_vectors+=structural
            page_occs=[]
            try: image_info_count=len(page.get_image_info())
            except Exception:image_info_count=None
            for bi,b in imageblocks:
                raw=b['image'];mask=b.get('mask');rh=h(raw);mh=h(mask) if mask else None;key=(rh,mh)
                if key not in decode_cache:
                    try:
                        with Image.open(io.BytesIO(raw)) as im:
                            base=im.convert('RGBA');original_mode=im.mode;embedded_alpha='A' in im.getbands();original_size=im.size
                            # 原始soft mask独立保留hash，并与真正图像组合；不复用旧黑底PNG。
                            if mask:
                                with Image.open(io.BytesIO(mask)) as mi:
                                    alpha=mi.convert('L');mask_size=mi.size
                                    if alpha.size!=base.size:raise ValueError('原始softmask与图像尺寸不同')
                                    base.putalpha(alpha)
                            else: mask_size=None
                            canvas=Image.new('RGBA',base.size,'white');canvas.alpha_composite(base);rgb=canvas.convert('RGB')
                            ph=pixel_sha(rgb);asset=O/'assets'/f'{ph}.png'
                            if not asset.exists():rgb.save(asset)
                            extrema=ImageStat.Stat(rgb).extrema
                            uniform=all(a==z for a,z in extrema)
                            decode_cache[key]={'pixel_sha256':ph,'rgb_size':list(rgb.size),'original_mode':original_mode,'embedded_alpha':embedded_alpha,'softmask_size':list(mask_size) if mask_size else None,
                                               'asset':str(asset),'asset_sha256':digest(asset),'uniform':uniform,'extrema':extrema,'decode_status':'完成',
                                               'input_kind':'原图像+原softmask在白底组合；PDF剪切/背景/叠层须再看页面'}
                    except Exception as e:
                        decode_cache[key]={'decode_status':'失败','error':type(e).__name__+': '+str(e),'pixel_sha256':None};errors.append({'source_id':sid,'page':number,'block_id':f'p{number}-b{bi}',**decode_cache[key]})
                decoded=decode_cache[key];box=list(b['bbox']);norm=[box[0]/page.rect.width,box[1]/page.rect.height,box[2]/page.rect.width,box[3]/page.rect.height]
                clipped=fitz.Rect(box)&page.rect;area=clipped.get_area()/page.rect.get_area()
                overlapping=sum(bool((fitz.Rect(tb['bbox'])&fitz.Rect(box)).get_area()>0) for tb in textblocks)
                flags=[]
                if decoded.get('uniform'):flags.append('像素均匀（不能单凭此证明整个页面装饰）')
                if area>=.85 and len(re.sub(r'\s','',text))<100:flags.append('扫描整页候选：大图+低原生字符')
                if area>=.85 and len(re.sub(r'\s','',text))>=100:flags.append('背景/扫描+文字叠层候选：须页面合成复核')
                if decoded.get('rgb_size') and min(decoded['rgb_size'])<=32:flags.append('小图/符号候选（不是语义已验收）')
                if mask:flags.append('含原始softmask')
                if overlapping==0:flags.append('无原生文本bbox相交（不是图中无文字）')
                occ={'occurrence_id':sid+f'/p{number}-b{bi}','source_id':sid,'source_sha256':before,'page':number,'native_block_id':f'p{number}-b{bi}','native_number':b.get('number'),
                     'bbox_points':box,'bbox_normalized':norm,'page_size_points':[page.rect.width,page.rect.height],'transform':list(b.get('transform',[])),
                     'original_image_sha256':rh,'original_softmask_sha256':mh,'original_image_bytes':len(raw),'original_softmask_bytes':len(mask) if mask else 0,
                     'area_fraction_clipped':area,'native_text_overlap_blocks':overlapping,'flags':flags,**decoded,'cpu_checked_by_this_lane':False,'semantic_approved':False}
                occurrences.append(occ);page_occs.append(occ);emit(of,occ);source_mask+=bool(mask)
                if decoded['pixel_sha256']:
                    g=groups.setdefault(decoded['pixel_sha256'],{'pixel_sha256':decoded['pixel_sha256'],'asset':decoded['asset'],'asset_sha256':decoded['asset_sha256'],'rgb_size':decoded['rgb_size'],'uniform':decoded['uniform'],
                        'occurrence_ids':[],'raw_image_mask_variants':[],'flags':collections.Counter()})
                    g['occurrence_ids'].append(occ['occurrence_id']);variant=[rh,mh]
                    if variant not in g['raw_image_mask_variants']:g['raw_image_mask_variants'].append(variant)
                    g['flags'].update(flags)
            pr={'source_id':sid,'source_sha256':before,'page':number,'pdf_sha256':pdf_sha,'pdf_path':str(pdf),'width_points':page.rect.width,'height_points':page.rect.height,'rotation':page.rotation,
                'native_block_count':len(blocks),'native_text_blocks':len(textblocks),'native_text_chars':chars,'native_text_sha256':h(text.encode()),'nonspace_chars':len(re.sub(r'\s','',text)),
                'replacement_characters':bad_count,'private_use_characters':private,'invalid_control_characters':controls,'native_suspect_ids':native_ids,
                'image_occurrences':len(imageblocks),'image_info_occurrences':image_info_count,'softmask_occurrences':sum(bool(o['original_softmask_sha256']) for o in page_occs),
                'image_group_ids':[o['pixel_sha256'] for o in page_occs],'occurrence_ids':[o['occurrence_id'] for o in page_occs],
                'scan_fullpage_candidates':sum(any('扫描整页候选' in x for x in o['flags']) for o in page_occs),'vector_drawing_count':len(drawings),'axis_aligned_segments':axis_lines,'rectangle_items':rectangles,
                'vector_structure_candidate':structural,'structure_heuristic':'>=12轴向线段或>=8矩形；仅筛查，不证明表格/图示语义','semantic_approved':False}
            pages.append(pr);emit(pf,pr)
    row.update(actual_image_occurrences=len(occurrences)-start_occ,actual_native_blocks=source_native,actual_native_text_chars=source_chars,softmask_occurrences=source_mask,
               vector_structure_candidate_pages=source_vectors,unique_pixel_groups=len({o['pixel_sha256'] for o in occurrences[start_occ:] if o['pixel_sha256']}),
               raw_only_office_audit_status='不适用')
    if fmt!='pdf':
        op=B/sid/'raw/office-inventory.json';oi=json.loads(op.read_text())
        row['office_inventory_path']=str(op);row['office_inventory_sha256']=digest(op)
        row['historical_office_counts']={k:v for k,v in oi.items() if not isinstance(v,(list,dict))}
        row['historical_office_list_counts']={k:len(v) for k,v in oi.items() if isinstance(v,list)}
        # 原始OOXML各part中源辅助文本与媒体逐项记录。DOC不伪装成OOXML；保留历史转换证据，分页不能等同源DOM覆盖。
        if fmt in ('docx','pptx'):
            with zipfile.ZipFile(original) as z:
                for info in z.infolist():
                    part=info.filename;raw=z.read(part)
                    if '/media/' in part:
                        aux.append({'source_id':sid,'source_sha256':before,'kind':'原始Office媒体part','part':part,'bytes':len(raw),'part_sha256':h(raw),'状态':'原件保留；可见引用与未渲染引用必须分别核对'})
                    if not part.endswith('.xml'):continue
                    try:root=ET.fromstring(raw)
                    except ET.ParseError:continue
                    text='\n'.join(e.text or '' for e in root.iter() if lname(e.tag)=='t')
                    is_aux=bool(re.search(r'(notesSlides/notesSlide\d+\.xml|header\d*\.xml|footer\d*\.xml|comments\d*\.xml|footnotes\.xml|endnotes\.xml)$',part))
                    if is_aux:
                        aux.append({'source_id':sid,'source_sha256':before,'kind':'原始Office辅助文本','part':part,'part_sha256':h(raw),'exact_source_text':text,'characters':len(text),'meaningful':meaningful(text),
                                    '状态':'源辅助内容原样保留；非视觉语义验收；默认staff-only，分享另由父会话处理'})
                    for ei,e in enumerate(root.iter()):
                        for attr in ('descr','title'):
                            if e.attrib.get(attr):aux.append({'source_id':sid,'source_sha256':before,'kind':'原始Office替代文本','part':part,'part_sha256':h(raw),'element_ordinal':ei,'attribute':attr,'exact_source_text':e.attrib[attr],'characters':len(e.attrib[attr]),'状态':'辅助描述不是图像内容的独立通过依据'})
                    if part.startswith('ppt/slides/slide') and part.endswith('.xml') and '/_rels/' not in part:
                        if root.attrib.get('show')=='0':aux.append({'source_id':sid,'source_sha256':before,'kind':'隐藏幻灯片标记','part':part,'part_sha256':h(raw),'状态':'不得假定排除；须与预览映射核对'})
            row['raw_only_office_audit_status']='原始OOXML parts已机械清点；master/layout/customXML/嵌入对象语义未验收'
        else:
            import olefile
            with olefile.OleFileIO(original) as ole:
                row['original_ole_streams']=[{'stream':'/'.join(p),'bytes':ole.get_size(p),'sha256':h(ole.openstream(p).read())} for p in ole.listdir()]
            row['raw_only_office_audit_status']='原始OLE流逐项hash；历史office inventory为转换证据，不证明源字段/修订/域/浮动对象完整识读'
        aux.append({'source_id':sid,'source_sha256':before,'kind':'历史Office辅助inventory','path':str(op),'input_sha256':digest(op),'native_units':oi.get('native_units',[]),'notes':oi.get('notes',[]),'image_references':oi.get('image_references',[]),'auxiliary_parts':oi.get('auxiliary_parts',[]),'状态':'保留历史精确定位；不把raw留存叫已读/正确'})
    row['remote_sha256_after']=digest(original);row['original_unchanged']=row['remote_sha256_after']==before;assert row['original_unchanged']
    sources.append(row);dump('sources.json',sources)
    print(f'{sid}: pages={row["actual_page_count"]} images={row["actual_image_occurrences"]} groups={row["unique_pixel_groups"]} masks={source_mask}',flush=True)
pf.close();of.close();nf.close()
for g in groups.values():g['flags']=dict(g['flags']);g['occurrence_count']=len(g['occurrence_ids']);g['重复推理策略']='同像素组仅一次CPU推理；不同source/page/bbox保留，页面合成差異不得自动通过'
dump('image-groups.json',list(groups.values()));dump('office-auxiliary.json',aux)
summary={'sources':len(sources),'formats':dict(collections.Counter(s['type'] for s in sources)),'pages':len(pages),'native_blocks':native_count,'native_text_chars':native_text_chars,'image_occurrences':len(occurrences),
         'image_info_occurrences':sum(p['image_info_occurrences'] or 0 for p in pages),'image_info_mismatched_pages':sum(p['image_info_occurrences']!=p['image_occurrences'] for p in pages),
         'unique_original_image_mask_pairs':len(decode_cache),'unique_composited_pixel_groups':len(groups),'repeated_pixel_occurrences':len(occurrences)-len(groups),
         'softmask_occurrences':sum(bool(o['original_softmask_sha256']) for o in occurrences),'softmask_original_pairs':sum(k[1] is not None for k in decode_cache),
         'uniform_pixel_groups':sum(g['uniform'] for g in groups.values()),'uniform_occurrences':sum(o.get('uniform',False) for o in occurrences),'image_decode_failures':len(errors),
         'scan_fullpage_candidate_pages':sum(p['scan_fullpage_candidates']>0 for p in pages),'vector_structure_candidate_pages':sum(p['vector_structure_candidate'] for p in pages),
         'native_flagged_blocks':len(native_suspects),'native_flagged_pages':sum(bool(p['native_suspect_ids']) for p in pages),'originals_all_unchanged':all(s['original_unchanged'] for s in sources),
         'semantic_approved_sources':0,'cpu_new_inferences':0,'gpu_model_calls':0,'范围':'完整机械清点，不是准确率；所有内容理解仍未整体验收'}
dump('mechanical-summary.json',{'summary':summary,'runtime':{'python':platform.python_version(),'pymupdf':fitz.VersionBind,'cuda_visible_devices':os.environ['CUDA_VISIBLE_DEVICES'],'script_sha256':digest(__file__)},'errors':errors,
                              'historical_baseline':{'pages':1338,'native_blocks':37801,'native_text_chars':1755098,'image_occurrences':5232},
                              '说明':['图像发生次数按真实PDF/绑定Office预览get_text(dict)的image blocks计数，不是唯一图像数量。','像素组以尺寸+RGB像素SHA区分，原始图像SHA与softmaskSHA另存。白底组合资产不是任意PDF背景/clip的最终合成。','无原生文字bbox相交不等于图中无文字；扫描、向量结构与乱码标签是候选风险。','Office预览物理页数固定于已hash绑定的历史转换；不是DOC/DOCX固定的原始页数。']})
print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
