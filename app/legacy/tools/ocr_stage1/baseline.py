"""Current installed CPU OCR and unchanged platform extraction benchmark."""
from pathlib import Path
import argparse, collections, hashlib, importlib.metadata, json, os, platform, shlex, signal, subprocess, sys, time
ROOT=Path(__file__).resolve().parents[2]
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[k]='2'
os.environ['CUDA_VISIBLE_DEVICES']='-1'
OUT=ROOT/'artifacts/ocr-stage1/baseline';DATA=ROOT/'artifacts/ocr-stage1/dataset'
CONTROL=DATA.parent; BUDGET_STATUS=CONTROL/'budget-status.json'; BUDGET_COMMAND=None
APP_ROOT=ROOT; REFERENCE_ENGINE=None

def gate():
    stop=CONTROL/'STOP'
    if stop.exists():raise SystemExit('PAUSED: '+stop.read_text(encoding='utf-8'))
    if os.name=='nt':
        # Only data validation is permitted locally after the scope change.
        from tools.ocr_stage1 import budget
        budget.check();return
    if BUDGET_COMMAND:
        p=subprocess.run(shlex.split(BUDGET_COMMAND),capture_output=True,text=True,timeout=75)
        if p.returncode:raise SystemExit('PAUSED: quota refresh command failed')
        try:status=json.loads(p.stdout)
        except ValueError:raise SystemExit('PAUSED: quota refresh returned no JSON status')
        dump(BUDGET_STATUS,status)
    else:
        try:status=json.loads(BUDGET_STATUS.read_text(encoding='utf-8'))
        except (OSError,ValueError):raise SystemExit('PAUSED: fresh mirrored quota status unavailable')
    if time.time()-status.get('checked_epoch',0)>120:raise SystemExit('PAUSED: quota status is stale; parent must refresh it')
    if status.get('paused') or status.get('remaining_min_percent',0)<1:raise SystemExit('PAUSED: quota below user threshold')

def asset(row,absolute_key,relative_key):
    if row.get(relative_key):return (DATA/row[relative_key]).resolve()
    return Path(row[absolute_key])

def validate():
    gate();samples=json.loads((DATA/'samples.json').read_text(encoding='utf-8'))
    inv=json.loads((DATA/'inventory.json').read_text(encoding='utf-8'))
    assert samples['count']==24 and len(samples['samples'])==24
    assert len({s['id'] for s in samples['samples']})==24
    assert len(inv['sources'])==23 and inv['count']==23
    assert {s['source_id'] for s in samples['samples']}=={s['id'] for s in inv['sources']}
    checked=[]
    for row in samples['samples']:
        gate();image=asset(row,'image_path','image_relpath');assert image.is_file(),image
        assert hashlib.sha256(image.read_bytes()).hexdigest()==row['image_sha256']
        if row['native_text_path']:assert asset(row,'native_text_path','native_text_relpath').is_file()
        checked.append(row['id'])
    for row in inv['sources']:
        gate();path=asset(row,'path','source_relpath');assert path.is_file(),path
        assert hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256']
    print(json.dumps({'status':'validated_without_OCR','sample_ids':checked,'source_count':23,'sample_count':24,'dataset':str(DATA),'platform_module_root':str(APP_ROOT)},indent=2))

def dump(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def append(path,row):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
def latest(path):
    rows={}
    if path.is_file():
        for line in path.read_text(encoding='utf-8').splitlines():
            if line.strip():
                row=json.loads(line)
                previous=rows.get(row['id'])
                if path.name=='rapidocr.jsonl' and previous and previous['status'] in {'ok','no_text'} and row['status'] not in {'ok','no_text'}:
                    continue
                rows[row['id']]=row
    return rows

def plain(value):
    if hasattr(value,'tolist'):return value.tolist()
    if isinstance(value,(list,tuple)):return [plain(v) for v in value]
    if isinstance(value,dict):return {k:plain(v) for k,v in value.items()}
    return value

def engine_info(engine):
    import rapidocr,onnxruntime
    versions={}
    for name in ('rapidocr','onnxruntime','numpy','pillow','pymupdf','python-pptx','python-docx'):
        try:versions[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:versions[name]=None
    modelroot=Path(rapidocr.__file__).parent/'models';models=[]
    for name in ('PP-OCRv6_det_small.onnx','ch_ppocr_mobile_v2.0_cls_mobile.onnx','PP-OCRv6_rec_small.onnx'):
        p=modelroot/name;models.append({'name':name,'path':str(p.resolve()),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    sessions=[]
    # Inspect actual object sessions, not merely installed available providers.
    seen=set()
    def walk(obj,label,depth):
        if id(obj) in seen or depth>5:return
        seen.add(id(obj))
        if isinstance(obj,onnxruntime.InferenceSession):
            opt=obj.get_session_options();sessions.append({'path':label,'providers':obj.get_providers(),'intra_op_num_threads':opt.intra_op_num_threads,'inter_op_num_threads':opt.inter_op_num_threads});return
        if hasattr(obj,'__dict__'):
            for k,v in vars(obj).items():
                if hasattr(v,'__dict__') or isinstance(v,onnxruntime.InferenceSession):walk(v,label+'.'+k,depth+1)
    walk(engine,'engine',0)
    if REFERENCE_ENGINE:
        reference=json.loads(REFERENCE_ENGINE.read_text(encoding='utf-8'))
        expected={m['name']:m['sha256'] for m in reference['models']}
        assert {m['name']:m['sha256'] for m in models}==expected, 'Baseline installed model hashes differ from the original CPU engine'
        assert versions['rapidocr']==reference['versions']['rapidocr'], 'RapidOCR package version differs from original CPU engine'
    dump(OUT/'engine.json',{'evaluation_scope':'ubuntu_server_final','engine':'backend.aicademiya.material_extraction._material_ocr_engine','constructor':'backend.aicademiya.worksheet_import._local_ocr_engine.__wrapped__','python':sys.version,'executable':sys.executable,'platform':platform.platform(),'versions':versions,'models':models,'actual_sessions':sessions,'thread_environment':{k:os.environ[k] for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')},'accuracy_note':'Confidence scores are engine confidence, NOT measured OCR accuracy. No OCR text used as gold.'})

def images():
    gate()
    from backend.aicademiya.material_extraction import _material_ocr_engine,_ocr_lines
    rows=json.loads((DATA/'samples.json').read_text(encoding='utf-8'))['samples'];assert len(rows)==24
    existing=latest(OUT/'rapidocr.jsonl');successful={}
    if (OUT/'rapidocr.jsonl').is_file():
        for line in (OUT/'rapidocr.jsonl').read_text(encoding='utf-8').splitlines():
            row=json.loads(line)
            if row['status'] in {'ok','no_text'}:successful[row['id']]=row
    engine=_material_ocr_engine();engine_info(engine)
    for n,sample in enumerate(rows):
        gate()
        if sample['id'] in successful:continue
        started=time.perf_counter()
        try:
            result=engine(asset(sample,'image_path','image_relpath').read_bytes())
            texts=[str(t) for t in (result.txts or []) if str(t).strip()]
            row={'id':sample['id'],'evaluation_scope':'ubuntu_server_final','image_path':str(asset(sample,'image_path','image_relpath')),'original_image_path':sample['image_path'],'image_sha256':sample['image_sha256'],'status':'ok' if texts else 'no_text','text':'\n'.join(texts),'elapsed_seconds':time.perf_counter()-started,'engine_elapsed':plain(result.elapse),'engine_stage_elapsed':plain(result.elapse_list),'boxes':plain(result.boxes),'confidences':plain(result.scores),'error_type':None,'engine':'current_installed_RapidOCR_CPU'}
            if n==0:
                row['existing_ocr_lines_matches']=_ocr_lines(asset(sample,'image_path','image_relpath').read_bytes())==texts
        except Exception as exc:
            row={'id':sample['id'],'evaluation_scope':'ubuntu_server_final','image_path':str(asset(sample,'image_path','image_relpath')),'status':'error','text':'','elapsed_seconds':time.perf_counter()-started,'boxes':None,'confidences':None,'error_type':type(exc).__name__,'error':str(exc)}
        append(OUT/'rapidocr.jsonl',row);print(sample['id'],row['status'],round(row['elapsed_seconds'],3),len(row['text']),flush=True)
    verify_images()

def verify_images():
    samples=json.loads((DATA/'samples.json').read_text(encoding='utf-8'))['samples'];records=latest(OUT/'rapidocr.jsonl');ids={s['id'] for s in samples}
    result={'expected_count':24,'unique_ids':len(records),'exact_ids_match':set(records)==ids,'status_counts':dict(collections.Counter(r['status'] for r in records.values())),'total_elapsed_seconds':sum(r['elapsed_seconds'] for r in records.values()),'per_sample_elapsed_seconds':{k:r['elapsed_seconds'] for k,r in records.items()},'human_gold_available':False,'accuracy_measured':False}
    dump(OUT/'rapidocr-summary.json',result);assert result['exact_ids_match'];print('OCR_SUMMARY',json.dumps(result),flush=True)

def file_worker(sid,target):
    gate()
    import backend.aicademiya.material_extraction as extraction
    source=next(s for s in json.loads((DATA/'inventory.json').read_text(encoding='utf-8'))['sources'] if s['id']==sid)
    original_ocr=extraction._ocr_lines;progress=OUT/'file_progress'/f'{sid}.jsonl'
    def guarded(png):
        # Harness-only cooperative STOP gate; preserve exact extraction policy.
        gate();started=time.perf_counter();texts=original_ocr(png)
        append(progress,{'id':sid,'event':'ocr_completed','seconds':time.perf_counter()-started,'lines':len(texts)});return texts
    extraction._ocr_lines=guarded
    started=time.perf_counter();result=extraction.extract_document(asset(source,'path','source_relpath'))
    dump(Path(target),{'id':sid,'source_path':source['path'],'status':'blocked' if source['input_gate']!='accepted' else result['status'],'blocked_reason':source['input_gate'] if source['input_gate']!='accepted' else None,'elapsed_seconds':time.perf_counter()-started,'result':result,'original_logic_unchanged':True,'cooperative_stop_gate_only':True})

def files():
    gate();sources=json.loads((DATA/'inventory.json').read_text(encoding='utf-8'))['sources']
    sampleids={s['source_id'] for s in json.loads((DATA/'samples.json').read_text(encoding='utf-8'))['samples']}
    sources=sorted(sources,key=lambda s:(s['id'] not in sampleids,s['input_gate']=='accepted',s.get('page_count',0)>100,s['id']))
    records=latest(OUT/'platform-files.jsonl')
    for source in sources:
        gate();sid=source['id']
        if sid in records and records[sid]['status'] not in {'worker_error','paused'}:continue
        target=OUT/'file_results'/f'{sid}.json';target.parent.mkdir(parents=True,exist_ok=True)
        cmd=[sys.executable,str(Path(__file__).resolve()),'worker','--source-id',sid,'--result',str(target),'--dataset',str(DATA),'--output',str(OUT),'--app-root',str(APP_ROOT),'--control-dir',str(CONTROL),'--budget-status',str(BUDGET_STATUS)]
        if BUDGET_COMMAND:cmd+=['--budget-command',BUDGET_COMMAND]
        if REFERENCE_ENGINE:cmd+=['--reference-engine',str(REFERENCE_ENGINE)]
        started=time.perf_counter();p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace',start_new_session=True)
        timedout=False;paused=False
        try:
            while p.poll() is None:
                if (CONTROL/'STOP').exists():paused=True;break
                if time.perf_counter()-started>=90:timedout=True;break
                time.sleep(.25)
        except BaseException:
            if p.poll() is None:os.killpg(p.pid,signal.SIGKILL)
            p.communicate(timeout=15)
            raise
        if paused or timedout:
            os.killpg(p.pid,signal.SIGKILL)
        stdout,stderr=p.communicate(timeout=15)
        log=OUT/'file_logs'/f'{sid}.txt';log.parent.mkdir(parents=True,exist_ok=True);log.write_text('STDOUT\n'+stdout+'\nSTDERR\n'+stderr,encoding='utf-8')
        elapsed=time.perf_counter()-started
        if paused or timedout:
            row={'id':sid,'source_path':source['path'],'status':'paused' if paused else 'timeout','elapsed_seconds':elapsed,'timeout_budget_seconds':90,'error_type':'BudgetStop' if paused else 'TimeoutExpired','extraction_report':None,'note':'No completed extraction_report; do not infer success or coverage from partial OCR progress.','worker_exit_code':p.returncode,'log_path':str(log.resolve())}
        elif p.returncode==0 and target.is_file():
            detail=json.loads(target.read_text(encoding='utf-8'));row={'id':sid,'source_path':source['path'],'status':detail['status'],'blocked_reason':detail['blocked_reason'],'elapsed_seconds':elapsed,'extraction_elapsed_seconds':detail['elapsed_seconds'],'extraction_report':detail['result']['extraction_report'],'warning':detail['result']['warning'],'platform_status':detail['result']['status'],'detail_path':str(target.resolve()),'worker_exit_code':0,'error_type':None,'timeout_budget_seconds':90,'log_path':str(log.resolve())}
        else:
            row={'id':sid,'source_path':source['path'],'status':'worker_error','elapsed_seconds':elapsed,'error_type':'WorkerExit','worker_exit_code':p.returncode,'log_path':str(log.resolve()),'extraction_report':None}
        row['evaluation_scope']='ubuntu_server_final'
        append(OUT/'platform-files.jsonl',row);records[sid]=row;print('FILE',sid,row['status'],round(elapsed,2),flush=True)
        if paused:raise SystemExit('PAUSED: source child closed and checkpoint flushed')
    summary={'expected_count':23,'unique_ids':len(records),'exact_ids_match':set(records)=={s['id'] for s in sources},'status_counts':dict(collections.Counter(r['status'] for r in records.values())),'total_wall_seconds':sum(r['elapsed_seconds'] for r in records.values()),'per_file_timeout_seconds':90,'limits_unchanged':{'max_input_bytes':25*1024*1024,'native_units':200,'ocr_units':64,'excerpt_chars':50000,'expanded_Office_bytes':100*1024*1024},'note':'Timeouts have no completed report; unsupported DOC / oversize PPTX are input gates, not OCR errors. Speaker notes are not extracted by the original platform.'}
    dump(OUT/'platform-summary.json',summary);assert summary['exact_ids_match'];print('PLATFORM_SUMMARY',json.dumps(summary),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Portable CPU baseline. Benchmarks are Ubuntu-only; Windows allows validate/verify, never new OCR.')
    parser.add_argument('action',choices=['images','files','all','worker','verify','validate'])
    parser.add_argument('--dataset',type=Path,default=DATA)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--app-root',type=Path,help='Root containing unchanged backend/aicademiya modules; defaults to bundled snapshot')
    parser.add_argument('--control-dir',type=Path,help='Parent-controlled directory with STOP and mirrored quota status')
    parser.add_argument('--budget-status',type=Path)
    parser.add_argument('--budget-command',help='Optional command returning sanitized budget.py-compatible JSON; otherwise parent must refresh mirrored status at least every120s')
    parser.add_argument('--reference-engine',type=Path,help='Original installed package/model reference, checked before server OCR')
    parser.add_argument('--source-id');parser.add_argument('--result')
    args=parser.parse_args()
    DATA=args.dataset.resolve();OUT=(args.output or DATA.parent/'baseline-server').resolve()
    APP_ROOT=(args.app_root or DATA/'runtime_reference/platform_root').resolve()
    CONTROL=(args.control_dir or DATA.parent).resolve();BUDGET_STATUS=(args.budget_status or CONTROL/'budget-status.json').resolve()
    BUDGET_COMMAND=args.budget_command;REFERENCE_ENGINE=(args.reference_engine or DATA/'runtime_reference/engine.json').resolve()
    sys.path.insert(0,str(APP_ROOT));sys.path.insert(1,str(ROOT))
    if os.name=='nt' and args.action in {'images','files','all','worker'}:raise SystemExit('Local benchmarks forbidden by latest user instruction. Run on Ubuntu-gpu-server; local validation only.')
    if args.action=='validate':validate()
    elif args.action=='verify':verify_images()
    else:
        OUT.mkdir(parents=True,exist_ok=True)
        if args.action=='worker':file_worker(args.source_id,args.result)
        elif args.action=='all':images();files()
        else:globals()[args.action]()

