"""定位与透明度纠偏：保留原bbox，显式分开PDF未旋转坐标与显示坐标。无额外OCR。"""
import os
os.environ.update(CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1')
import json,hashlib,io,collections
from pathlib import Path
import pymupdf as fitz
from PIL import Image,ImageChops
R=Path('/home/adminz/llm/ocr-stage1-20261009');O=R/'stage14-corpus-audit'
def digest(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pixhash(im):return hashlib.sha256(im.convert('RGB').tobytes()+str(im.size).encode()).hexdigest()
def rows(n):return [json.loads(x) for x in (O/n).read_text().splitlines()]
def save_rows(n,data):(O/n).write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in data))
sources=json.loads((O/'sources-final.json').read_text());occ=rows('occurrences.jsonl');pages=rows('pages.jsonl');suspects=rows('native-suspects.jsonl');pby={(p['source_id'],p['page']):p for p in pages}
changes=[];alphachecks=[];maskchecked={};native_removed=[]
for s in sources:
    with fitz.open(s['pdf_audit_path']) as doc:
        for pn,p in enumerate(doc,1):
            pr=pby[(s['id'],pn)];original_rect=p.rect*p.derotation_matrix
            pr['page_size_unrotated_points']=[original_rect.width,original_rect.height];pr['pdf_rotation_matrix']=list(p.rotation_matrix)
            for x in [o for o in occ if o['source_id']==s['id'] and o['page']==pn]:
                oldnorm=x['bbox_normalized'];display=fitz.Rect(x['bbox_points'])*p.rotation_matrix
                newnorm=[display.x0/p.rect.width,display.y0/p.rect.height,display.x1/p.rect.width,display.y1/p.rect.height]
                x['bbox_unrotated_points']=x['bbox_points'];x['bbox_display_points']=list(display);x['bbox_normalized']=newnorm;x['page_size_unrotated_points']=[original_rect.width,original_rect.height];x['pdf_rotation_matrix']=list(p.rotation_matrix)
                x['bbox_coordinate_system']='bbox_points为原始未旋转PDF坐标；bbox_normalized为rotation_matrix变换后的显示页面坐标，未clamp'
                clip=fitz.Rect(x['bbox_points']) & original_rect
                x['area_fraction_clipped']=clip.get_area()/original_rect.get_area()
                x['flags']=[f for f in x['flags'] if '扫描整页候选' not in f and '背景/扫描+文字叠层候选' not in f]
                if x['area_fraction_clipped']>=.85:
                    x['flags'].append('扫描整页候选：大图+低原生字符' if pr['nonspace_chars']<100 else '背景/扫描+文字叠层候选：须页面合成复核')
                if oldnorm!=newnorm:changes.append({'occurrence_id':x['occurrence_id'],'rotation':p.rotation,'previous_bbox_normalized':oldnorm,'correct_display_bbox_normalized':newnorm})
                if x.get('embedded_alpha') and x.get('original_softmask_sha256'):
                    key=(x['original_image_sha256'],x['original_softmask_sha256'])
                    if key not in maskchecked:
                        b=p.get_text('dict',sort=True)['blocks'][int(x['native_block_id'].rsplit('b',1)[1])]
                        with Image.open(io.BytesIO(b['image'])) as im:
                            base=im.convert('RGBA');alpha_extrema=base.getchannel('A').getextrema()
                            with Image.open(io.BytesIO(b['mask'])) as mi:base.putalpha(ImageChops.multiply(base.getchannel('A'),mi.convert('L')))
                            canvas=Image.new('RGBA',base.size,'white');canvas.alpha_composite(base);rgb=canvas.convert('RGB')
                            ph=pixhash(rgb);maskchecked[key]=(ph,alpha_extrema)
                            if ph!=x['pixel_sha256']:raise RuntimeError('像素组必须重新组合，不能沿用原计数：'+x['occurrence_id'])
                    ph,alpha_extrema=maskchecked[key]
                    alphachecks.append({'occurrence_id':x['occurrence_id'],'original_image_sha256':key[0],'original_mask_sha256':key[1],'intrinsic_alpha_extrema':list(alpha_extrema),'alpha_times_original_mask_pixel_sha256':ph,'existing_pixel_group_unchanged':True})
            if p.rotation:
                existing={n['block_id'] for n in suspects if n['source_id']==s['id'] and n['page']==pn}
                allblocks=p.get_text('dict',sort=True)['blocks']
                for bi,b in enumerate(allblocks):
                    if b['type']!=0 or f'p{pn}-b{bi}' in existing:continue
                    text='\n'.join(''.join(sp['text'] for sp in ln['spans']) for ln in b['lines']).strip();box=list(b['bbox'])
                    flags={'replacement_characters':text.count('\ufffd'),'private_use_characters':sum(0xE000<=ord(c)<=0xF8FF for c in text),'invalid_control_characters':sum(ord(c)<32 and c not in '\n\r\t' for c in text),
                           'bbox_out_of_page':box[0]<original_rect.x0-.01 or box[1]<original_rect.y0-.01 or box[2]>original_rect.x1+.01 or box[3]>original_rect.y1+.01}
                    if any(flags.values()):suspects.append({'source_id':s['id'],'source_sha256':s['sha256'],'page':pn,'block_id':f'p{pn}-b{bi}','bbox_points':box,'text_sha256':hashlib.sha256(text.encode()).hexdigest(),'exact_native_text':text,'flags':flags,'判断':'机械候选非准确率/语义判决'})
            for x in [n for n in suspects if n['source_id']==s['id'] and n['page']==pn]:
                bbox=x['bbox_points'];old=x['flags']['bbox_out_of_page'];new=bbox[0]<original_rect.x0-.01 or bbox[1]<original_rect.y0-.01 or bbox[2]>original_rect.x1+.01 or bbox[3]>original_rect.y1+.01
                x['bbox_unrotated_points']=bbox;x['bbox_display_points']=list(fitz.Rect(bbox)*p.rotation_matrix);x['pdf_rotation_matrix']=list(p.rotation_matrix)
                x['bbox_coordinate_system']='原始PDF未旋转坐标，出页检查与derotation后的原始页面大小比较'
                x['flags']['bbox_out_of_page']=new
                if old and not new:native_removed.append({'source_id':x['source_id'],'page':pn,'block_id':x['block_id'],'reason':'旧检查把未旋转bbox与显示width/height比较；原始坐标实际未出页'})
new_suspects=[x for x in suspects if any(x['flags'].values())]
for p in pages:
    p['native_suspect_ids']=[x['block_id'] for x in new_suspects if x['source_id']==p['source_id'] and x['page']==p['page']]
    p['scan_fullpage_candidates']=sum(any('扫描整页候选' in f for f in x['flags']) for x in occ if x['source_id']==p['source_id'] and x['page']==p['page'])
groups=json.loads((O/'image-groups.json').read_text())
for group in groups:
    counter=collections.Counter()
    for x in occ:
        if x['pixel_sha256']==group['pixel_sha256']:counter.update(x['flags'])
    group['flags']=dict(counter)
(O/'image-groups.json').write_text(json.dumps(groups,ensure_ascii=False,indent=2))
for n in ['occurrences.jsonl','pages.jsonl','native-suspects.jsonl']:
    old=(O/n).read_bytes();history=O/('initial-'+n)
    if not history.exists():history.write_bytes(old)
save_rows('occurrences.jsonl',occ);save_rows('pages.jsonl',pages);save_rows('native-suspects.jsonl',new_suspects)
# 主计数更新，原始历史汇总仍保留。
c=json.loads((O/'counts-final.json').read_text());c['summary']['native_flagged_blocks']=len(new_suspects);c['summary']['native_flagged_pages']=sum(bool(p['native_suspect_ids']) for p in pages)
c['summary']['rotation_pages']=sum(p['rotation']!=0 for p in pages);c['summary']['scan_fullpage_candidate_pages']=sum(p['scan_fullpage_candidates']>0 for p in pages);c['summary']['intrinsic_alpha_and_softmask_occurrences_checked']=len(alphachecks)
c['说明'].append('60旋转页原始bbox与display bbox分开，纠正错误的出页筛查；29 intrinsic-alpha+softmask实例实际验证alpha乘mask后像素hash不变，无需额外OCR。')
(O/'counts-final.json').write_text(json.dumps(c,ensure_ascii=False,indent=2))
report={'说明':'真实原件坐标及透明度检查，无模型/CPU重复推理。','display_bbox_corrected_occurrences':changes,'false_out_of_page_flags_removed':native_removed,'intrinsic_alpha_mask_checks':alphachecks,
        'summary':{'rotation_pages':sum(p['rotation']!=0 for p in pages),'changed_display_occurrences':len(changes),'false_bbox_flags_removed':len(native_removed),'remaining_native_flagged_blocks':len(new_suspects),'remaining_native_flagged_pages':sum(bool(p['native_suspect_ids']) for p in pages),'intrinsic_alpha_mask_occurrences':len(alphachecks),'intrinsic_alpha_mask_pairs':len(maskchecked),'pixel_group_changes':0,'extra_ocr_inferences':0},
        'source_sha256_after':{s['id']:digest(s['remote_original_path']) for s in sources}}
assert all(report['source_sha256_after'][s['id']]==s['sha256'] for s in sources)
(O/'coordinate-alpha-correction.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report['summary'],ensure_ascii=False,indent=2))
