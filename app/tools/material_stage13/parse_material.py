"""Ubuntu complete-material adapter; no deployment/model lifecycle operations.

All parser_worker options are forwarded after service-side Office conversion.
Original source bytes/hash remain authoritative; preview.pdf is derived only.
"""
from __future__ import annotations
import argparse
import json
import os
import platform
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]))  # Preserve release/tools namespace imports.
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(HERE.parent/'document_stage12'))
from parser_helpers import dump, sha256, validate_bundle
from office_inventory import inventory, preflight, binary_doc_inventory

MAX_INPUT = 64 * 1024 * 1024
FORMATS = ('pdf','pptx','ppt','docx','doc','xls','xlsx','txt','md','png','jpg','jpeg','webp')
VERSION = '1.2.0'


def child_limits():
    # Independent conversion process, bounded before parsers allocate memory.
    resource.setrlimit(resource.RLIMIT_AS,(8*1024**3,8*1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE,(128*1024**2,128*1024**2))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))


def run_owned(command, *, seconds, env, limits=False):
    process = subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,text=True,env=env,start_new_session=True,
        preexec_fn=child_limits if limits else None)
    try:
        stdout,stderr=process.communicate(timeout=max(.1,seconds))
    except BaseException:
        if process.poll() is None:
            os.killpg(process.pid,signal.SIGTERM)
            try:process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL);process.communicate(timeout=5)
        raise
    return process.returncode,stdout,stderr


def convert(source, temp, target, seconds, env):
    available=int(next(line for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:')).split()[1])//1024
    if available<6144:
        raise MemoryError('Less than6GiB reserved available memory before Office conversion')
    executable=shutil.which('libreoffice') or shutil.which('soffice')
    if not executable:
        raise RuntimeError('LibreOffice is not installed on the Ubuntu worker')
    temp=Path(temp)
    profile=temp/('profile-'+target)
    (profile/'user').mkdir(parents=True)
    # Fresh per-job profile: macros disabled and links never updated.
    (profile/'user/registrymodifications.xcu').write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<oor:items xmlns:oor="http://openoffice.org/2001/registry">'
        '<item oor:path="/org.openoffice.Office.Common/Security/Scripting">'
        '<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item>'
        '<item oor:path="/org.openoffice.Office.Writer/Content/Update">'
        '<prop oor:name="Link" oor:op="fuse"><value>2</value></prop></item>'
        '<item oor:path="/org.openoffice.Office.Calc/Content/Update">'
        '<prop oor:name="Link" oor:op="fuse"><value>2</value></prop></item></oor:items>',encoding='utf-8')
    dest=temp/('convert-'+target);dest.mkdir()
    kind={'pdf': 'pdf:impress_pdf_Export:{"ExportHiddenSlides":{"type":"boolean","value":"true"}}' if source.suffix.lower() in ('.ppt','.pptx') else 'pdf:writer_pdf_Export',
          'docx':'docx:Office Open XML Text', 'pptx':'pptx:Impress MS PowerPoint 2007 XML',
          'xlsx':'xlsx:Calc MS Excel 2007 XML'}[target]
    cmd=[executable,'-env:UserInstallation='+profile.as_uri(),'--headless','--norestore','--nodefault',
         '--nofirststartwizard','--nolockcheck','--convert-to',kind,'--outdir',str(dest),str(source)]
    begun=time.monotonic()
    rc,stdout,stderr=run_owned(cmd,seconds=min(120,seconds),env=env,limits=True)
    derived=dest/(source.stem+'.'+target)
    # Logs contain no private runtime paths; retained failure code is truthful.
    for path in (str(source),str(dest),str(profile),str(temp)):
        stdout=stdout.replace(path,'[job-path]');stderr=stderr.replace(path,'[job-path]')
    stderr='\n'.join(line for line in stderr.splitlines() if not line.startswith('/') and not line.startswith('Stack:'))
    row={'target_format':target,'returncode':rc,'seconds':time.monotonic()-begun,
         'stdout':stdout[:4000],'stderr':stderr[:4000],'output_exists':derived.is_file()}
    if rc or not derived.is_file() or derived.is_symlink():
        raise ConversionError(row)
    if derived.stat().st_size>MAX_INPUT:
        row['error']='derived_file_exceeds64MiB';raise ConversionError(row)
    return derived,row


class ConversionError(RuntimeError):
    def __init__(self,row):
        super().__init__('Office conversion did not produce a valid bounded output')
        self.row=row


def reject_symlinks(root):
    for path in root.rglob('*'):
        if path.is_symlink():raise ValueError('Symlink in returned bundle')


def main(argv=None):
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--input',required=True)
    cli.add_argument('--output',required=True)
    cli.add_argument('--source-format',choices=FORMATS,help='trusted original suffix when transport filename has no suffix')
    cli.add_argument('--prepared-dir',help='same-job native Office bundle; reuse source-bound CPU conversion')
    cli.add_argument('--deadline-seconds',type=float,default=900)
    args,forward=cli.parse_known_args(argv)
    if platform.system()!='Linux':cli.error('formal material execution is Ubuntu-only')
    source,out=Path(args.input),Path(args.output)
    fmt=args.source_format or source.suffix.lower().lstrip('.')
    if fmt not in FORMATS:cli.error('Unsupported complete material format')
    if not source.is_file() or source.is_symlink() or any(p.is_symlink() for p in source.parents):
        cli.error('safe regular source file required')
    if source.stat().st_size>MAX_INPUT:cli.error('material input exceeds64MiB')
    if any(p.is_symlink() for p in out.parents):cli.error('safe non-symlink output parent required')
    if fmt in ('xls','xlsx'):
        from tools.material_stage16.workbook_material import process
        def workbook_interrupted(signum, frame):
            if signum==signal.SIGTERM:raise InterruptedError('Workbook parser cancelled by supervisor')
            raise TimeoutError('Workbook total wall deadline reached')
        signal.signal(signal.SIGTERM,workbook_interrupted);signal.signal(signal.SIGALRM,workbook_interrupted)
        signal.setitimer(signal.ITIMER_REAL,max(.01,args.deadline_seconds))
        try:return process(source,out,fmt,args.deadline_seconds,forward,args.prepared_dir)
        finally:signal.setitimer(signal.ITIMER_REAL,0)
    if fmt in ('txt','md','png','jpg','jpeg','webp'):
        from simple_material import main as simple_main
        options=['--input',str(source),'--output',str(out),'--source-format',fmt,'--deadline-seconds',str(args.deadline_seconds)]+forward
        if args.prepared_dir:options+=['--prepared-dir',args.prepared_dir]
        return simple_main(options)
    if fmt=='pdf':
        from parser_worker import main as pdf_main
        return pdf_main(['--input',str(source),'--output',str(out),'--deadline-seconds',str(args.deadline_seconds)]+forward)
    out.mkdir(parents=True,exist_ok=False)
    start=time.monotonic();digest=sha256(source)
    receipt={'status':'running','source_sha256':digest,'source_format':fmt,'quality_accepted':False,
             'conversion':[],'page_timings':[]}
    manifest={'schema_version':1,'source_sha256':digest,'source_format':fmt,
        'parser':{'name':'stage13-material','version':VERSION,'recipe':'office-conversion+pdf'},
        'page_count':0,'complete':False,'warnings':['Machine extraction is not human-approved accuracy.'],'pages':[]}
    env=dict(os.environ,CUDA_VISIBLE_DEVICES='',HF_HUB_OFFLINE='1',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4',SAL_MAX_CONCURRENCY='4',SAL_USE_VCLPLUGIN='svp')
    def remaining():
        seconds=args.deadline_seconds-(time.monotonic()-start)
        if seconds<=0:raise TimeoutError('Material total wall deadline reached')
        return seconds
    def interrupted(signum,frame):
        if signum==signal.SIGTERM:raise InterruptedError('Material parser cancelled by supervisor; not a parser wall deadline')
        raise TimeoutError('Material total wall deadline reached')
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGALRM,interrupted)
    signal.setitimer(signal.ITIMER_REAL,max(.01,args.deadline_seconds))
    try:
        if args.prepared_dir:
            from prepared_material import reuse_office
            native,binary,count,rows=reuse_office(args.prepared_dir,source,fmt,out)
            receipt['conversion']=rows
            receipt['conversion_reused_from_native_phase']=True
            manifest.update(preview_pdf='preview.pdf',page_count=count)
        else:
            binary=None
            if fmt=='doc':
                binary=binary_doc_inventory(source);dump(out/'raw/legacy-doc-inventory.json',binary)
            elif fmt=='ppt':
                from tools.material_stage16.legacy_office import binary_inventory
                binary=binary_inventory(source,fmt);dump(out/'raw/legacy-ppt-inventory.json',binary)
            else:preflight(source,fmt)
            with tempfile.TemporaryDirectory(prefix='office-',dir=out) as td:
                temp=Path(td)
                # Original is only read; LibreOffice never receives the original path.
                copy=temp/('source.'+fmt);shutil.copyfile(source,copy);copy.chmod(0o400)
                inv_source=copy
                if fmt in ('doc','ppt'):
                    derived_format='docx' if fmt=='doc' else 'pptx'
                    inv_source,row=convert(copy,temp,derived_format,remaining(),env)
                    receipt['conversion'].append(row)
                    shutil.copyfile(inv_source,out/('raw/derived.'+derived_format))
                native=inventory(inv_source,{'doc':'docx','ppt':'pptx'}.get(fmt,fmt),out/'raw')
                derived,row=convert(copy,temp,'pdf',remaining(),env)
                receipt['conversion'].append(row)
                import pymupdf as fitz
                with fitz.open(derived) as doc:
                    if not doc.is_pdf or doc.needs_pass or not 1<=len(doc)<=1000:
                        raise ValueError('Derived PDF must contain1..1000unencrypted pages')
                    count=len(doc)
                shutil.copyfile(derived,out/'preview.pdf')
                manifest['preview_pdf']='preview.pdf';manifest['page_count']=count
                if fmt in ('ppt','pptx') and count!=native['slides_expected']:
                    raise ValueError('Rendered PDF page count does not match inventoried OOXML slides including hidden slides')
        # Evidence from an original-PDF job cannot silently bind to Office.
        if '--evidence-dir' in forward or '--evidence-source-sha256' in forward:
            raise ValueError('Imported PDF evidence is unsupported for Office sources')
        command=[sys.executable,str(HERE.parent/'document_stage12/parser_worker.py'),'--input',str(out/'preview.pdf'),
                 '--output',str(out/'pdf-work'),'--deadline-seconds',str(remaining())]+forward
        rc,stdout,stderr=run_owned(command,seconds=remaining()+5,env=env)
        work=out/'pdf-work'
        if not (work/'manifest.json').is_file():
            raise RuntimeError('Derived PDF parser did not write a manifest')
        pdf_manifest=json.loads((work/'manifest.json').read_text(encoding='utf-8'))
        pdf_receipt=json.loads((work/'receipt.json').read_text(encoding='utf-8'))
        # Retain the exact child failure cause, not just its exception type.
        # Redact runtime locations while preserving the original message.
        portable=json.dumps(pdf_receipt,ensure_ascii=False)
        private_paths=[str(source),str(out),str(HERE),sys.prefix]
        if '--models' in forward:private_paths.append(forward[forward.index('--models')+1])
        for path in sorted(private_paths,key=len,reverse=True):portable=portable.replace(path,'[job-path]')
        dump(out/'raw/pdf-parser-receipt.json',json.loads(portable))
        for name in ('pages','assets','raw'):
            if not (work/name).is_dir():continue
            if name=='raw':
                for path in (work/name).iterdir():shutil.move(str(path),str(out/'raw'/path.name))
            else:shutil.move(str(work/name),str(out/name))
        shutil.rmtree(work)
        manifest=pdf_manifest
        manifest.update(source_sha256=digest,source_format=fmt,preview_pdf='preview.pdf')
        manifest['parser']={'name':'stage13-material','version':VERSION,'recipe':fmt+'-libreoffice+'+pdf_manifest['parser']['recipe']}
        coverage=manifest['coverage'];coverage['representation']='rendered_office_pdf_pages'
        coverage.update(original_source_format=fmt,original_source_bytes=source.stat().st_size,
            rendered_pdf_sha256=sha256(out/'preview.pdf'),rendered_pdf_pages=count,
            office_native_units=len(native['native_units']),office_native_text_chars=native['native_text_chars'],
            office_media_parts=native['media_count'],office_image_references=len(native['image_references']),
            notes_count=len(native['notes']),notes_text_chars=native['notes_text_chars'],
            notes_retained=True,notes_integrated_in_reading=False,
            office_auxiliary_parts_retained=len(native['auxiliary_parts']),
            office_raw_inventory='raw/office-inventory.json',
            inventory_derivation={'doc':'libreoffice_docx','ppt':'libreoffice_pptx'}.get(fmt,'original_ooxml'),
            hidden_slides=sum(u['hidden'] for u in native['native_units']),
            missing_components=['notes_and_auxiliary_content_not_integrated_into_reading',
                'off_page_objects_and_embedded_objects_not_semantically_verified'],
            warnings=coverage['warnings']+native['warnings']+(binary['warnings'] if binary else []))
        manifest['warnings']+=native['warnings']+(binary['warnings'] if binary else [])
        receipt.update(status=pdf_receipt['status'],page_timings=pdf_receipt['page_timings'],
            pdf_source_sha256=pdf_receipt['source_sha256'],device=pdf_receipt['device'],
            vlm_device=pdf_receipt['vlm_device'],engine=pdf_receipt['engine'])
        if rc:
            portable_receipt=json.loads(portable)
            receipt.update(error_type=pdf_receipt.get('error_type','ParserError'),
                error='Derived PDF parser failed: '+portable_receipt.get('error','unknown error'),
                child_receipt='raw/pdf-parser-receipt.json')
            manifest['complete']=False
            return 2
        if sha256(source)!=digest:raise ValueError('Original source changed during parsing')
        reject_symlinks(out)
        receipt['validation']=validate_bundle(out,manifest)
        receipt['status']='complete'
        return 0
    except BaseException as exc:
        manifest['complete']=False
        if 'coverage' in manifest:
            manifest['coverage']['page_set_complete']=False
        receipt.update(status='failed',error_type=type(exc).__name__,error=str(exc) if isinstance(exc,(ValueError,RuntimeError,TimeoutError,InterruptedError)) else 'Material parser failed; evidence retained')
        if isinstance(exc,ConversionError):receipt['conversion'].append(exc.row)
        # No traceback/private argv/paths enter portable receipts.
        for p in (str(source),str(out),str(HERE)):
            receipt['error']=receipt['error'].replace(p,'[job-path]')
        manifest['warnings'].append('Incomplete material job; inspect retained receipt and raw evidence.')
        return 2
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        receipt['wall_seconds']=time.monotonic()-start
        dump(out/'manifest.json',manifest);dump(out/'receipt.json',receipt)
        print(json.dumps(receipt,ensure_ascii=False),flush=True)


if __name__=='__main__':raise SystemExit(main())
