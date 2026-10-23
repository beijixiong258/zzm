"""Prepare portable source/sample payload and preserve interrupted local OCR."""
from pathlib import Path
import collections,json,shutil,sys,tarfile,time
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.ocr_stage1 import budget
from tools.ocr_stage1.prepare_samples import OUT,dump,absolute,sha
BASE=ROOT/'artifacts/ocr-stage1/baseline'

def rel(path):return Path(path).resolve().relative_to(OUT.resolve()).as_posix()

def portable():
    budget.check();BASE.mkdir(parents=True,exist_ok=True)
    pre=BASE/'local_preflight';pre.mkdir(parents=True,exist_ok=True)
    # Retain original raw bytes: move, do not rewrite OCR records.
    for name in ('rapidocr.jsonl','engine.json','rapidocr-summary.json','platform-files.jsonl','platform-summary.json'):
        p=BASE/name
        if p.is_file() and not (pre/name).exists():p.rename(pre/name)
    local=[]
    if (pre/'rapidocr.jsonl').is_file():local=[json.loads(line) for line in (pre/'rapidocr.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    latest={r['id']:r for r in local}
    scope={'evaluation_scope':'local_preflight','final_comparison_eligible':False,'stop_reason':'User directed all final CPU/GPU/model tests to Ubuntu-gpu-server. Owned Windows OCR process was terminated immediately. Raw completed records retained unchanged.','records_completed':len(latest),'sample_ids_completed':sorted(latest),'status_counts':dict(collections.Counter(r['status'] for r in latest.values())),'total_completed_image_seconds':sum(r['elapsed_seconds'] for r in latest.values()),'expected_final_sample_count':24,'file_level_baseline_started':False,'remaining_sample_ids':[f'sample{n:02d}' for n in range(1,25) if f'sample{n:02d}' not in latest],'accuracy_measured':False}
    dump(pre/'scope.json',scope)
    inv=json.loads((OUT/'inventory.json').read_text(encoding='utf-8'))
    for source in inv['sources']:
        budget.check();dest=OUT/'sources'/f"{source['id']}.{source['type']}";dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists():shutil.copy2(source['path'],dest)
        assert sha(dest)==source['sha256'];source['source_relpath']=rel(dest)
        for pageskey in ('pages','rendered_pages'):
            for page in source.get(pageskey,[]):
                if page.get('native_text_path'):page['native_text_relpath']=rel(page['native_text_path'])
        if source.get('native_text_path'):source['native_text_relpath']=rel(source['native_text_path'])
        if source.get('rendered_pdf_path'):source['rendered_pdf_relpath']=rel(source['rendered_pdf_path'])
        for slide in source.get('slides',[]):
            for key in ('native_text_path','notes_text_path'):slide[key.replace('_path','_relpath')]=rel(slide[key])
    dump(OUT/'inventory.json',inv)
    dump(OUT/'sources.json',{'count':len(inv['sources']),'sources':[{k:s[k] for k in ('id','path','bytes','sha256','type','session','input_gate','source_relpath')} for s in inv['sources']],'mapping_note':'Absolute original paths retained for provenance; source_relpath is relative to transferred dataset root. Copies are exact source bytes, not Office-converted replacements.'})
    manifest=json.loads((OUT/'samples.json').read_text(encoding='utf-8'));lookup={s['id']:s for s in inv['sources']}
    for sample in manifest['samples']:
        budget.check();sample['image_relpath']=rel(sample['image_path']);sample['native_text_relpath']=rel(sample['native_text_path']) if sample['native_text_path'] else None;sample['source_relpath']=lookup[sample['source_id']]['source_relpath']
        if sample['unit_kind']!='pdf_page':sample['render_source_relpath']=rel(sample['render_source_path'])
        else:sample['render_source_relpath']=sample['source_relpath']
    manifest['path_mapping_note']='Use relative paths under --dataset on Linux. Preserve original logical IDs and absolute provenance fields.';dump(OUT/'samples.json',manifest)
    # Snapshot the exact current parser and already installed CPU weights. No
    # candidate downloads, dependency installs, platform changes or inference.
    runtime=OUT/'runtime_reference';runtime.mkdir(parents=True,exist_ok=True)
    original=json.loads((pre/'engine.json').read_text(encoding='utf-8'));dump(runtime/'engine.json',original)
    for model in original['models']:
        budget.check();dest=runtime/'models'/model['name'];dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists():shutil.copy2(model['path'],dest)
        assert sha(dest)==model['sha256']
    modules=['backend/__init__.py','backend/aicademiya/__init__.py','backend/aicademiya/material_extraction.py','backend/aicademiya/worksheet_import.py','backend/aicademiya/extraction_limits.py'];modulemanifest=[]
    for name in modules:
        budget.check();src=ROOT/name;dest=runtime/'platform_root'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest);modulemanifest.append({'path':name,'sha256':sha(src),'copy_sha256':sha(dest),'bytes':src.stat().st_size})
    dump(runtime/'platform_modules.json',{'modules':modulemanifest,'note':'Exact unchanged source-file copies for server import; no database, credential, app configuration or service files.'})
    print(json.dumps(scope,indent=2));print('PORTABLE_SOURCES',len(inv['sources']),'PORTABLE_SAMPLES',manifest['count'])

def bundle():
    budget.check();archive=BASE/'dataset-transfer.tar.gz';started=time.perf_counter();members=sorted(p for p in OUT.rglob('*') if p.is_file());total=0
    with tarfile.open(archive,'w:gz',compresslevel=3) as tar:
        for n,p in enumerate(members):
            if n%20==0:budget.check()
            tar.add(p,arcname='dataset/'+p.relative_to(OUT).as_posix(),recursive=False);total+=p.stat().st_size
        tar.add(ROOT/'tools/ocr_stage1/baseline.py',arcname='baseline.py',recursive=False)
    meta={'path':absolute(archive),'sha256':sha(archive),'bytes':archive.stat().st_size,'dataset_file_count':len(members),'uncompressed_dataset_bytes':total,'elapsed_seconds':time.perf_counter()-started,'contains':'All23 original-file copies,24 image samples, full native text, Office exports, contact sheets, existing CPU-model files, unchanged parser snapshot and portable baseline.py. Local_preflight OCR is NOT included.'}
    dump(BASE/'transfer-manifest.json',meta);print(json.dumps(meta,indent=2))

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='bundle':bundle()
    else:portable()
