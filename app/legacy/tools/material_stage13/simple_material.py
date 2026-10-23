"""Complete plain-text/Markdown and all-frame image source adapters.

Text is never OCR'd or truncated: contiguous original decoded spans are retained
verbatim, independent of PDF font support. Markdown is source text, not executed
HTML. Images keep original identity and use a derived PDF for the common reader.
"""
from __future__ import annotations
import argparse
import io
import json
import math
import os
import signal
from pathlib import Path
import shutil
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'document_stage12'))
from parser_helpers import coverage_of,dump,sha256,validate_bundle

FORMATS=('txt','md','png','jpg','jpeg','webp')
IMAGE_FORMATS={'png':'PNG','jpg':'JPEG','jpeg':'JPEG','webp':'WEBP'}
MAX_BYTES=64*1024*1024


if __package__:
    from .source_text import decode_text
else:
    from source_text import decode_text


def text_lines(text,font,width,size):
    """Yield exact contiguous source spans with separate display strings."""
    offset=0
    for line in text.splitlines(keepends=True):
        body=line.rstrip('\r\n');part_start=0;used=0
        for index,char in enumerate(body):
            advance=font.text_length('    'if char=='\t'else char,fontsize=size)
            if used+advance>width and index>part_start:
                yield offset+part_start,offset+index,line[part_start:index]
                part_start=index;used=0
            used+=advance
        yield offset+part_start,offset+len(line),line[part_start:]
        offset+=len(line)
    assert offset==len(text)


def text_bundle(source,out,fmt,deadline):
    import pymupdf as fitz
    start=time.monotonic();text,encoding=decode_text(source.read_bytes());font=fitz.Font('china-s')
    lines=list(text_lines(text,font,523,11))
    count=max(1,math.ceil(len(lines)/48))
    if count>1000:raise ValueError('Rendered text source exceeds1000pages; no partial text accepted')
    manifest={'schema_version':1,'source_sha256':sha256(source),'source_format':fmt,'preview_pdf':'preview.pdf',
              'parser':{'name':'stage14-simple','version':'1.1.0','recipe':'exact-decoded-text+derived-pdf'},
              'page_count':count,'complete':False,'warnings':[],'pages':[]}
    receipt={'status':'running','source_sha256':manifest['source_sha256'],'source_format':fmt,'device':'cpu','vlm_device':'cpu',
             'engine':'native','quality_accepted':False,'page_timings':[],'text_encoding':encoding}
    pdf=fitz.open();(out/'pages').mkdir(parents=True);offset=0
    for number in range(1,count+1):
        if time.monotonic()-start>deadline:raise TimeoutError('Text rendering deadline reached')
        begun=time.monotonic();page=pdf.new_page(width=595,height=842);blocks=[]
        for ordinal,(first,last,literal)in enumerate(lines[(number-1)*48:number*48]):
            y=42+ordinal*16
            display=literal.rstrip('\r\n').replace('\t','    ')
            page.insert_text((36,y),display,fontname='china-s',fontsize=11)
            blocks.append({'id':f'p{number}-b{ordinal}','type':'text','bbox':[36/595,(y-12)/842,559/595,(y+4)/842],
                           'text':literal,'quality':'extracted','issues':['source_transcription_native',f'original_text_chars:{first}:{last}'],
                           'assets':[],'parent_id':None})
            assert first==offset;offset=last
        if blocks:
            first=lines[(number-1)*48][0];last=lines[min(number*48,len(lines))-1][1]
            blocks=[{'id':f'p{number}-b0','type':'text','bbox':[36/595,30/842,559/595,(46+(len(blocks)-1)*16)/842],
                     'text':text[first:last],'quality':'extracted',
                     'issues':['source_transcription_native',f'original_text_chars:{first}:{last}'],
                     'assets':[],'parent_id':None}]
        pix=page.get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False);name=f'pages/p{number:04}.png';pix.save(out/name)
        manifest['pages'].append({'number':number,'printed_label':None,'rotation':0,'image':name,'width':pix.width,'height':pix.height,
                                  'status':'text'if any(b['text'].strip()for b in blocks)else'blank','issues':[],'blocks':blocks})
        receipt['page_timings'].append({'page':number,'seconds':time.monotonic()-begun,'mode':'native','model_processed':False,'model_calls':0,'imported_evidence':False,'vector_paths':0})
    assert offset==len(text)and ''.join(b['text']for p in manifest['pages']for b in p['blocks'])==text
    pdf.save(out/'preview.pdf');pdf.close();manifest['complete']=True
    manifest['coverage']=coverage_of(manifest)
    manifest['coverage'].update(representation='decoded_text_spans',original_source_format=fmt,decoded_encoding=encoding,
                                exact_decoded_character_count=len(text),exact_decoded_text_complete=True,
                                rendered_pdf_sha256=sha256(out/'preview.pdf'),rendered_pdf_pages=count)
    receipt.update(status='complete',wall_seconds=time.monotonic()-start,validation=validate_bundle(out,manifest))
    dump(out/'manifest.json',manifest);dump(out/'receipt.json',receipt)
    return 0


def image_pdf(source,target,fmt):
    """Decode ALL display frames before inference, retaining alpha and locators.

    Pillow composes APNG/WebP disposal/blend into each displayed canvas. A PNG
    default/poster image is retained as its own page, never silently discarded.
    Original identity is unchanged; these lossless PNGs are derived evidence.
    """
    import pymupdf as fitz
    from PIL import Image,ImageOps
    target=Path(target);frame_dir=target.parent/'raw/source-frames'
    frame_dir.mkdir(parents=True,exist_ok=True)
    budget=100*1024*1024;expanded=0;rows=[];doc=fitz.open();original_digest=sha256(source)
    try:
        with Image.open(source)as image:
            if image.format!=IMAGE_FORMATS[fmt]:raise ValueError('Image bytes do not match original suffix')
            count=getattr(image,'n_frames',1)
            if not 1<=count<=1000:raise ValueError('Image exceeds1000frames; no partial image accepted')
            if image.width*image.height>16_000_000:raise ValueError('Image exceeds16million original pixels')
            info={'original_width':image.width,'original_height':image.height,
                  'exif_orientation':image.getexif().get(274,1),'frames':count,
                  'default_image':bool(image.info.get('default_image',False)),
                  'loop':image.info.get('loop'),'alpha_display_background':'white',
                  'frame_representation':'composited_display_canvas','frame_map':rows}
            for index in range(count):
                image.seek(index)
                if image.width*image.height>16_000_000:raise ValueError('Image frame exceeds16million original pixels')
                image.load()  # Corrupt late frames fail before any parser/model call.
                upright=ImageOps.exif_transpose(image);rgba=upright.convert('RGBA')
                buffer=io.BytesIO();rgba.save(buffer,format='PNG');data=buffer.getvalue()
                expanded+=len(data)
                if expanded>budget:raise ValueError('Decoded image frames exceed100MiB bounded bytes')
                ref=f'raw/source-frames/f{index:04}.png';(target.parent/ref).write_bytes(data)
                rgb=Image.new('RGB',rgba.size,'white');rgb.paste(rgba,mask=rgba.getchannel('A'))
                display=io.BytesIO();rgb.save(display,format='PNG')
                duration=image.info.get('duration')
                if duration is not None and (not isinstance(duration,(int,float))or not math.isfinite(duration)or duration<0):
                    raise ValueError('Invalid image frame duration')
                row={'page':index+1,'frame_index':index,'duration_ms':duration,
                     'is_default_image':bool(info['default_image']and index==0),
                     'original_width':image.width,'original_height':image.height,
                     'normalized_width':rgba.width,'normalized_height':rgba.height,
                     'exif_orientation':image.getexif().get(274,1),
                     'decoded_rgba_asset':ref,'decoded_rgba_sha256':sha256(target.parent/ref),
                     'original_source_sha256':original_digest}
                for key in ('disposal','blend'):
                    if key in image.info:row[key]=image.info[key]
                rows.append(row)
                page=doc.new_page(width=rgb.width,height=rgb.height)
                page.insert_image(page.rect,stream=display.getvalue())
            info.update(normalized_width=rows[0]['normalized_width'],normalized_height=rows[0]['normalized_height'],
                        decoded_frame_bytes=expanded,all_frames_retained=True)
        doc.save(target)
        if target.stat().st_size>MAX_BYTES:raise ValueError('Derived frame PDF exceeds64MiB parser input limit')
        return info
    finally:doc.close()


def main(argv=None):
    cli=argparse.ArgumentParser();cli.add_argument('--input',required=True);cli.add_argument('--output',required=True)
    cli.add_argument('--source-format',required=True,choices=FORMATS);cli.add_argument('--prepared-dir')
    cli.add_argument('--deadline-seconds',type=float,default=900);a,forward=cli.parse_known_args(argv)
    source,out,fmt=Path(a.input),Path(a.output),a.source_format
    if not source.is_file()or source.is_symlink()or any(p.is_symlink()for p in source.parents)or source.stat().st_size>MAX_BYTES:
        raise ValueError('Safe bounded original source required')
    if any(p.is_symlink()for p in out.parents):raise ValueError('Safe output parent required')
    out.mkdir(parents=True,exist_ok=False);started=time.monotonic();digest=sha256(source)
    def interrupted(signum,frame):
        if signum==signal.SIGTERM:raise InterruptedError('Simple material parser cancelled by supervisor')
        raise TimeoutError('Simple material parser deadline reached')
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGALRM,interrupted)
    signal.setitimer(signal.ITIMER_REAL,max(.01,a.deadline_seconds))
    try:
        if fmt in ('txt','md'):return text_bundle(source,out,fmt,a.deadline_seconds)
        if a.prepared_dir:
            prepared=Path(a.prepared_dir);m=json.loads((prepared/'manifest.json').read_text());r=json.loads((prepared/'receipt.json').read_text())
            validate_bundle(prepared,m)
            if(m['source_sha256']!=digest or m.get('source_format')!=fmt or not m['complete']or r.get('engine')!='native'
                    or r.get('status')!='complete'or m.get('preview_pdf')!='preview.pdf'
                    or any(row.get('model_calls',0)or row.get('model_processed')for row in r.get('page_timings',[]))
                    or sha256(prepared/'preview.pdf')!=m.get('coverage',{}).get('rendered_pdf_sha256')):
                raise ValueError('Prepared image identity mismatch')
            info=m['coverage']['original_image']
            if info.get('frames')!=m['page_count']or not info.get('all_frames_retained'):
                raise ValueError('Prepared image does not retain every frame; prepare again')
            for row in info['frame_map']:
                if row['original_source_sha256']!=digest or sha256(prepared/row['decoded_rgba_asset'])!=row['decoded_rgba_sha256']:
                    raise ValueError('Prepared decoded frame identity mismatch')
            shutil.copyfile(prepared/'preview.pdf',out/'preview.pdf')
            shutil.copytree(prepared/'raw/source-frames',out/'raw/source-frames')
        else:info=image_pdf(source,out/'preview.pdf',fmt)
        remaining=a.deadline_seconds-(time.monotonic()-started)
        if remaining<=0:raise TimeoutError('Image preparation deadline reached')
        # Reuse adapter process cancellation/child ownership, not a detached model.
        from parse_material import run_owned
        command=[sys.executable,str(HERE.parent/'document_stage12/parser_worker.py'),'--input',str(out/'preview.pdf'),
                 '--output',str(out/'pdf-work'),'--deadline-seconds',str(remaining)]+forward
        rc,stdout,stderr=run_owned(command,seconds=remaining+5,env={**os.environ,'CUDA_VISIBLE_DEVICES':''})
        work=out/'pdf-work';manifest=json.loads((work/'manifest.json').read_text());receipt=json.loads((work/'receipt.json').read_text())
        for name in ('pages','assets','raw'):
            if(work/name).is_dir():
                shutil.copytree(work/name,out/name,dirs_exist_ok=True)
        manifest.update(source_sha256=digest,source_format=fmt,preview_pdf='preview.pdf')
        manifest['parser']={'name':'stage14-simple','version':'1.1.0','recipe':'all-original-image-frames+derived-pdf+'+receipt['engine']}
        manifest['coverage'].update(representation='original_image',original_source_format=fmt,original_image=info,
                                    rendered_pdf_sha256=sha256(out/'preview.pdf'),rendered_pdf_pages=manifest['page_count'])
        for page in manifest['pages']:
            frame=info['frame_map'][page['number']-1]
            page['issues'].append(f"original_image_frame:{frame['frame_index']}; duration_ms:{frame['duration_ms']}")
        receipt.update(source_sha256=digest,source_format=fmt,preparation_reused=bool(a.prepared_dir),wall_seconds=time.monotonic()-started)
        # Inner receipt remains precise; no source alias is misrepresented as original.
        dump(out/'raw/derived-parser-receipt.json',json.loads((work/'receipt.json').read_text()))
        shutil.rmtree(work)
        if sha256(source)!=digest:raise ValueError('Original image changed while parsing')
        if rc==0:receipt['validation']=validate_bundle(out,manifest)
        dump(out/'manifest.json',manifest);dump(out/'receipt.json',receipt);return rc
    except BaseException as error:
        dump(out/'receipt.json',{'status':'failed','source_sha256':digest,'source_format':fmt,'quality_accepted':False,
                                'error_type':type(error).__name__,'error':str(error),'wall_seconds':time.monotonic()-started,'page_timings':[]})
        return 2
    finally:signal.setitimer(signal.ITIMER_REAL,0)
if __name__=='__main__':raise SystemExit(main())
