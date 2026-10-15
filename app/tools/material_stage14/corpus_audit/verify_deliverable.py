"""有限交付验证；实跑CPU物化、负例输入与硬计数，不调用模型。"""
import json,hashlib,subprocess,sys,tarfile
from pathlib import Path
APP=Path('D:/HermesProjects/EDUC7703/app');O=APP/'artifacts/stage14/corpus-audit';T=APP/'tools/material_stage14/corpus_audit';PY=APP/'.venv/Scripts/python.exe'
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(n):return json.loads((O/n).read_text(encoding='utf-8'))
def command(args,expected=0):
    proc=subprocess.run([str(PY),'-B',str(T/'materialize_inputs.py'),*args],capture_output=True,text=True,encoding='utf-8',timeout=120)
    assert proc.returncode==expected,(args,proc.returncode,proc.stderr)
    try:data=json.loads(proc.stdout)
    except json.JSONDecodeError:data={'stdout':proc.stdout,'stderr':proc.stderr}
    return {'args':args,'returncode':proc.returncode,'data':data}
report={'说明':'CPU真实执行验证及计数聚合；不是第二模型reviewer，无GPU/服务请求。','checks':[],'gpu_calls':0}
for args in [['--validate-all'],['--priority','sample23'],['--priority','sample24'],['--page','src08:1']]:report['checks'].append(command(args))
report['checks'].append(command(['--page','src08:999'],2))
report['checks'].append(command(['--priority','sample023'],2))
g=load('gpu-priority.json');a=load('audit.json');p=[json.loads(x) for x in (O/'page-units.jsonl').read_text(encoding='utf-8').splitlines()];gs=[json.loads(x) for x in (O/'group-units.jsonl').read_text(encoding='utf-8').splitlines()];u=[json.loads(x) for x in (O/'unresolved-mask-units.jsonl').read_text(encoding='utf-8').splitlines()]
assert len(p)==1338 and len(gs)==2914 and len(u)==15
allids=[i for group in gs for i in group['occurrence_ids']]+[x['occurrence_id'] for x in u]
assert len(allids)==5232==len(set(allids))
assert len({x['task_id'] for x in p})==len(p)
assert g['count']==len(g['jobs'])==34
for pinned,sid,pn in [('sample23','src22',8),('sample24','src23',4)]:
    job=next(x for x in g['jobs'] if x['case_id']==pinned);assert job['source_id']==sid and job['page']==pn
assert all(x['source_sha256']==next(s['sha256'] for s in a['originals'] if s['id']==x['source_id']) for x in g['jobs'])
# portable已有34真实输入，供远端读取；复制字节，不生成新内容。
with tarfile.open(O/'priority-bundle.tar.gz','w:gz') as tf:
    for j in g['jobs']:tf.add(j['input_path'],arcname='priority-bundle/'+j['case_id']+'.png')
report['hard_counts']={'sources':len(a['originals']),'pages':len(p),'pixel_groups':len(gs),'unresolved_mask_instances':len(u),'all_image_occurrence_ids':len(allids),'duplicate_or_missing_occurrence_ids':0,'priority_jobs':len(g['jobs'])}
report['originals_all_local_hashes_still_match']=all(sha(s['strict_original_path'])==s['sha256'] for s in a['originals']);assert report['originals_all_local_hashes_still_match']
report['priority_bundle_sha256']=sha(O/'priority-bundle.tar.gz');report['scripts']={p.name:sha(p) for p in T.glob('*.py')};report['status']='通过：真实CPU渲染/复制/严格token负例/所有数量闭合；视觉整体未验收'
(O/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':report['status'],'counts':report['hard_counts'],'checks_returncodes':[x['returncode'] for x in report['checks']],'all_originals_still_match':True},ensure_ascii=False,indent=2))
