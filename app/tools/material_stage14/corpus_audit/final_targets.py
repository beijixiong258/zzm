"""最终口径对齐和源crop导出；只读取原件与历史bundle，只写审计目录。"""
import json,hashlib,tarfile,io
from pathlib import Path
import pymupdf as fitz
R=Path('/home/adminz/llm/ocr-stage1-20261009');O=R/'stage14-corpus-audit';B=R/'stage13-parser/native-v2/bundles'
def digest(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
s=json.loads((O/'sources-refined.json').read_text());count=json.loads((O/'count-refinement.json').read_text());cfg=[]
for r in s:
    corrections=[];m=json.loads((B/r['id']/'manifest.json').read_text())
    with fitz.open(r['pdf_audit_path']) as doc:
        for pn in r['native_text_different_pages']:
            a=doc[pn-1].get_text('dict',sort=True)['blocks'];b=doc[pn-1].get_text('dict',sort=True,flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)['blocks']
            def texts(blocks):return ['\n'.join(''.join(sp['text'] for sp in ln['spans']) for ln in x['lines']) for x in blocks if x['type']==0]
            aa=texts(a);bb=texts(b);old=[x['text'] for x in m['pages'][pn-1]['blocks'] if x['type']=='text']
            assert aa==old,(r['id'],pn)
            corrections.append({'source_id':r['id'],'page':pn,'default_dict_characters':sum(map(len,aa)),'text_only_flags_characters':sum(map(len,bb)),
                                'default_equals_retained_manifest':True,'说明':'关闭PRESERVE_IMAGES会改变某些text分块；这是抽取口径差异，不是源文本丢失。'})
    r['actual_native_text_chars_default']=r['actual_native_text_chars_no_trim']+sum(x['default_dict_characters']-x['text_only_flags_characters'] for x in corrections)
    assert r['actual_native_text_chars_default']==r['historical_native_text_chars']
    r['native_text_default_matches_retained']=True;cfg.extend(corrections)
(O/'sources-final.json').write_text(json.dumps(s,ensure_ascii=False,indent=2))
count['summary']['native_text_chars_text_only_flags']=count['summary']['native_text_chars']
count['summary']['native_text_chars']=sum(x['actual_native_text_chars_default'] for x in s)
count['summary']['native_text_default_mismatch_pages']=0;count['summary']['native_text_text_only_flag_affected_pages']=len(cfg)
count['summary'].pop('native_text_sequence_mismatch_pages',None)
count['extractor_configuration_evidence']=cfg
count['说明'].append('最终native_text_chars采用与Stage13一致的默认dict、不trim、保留images口径；同口径逐项一致1755098。text-only flags1755124只保留为中间方法差异，不能当OCR补字。')
(O/'counts-final.json').write_text(json.dumps(count,ensure_ascii=False,indent=2))
# 对原始mask尺寸不相同的15实例，不任意重采样mask。直接从源页面渲染实际clip并保留transform。
occ=[json.loads(x) for x in (O/'occurrences.jsonl').read_text().splitlines()];crops=[]
for x in occ:
    if x['decode_status']=='完成':continue
    src=next(r for r in s if r['id']==x['source_id'])
    with fitz.open(src['pdf_audit_path']) as doc:
        page=doc[x['page']-1];box=fitz.Rect(x['bbox_points']);path=O/'assets'/('fallback-'+x['occurrence_id'].replace('/','-')+'.png')
        pm=page.get_pixmap(matrix=fitz.Matrix(4,4),clip=box,alpha=False);pm.save(path)
        crops.append({'occurrence_id':x['occurrence_id'],'source_id':x['source_id'],'source_sha256':x['source_sha256'],'page':x['page'],'bbox_points':x['bbox_points'],'bbox_normalized':x['bbox_normalized'],
                      'input_kind':'实际原PDF页面clip渲染：包括softmask/背景/文字叠层；不是重新组合旧黑底图片',
                      'render_matrix':[4,0,0,4,0,0],'asset':str(path),'asset_sha256':digest(path),'size':[pm.width,pm.height],'scope':'渲染成功，仅有真实像素；mask本身是否语义修复/文字准确未判通过'})
(O/'mask-fallback-inputs.json').write_text(json.dumps(crops,ensure_ascii=False,indent=2))
# 导出有限CPU输入供父会话核图；全量2914独特像素资产仍留审计remote目录。
cpu=json.loads((O/'cpu-sampling.json').read_text());selected=[]
for c in cpu['cases']:
    p=Path(c['input_path']);selected.append((p,'review-inputs/'+c['case_id']+'.png'))
for sid,pn in [('src11',1),('src19',1),('src03',127),('src01',49)]:
    m=json.loads((B/sid/'manifest.json').read_text());p=B/sid/m['pages'][pn-1]['image'];selected.append((p,f'review-inputs/page-{sid}-{pn}.png'))
with tarfile.open(O/'review-inputs.tar.gz','w:gz') as tar:
    for p,name in selected:tar.add(p,arcname=name)
    for row in crops:tar.add(row['asset'],arcname='review-inputs/'+Path(row['asset']).name)
manifest=[{'archive_member':name,'source_path':str(p),'sha256':digest(p)} for p,name in selected]
manifest+=[{'archive_member':'review-inputs/'+Path(x['asset']).name,'source_path':x['asset'],'sha256':x['asset_sha256']} for x in crops]
(O/'review-inputs-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print('最终字符计数',count['summary']['native_text_chars'],'配置差异页',len(cfg),'fallback instances',len(crops),'review inputs',len(manifest),flush=True)
