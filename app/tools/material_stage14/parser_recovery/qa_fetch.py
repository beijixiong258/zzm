"""Read ONLY parent's explicitly authorized QA bundle/source via PVE pct exec."""
import argparse,base64,hashlib,json,shlex,subprocess
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'artifacts/stage14/parser-recovery/qa-fresh-scan'
BASE='/var/lib/aicademiya-qa/stage14-native-0986d5dd/scan-bundle-r1'
SOURCE='/var/lib/aicademiya-qa/stage14-native-0986d5dd/src14.pdf'
PREFIX=['ssh','-i','C:/Users/17193/.ssh/id_ed25519_aicademiya_pve','-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes','root@192.168.10.16']

def call(code):
    result=subprocess.run(PREFIX+['pct exec 255 -- python3 -c '+shlex.quote(code)],capture_output=True,text=True,check=True,timeout=90)
    return json.loads(result.stdout)

def fetch(ref):
    rel=PurePosixPath(ref)
    if rel.is_absolute()or '..'in rel.parts or '\\'in ref:raise ValueError('Only authorized QA relative files')
    answer=call('import base64,hashlib,json;from pathlib import Path;r=Path('+repr(BASE)+');p=r/'+repr(ref)+';assert p.resolve().is_relative_to(r);d=p.read_bytes();print(json.dumps({"sha256":hashlib.sha256(d).hexdigest(),"data":base64.b64encode(d).decode()}))')
    data=base64.b64decode(answer['data']);assert hashlib.sha256(data).hexdigest()==answer['sha256']
    path=OUT/ref;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    return {'file':ref,'bytes':len(data),'sha256':answer['sha256']}

parser=argparse.ArgumentParser();parser.add_argument('--image',action='append',default=[]);args=parser.parse_args()
OUT.mkdir(parents=True,exist_ok=True)
if args.image:
    rows=[fetch(ref)for ref in args.image];print(json.dumps(rows,indent=2));raise SystemExit(0)
listing=call('import hashlib,json;from pathlib import Path;r=Path('+repr(BASE)+');p=Path('+repr(SOURCE)+');print(json.dumps({"source_sha256":hashlib.file_digest(p.open("rb"),"sha256").hexdigest(),"source_bytes":p.stat().st_size,"raw_receipts":[str(p.relative_to(r))for p in r.glob("raw/*.json")]}))')
refs=['manifest.json','receipt.json',*listing['raw_receipts']]
answer=call('import base64,hashlib,json;from pathlib import Path;r=Path('+repr(BASE)+');refs='+repr(refs)+';files={};total=0\nfor ref in refs:\n p=r/ref;assert p.resolve().is_relative_to(r);d=p.read_bytes();total+=len(d);assert total<=24*1024*1024;files[ref]={"sha256":hashlib.sha256(d).hexdigest(),"data":base64.b64encode(d).decode()}\nprint(json.dumps(files))')
rows=[]
for ref,value in answer.items():
    data=base64.b64decode(value['data']);assert hashlib.sha256(data).hexdigest()==value['sha256']
    path=OUT/ref;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    rows.append({'file':ref,'bytes':len(data),'sha256':value['sha256']})
m=json.loads((OUT/'manifest.json').read_text());blocks=[b for p in m['pages']for b in p['blocks']]
report={'authorization_scope':'exact QA bundle and src14.pdf only; read-only CT255/PVE','source':listing,
        'manifest_sha256':m['source_sha256'],'transport':rows,'page_count':m['page_count'],'complete':m['complete'],
        'table_candidates':[{'page':p['number'],'block_id':b['id'],'bbox':b['bbox'],'quality':b['quality'],'text':b['text'],'assets':b['assets']}for p in m['pages']for b in p['blocks']if b['type']in ('table','equation','other')],
        'blocks':len(blocks),'quality_counts':{q:sum(b['quality']==q for b in blocks)for q in ('extracted','needs_review','excluded','approved')}}
assert listing['source_sha256']==m['source_sha256']=='5ffdc6a8dce6d5136397afb13bcaf627a5396f8c004ab1007d6493981ca8e723'
(OUT/'read-only-diagnosis.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items()if k not in ('transport','table_candidates','source')},indent=2))
print(json.dumps([{'page':b['page'],'id':b['block_id'],'chars':len(b['text']),'head':b['text'][:180]}for b in report['table_candidates']],indent=2))
