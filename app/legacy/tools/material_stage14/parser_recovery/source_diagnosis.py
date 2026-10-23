"""Read-only retained source/output diagnosis. No inference/network/model calls."""
import hashlib,json,struct,subprocess
from pathlib import Path
R=Path('/home/adminz/llm/ocr-stage1-20261009')
O=R/'stage14-parser-recovery'
def digest(p):
    with p.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def gguf(p):
    with p.open('rb')as f:
        def read(fmt):return struct.unpack('<'+fmt,f.read(struct.calcsize('<'+fmt)))[0]
        def text():return f.read(read('Q')).decode('utf-8')
        def val(t):
            if t==8:return text()
            if t==9:
                subtype,n=read('I'),read('Q');return [val(subtype)for _ in range(n)]
            return read({0:'B',1:'b',2:'H',3:'h',4:'I',5:'i',6:'f',7:'?',10:'Q',11:'q',12:'d'}[t])
        if f.read(4)!=b'GGUF':raise ValueError('Not GGUF')
        version,nt,nk=read('I'),read('Q'),read('Q');meta={}
        for _ in range(nk):
            k=text();v=val(read('I'))
            if not k.startswith('tokenizer.') and not isinstance(v,list):meta[k]=v
        tensors=[]
        for _ in range(nt):
            name=text();nd=read('I');shape=[read('Q')for _ in range(nd)];typ,off=read('I'),read('Q')
            if name.startswith(('v.','mm.','vision','mtp')) or 'embd' in name:tensors.append({'name':name,'shape':shape,'type':typ})
        return {'path':str(p),'bytes':p.stat().st_size,'sha256':digest(p),'version':version,'tensor_count':nt,'metadata':meta,'selected_tensors':tensors[:35]}
report={'bundles':{},'originals':{},'models':[],'cpu':{}}
for name in ('gpu-additive-literal-final','gpu-final','native-v2/bundles'):
    root=R/'stage13-parser'/name;rows=[]
    for mp in sorted(root.rglob('manifest.json')):
        m=json.loads(mp.read_text());blocks=[b for page in m['pages']for b in page['blocks']]
        raw=[]
        for p in sorted(mp.parent.glob('raw/*-region*.json')):
            d=json.loads(p.read_text());raw.append({'file':str(p.relative_to(mp.parent)),'sha256':digest(p),'page':d.get('original_pdf_page'),'chars':len(d.get('raw_text','')),'generation_finish_reason_available':d.get('generation_finish_reason_available'),'tail':d.get('raw_text','')[-180:]})
        rows.append({'bundle':str(mp.parent.relative_to(root)),'source_sha256':m['source_sha256'],'complete':m['complete'],'page_count':m['page_count'],'represented_pages':len(m['pages']),'quality_counts':{q:sum(b['quality']==q for b in blocks)for q in ('extracted','needs_review','approved')},'coverage':m.get('coverage'),'raw_regions':raw})
    report['bundles'][name]=rows
for id in ('src01','src23','src16','src17','src15'):
    p=next((R/'data/dataset/sources').glob(id+'.*'));report['originals'][id]={'sha256':digest(p),'bytes':p.stat().st_size,'path':str(p)}
for p in Path('/home/adminz/llm/models/Qwen3.8-27B-GSQ-RCO-IQ3_XXS-Uncensored').glob('*.gguf'):report['models'].append(gguf(p))
report['commands']=[s for s in subprocess.run(['ps','-eo','pid,args'],capture_output=True,text=True).stdout.splitlines()if 'llama-server' in s and 'python' not in s]
base=R/'.venv-baseline/lib/python3.12/site-packages/rapidocr'
report['cpu']['config']=(base/'config.yaml').read_text()if(base/'config.yaml').is_file()else ''
report['cpu']['models']=[{'path':str(p),'sha256':digest(p),'bytes':p.stat().st_size}for p in (base/'models').glob('*')]
(O/'source-diagnosis.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({'saved':str(O/'source-diagnosis.json'),'bundle_counts':{k:len(v)for k,v in report['bundles'].items()},'models':[{k:v for k,v in m.items()if k!='selected_tensors'}for m in report['models']],'commands':report['commands'],'cpu':report['cpu']},ensure_ascii=False,indent=2))
