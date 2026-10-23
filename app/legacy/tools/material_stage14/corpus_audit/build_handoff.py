"""聚合真实审计证据，输出一个中文HANDOFF和可执行输入/验收清单。无模型请求。"""
import json,hashlib,collections,math,shutil,re
from pathlib import Path
from PIL import Image
APP=Path('D:/HermesProjects/EDUC7703/app');O=APP/'artifacts/stage14/corpus-audit';T=APP/'tools/material_stage14/corpus_audit'
def digest(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def dump(n,d):(O/n).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def write_jsonl(n,rows):(O/n).write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in rows),encoding='utf-8')
sources=load(O/'sources-final.json');counts=load(O/'counts-final.json')['summary'];groups=load(O/'image-groups.json');cpu=load(O/'cpu-sampling.json')
occ=[json.loads(x) for x in (O/'occurrences.jsonl').read_text(encoding='utf-8').splitlines()];pages=[json.loads(x) for x in (O/'pages.jsonl').read_text(encoding='utf-8').splitlines()]
sby={s['id']:s for s in sources};pby={(p['source_id'],p['page']):p for p in pages};oby={o['occurrence_id']:o for o in occ}
assert len(sources)==23 and len(sby)==23;assert len(pages)==1338 and len(occ)==5232
assert sum(s['actual_image_occurrences'] for s in sources)==len(occ)
assert sum(s['actual_page_count'] for s in sources)==len(pages)
assert sum(g['occurrence_count'] for g in groups)+counts['image_decode_failed_occurrences']==len(occ)
assert sum(s['actual_native_text_chars_default'] for s in sources)==1755098
# 父会话新installed r5结果只读引用，不重跑模型、不改变parser。
r5_path=APP/'artifacts/stage14/installed-scan-parser-r5.json';r5=load(r5_path);r5m=r5['files']['manifest.json'];r5r=r5['files']['receipt.json']
assert r5m['source_sha256']==sby['src14']['sha256']
r5_pages=[]
for p in r5m['pages']:
    r5_pages.append({'page':p['number'],'blocks':len(p['blocks']),'quality_counts':dict(collections.Counter(b['quality'] for b in p['blocks'])),
                     'targeted_recovery_blocks':sum('recovery' in b['id'] or any('targeted_recovery' in i for i in b['issues']) for b in p['blocks'])})
r5_evidence={'path':str(r5_path),'sha256':digest(r5_path),'source_id':'src14','source_sha256':r5m['source_sha256'],'parser':r5m['parser'],'page_count':len(r5m['pages']),
    'blocks':sum(p['blocks'] for p in r5_pages),'quality_counts':dict(collections.Counter(b['quality'] for p in r5m['pages'] for b in p['blocks'])),
    'machine_verified_literal_blocks':r5m['coverage']['machine_verified_literal_blocks'],'targeted_recovery_calls':r5r['targeted_recovery_calls'],'per_page':r5_pages,
    'remote_output':'CT255:/var/lib/aicademiya-qa/stage14-native-0986d5dd/scan-parser-r5','semantic_accuracy_approved':False,
    '说明':'59真实CPUverified块不等于全份准确率；64recovery全在前8页，p9/10为0恢复。resource pass只读自父会话留存receipt/supervisor，不是本lane新GPU结果。'}
assert r5_evidence['blocks']==266 and r5_evidence['machine_verified_literal_blocks']==59 and sum(p['targeted_recovery_blocks'] for p in r5_pages)==64
assert all(p['targeted_recovery_blocks']==0 for p in r5_pages if p['page'] in (9,10))
dump('installed-r5-evidence.json',r5_evidence)
for s in sources:
    assert re.fullmatch('[0-9a-f]{64}',s['sha256'])
    s['local_sha256_after']=digest(s['strict_original_path']);s['local_original_unchanged']=s['local_sha256_after']==s['local_sha256_before']==s['sha256'];assert s['local_original_unchanged']
originals={'说明':'Windows真实原件与Linux只读副本全部逐项SHA匹配原始inventory；同一本源在审计前后逐字节保持。','inventory_path':load(O/'inputs.json')['inventory_path'],'inventory_sha256':load(O/'inputs.json')['inventory_sha256'],
           'sources':[{k:s[k] for k in ['id','original_token','strict_original_path','type','sha256','local_bytes','remote_original_path','local_sha256_before','local_sha256_after','remote_sha256_before','remote_sha256_after','local_original_unchanged','original_unchanged','pdf_audit_path','pdf_sha256','actual_page_count','page_count_kind','actual_native_blocks','actual_native_text_chars_default','actual_image_occurrences','softmask_occurrences','unique_pixel_groups','office_inventory_path','office_inventory_sha256'] if k in s} for s in sources],
           'all_23_local_and_remote_originals_unchanged':True}
dump('originals-unchanged.json',originals)
# 按每个页面完整留任务；没有图像的页也不能因5232 image清点而被遗漏。
page_units=[]
for p in pages:
    flags=[]
    if p['native_suspect_ids']:flags.append('原生字体/定位候选风险，需区分bullet与prose损坏')
    if p['scan_fullpage_candidates']:flags.append('扫描整页候选：需全文OCR含最后段/两栏')
    if p['vector_structure_candidate']:flags.append('向量结构候选：行列/合并表头/连线/顺序未核')
    if p['image_occurrences']:flags.append('图像及实际页面合成尚未全量验收')
    if not flags:flags.append('原生文本已有机械留存；逐段正确性与阅读次序仍未核')
    task={'task_id':p['source_id']+f'/page{p["page"]}','source_id':p['source_id'],'source_sha256':p['source_sha256'],'strict_original_path':sby[p['source_id']]['strict_original_path'],
          'remote_original_path':sby[p['source_id']]['remote_original_path'],'pdf_path':p['pdf_path'],'pdf_sha256':p['pdf_sha256'],'page':p['page'],'bbox_normalized':[0,0,1,1],
          'image_occurrence_ids':p['occurrence_ids'],'pixel_group_ids':p['image_group_ids'],'native_suspect_ids':p['native_suspect_ids'],'risk_categories':flags,
          'cpu_evidence_refs':[{'file':'cpu-sampling.json','case_id':c['case_id'],'input_sha256':c['input_sha256']} for c in cpu['cases'] if c['kind']=='页面合成' and c['source_id']==p['source_id'] and c['page']==p['page']],
          'status':'待真实源核对，不是已准确识别','execution':'先按源SHA校验，CPU渲染实际页面；仅发现独特OCR/结构缺口时升级GPU；不逐重复图像重跑CPU'}
    page_units.append(task)
write_jsonl('page-units.jsonl',page_units)
group_units=[]
for g in groups:
    os=[oby[x] for x in g['occurrence_ids']];group_units.append({**g,'task_id':'pixel/'+g['pixel_sha256'],'cpu_independently_checked':g['pixel_sha256'] in cpu['checked_group_ids'],
        'source_locators':[{'occurrence_id':x['occurrence_id'],'source_id':x['source_id'],'source_sha256':x['source_sha256'],'page':x['page'],'block_id':x['native_block_id'],'bbox_points':x['bbox_points'],'bbox_normalized':x['bbox_normalized'],'transform':x['transform']} for x in os],
        'status':'纯色像素可机械说明、但不关闭整个页面语义' if g['uniform'] else '该唯一像素组文字/结构尚待核；CPU检测不等于验收',
        'gpu_policy':'纯色不单独送模型；真实页面叠层仍按page-unit核' if g['uniform'] else '相同像素先处理一次；每个出现位置单独保留引用，页面背景/clip/顺序另核'})
write_jsonl('group-units.jsonl',group_units)
failed=[x for x in occ if x['decode_status']!='完成'];write_jsonl('unresolved-mask-units.jsonl',[{'task_id':x['occurrence_id'],**x,'fallback_evidence_file':'mask-fallback-inputs.json','execution':'当前原图2x2与softmask287x112尺寸不同；使用原PDFclip渲染，不改源或任意缩放mask'} for x in failed])
# 有限优先列表。既有GPU结果可先核验，不意味每项必须新推理；本lane只制输入。
priority=[];(O/'priority-inputs').mkdir(exist_ok=True)
common=['严格保留源字面文本，拒绝解题/补写；所有不确定字保留未知','记录每次generation finish/events；length/循环/unknown finish不得通过','文字、表格结构、图示关系分开验收；字符/页数不作为准确率','每个source/page/bbox保留引用，重复像素不覆盖不同位置的背景/叠层/阅读顺序']
def add(case_id,sid,pn,input_path,bbox,reason,category='P1',block_id=None,action='待父会话授权GPU/安装UID999验收',extra=None):
    assert case_id not in {x['case_id'] for x in priority}
    p=Path(input_path);assert p.is_file();src=sby[sid]
    row={'case_id':case_id,'priority':category,'source_id':sid,'source_sha256':src['sha256'],'strict_original_path':src['strict_original_path'],'pdf_sha256':src['pdf_sha256'],'page':pn,'source_bbox_normalized':bbox,
         'source_block_id':block_id,'input_path':str(p),'input_sha256':digest(p),'reason':reason,'next_action':action,'acceptance':common,'status':'未整体验收'}
    if extra:row.update(extra)
    priority.append(row)
# QA真实页9的有限CPU定位crop；旧主OCR1736 vs独立CPU4664为缺失证据，不外推准确率。
Q=APP/'artifacts/stage14/parser-recovery/qa-fresh-scan';qa=load(APP/'artifacts/stage14/parser-recovery/qa-cpu-comparison.json');c9=next(c for c in qa['cases'] if c['page']==9)
raw9=load(Q/'raw/p0009-region0.json');source_image=Q/raw9['ocr_input_asset'];tiles=c9['whole_region']['targeted_plan'];rb=raw9['final_raster_bbox']
with Image.open(source_image) as im:
    for ti,tile in enumerate(tiles):
        b=tile['bbox'];box=[math.floor(b[0]*im.width),math.floor(b[1]*im.height),math.ceil(b[2]*im.width),math.ceil(b[3]*im.height)]
        crop=im.crop(box);dest=O/'priority-inputs'/f'src14-p9-prose-{ti+1:02}.png';crop.save(dest)
        # 将实际取整像素的裁切位置映射回真实源页，保留原region及检测bbox区别。
        effective=[box[0]/im.width,box[1]/im.height,box[2]/im.width,box[3]/im.height]
        pb=[rb[0]+effective[0]*(rb[2]-rb[0]),rb[1]+effective[1]*(rb[3]-rb[1]),rb[0]+effective[2]*(rb[2]-rb[0]),rb[1]+effective[3]*(rb[3]-rb[1])]
        add(f'prose-src14-p9-{ti+1:02}','src14',9,dest,pb,'已观测旧主OCR遗漏大量prose；先恢复独立CPU定位行，勿继续只读表5.7','P0',extra={'input_transform':{'source_input':str(source_image),'source_input_sha256':digest(source_image),'region_bbox_normalized':rb,'cpu_detected_tile_bbox':b,'crop_pixels':box,'scale':1},
            'evidence':{'file':'../parser-recovery/qa-cpu-comparison.json','sha256':digest(APP/'artifacts/stage14/parser-recovery/qa-cpu-comparison.json'),'pointer':f'/cases/2/whole_region/targeted_plan/{ti}'},
            'expected_cpu_lines_not_groundtruth':tile['expected_cpu_text'],'cpu_line_indices':tile['cpu_line_indices'],'acceptance_extra':['逐行核验源crop与原页面，对照文字锚点、数字和段尾；缺失prose未覆盖行仍必须保留待办']})
# 表格用真实旧crop与27B已有新证据比对；不重复提交同图以制造新成功。
trans=load(APP/'artifacts/stage14/vision-focused-input/source-transforms.json')
qm=load(Q/'manifest.json')
for label,pn,bid,filename in [('table5.1',3,'p3-b7-vlm','table5-1-2x.png'),('table5.7',9,'p9-b20-vlm','table5-7-2x.png')]:
    block=next(b for b in qm['pages'][pn-1]['blocks'] if b['id']==bid)
    add(label,'src14',pn,APP/'artifacts/stage14/vision-focused-input'/filename,block['bbox'],'27B内容/结构已有改善；须逐单元格核源、跨行/列、表头与脚注，尚不通过','P0',bid,
        '先核既存focused-r2输出，下一步才是UID999新parser对同源真实验收',extra={'source_crop_locator':str(Q/'assets'/f'{bid}.png'),'bbox_evidence_kind':'历史VLM表格定位候选；输入为真实源像素crop，bbox不当作已人工验收边界','source_transform':next(t for t in trans if t['output']==filename),'existing_gpu_evidence':{'file':'../vision-focused-r2-result.json','sha256':digest(APP/'artifacts/stage14/vision-focused-r2-result.json')}})
# 复杂关系图不盲重跑：已有两次真实27B错误，第二次length。
add('feedback-src01-p49','src01',49,APP/'artifacts/stage14/vision-focused-input/p49-content-2x.png',oby['src01/p49-b4']['bbox_normalized'],
    '复杂feedback图已有边/样式错误；focused-r2生成循环且length，保留失败，不把标签检测叫完整关系通过','P1','p49-b4','挂起盲目同配置复跑；先真实源关系定位/有限分区策略，再由父会话决定GPU',
    {'source_transform':trans[0],'original_image_sha256':oby['src01/p49-b4']['original_image_sha256'],'original_softmask_sha256':oby['src01/p49-b4']['original_softmask_sha256'],'existing_gpu_evidence':{'file':'../vision-focused-r2-result.json','sha256':digest(APP/'artifacts/stage14/vision-focused-r2-result.json')},'acceptance_extra':['标签与每条连接的起终点、箭头、虚实线、黑点/圈、分组分别对源图；不可凭文字重构边']})
feedback=next(j for j in priority if j['case_id']=='feedback-src01-p49');feedback_parent=oby['src01/p49-b4'];crop=trans[0]['crop']
with Image.open(Path(trans[0]['source'])) as original_mask_image:iw,ih=original_mask_image.size
ma,mb,mc,md,me,mf=feedback_parent['transform'];corners=[]
for u,v in [(crop[0]/iw,crop[1]/ih),(crop[2]/iw,crop[1]/ih),(crop[2]/iw,crop[3]/ih),(crop[0]/iw,crop[3]/ih)]:corners.append([ma*u+mc*v+me,mb*u+md*v+mf])
feedback['parent_image_bbox_normalized']=feedback['source_bbox_normalized'];pw,ph=feedback_parent['page_size_points']
feedback['input_source_polygon_points']=corners;feedback['source_bbox_normalized']=[min(c[0] for c in corners)/pw,min(c[1] for c in corners)/ph,max(c[0] for c in corners)/pw,max(c[1] for c in corners)/ph]
cpuby={c['case_id']:c for c in cpu['cases']}
def addcpu(cid,reason,cat='P1',action='待父会话授权GPU/安装UID999验收'):
    c=cpuby[cid];extra={'cpu_evidence':{'file':'cpu-sampling.json','sha256':digest(O/'cpu-sampling.json'),'case_id':cid},'cpu_detected_lines':len(c['independent_ocr']['lines'])}
    if c['kind']=='唯一像素组':
        x=oby[c['occurrence_id']];extra.update(pixel_group_sha256=c['input_pixel_sha256'],all_occurrence_ids=next(g['occurrence_ids'] for g in groups if g['pixel_sha256']==c['input_pixel_sha256']),original_image_sha256=x['original_image_sha256'],original_softmask_sha256=x['original_softmask_sha256'])
    add(cid,c['source_id'],c['page'],O/'review-inputs'/f'{cid}.png',c['bbox_normalized'],reason,cat,c.get('occurrence_id','').split('/')[-1] or None,action,extra)
addcpu('page-src20-2','源多栏英文prose真实可读，native包含大量控制字/奇怪字符；不是bullet字体而是正文映射失败','P0')
addcpu('page-src08-1','真实多层合并表头/多栏表格，无image blocks；私用字主要arrow/bullet不可泛判正文乱码','P0')
addcpu('page-src07-2','无image blocks的scheme of work表格：行列、关联目标与顺序未覆盖','P1')
addcpu('page-src09-1','无image blocks的unit/chapter plan：表格关联和阅读顺序未覆盖','P1')
addcpu('page-src10-4','lesson plan向量表格，image数量少不能代替全页结构验收','P1')
addcpu('group-0bec698ebe63','src04/p118 Plot Diagram有源文字、节点与阶段位置，非装饰；CPU23行不建立图关系','P0')
addcpu('group-ec769f6113f9','src18/p42图片含约1237非空白CPU字符，native无嵌入文字；不能以原生覆盖率跳过','P0')
addcpu('group-2ee40ebb5434','原始DOC转PDF的src16/p5大图含37条高置信未匹配源行，完整字面识读与表格仍待核','P1')
addcpu('group-6621456f4f3b','原始DOCX转PDF的src17/p2大图含源文字，原图原生text为空不代表无字','P1')
addcpu('sample23','严格保留sample23=src22/page8；练习版式/图示定位未验收，不得由OCR解答','P1')
addcpu('sample24','严格保留sample24=src23/page4；练习版式/图示定位未验收，不得由OCR解答','P1')
addcpu('page-src15-10','Stage13同slide8654字符循环幻觉；当前CPU真实源32行，旧finish缺失仍未通过','P0')
addcpu('group-51de5e4a82c5','Stage13同图反复1.而CPU零检测；这只能证明检测未读到，模糊小字是否存在仍未知','P1','先核真实像素是否可读；不可把零检测升级为无文字/装饰已通过')
fallback=load(O/'mask-fallback-inputs.json');f=fallback[0]
add('mask-size-src03','src03',f['page'],O/'review-inputs'/Path(f['asset']).name,f['bbox_normalized'],'原2x2图与287x112 softmask尺寸不同影响15实例；真实源clip能渲染可见Ss，当前组合helper仍有遗漏风险','P0',f['occurrence_id'].split('/')[-1],
    '父会话检查真实parser1.2对尺寸不同softmask的fallback，不需对15重复实例重CPU推理',{'all_affected_occurrence_ids':[x['occurrence_id'] for x in failed],'render_transform':f['render_matrix'],'original_image_sha256':failed[0]['original_image_sha256'],'original_softmask_sha256':failed[0]['original_softmask_sha256']})
addcpu('page-src14-8','扫描两栏长prose，既有CPU对齐不等于表格层级/顺序通过；须检查列序与段尾','P1')
addcpu('page-src01-47','扫描整页native为0，CPU能检测源文字；不以零原生字符当空页','P1')
addcpu('page-src02-162','大书原生符号/注释风险代表，有限源定位核对，不因单页匹配宣称317页正确','P2')
addcpu('page-src03-209','无image blocks的密集向量结构；CPU文字匹配不证明行列关系','P1')
addcpu('page-src04-163','无image blocks的密集向量表格，122CPU行；合并表头/目标层级需独立核','P1')
addcpu('page-src05-93','课程指南向量结构与密集prose，native大体可读但结构未核','P2')
for sid in ('src11','src19'):
    add('worksheet-'+sid,sid,1,O/'review-inputs'/f'page-{sid}-1.png',[0,0,1,1],'worksheet原生页无image blocks，但提示、答案区和表格阅读关系未CPU分层抽查；不是自动通过','P2')
# r5前8页用尽64恢复预算，末两页必须独立保留P0，而非只算10页覆盖。
import pymupdf as fitz
p10input=O/'priority-inputs/src14-p10-source.png'
with fitz.open(sby['src14']['strict_original_path']) as original_pdf:
    original_pdf[9].get_pixmap(matrix=fitz.Matrix(2,2),alpha=False).save(p10input)
add('tail-recovery-src14-p10','src14',10,p10input,[0,0,1,1],'新installed-r5的64recovery前8页耗尽，p10没有targeted recovery；需末页prose/段尾独立验收','P0',
    extra={'new_installed_evidence':r5_evidence,'input_transform':{'source_path':sby['src14']['strict_original_path'],'source_sha256':sby['src14']['sha256'],'page':10,'matrix':[2,0,0,2,0,0]}})
for job in priority:
    if job['source_id']=='src14' and job['page']==9:
        job['new_installed_evidence']={'file':'installed-r5-evidence.json','sha256':digest(O/'installed-r5-evidence.json'),'page9_targeted_recovery_blocks':0,'status':'64全局恢复预算前8页耗尽；59verified块非整体准确率'}
priority.sort(key=lambda x:({'P0':0,'P1':1,'P2':2}[x['priority']],0 if x['case_id'].startswith('prose-') else 1))
dump('gpu-priority.json',{'说明':'有限的下一批验收项，不是新GPU调用授权；表5.1/5.7先核已有输出，复杂反馈图不盲重跑。编号sample23/sample24不改。','count':len(priority),'priority_counts':dict(collections.Counter(x['priority'] for x in priority)),
    'jobs':priority,'missing_prose_remaining':{'source_id':'src14','page':9,'planned_cpu_lines':c9['whole_region']['planned_lines'],'detected_cpu_lines':c9['whole_region']['detected_lines'],'unattempted_line_indices':c9['whole_region']['unattempted_lines'],'scope':'8crop只覆盖有限CPU行；未计划行不得被当完成'}})
# 清晰类别证据：硬失败、机械信号、未知分开。
risks=[{'category':'原生prose字体映射损坏','status':'已观测问题','source_id':'src20','page':2,'evidence':'cpu-sampling.json/page-src20-2 + review-inputs/page-src20-2.png','detail':'源多栏连续英文可见；native包含控制字与错映射字符，真实CPU47行；不是字符数量不足。'},
       {'category':'私用字/控制字风险','status':'机械筛查非失败','flagged_blocks':counts['native_flagged_blocks'],'flagged_pages':counts['native_flagged_pages'],'evidence':'native-suspects.jsonl','detail':'包括bbox出页、bullet和arrow。src08/p1可见bullet/arrow且真实表格，src06多控制字是bullet，抽样prose无高置信未匹配行；不得把风险标记块一律判乱码。'},
       {'category':'图像没有检测到文字','status':'未知','detail':'CPU零检测/纯色像素分别记录；前者不能证明无字，后者只说明图像自身像素无文字图案，不关闭源页合成/语义。','evidence':'cpu-sampling.json + image-groups.json'},
       {'category':'扫描整页与缺失prose','status':'已观测缺失+其余未知','source_id':'src14','page':9,'evidence':'../parser-recovery/qa-cpu-comparison.json','detail':f'旧主OCR1736归一化字符vs独立CPU4664，源prose遗漏；数字不是准确率。{counts["scan_fullpage_candidate_pages"]}页扫描候选不等于纯扫描总数，空白背景也可能入候选。'},
       {'category':'图表/向量结构','status':'未语义验收','candidate_pages':counts['vector_structure_candidate_pages'],'evidence':'pages.jsonl + page-units.jsonl','detail':'719页仅轴向线/矩形阈值候选，真实向量表格可能不达阈值。src08/p1真实表格，src04/p118真实Plot Diagram，CPU标签不是结构通过。'},
       {'category':'原始softmask','status':f'softmask{counts["softmask_occurrences"]}实例已审计，其中{counts["image_decode_failed_occurrences"]}实例无法直接组合、其余{counts["softmask_occurrences"]-counts["image_decode_failed_occurrences"]}实例组合完成','evidence':'occurrences.jsonl + mask-fallback-inputs.json','detail':'一原图+mask尺寸不符影响src03/p126及p127共15位置；实际页面clip源可见Ss。源原图与mask hash保留，未修改parser。'},
       {'category':'源辅助内容','status':'机械原样保留、语义/阅读投影未全面核','evidence':'office-auxiliary.json + sources-final.json + ../real-supplement-index.json','detail':'原OOXML part/hash/text与媒体独立清点；DOC只审计原始OLE流hash和历史derived DOCX库存，未宣称源DOM全解析。既存src15有20speaker notes+15alt text/4234字符索引证据，不等于模型读过。'}]
dump('risk-evidence.json',risks)
failed_history=[{'scope':'本lane初次CPU路径不可用','evidence':'cpu-sampling-initial-unavailable.json','error':'缺LD_LIBRARY_PATH的libGL.so.1，不是源识别失败','correction':'使用既有native-libs只读路径，未安装依赖。初报new_cpu_inferences56是失真标签；实际该次无CPU推理，不能作为数量依据。'},
    {'scope':'Stage13 PPTX循环幻觉/旧generation_finish缺失','evidence':'../parser-recovery/cpu-source-comparison.json','accepted':False},
    {'scope':'旧p49黑底/softmask丢失','evidence':'../parser-recovery/verification-summary.json + occurrences.jsonl','accepted':False},
    {'scope':'src14p9旧prose遗漏','evidence':'../parser-recovery/qa-cpu-comparison.json','accepted':False},
    {'scope':'新installed-r5恢复预算末页覆盖缺口','evidence':'installed-r5-evidence.json','machine_verified_literal_blocks':59,'recovery_calls':64,'recovery_page9_page10':0,'accepted':False},
    {'scope':'27B复杂feedback两次未过，focused-r2length','evidence':'../vision-focused-r2-result.json','cases':[{k:c[k] for k in ['name','sha256','finish_reason','usage'] if k in c} for c in load(APP/'artifacts/stage14/vision-focused-r2-result.json')['cases']],'accepted':False}]
dump('failure-history.json',failed_history)
counts.update(cpu_sampling=cpu['summary'],local_sources_all_unchanged=True,fullpage_units=len(page_units),group_units=len(group_units),unresolved_mask_units=len(failed),gpu_priority_jobs=len(priority),gpu_priority_counts=dict(collections.Counter(x['priority'] for x in priority)),
              native_flag_kinds={k:sum(bool(json.loads(x)['flags'][k]) for x in (O/'native-suspects.jsonl').read_text(encoding='utf-8').splitlines()) for k in ['replacement_characters','private_use_characters','invalid_control_characters','bbox_out_of_page']},
              unique_nonuniform_pixel_groups=sum(not g['uniform'] for g in groups),fullpage_cpu_sampled_unique_pages=len({(c['source_id'],c['page']) for c in cpu['cases'] if c['kind']=='页面合成'}))
counts['fullpage_cpu_not_sampled']=len(page_units)-counts['fullpage_cpu_sampled_unique_pages']
manifest={'说明':'23份真实资料的有限缺口审计；完整机械清单不等于准确识别、视觉语义或应用/UID999新parser验收。','summary':counts,'originals':originals['sources'],
          'files':{name:{'path':str(O/name),'sha256':digest(O/name)} for name in ['coordinate-alpha-correction.json','installed-r5-evidence.json','originals-unchanged.json','counts-final.json','pages.jsonl','occurrences.jsonl','native-suspects.jsonl','image-groups.json','office-auxiliary.json','cpu-sampling.json','cpu-sampling-plan.json','page-units.jsonl','group-units.jsonl','unresolved-mask-units.jsonl','gpu-priority.json','risk-evidence.json','failure-history.json','mask-fallback-inputs.json','review-inputs-manifest.json']},
          'remote_workspace':'/home/adminz/llm/ocr-stage1-20261009/stage14-corpus-audit','all_originals_unchanged':True,'source_semantics_fully_accepted':False,'gpu_model_calls_by_this_lane':0,
          'reused_ocr_scope':'17件既有CPU证据引用；56项抽样中4项复用，52次新增CPU推理，CPUExecutionProvider独立确认。','pinned_samples':{'sample23':{'source_id':'src22','page':8},'sample24':{'source_id':'src23','page':4}},
          'unverified':['所有23源整份语义仍未通过','2891成功组合像素组未直接CPU抽查；已有23组文字检测也不是语义验收','1299页未进入本轮39页整页CPU样本（历史17件并非新增页覆盖且分辨率不同）','15个不同mask尺寸实例只有页面clip恢复像素，不证明新parser fallback成功','719向量结构候选页及阈值外结构的表头/行列/顺序未全核','Office master/layout/off-page/嵌入对象、原始DOC辅助字段仍未知','parent负责真实UID999parser1.2、GPU/应用/引用/发布，未由本lane验证'],
          'authorization_boundary':'本lane只用CPU只读源、无应用/parser修改，无部署/sudo/服务操作/GPU请求；报告为优先级，不增加GPU授权。'}
dump('audit.json',manifest)
# 一个报告，包括全部严格原始token/path/hash/格式/实际页数/发生次数；无需第二reviewer。
lines=['# 23份真实资料：CPU审计与全语料视觉处理交接','',
'## 结果与边界','',f'- 逐项核对原始inventory并重读23份真实原件及23份Linux副本。格式18PDF/2DOCX/1PPTX/2DOC；1338物理页、37801默认dict blocks、1755098原生字符、5232图像发生次数，已由代码聚合闭合。上述不是准确率。',
f'- 2939个原图+mask组合；成功组合5217实例/2914唯一RGB像素组，其中2303是重复发生次数。另1种尺寸不同mask涉及15实例（src03/p126、p127），不得计作成功像素或重复。',
f'- softmask436实例/166原始组合；804唯一纯色像素组/1375实例；2110非均匀唯一像素组。重复像素仍保留全部source/page/bbox/transform，页面背景/clip/叠层不自动继承通过。',
f'- 一条Linux CPU lane，52次新增CPU推理，4项抽样缓存复用，引用17件既有CPU证据；56项抽样中39为整页输入。实际CPUExecutionProvider，零GPU/模型/服务请求。{counts["scan_fullpage_candidate_pages"]}页扫描候选、719页向量结构候选仅为筛查。',
f'- 直接CPU已检测23唯一像素组/104出现位置，另2891组未直接检测；1299页未进入本轮整页CPU样本。全部23源整份语义验收数0，CPU检测不是自动通过。',
'- 所有Windows原件与Linux副本SHA在前后均匹配原始inventory。只创建约定的tools/material_stage14/corpus_audit/与artifacts/stage14/corpus-audit/及独立remote CPU目录；未改应用、解析器、源材料、模型/服务。','',
'## 原件逐项清单（token/path保留原样）','',
'PDF页数为原件物理页；Office没有固定原始页数，下面为SHA绑定的历史LibreOffice预览物理页。原始Office身份与preview SHA分开记录，不能把27幻灯片/6预览页说成源DOM完全识读。','']
for s in sources:
    lines += [f'### {s["id"]} — {s["type"]} / {s["actual_page_count"]}页 / {s["actual_image_occurrences"]}图像实例',
              f'- 原始token：`{s["original_token"]}`',f'- 原始path：`{s["strict_original_path"]}`',f'- 原始SHA256：`{s["sha256"]}`',
              f'- Linux只读副本：`{s["remote_original_path"]}`',f'- 页面计数口径：{s["page_count_kind"]}；PDF输入SHA：`{s["pdf_sha256"]}`','']
lines += ['## 已观测缺口与未知','',
'- **原生prose乱码**：src20/page2源图有连续可读英文；native有正文控制字/错映射。`cpu-sampling.json/page-src20-2`保存源hash、native原文、47条CPU行及bbox。不要把中文/符号/arrow/bullet的私用字当成同样错误。',
f'- **{counts["native_flagged_blocks"]}块/{counts["native_flagged_pages"]}页风险信号**：含私用字1519块、控制字699块、bbox出页26块（可重叠）；U+FFFD块0。src08/page1真实向量表格，arrow/bullet是风险非prose失败；src06抽查页的prose基本能文字匹配，不据风险块数判全书损坏。已纠正60旋转页坐标：原始bbox不改写，另存显示bbox；移除1102个错误出页标记。',
'- **图像CPU零文字**：例如src15/page1模糊背景/图片、src21/page4、src22/page4大插画，CPU未检测不证明无可读字。纯色组只可说明自身像素，无整页语义通过。',
'- **遗漏prose（保留旧失败）**：src14/page9旧主OCR1736归一化字符 vs真实CPU4664，table之外prose明显遗漏。8个定位crop已输出；仍有未计划CPU行，在gpu-priority.json明确列出。其余页未因该统计外推准确率。',
'- **图表结构**：src08/page1等无image blocks但真实多层表格；src04/page118 Plot Diagram有图、源文字与阶段位置。原生字符/CPU标签无法建立行列/节点/连接的完整通过。719仅是启发式向量结构候选，不是图表总数。',
'- **softmask新发现**：src03/page126-127同一原始2x2图+287x112 mask分15处；组合严格尺寸检查失败。真实源clip显现Ss，可见像素恢复不等于parser通过。`unresolved-mask-units.jsonl`保留每处定位；不得丢掉15实例。',
'- **源辅助内容**：所有5Office的历史inventory和原始DOC/OLE流或OOXML parts/hash独立审计。src15既有20speaker_notes+15alt_text/4234字符索引证据仍保留staff-only边界。raw保留、源下载含notes、AI已读和视觉正确是不同验收，DOC源辅助字段仍未知。',
'- **新installed r5证据**：`installed-r5-evidence.json`从父会话真实结果重算10页/266blocks、59extracted/207needs_review、64recovery；每页1-8各8恢复，p9/10为0。59CPUverified不是整体准确率，末两页P0另列。本lane没有重跑或改parser。',
'- **既有27B**：表5.1/5.7已有改善但源对照由父会话处理；feedback src01/page49仍错，focused-r2循环length保留。优先项说明不得继续同配置盲重跑或把文字标签当完整图意通过。','',
'## 后续执行与验收优先级','',f'- 有限清单`gpu-priority.json`共{len(priority)}项，优先计数{json.dumps(counts["gpu_priority_counts"],ensure_ascii=False)}。8prose定位crop在前，其次表格/原生映射/未覆盖结构。它是验收队列，不是{len(priority)}次新请求承诺；表5.1/5.7先利用既有结果，feedback项挂起盲重跑。',
'- `sample23=src22/page8`与`sample24=src23/page4`始终原编号，不解练习。',
'- 每项有source SHA、真实page、bbox、input path/hash、转换/旧证据和验收门槛。必须保存generation finish/events；length/循环/finish unknown不通过。逐行字面、表格单元格及关系/线型各自验收，禁止生成补全源。',
'- 全语料机器任务：`page-units.jsonl`1338条；`group-units.jsonl`2914条，附5232中所有成功实例定位；`unresolved-mask-units.jsonl`15条。图像去重只减少重复CPU推理，不能删引用或跳过无图原生页。',
'- 输入materializer只做CPU渲染/校验，不含GPU客户端。可运行`python -B tools/material_stage14/corpus_audit/materialize_inputs.py --list-priority`查看有限队列；Linux同一CPU目录执行`python materialize_inputs.py --page src08:1`可从SHA绑定原PDF渲染真实页。不要因此自行调用模型。','',
'## 证据路径','',f'- 主机可读机器文件：`{O / "audit.json"}`',f'- 本交接：`{O / "HANDOFF.md"}`',f'- 原件未变：`{O / "originals-unchanged.json"}`',
f'- 原始inventory：`{load(O/"inputs.json")["inventory_path"]}`，SHA `{load(O/"inputs.json")["inventory_sha256"]}`',
'- Linux资产/CPU脚本：`/home/adminz/llm/ocr-stage1-20261009/stage14-corpus-audit/`。全量2914唯一像素PNG留该目录；本地导出75份有限源输入并全部readback核hash，重点原图/图表/渲染非生成。','',
'## 方法问题与保留的失败','',
'- 初次CPU缺只读native-libs路径，libGL unavailable，未真正做56次推理；初报错误计数保存在`cpu-sampling-initial-unavailable.json`并明确排除。加已有LD_LIBRARY_PATH后真实52次CPU成功，不安装、不修改环境/依赖。',
'- 字符口径对齐：默认dict（保留image、不trim）1755098与历史逐项相同；去image flags暂测1755124，只在11页改变分块；trim口径1716243。方法差异不叫补字或识别遗漏，`counts-final.json`保留对比。',
'- 所有23源完整语义、2891未直接检测像素组、1299未入整页CPU样本、Office未渲染结构与DOC辅助字段、实际UID999parser1.2/GPU/应用投影/引用/发布仍未验证。父会话的安装/运行不能被本CPU审计替代。','']
(O/'HANDOFF.md').write_text('\n'.join(lines),encoding='utf-8')
print(json.dumps({'sources':len(sources),'pages':len(page_units),'image_occurrences':len(occ),'pixel_groups':len(groups),'cpu':cpu['summary'],'gpu_priority_count':len(priority),'all_originals_unchanged':True,'audit_path':str(O/'audit.json'),'handoff_path':str(O/'HANDOFF.md')},ensure_ascii=False,indent=2))
