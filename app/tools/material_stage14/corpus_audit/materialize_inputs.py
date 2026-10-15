"""只做CPU输入物化/验证，不含GPU/HTTP/模型客户端。
Windows用app/.venv/Scripts/python.exe；Linux在独立审计目录用research python。
所有输出固定落在corpus-audit/materialized/。"""
import os
os.environ.update(CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1')
import argparse,json,hashlib,re,sys
from pathlib import Path

def digest(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def check_sha(p,sha):
    if not re.fullmatch('[0-9a-f]{64}',sha):raise ValueError('输入SHA格式无效；不更正token')
    if digest(p)!=sha:raise ValueError('真实输入SHA不匹配，停止物化：'+str(p))
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    default=Path(__file__).resolve().parent if os.name!='nt' else Path(__file__).resolve().parents[3]/'artifacts/stage14/corpus-audit'
    parser.add_argument('--root',type=Path,default=default)
    g=parser.add_mutually_exclusive_group(required=True)
    g.add_argument('--list-priority',action='store_true');g.add_argument('--validate-all',action='store_true');g.add_argument('--page');g.add_argument('--group');g.add_argument('--priority')
    a=parser.parse_args();root=a.root.resolve();manifest=load(root/'audit.json');jobs=load(root/'gpu-priority.json')['jobs']
    if a.list_priority:
        print(json.dumps([{'case_id':j['case_id'],'priority':j['priority'],'source_id':j['source_id'],'page':j['page'],'input_sha256':j['input_sha256'],'next_action':j['next_action']} for j in jobs],ensure_ascii=False,indent=2));return 0
    if a.validate_all:
        checked=[]
        for name,ref in manifest['files'].items():check_sha(root/name,ref['sha256']);checked.append(name)
        # 本地/remote优先输入复制后各项local_input_path需存在；remote只做page/group输入时不依赖Windows路径。
        inputs_checked=0
        for j in jobs:
            p=Path(j['input_path'])
            if not p.is_file():p=root/'priority-bundle'/f'{j["case_id"]}.png'
            check_sha(p,j['input_sha256']);inputs_checked+=1
        summary={'状态':'清单与全部有限优先输入hash验证通过','manifest_files_checked':len(checked),'priority_inputs_checked':inputs_checked,'gpu_calls':0,'source_writes':0}
        print(json.dumps(summary,ensure_ascii=False,indent=2));return 0
    dest=root/'materialized';dest.mkdir(exist_ok=True)
    if a.priority:
        selected=[j for j in jobs if j['case_id']==a.priority]
        if len(selected)!=1:raise ValueError('case_id必须原样精确匹配；不重编号')
        j=selected[0];p=Path(j['input_path'])
        if not p.is_file():p=root/'priority-bundle'/f'{j["case_id"]}.png'
        check_sha(p,j['input_sha256'])
        out=dest/(j['case_id']+'.png');out.write_bytes(p.read_bytes());check_sha(out,j['input_sha256'])
        result={**j,'materialized_input':str(out),'gpu_calls':0,'状态':'真实输入已验证复制；未请求模型'}
    elif a.group:
        if not re.fullmatch('[0-9a-f]{64}',a.group):raise ValueError('原始pixel SHA格式不匹配')
        gs=load(root/'image-groups.json');selected=[x for x in gs if x['pixel_sha256']==a.group]
        if len(selected)!=1:raise ValueError('pixel group未知或不唯一')
        j=selected[0];p=Path(j['asset'])
        if not p.is_file():p=root/'assets'/f'{j["pixel_sha256"]}.png'
        check_sha(p,j['asset_sha256']);out=dest/('group-'+a.group+'.png');out.write_bytes(p.read_bytes());check_sha(out,j['asset_sha256'])
        result={'pixel_sha256':a.group,'input_path':str(out),'input_sha256':digest(out),'all_occurrence_ids':j['occurrence_ids'],'gpu_calls':0,'状态':'仅复制源hash绑定组合像素；页面背景/叠层不自动通过'}
    else:
        # 页数按物理页，严格srcNN:N token，不改错标点或编号。
        if not re.fullmatch(r'src\d{2}:[1-9]\d*',a.page):raise ValueError('page token须严格srcNN:N')
        sid,pn=a.page.split(':');pn=int(pn)
        sources={s['id']:s for s in manifest['originals']}
        if sid not in sources:raise ValueError('未知source token')
        s=sources[sid];original=Path(s['strict_original_path']) if os.name=='nt' else Path(s['remote_original_path']);check_sha(original,s['sha256'])
        pdf=original if s['type']=='pdf' else Path(s['pdf_audit_path'])
        check_sha(pdf,s['pdf_sha256'])
        import pymupdf as fitz
        out=dest/(sid+f'-page{pn:04}.png')
        with fitz.open(pdf) as doc:
            if not 1<=pn<=len(doc):raise ValueError('物理页号越界')
            page=doc[pn-1];page.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False).save(out)
            result={'source_id':sid,'source_sha256':s['sha256'],'pdf_sha256':s['pdf_sha256'],'page':pn,'source_bbox_normalized':[0,0,1,1],
                    'source_size_points':[page.rect.width,page.rect.height],'render_matrix':[2,0,0,2,0,0],'input_path':str(out),'input_sha256':digest(out),'gpu_calls':0,'状态':'实际源页面CPU渲染；非识别/语义通过'}
        check_sha(original,s['sha256'])
    report=dest/(('priority-'+a.priority if a.priority else 'group-'+a.group if a.group else a.page.replace(':','-'))+'.json')
    report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0
if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError,KeyError) as e:print('CPU输入物化失败：'+str(e),file=sys.stderr);raise SystemExit(2)
