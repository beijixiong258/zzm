"""补齐字符口径与失败实例计数；不重做像素全量清点。保留初始机械报告。"""
import json,hashlib,collections,io
from pathlib import Path
import pymupdf as fitz
from PIL import Image
R=Path('/home/adminz/llm/ocr-stage1-20261009');O=R/'stage14-corpus-audit';B=R/'stage13-parser/native-v2/bundles'
def digest(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
s=json.loads((O/'sources.json').read_text());occ=[json.loads(x) for x in (O/'occurrences.jsonl').read_text().splitlines()]
g=json.loads((O/'image-groups.json').read_text());rows=[]
for r in s:
    m=json.loads((B/r['id']/'manifest.json').read_text());stored=sum(len(b['text']) for p in m['pages'] for b in p['blocks'])
    rawchars=0;normalized_match=True;diffpages=[]
    with fitz.open(r['pdf_audit_path']) as doc:
        for pi,p in enumerate(doc):
            textblocks=p.get_text('dict',sort=True,flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)['blocks']
            text=['\n'.join(''.join(sp['text'] for sp in ln['spans']) for ln in b['lines']) for b in textblocks]
            rawchars+=sum(len(x) for x in text)
            historical=[b['text'] for b in m['pages'][pi]['blocks'] if b['type']=='text']
            if text!=historical:diffpages.append(pi+1)
    r['actual_native_text_chars_no_trim']=rawchars;r['historical_native_text_chars']=stored;r['native_text_sequence_matches_retained_manifest']=not diffpages;r['native_text_different_pages']=diffpages
    rows.append({'id':r['id'],'raw_no_trim':rawchars,'trimmed':r['actual_native_text_chars'],'retained':stored,'diff_pages':diffpages})
fails=[x for x in occ if x['decode_status']!='完成'];failed_pairs={ (x['original_image_sha256'],x['original_softmask_sha256']) for x in fails}
failed_detail=[]
for x in fails:
    with fitz.open(next(r['pdf_audit_path'] for r in s if r['id']==x['source_id'])) as doc:
        b=doc[x['page']-1].get_text('dict',sort=True)['blocks'][int(x['native_block_id'].rsplit('b',1)[1])]
        with Image.open(io.BytesIO(b['image'])) as im:base_size=list(im.size)
        with Image.open(io.BytesIO(b['mask'])) as im:mask_size=list(im.size)
    failed_detail.append({**x,'original_image_size':base_size,'original_mask_size':mask_size,'后续动作':'用原PDF页面clip渲染核对；本审计不任意缩放mask，不改parser。'})
summary=json.loads((O/'mechanical-summary.json').read_text())['summary']
summary.update(native_text_chars=sum(r['actual_native_text_chars_no_trim'] for r in s),native_text_chars_trimmed=sum(r['actual_native_text_chars'] for r in s),
               native_manifest_text_chars=sum(r['historical_native_text_chars'] for r in s),native_text_sequence_mismatch_pages=sum(len(r['native_text_different_pages']) for r in s),
               decoded_image_occurrences=len(occ)-len(fails),image_decode_failed_occurrences=len(fails),image_decode_failed_original_pairs=len(failed_pairs),
               repeated_decoded_pixel_occurrences=(len(occ)-len(fails))-len(g))
summary.pop('repeated_pixel_occurrences',None);summary.pop('image_decode_failures',None)
out={'summary':summary,'characters_comparison':rows,'unresolved_mask_instances':failed_detail,
     '说明':['原生字符基线不trim每个block；trim后的字符只是另一个口径，不是缺失字符/准确率。','初始mechanical-summary.json中image_decode_failures=1是失败原图+mask对数；实际受影响实例须按完整occurrences重算。','pixel重复只对成功组合的实例计算，未成功组合的实例不冒充重复像素。']}
(O/'count-refinement.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
(O/'sources-refined.json').write_text(json.dumps(s,ensure_ascii=False,indent=2))
print(json.dumps(summary,ensure_ascii=False,indent=2))
print('char source diffs:',[(x['id'],x['raw_no_trim']-x['retained']) for x in rows if x['raw_no_trim']!=x['retained']])
print('mask dimensions:',base_size,mask_size,'affected:',len(fails),'pages:',sorted(set(x['page'] for x in fails)))
