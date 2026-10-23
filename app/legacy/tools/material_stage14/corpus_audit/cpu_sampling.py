"""风险分层CPU抽样：先用机械清单选组，复用已有证据，绝不按重复出现逐次推理。"""
import os
os.environ.update(CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',PYTHONDONTWRITEBYTECODE='1')
import json,hashlib,sys,collections,re,difflib
from pathlib import Path
R=Path('/home/adminz/llm/ocr-stage1-20261009');O=R/'stage14-corpus-audit';B=R/'stage13-parser/native-v2/bundles'
try:import cv2,numpy
except ImportError:pass
sys.path.append(str(R/'.venv-baseline/lib/python3.12/site-packages'));sys.path.insert(0,str(R/'stage14-parser-recovery/code'))
from ocr_verification import CPUVerifier,normalized,linear_layout
from PIL import Image
import pymupdf as fitz
def digest(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def dump(n,d):(O/n).write_text(json.dumps(d,ensure_ascii=False,indent=2))
def load(n):return json.loads((O/n).read_text())
sources=load('sources-refined.json');groups=load('image-groups.json');pages=[json.loads(x) for x in (O/'pages.jsonl').read_text().splitlines()];occs=[json.loads(x) for x in (O/'occurrences.jsonl').read_text().splitlines()]
sby={s['id']:s for s in sources};pby={(p['source_id'],p['page']):p for p in pages};oby={o['occurrence_id']:o for o in occs}
# 关闭出站网络，使用已保存权重，不请求GPU或任何服务。
import socket
import requests
def blocked(*args,**kwargs):raise RuntimeError('审计CPU路径不允许出站网络')
socket.create_connection=blocked
requests.sessions.Session.request=blocked
verifier=CPUVerifier(R/'.venv-baseline/lib/python3.12/site-packages/rapidocr/models')
report={'说明':'有限风险分层样本；CPU文本检测不是语义真值、无文字判决或准确率。每个像素仅推理一次，source/page/bbox定位不去重。','gpu_calls':0,'cases':[],'reused_evidence':[],'plan':[],'source_sha256_before':{s['id']:digest(s['remote_original_path']) for s in sources}}
# 复用前序真实CPU结果，不反复推理同一输入。完整原始证据path/hash明确。
for filename in ['cpu-source-comparison.json','qa-cpu-comparison.json']:
    fp=R/'stage14-parser-recovery'/filename;data=json.loads(fp.read_text())
    for i,c in enumerate(data['cases']):
        scan=c['independent_ocr'];pp=c.get('page');bundle=c.get('bundle','')
        sid=next((s['id'] for s in sources if s['sha256']==c.get('source_sha256')),None)
        if not sid:
            if 'mixed_pdf' in bundle:sid='src01'
            elif bundle.endswith('/pptx'):sid='src15'
            elif bundle.endswith('/docx'):sid='src17'
            elif bundle.endswith('/doc'):sid='src16'
            elif filename=='qa-cpu-comparison.json':sid='src14'
        if pp is None and c.get('raw_receipt'):pp=int(re.search(r'p(\d+)',c['raw_receipt']).group(1))
        report['reused_evidence'].append({'source_id':sid,'page':pp,'evidence_path':str(fp),'evidence_sha256':digest(fp),'json_pointer':f'/cases/{i}','pixel_sha256':scan.get('input_pixel_sha256'),'input_size':scan.get('input_size'),
                  'cpu_lines':len(scan.get('lines',[])),'status':c['status'],'scope':'既存真实CPU推理；未整体通过；旧generation finish缺失保留',
                  'raw_receipt':c.get('raw_receipt'),'ocr_input_sha256':c.get('ocr_input_sha256'),'source_raster_sha256':c.get('source_raster_sha256') or c.get('page_raster_sha256')})
        if scan.get('input_pixel_sha256'):verifier.cache[scan['input_pixel_sha256']]=scan
    if filename=='cpu-source-comparison.json':
        scan=data['mask_recovery']['independent_ocr'];verifier.cache[scan['input_pixel_sha256']]=scan
        report['reused_evidence'].append({'source_id':'src01','page':49,'native_block_id':'p49-b4','evidence_path':str(fp),'evidence_sha256':digest(fp),'json_pointer':'/mask_recovery','pixel_sha256':scan['input_pixel_sha256'],'scope':'原softmask组合路径已恢复，仅CPU文字检测，不通过图示语义'})
seen_pages=set();seen_groups=set()
def addpage(sid,pn,reason,caseid=None):
    if (sid,pn) in seen_pages:return
    seen_pages.add((sid,pn));p=pby[(sid,pn)]
    report['plan'].append({'case_id':caseid or f'page-{sid}-{pn}','kind':'页面合成','source_id':sid,'page':pn,'reason':reason,'input_bbox_normalized':[0,0,1,1]})
def addgroup(g,reason):
    if g['pixel_sha256'] in seen_groups:return
    seen_groups.add(g['pixel_sha256']);o=oby[g['occurrence_ids'][0]]
    report['plan'].append({'case_id':'group-'+g['pixel_sha256'][:12],'kind':'唯一像素组','source_id':o['source_id'],'page':o['page'],'occurrence_id':o['occurrence_id'],'pixel_sha256':g['pixel_sha256'],'reason':reason})
# 精确既存sample编号不改。采用原缓存页面，故应复用此前CPU结果。
addpage('src22',8,'保留sample23练习视觉布局，不解题','sample23')
addpage('src23',4,'保留sample24练习视觉布局，不解题','sample24')
addpage('src20',2,'既存字体映射损坏证据，源page2，不用字符数冒充正确率')
# 扫描来源先选原生文本最少、图像最大的一页；追加src14末尾prose已遗漏页8/9，应该复用QA证据。
for sid in sby:
    sp=[p for p in pages if p['source_id']==sid]
    scans=[p for p in sp if p['scan_fullpage_candidates']]
    if scans:addpage(sid,min(scans,key=lambda p:(p['nonspace_chars'],-sum(oby[x]['area_fraction_clipped'] for x in p['occurrence_ids'])))['page'],'扫描整页分层首例：原生低文本，不假定已无字')
    # 每种源的向量结构/乱码风险选一页，优先无图表格，避免图像计数遗漏源结构。
    v=[p for p in sp if p['vector_structure_candidate'] and not p['image_occurrences']]
    if v:addpage(sid,max(v,key=lambda p:(p['axis_aligned_segments']+p['rectangle_items'],p['native_text_chars']))['page'],'无image block但存在轴线/矩形结构；优先未覆盖的表格/阅读顺序')
    bad=[p for p in sp if p['private_use_characters'] or p['invalid_control_characters']]
    if bad:addpage(sid,max(bad,key=lambda p:p['private_use_characters']+p['invalid_control_characters'])['page'],'私用字/控制字最多页；判断符号还是prose映射损坏，不自动纠正')
    # 只有小图片碎片的src20采用页面合成；不将每个glyph重复送OCR。
    candidates=[g for g in groups if not g['uniform'] and any(oby[x]['source_id']==sid for x in g['occurrence_ids']) and min(g['rgb_size'])>=48]
    if candidates:
        largest=max(candidates,key=lambda g:g['rgb_size'][0]*g['rgb_size'][1])
        addgroup(largest,'每源最大非均匀嵌入图代表：与整页扫描/页面合成分开；同pixel只一次')
addpage('src14',8,'既存QA末尾两栏prose/表格边界；复用CPU整页证据')
addpage('src14',9,'既存QA大量prose遗漏；复用CPU整页证据')
addpage('src15',10,'历史8654字符循环幻觉所在slide，整页合成需恢复定位')
addpage('src03',126,'原始2x2图+287x112 mask合法性待核；不改mask，直接页面合成')
# 比较新清点和Stage13 manifest差异，记录exact输入，不修字。
diffs=[]
for s in sources:
    if not s['native_text_different_pages']:continue
    m=json.loads((B/s['id']/'manifest.json').read_text())
    with fitz.open(s['pdf_audit_path']) as doc:
        for pn in s['native_text_different_pages']:
            allblocks=doc[pn-1].get_text('dict',sort=True)['blocks']
            fresh=[(f'p{pn}-b{i}','\n'.join(''.join(sp['text'] for sp in ln['spans']) for ln in b['lines'])) for i,b in enumerate(allblocks) if b['type']==0]
            old={b['id']:b['text'] for b in m['pages'][pn-1]['blocks'] if b['type']=='text'}
            for bid,text in fresh:
                if old.get(bid)!=text:diffs.append({'source_id':s['id'],'page':pn,'block_id':bid,'fresh_exact_text':text,'historical_exact_text':old.get(bid),'source_sha256':s['sha256'],'historical_manifest_sha256':digest(B/s['id']/'manifest.json')})
dump('native-text-differences.json',diffs)
dump('cpu-sampling-plan.json',{'plan':report['plan'],'说明':'理由先于推理保留；有限抽样，不外推正确率。','plan_count':len(report['plan'])})
for plan in report['plan']:
    sid=plan['source_id'];pn=plan['page'];src=sby[sid]
    m=json.loads((B/sid/'manifest.json').read_text());page=m['pages'][pn-1];native='\n'.join(b['text'] for b in page['blocks'] if b['type']=='text')
    if plan['kind']=='页面合成':
        # 原缓存真实页渲染，hash绑定原manifest。不得拿黑底embedded图假装source。
        image_path=B/sid/page['image'];bbox=[0,0,1,1];covered=page['blocks']
    else:
        o=oby[plan['occurrence_id']];image_path=Path(o['asset']);bbox=o['bbox_normalized'];covered=[b for b in page['blocks'] if b['id']==o['native_block_id']];native='\n'.join(b['text'] for b in covered if b['type']=='text')
    with Image.open(image_path) as im:
        rgb=im.convert('RGB');ph=hashlib.sha256(rgb.tobytes()+str(rgb.size).encode()).hexdigest()
        scan={**verifier.cache[ph],'cache_reused':True} if ph in verifier.cache else verifier.scan(rgb)
    native_norm=normalized(native)
    lines=scan.get('lines',[])
    absent=[i for i,l in enumerate(lines) if len(normalized(l['text']))>=10 and l['confidence']>=.94 and normalized(l['text']) not in native_norm]
    case={**plan,'source_sha256':src['sha256'],'pdf_sha256':src['pdf_sha256'],'input_path':str(image_path),'input_sha256':digest(image_path),'input_pixel_sha256':ph,'bbox_normalized':bbox,
          'independent_ocr':scan,'exact_native_text':native,'native_text_sha256':hashlib.sha256(native.encode()).hexdigest(),'native_nonspace_chars':len(re.sub(r'\s','',native)),
          'high_confidence_cpu_lines_not_literal_substring_of_native':absent,'cpu_nonspace_chars':sum(len(re.sub(r'\s','',l['text'])) for l in lines),'linear_layout_candidate':linear_layout(lines),
          'pixel_group_occurrence_count':next((g['occurrence_count'] for g in groups if g['pixel_sha256']==ph),None),
          '状态':'未语义验收','限制':'CPU未检测文字不证明图中无文字；行不匹配也可能是连字/断行/符号，不作为自动缺失判决；表格/练习/边关系仍未验收'}
    report['cases'].append(case);dump('cpu-sampling.json',report)
    print(plan['case_id'],sid,pn,'lines='+str(len(lines)),'new='+str(not scan.get('cache_reused',False)),'status='+scan['status'],flush=True)
report['source_sha256_after']={s['id']:digest(s['remote_original_path']) for s in sources};report['originals_unchanged']=report['source_sha256_after']==report['source_sha256_before'];assert report['originals_unchanged']
checked_groups={c['input_pixel_sha256'] for c in report['cases'] if c['independent_ocr']['status']=='complete'} & {g['pixel_sha256'] for g in groups}
checked_groups|={c['pixel_sha256'] for c in report['reused_evidence'] if c.get('pixel_sha256')} & {g['pixel_sha256'] for g in groups}
report['summary']={'plan_cases':len(report['plan']),'actual_cases':len(report['cases']),'new_cpu_inferences':sum(c['independent_ocr']['status']=='complete' and not c['independent_ocr'].get('cache_reused',False) for c in report['cases']),
    'reused_in_plan':sum(c['independent_ocr'].get('cache_reused',False) for c in report['cases']),'retained_evidence_cases':len(report['reused_evidence']),'failed_or_unavailable_cases':sum(c['independent_ocr']['status']!='complete' for c in report['cases']),
    'fullpage_cases':sum(c['kind']=='页面合成' for c in report['cases']),'direct_unique_pixel_groups_checked':len(checked_groups),'unique_pixel_groups_unchecked':len(groups)-len(checked_groups),
    'direct_group_occurrences_represented':sum(g['occurrence_count'] for g in groups if g['pixel_sha256'] in checked_groups),'semantic_approved_sources':0,'gpu_calls':0}
report['engine']=verifier.info;report['checked_group_ids']=sorted(checked_groups)
dump('cpu-sampling.json',report);print(json.dumps(report['summary'],ensure_ascii=False,indent=2),flush=True)
