"""只读原始 inventory 和本地原件；仅向本审计产物目录写入。"""
import hashlib,json,subprocess,shlex
from pathlib import Path
APP=Path('D:/HermesProjects/EDUC7703/app')
OUT=APP/'artifacts/stage14/corpus-audit'
OUT.mkdir(parents=True,exist_ok=True)
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
inventory=APP/'artifacts/ocr-stage1/dataset/inventory.json'
data=json.loads(inventory.read_text(encoding='utf-8'))
assert data['count']==23==len(data['sources'])
assert len({s['id'] for s in data['sources']})==23
rows=[]
for s in data['sources']:
    p=Path(s['path']); actual=sha(p)
    row={k:v for k,v in s.items() if k!='pages'}
    row.update(original_token=p.name,strict_original_path=s['path'],local_sha256_before=actual,local_bytes=p.stat().st_size,inventory_hash_matches=actual==s['sha256'])
    assert row['inventory_hash_matches'],s['id']
    rows.append(row)
out={'说明':'原始token/path不改写；本地真实原件SHA已逐项读取；页面与图像数量须由远端原件或已绑定的Office预览重新清点。','inventory_path':str(inventory),'inventory_sha256':sha(inventory),'sources':rows,'local_sources_all_match':True}
(OUT/'inputs.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print('sources:',len(rows),'local originals hash matched:',sum(r['inventory_hash_matches'] for r in rows))
remote='/home/adminz/llm/ocr-stage1-20261009/stage14-corpus-audit'
subprocess.run(['ssh','-o','BatchMode=yes','ubuntu-gpu','mkdir -p '+shlex.quote(remote)],check=True,timeout=60)
subprocess.run(['scp',str(OUT/'inputs.json'),'ubuntu-gpu:'+remote+'/inputs.json'],check=True,timeout=60)
print('输入清单已传至独立CPU审计目录；源文件未传写。')
