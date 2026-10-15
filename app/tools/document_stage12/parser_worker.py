"""Whole-PDF schema1 worker. CPU native; optional isolated local MinerU4 VLM.

No service lifecycle or GPU allocation. CLI VLM points only at an explicitly
provided loopback server. Existing successful/partial output is never overwritten.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import math
import os
import platform
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from parser_helpers import bbox, convert_middle, dump, sha256, validate_bundle, localize_native_warnings, rotate_bbox, merge_native_visual, coverage_of, literal_response, observe_vlm_http, composite_embedded

VERSION = '1.2.2'

# Runtime packaging preserves this sibling module layout.
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'material_stage13'))
from ocr_verification import CPUVerifier,compare_literal,apply_native_verification,recovery_tiles,pixel_crop,duplicate_candidates,normalized,linear_layout,orientation_needed,recovery_allowance


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--input', required=True)
    cli.add_argument('--output', required=True)
    cli.add_argument('--engine', choices=('native','hybrid','mineru','region-text'), default='native')
    cli.add_argument('--vlm-url', help='explicit loopback MinerU llama-cpp base URL')
    cli.add_argument('--models', help='read-only MinerU model base_dir')
    cli.add_argument('--device', choices=('cpu',), default='cpu')
    cli.add_argument('--vlm-device', choices=('cpu','cuda'), default='cpu', help='declared device of the separately supervised loopback VLM; native/layout processing remains CPU')
    cli.add_argument('--vision-pages', default='', help='one-based original page numbers; no coverage cap')
    cli.add_argument('--layout-pages', default='', help='CPU triage pages requiring full-page visual layout; does not restrict image OCR on other pages')
    cli.add_argument('--regions', default='{}', help='JSON page -> normalized final-raster regions for literal Text Recognition, no image/table reconstruction')
    cli.add_argument('--rotations', default='{}', help='JSON original page -> clockwise rotation of original raster')
    cli.add_argument('--evidence-dir', help='reuse existing complete or selective MinerU document evidence, no model execution')
    cli.add_argument('--evidence-source-sha256', help='required exact original hash for imported evidence')
    cli.add_argument('--dpi', type=int, default=120)
    cli.add_argument('--deadline-seconds', type=float, default=900)
    cli.add_argument('--min-available-mib', type=int, default=6144)
    cli.add_argument('--ocr-models', help='existing RapidOCR det/cls/rec ONNX directory; CPU only, no downloads')
    cli.add_argument('--ocr-recovery-call-limit',type=int,default=64,help='maximum additional targeted OCR calls per document (0..256)')
    a = cli.parse_args(argv)
    if platform.system() != 'Linux':
        cli.error('formal parser execution is Ubuntu-only')
    if not 72 <= a.dpi <= 300:
        cli.error('dpi must be72..300')
    if not 0<=a.ocr_recovery_call_limit<=256:cli.error('OCR recovery call limit must be0..256')
    source, out = Path(a.input), Path(a.output)
    if not source.is_file() or source.is_symlink() or any(p.is_symlink() for p in source.parents):
        cli.error('input does not exist')
    if source.stat().st_size > 64 * 1024 * 1024:
        cli.error('PDF input exceeds64MiB')
    out.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    digest = sha256(source)
    receipt = {'status':'running', 'source_sha256':digest, 'device':'cpu', 'vlm_device':a.vlm_device, 'engine':a.engine,
               'quality_accepted':False, 'page_timings':[]}
    manifest = {'schema_version':1, 'source_sha256':digest, 'source_format':'pdf',
                'parser':{'name':'stage12-pdf','version':VERSION,'recipe':a.engine + ('+imported-mineru4-evidence' if a.evidence_dir else '')},
                'page_count':0,'complete':False,'warnings':['Machine extraction is not human-approved accuracy.'], 'pages':[]}
    rotations = {int(k):int(v) for k,v in json.loads(a.rotations).items()}
    regions = {int(k):v for k,v in json.loads(a.regions).items()}
    home = region_client = None
    image_cache = {}
    model_counter,restore_counter = {'calls':0,'events':[]},None
    verifier=CPUVerifier(a.ocr_models or os.environ.get('AICADEMIYA_RAPIDOCR_MODELS'))
    recovery_calls=0
    import signal
    def deadline_signal(signum, frame):
        if signum == signal.SIGTERM:
            raise InterruptedError('Parser cancelled by supervisor; not a parser wall deadline')
        raise TimeoutError('worker total wall deadline reached')
    signal.signal(signal.SIGALRM, deadline_signal)
    signal.signal(signal.SIGTERM, deadline_signal)
    signal.setitimer(signal.ITIMER_REAL, max(.01,a.deadline_seconds))
    selected = {int(v) for v in a.vision_pages.split(',') if v}
    layout_pages = {int(v) for v in a.layout_pages.split(',') if v}
    env = {'CUDA_VISIBLE_DEVICES':'','HF_HUB_OFFLINE':'1','MINERU_MODEL_SOURCE':'local',
           'OMP_NUM_THREADS':'4','OPENBLAS_NUM_THREADS':'4','MKL_NUM_THREADS':'4','TOKENIZERS_PARALLELISM':'false'}
    os.environ.update(env)
    try:
        import pymupdf as fitz
        from PIL import Image
        doc = fitz.open(source)
        if not doc.is_pdf:
            raise ValueError('PDF input required; convert image fixtures separately with explicit provenance')
        if doc.needs_pass:
            raise ValueError('Encrypted PDF: provide an unlocked source copy')
        if len(doc) > 1000:
            raise ValueError('PDF exceeds1000pages; no partial-success extraction')
        manifest['page_count'] = len(doc)
        if not (selected | layout_pages).issubset(set(range(1,len(doc)+1))) or not set(rotations).issubset(set(range(1,len(doc)+1))) or not set(regions).issubset(set(range(1,len(doc)+1))):
            raise ValueError('selected/rotated page outside source PDF')
        if any(v not in (0,90,180,270) for v in rotations.values()):
            raise ValueError('rotation not cardinal')
        evidence = {}
        if a.evidence_dir:
            if a.evidence_source_sha256 != digest:
                raise ValueError('imported evidence source hash not bound to original')
            e = Path(a.evidence_dir)
            native = json.loads((e/'middle_json.json').read_text())
            dump(out/'raw/imported-middle.json', native)
            if (e/'images').is_dir():
                import shutil
                shutil.copytree(e/'images',out/'raw/images')
            for filename in ('structured_content.json','document.md','full.md'):
                if (e/filename).is_file():
                    (out/'raw'/filename).write_bytes((e/filename).read_bytes())
            evidence = {p['page_idx']+1:p for p in native['pages']}
            if not set(evidence).issubset(set(range(1,len(doc)+1))):
                raise ValueError('evidence page indices not original')
        parse = writer = None
        if a.engine != 'native':
            url = urlparse(a.vlm_url or '')
            if url.scheme != 'http' or url.hostname not in ('127.0.0.1','localhost') or url.username or url.password:
                raise ValueError('explicit credential-free loopback --vlm-url required')
            if not a.models or not Path(a.models).is_dir():
                raise ValueError('existing read-only --models required; no downloads')
            model_counter,restore_counter = observe_vlm_http(a.vlm_url)
            home = out/'raw/mineru-home'
            home.mkdir(parents=True)
            config = {'model':{'base_dir':a.models,'source':'local','small_backend':'onnx',
                              'vlm':{'engine':'llama-cpp','server_url':a.vlm_url,'model':'mineru-doc','http_timeout':max(1,min(600,int(a.deadline_seconds))),'max_concurrency':1}},
                      'llm_aided':{'api_key':'','base_url':a.vlm_url+'/v1','model':'mineru-doc',
                                   'features':{'title_leveling':False,'cross_page_table_cell_merge':False}}}
            dump(home/'config.yaml', config)
            os.environ.update(MINERU_HOME=str(home),MINERU_CONFIG=str(home/'config.yaml'))
            if a.engine in ('region-text', 'hybrid'):
                from mineru_vl_utils import MinerUClient
                from mineru_vl_utils.vlm_client import SamplingParams
                region_client = MinerUClient(backend='http-client',server_url=a.vlm_url,model_name='mineru-doc',
                                             max_concurrency=1,http_timeout=min(240,int(a.deadline_seconds)),max_retries=0,
                                             sampling_params={'[default]':SamplingParams(temperature=0,top_p=.01,top_k=1,max_new_tokens=4096)},use_tqdm=False)
            if a.engine != 'region-text':
                from mineru.parser import parse
                from mineru.parser.writer import FileBasedDataWriter
                writer = FileBasedDataWriter
        for number, page in enumerate(doc,1):
            begun = time.monotonic()
            model_calls_before = model_counter['calls']
            if time.monotonic()-start > a.deadline_seconds:
                raise TimeoutError('worker deadline before next original page')
            if Path('/proc/meminfo').exists():
                available = int(next(s for s in Path('/proc/meminfo').read_text().splitlines() if s.startswith('MemAvailable:')).split()[1]) // 1024
                if available < a.min_available_mib:
                    raise MemoryError('less than reserved available system memory')
            rotation = rotations.get(number,0)
            # Bound allocations before rendering; a tiny PDF may declare an
            # enormous page or embed a highly expanded source raster.
            for embedded in page.get_images(full=True):
                if embedded[2] * embedded[3] > 16000000:
                    raise ValueError('Embedded raster exceeds16million source pixels')
                if embedded[1]:
                    # A small base may reference a much larger mask. Bound its
                    # PDF header before get_pixmap/get_text decode either one.
                    mask_header=[doc.xref_get_key(embedded[1],key) for key in ('Width','Height')]
                    if any(kind!='int' or int(value)<=0 for kind,value in mask_header):
                        raise ValueError('Embedded softmask has invalid source dimensions')
                    mask_size=tuple(int(value) for _,value in mask_header)
                    if mask_size[0]*mask_size[1]>16000000:
                        raise ValueError('Embedded softmask exceeds16million source pixels')
                    if mask_size!=(embedded[2],embedded[3]) and doc.xref_get_key(embedded[1],'Matte')[0]!='null':
                        raise ValueError('Embedded image mask dimensions disagree; unequal Matte softmask unsupported')
            for embedded in page.get_image_info():
                if embedded['width'] * embedded['height'] > 16000000:
                    raise ValueError('Embedded raster exceeds16million source pixels')
            scale = a.dpi / 72
            projected = page.rect.width * page.rect.height * scale * scale
            if projected > 3900000:
                scale *= math.sqrt(3900000 / projected)
            pix = page.get_pixmap(matrix=fitz.Matrix(scale,scale),alpha=False)
            image = Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
            if rotation:
                image = image.rotate(-rotation,expand=True)
            rel = f'pages/p{number:04}.png'
            (out/'pages').mkdir(exist_ok=True)
            image.save(out/rel)
            def crop(ident, box):
                name = 'assets/'+ident+'.png'
                (out/'assets').mkdir(exist_ok=True)
                x1,y1,x2,y2 = box
                bounds = (int(x1*image.width),int(y1*image.height),max(int(x1*image.width)+1,int(x2*image.width)),max(int(y1*image.height)+1,int(y2*image.height)))
                image.crop(bounds).save(out/name)
                return name
            textpage=page.get_textpage(flags=fitz.TEXTFLAGS_DICT)
            native_text = page.get_text('dict',sort=True,textpage=textpage)
            native_raw = page.get_text('rawdict',sort=True,textpage=textpage)
            # Use unrotated coordinates then transform by PDF rotation and our
            # explicit display rotation, matching PyMuPDF's rendered orientation.
            nb = []
            source_images = {}
            def native_box(points):
                rect=fitz.Rect(points)*page.rotation_matrix
                return [min(1,max(0,v))for v in (rect.x0/page.rect.width,rect.y0/page.rect.height,
                                                rect.x1/page.rect.width,rect.y1/page.rect.height)]
            for i,b in enumerate(native_text['blocks']):
                rect = fitz.Rect(b['bbox']) * page.rotation_matrix
                box = [rect.x0/page.rect.width,rect.y0/page.rect.height,rect.x1/page.rect.width,rect.y1/page.rect.height]
                box = [min(1,max(0,v)) for v in box]
                txt = '\n'.join(''.join(s['text'] for s in line['spans']) for line in b.get('lines',[]))
                invalid = box[0] > box[2] or box[1] > box[3]
                issues = ['native_bbox_invalid; fullpage_review_fallback'] if invalid else []
                issues.append('source_transcription_native' if b['type']==0 else 'source_image_occurrence')
                if invalid:
                    # Preserve source anomaly, not an invented fine-grained box.
                    box = [0,0,1,1]
                nb.append({'index':i,'type':'text' if b['type']==0 else 'image','bbox':box,'content':txt,
                           'original_bbox_points':list(b['bbox']), 'issues':issues,
                           'quality':'needs_review' if invalid else 'extracted'})
                if b['type']==0:
                    issues.extend(['native_literal_only; table_graph_relationships_unverified',
                                   'native_independent_verification_not_performed'])
                    spans=[];lines=[];offset=0
                    raw_lines=native_raw['blocks'][i]['lines']
                    if len(b['lines'])!=len(raw_lines):raise ValueError('Native line evidence count mismatch')
                    for li,(line,raw_line)in enumerate(zip(b['lines'],raw_lines)):
                        if len(line['spans'])!=len(raw_line['spans']):raise ValueError('Native span evidence count mismatch')
                        if li:offset+=1
                        line_text=''.join(s['text']for s in line['spans'])
                        lines.append({'text':line_text,'bbox':native_box(line['bbox']),
                                      'original_bbox_points':list(line['bbox']),'direction':list(line['dir']),
                                      'writing_mode':line['wmode']})
                        for si,(span,raw_span)in enumerate(zip(line['spans'],raw_line['spans'])):
                            if ''.join(c['c']for c in raw_span['chars'])!=span['text']:
                                raise ValueError('Native raw-character and span text alignment mismatch')
                            spans.append({'text':span['text'],'font':span['font'],'flags':span['flags'],'size':span['size'],
                                'line_index':li,'span_index':si,'text_range':[offset,offset+len(span['text'])],
                                'bbox':native_box(span['bbox']),'original_bbox_points':list(span['bbox']),
                                'characters':[{'text':c['c'],'text_offset':offset+ci,'original_bbox_points':list(c['bbox']),
                                               'bbox':native_box(c['bbox']),'origin_points':list(c['origin'])}
                                              for ci,c in enumerate(raw_span['chars'])]})
                            offset+=len(span['text'])
                    nb[-1].update(source_text_spans=spans,source_text_lines=lines)
                if b['type']==1 and b.get('image'):
                    source_images[f'p{number}-b{i}'] = {'image':b['image'],'mask':b.get('mask'),
                        'transform_points':list(b.get('transform',[])), 'bbox_points':list(b['bbox'])}
            native_ref=f'raw/p{number:04}-native.json'
            native_warning=localize_native_warnings(nb,native_ref)
            dump(out/native_ref, {'page_idx':number-1,'parser_input_pdf_sha256':digest,'blocks':nb})
            native_chars = sum(len(b['content']) for b in nb)
            vector_paths = len(page.get_drawings())
            blank = native_chars == 0 and image.convert('L').getextrema() == (255,255)
            native_blocks = convert_middle({'blocks':nb},number,crop,rotation)
            native_source={}
            for source_block in nb:
                for item in [source_block]+source_block.get('children',[]):
                    native_source[f'p{number}-b{item["index"]}']=[{**line,'bbox':rotate_bbox(line['bbox'],rotation)}
                        for line in item.get('source_text_lines',[])]
            use_vlm = a.engine == 'mineru' or (a.engine == 'hybrid' and not blank and
                (number in selected or number in layout_pages or native_warning or (not selected and native_chars<40)))
            page_event_start=len(model_counter['events'])
            if number in evidence:
                visual = convert_middle(evidence[number],number,lambda ident,box:crop(ident+'-vlm',box),rotation)
                blocks = merge_native_visual(native_blocks,visual)
                mode = 'imported-evidence'
            elif use_vlm:
                # Upright high-resolution derived page retains original locator.
                derived = out/f'raw/p{number:04}-derived.pdf'
                one = fitz.open()
                pp = one.new_page(width=image.width,height=image.height)
                pp.insert_image(pp.rect,filename=str(out/rel))
                one.save(derived)
                one.close()
                parsed = parse(derived,tier='advanced',ocr_mode='ocr',image_analysis=True)
                dest = out/f'raw/p{number:04}-mineru'
                parsed.save(writer(str(dest)))
                data = json.loads((dest/'middle_json.json').read_text())
                if len(data['pages']) != 1 or data['pages'][0]['page_idx'] != 0:
                    raise ValueError('derived page evidence coverage mismatch')
                visual = convert_middle(data['pages'][0],number,lambda ident,box:crop(ident+'-vlm',box))
                # Preserve all native/image occurrences. On image-only scans,
                # literal-looking MinerU text is still a model candidate, never
                # a verified graph reconstruction or exercise answer.
                blocks = merge_native_visual(native_blocks,visual)
                mode = f'mineru-{a.vlm_device}-local-vlm'
            else:
                blocks = native_blocks
                mode = 'native'
            layout_generation={'events':model_counter['events'][page_event_start:]}
            if a.engine!='native' and not blank:
                # Native high-character counts are representation, not a font
                # mapping proof. Compare independently detected spatial lines;
                # never replace native IDs/text/bboxes with guessed corrections.
                page_scan=verifier.scan(image)
                checks=[]
                for block in blocks:
                    if not block['text'].strip()or block['type']in ('image','table','equation','other'):continue
                    box=block['bbox']
                    inside=[line for line in page_scan.get('lines',[])if
                        box[0]-.003<=line['bbox'][0] and box[1]-.003<=line['bbox'][1] and
                        box[2]+.003>=line['bbox'][2] and box[3]+.003>=line['bbox'][3]]
                    subset={**page_scan,'lines':inside}
                    native=any(i.startswith('source_transcription_native')for i in block['issues'])
                    if native:
                        proof=apply_native_verification(block,subset,native_source.get(block['id'],[]),
                            f'raw/p{number:04}-text-verification.json#{block["id"]}')
                    else:
                        proof=compare_literal(block['text'],subset,layout_generation)
                        if proof['status']=='verified':
                            block['quality']='extracted';block['issues'].append(f'ocr_machine_verified_literal:raw/p{number:04}-text-verification.json#{block["id"]}')
                    checks.append({'block_id':block['id'],'native_text_preserved':native,'verification':proof})
                dump(out/f'raw/p{number:04}-text-verification.json',{'original_pdf_page':number,'independent_ocr':page_scan,'checks':checks})
            automatic = []
            if region_client is not None and (not selected or number in selected):
                # Native prose must never suppress OCR of embedded image text.
                automatic = [(b['bbox'],b) for b in native_blocks if b['type']=='image' and
                             not any('native_bbox_invalid' in i for i in b['issues'])]
                if not automatic and not native_chars and not blank:
                    automatic = [([0,0,1,1],None)]
            requested_regions = [(box,None) for box in regions.get(number, [])]
            requested_regions += [pair for pair in automatic if pair[0] not in regions.get(number, [])]
            if region_client is not None:
                for ordinal, (requested,auto_parent) in enumerate(requested_regions):
                    box = bbox(requested)
                    ident = f'p{number}-b{len(nb)+ordinal}-region'
                    asset = crop(ident, box)
                    region_image = Image.open(out/asset).convert('RGB')
                    candidates = [b for b in native_blocks if b['type']=='image' and b['bbox'][0]<=box[0] and b['bbox'][1]<=box[1] and b['bbox'][2]>=box[2] and b['bbox'][3]>=box[3]]
                    parent = auto_parent if auto_parent is not None else min(candidates,key=lambda b:(b['bbox'][2]-b['bbox'][0])*(b['bbox'][3]-b['bbox'][1])) if candidates else None
                    input_kind = 'final_raster_region'
                    source_ref = None
                    mask_ref=None;source_transform=None
                    compositing=None
                    # Recognize the actual embedded raster, not native text or
                    # other overlays inside its rendered bbox. Exact-source
                    # cache reuse retains every occurrence's own page/bbox.
                    if auto_parent is not None and parent and parent['id'] in source_images:
                        original_record = source_images[parent['id']]
                        original_image = original_record['image'];source_transform=original_record['transform_points']
                        digest_image = hashlib.sha256(original_image).hexdigest()
                        source_ref = 'raw/source-images/i'+digest_image+'.bin'
                        (out/'raw/source-images').mkdir(exist_ok=True)
                        (out/source_ref).write_bytes(original_image)
                        if original_record['mask']:
                            mask_bytes=original_record['mask'];mask_digest=hashlib.sha256(mask_bytes).hexdigest()
                            mask_ref='raw/source-images/m'+mask_digest+'.bin';(out/mask_ref).write_bytes(mask_bytes)
                        compositing={'source_image_sha256':digest_image,
                            'source_mask_sha256':mask_digest if original_record['mask'] else None,
                            'source_image_bytes':len(original_image),
                            'source_mask_bytes':len(original_record['mask']) if original_record['mask'] is not None else None,
                            'source_bbox_points':original_record['bbox_points'],'parent_id':parent['id']}
                        region_image=composite_embedded(original_image,original_record['mask'],pdf_softmask=True,evidence=compositing)
                        input_kind = 'embedded_raster_original_orientation_composited_white; spatial_parent_only'
                        if compositing['source_image_size']!=compositing['output_size']:
                            input_kind += '; opaque_constant_colour_expanded_to_original_mask_resolution; no_page_overlays'
                    if region_image.width*region_image.height > 3900000:
                        factor = math.sqrt(3900000/(region_image.width*region_image.height))
                        region_image = region_image.resize((max(1,int(region_image.width*factor)),max(1,int(region_image.height*factor))))
                    ocr_ref = f'raw/p{number:04}-region{ordinal}-ocr.png'
                    region_image.save(out/ocr_ref)
                    region_start = time.monotonic()
                    cache_key = sha256(out/ocr_ref)
                    reused = cache_key in image_cache
                    uniform = all(lo==hi for lo,hi in region_image.getextrema())
                    event_start=len(model_counter['events'])
                    response = image_cache[cache_key]['response'] if reused else '' if uniform else region_client.content_extract(region_image,type='text')
                    if not isinstance(response,str):
                        raise ValueError('unexpected official text-recognition response type')
                    generation=image_cache[cache_key]['generation']if reused else {'events':model_counter['events'][event_start:]}
                    if not reused:image_cache[cache_key] = {'response':response,'generation':generation}
                    literal,response_kind = literal_response(response)
                    cpu_scan=verifier.scan(region_image)if not uniform else {'status':'uniform','lines':[]}
                    proof=compare_literal(literal,cpu_scan,generation)
                    raw_ref=f'raw/p{number:04}-region{ordinal}.json'
                    raw={'original_pdf_page':number,'parser_input_pdf_sha256':digest,'final_raster_bbox':box,
                         'prompt':region_client.prompts['[default]'], 'raw_text':response,'seconds':time.monotonic()-region_start,
                         'source_crop_sha256':cache_key,'cache_reused':reused,'uniform_decorative':uniform,
                         'input_kind':input_kind,'source_image_asset':source_ref,'source_mask_asset':mask_ref,
                         'source_transform_points':source_transform,'source_compositing':compositing,'ocr_input_asset':ocr_ref,
                         'semantic_role':response_kind+'; no diagram relationships inferred',
                         'generation_limit_tokens':4096,'generation':generation,
                         'generation_finish_reason_available':bool(generation['events'])and all(e.get('finish_metadata_available')for e in generation['events']),
                         'independent_ocr':cpu_scan,'verification':proof,'recovery':[]}
                    # Persist primary response immediately; failed targeted work
                    # must not erase the original successful/partial evidence.
                    dump(out/raw_ref,raw)

                    region_block = {'id':ident,'type':'text','bbox':box,'text':literal,'quality':'needs_review',
                                    'issues':['source_transcription_ocr','region_transcription_not_verified_diagram_structure',
                                              'ocr_generation_completeness_not_proven'], 'assets':[asset],
                                    'parent_id':parent['id'] if parent else None}
                    if proof['status']=='verified':
                        region_block['quality']='extracted';region_block['issues']=['source_transcription_ocr',
                            'region_transcription_not_verified_diagram_structure','ocr_machine_verified_literal:'+raw_ref]
                    else:
                        region_block['issues'].extend('ocr_verification:'+reason for reason in proof['reasons'])
                    if response_kind=='explicit_refusal_not_source_text':
                        region_block['issues'].remove('source_transcription_ocr')
                        region_block['issues'].append('ocr_response_refusal_not_source_transcription; exact_response_retained_raw')
                        warning='Some image OCR requests returned explicit refusal/no-text responses; raw responses retained, not indexed as source text.'
                        if warning not in manifest['warnings']:manifest['warnings'].append(warning)
                    if parent:
                        parent['issues'].extend(['image_ocr_attempted' if not uniform else 'image_ocr_not_needed_uniform',
                            'image_class_decorative_uniform' if uniform else 'image_class_text_bearing' if literal.strip() else 'image_class_visual_without_recognized_text'])
                        if reused: parent['issues'].append('image_cache_reuse; occurrence_locator_retained')
                        blocks.insert(blocks.index(parent)+1,region_block)
                    else:
                        blocks.append(region_block)
                    def append_recovery(trial,tile_index):
                        if trial.get('status')!='complete':return
                        trial_literal,trial_kind=literal_response(trial['raw_text'])
                        trial_proof=trial['verification'];sub=trial['source_input_bbox']
                        recovered_asset='assets/'+ident+f'-recovery{tile_index}.png'
                        # Reader accepts only registered assets/, never expose
                        # private raw/ as a public raster-serving namespace.
                        (out/recovered_asset).write_bytes((out/trial['ocr_input_asset']).read_bytes())
                        spatial_only=bool(source_ref or trial.get('source_input_rotation',0))
                        final_box=box if spatial_only else [box[0]+sub[0]*(box[2]-box[0]),box[1]+sub[1]*(box[3]-box[1]),
                            box[0]+sub[2]*(box[2]-box[0]),box[1]+sub[3]*(box[3]-box[1])]
                        recovered={'id':ident+f'-recovery{tile_index}','type':'text','bbox':final_box,'text':trial_literal,
                            'quality':'extracted'if trial_proof['status']=='verified'else 'needs_review',
                            'issues':['source_transcription_ocr','targeted_literal_recovery; not_graph_relationships',
                                      ('ocr_machine_verified_literal:'if trial_proof['status']=='verified'else 'ocr_recovery_unverified:')+raw_ref+f'#recovery{tile_index}',
                                      'source_tile; spatial_parent_only'if spatial_only else 'final_raster_source_tile'],
                            'assets':[recovered_asset],'parent_id':parent['id']if parent else None}
                        if trial_kind=='explicit_refusal_not_source_text':recovered['issues'][0]='ocr_response_refusal_not_source_transcription'
                        blocks.append(recovered)
                    if reused:
                        for tile_index,trial in enumerate(image_cache[cache_key].get('recovery',[])):
                            raw['recovery'].append({**trial,'cache_reused':True});append_recovery(trial,tile_index)
                        raw.update(image_cache[cache_key].get('recovery_summary',{}))
                        dump(out/raw_ref,raw)
                    if not uniform and not reused and proof['status']!='verified':
                        recovery_scan=cpu_scan;recovery_image=region_image;recovery_rotation=0
                        raw['orientation_probes']=[]
                        if cpu_scan.get('status')=='complete'and orientation_needed(cpu_scan):
                            # CPU-only bounded cardinal probes; no blind VLM
                            # retries on a no-text photograph/decorative raster.
                            for degrees in (90,270):
                                rotated=region_image.rotate(-degrees,expand=True);scan=verifier.scan(rotated)
                                raw['orientation_probes'].append({'clockwise_degrees':degrees,'independent_ocr':scan})
                                lines=scan.get('lines',[])
                                better=(linear_layout(lines)and not linear_layout(recovery_scan.get('lines',[])))or sum(len(line['text'])for line in lines)>sum(len(line['text'])for line in recovery_scan.get('lines',[]))
                                if lines and min(line['confidence']for line in lines)>=.94 and better:
                                    recovery_scan=scan;recovery_image=rotated;recovery_rotation=degrees
                            dump(out/raw_ref,raw)
                        allowance=recovery_allowance(a.ocr_recovery_call_limit,recovery_calls,number,len(doc))
                        raw['recovery_cumulative_page_allowance']=a.ocr_recovery_call_limit*number//len(doc)
                        raw['recovery_deferred_by_page_budget']=allowance==0 and recovery_calls<a.ocr_recovery_call_limit
                        trials=recovery_tiles(recovery_scan,max_tiles=allowance,candidate_text=literal)
                        planned={i for tile in trials for i in tile['cpu_line_indices']}
                        raw['targeted_cpu_line_count']=len(recovery_scan.get('lines',[]))
                        raw['targeted_cpu_lines_unattempted']=sorted(set(range(raw['targeted_cpu_line_count']))-planned)
                        for tile_index,tile in enumerate(trials):
                            recovery_calls+=1
                            tile_image=pixel_crop(recovery_image,tile['bbox'])
                            tile_ref=f'raw/p{number:04}-region{ordinal}-recovery{tile_index}.png'
                            tile_image.save(out/tile_ref)
                            before=len(model_counter['events'])
                            trial={'source_input_bbox':tile['bbox'],'scope':tile['scope'],'ocr_input_asset':tile_ref,
                                   'source_input_rotation':recovery_rotation,
                                   'cpu_line_indices':tile['cpu_line_indices'],
                                   'original_cpu_expected_text':tile['expected_cpu_text'],
                                   'minimum_original_cpu_confidence':tile['minimum_original_cpu_confidence'],
                                   'ocr_input_sha256':sha256(out/tile_ref)}
                            try:
                                trial_response=region_client.content_extract(tile_image,type='text')
                                if not isinstance(trial_response,str):raise ValueError('unexpected targeted OCR response type')
                                trial_literal,trial_kind=literal_response(trial_response)
                                trial_generation={'events':model_counter['events'][before:]}
                                trial_scan=verifier.scan(tile_image)
                                trial_proof=compare_literal(trial_literal,trial_scan,trial_generation)
                                trial.update(raw_text=trial_response,response_kind=trial_kind,generation=trial_generation,
                                             independent_ocr=trial_scan,verification=trial_proof,status='complete')
                                # A re-recognition that drops a detected line is
                                # not a verified replacement for the parent crop.
                                expected=normalized(tile['expected_cpu_text'])
                                if normalized(trial_literal)!=expected:
                                    high_original=[recovery_scan['lines'][i]['text']for i in tile['cpu_line_indices']if recovery_scan['lines'][i]['confidence']>=.94]
                                    if tile['minimum_original_cpu_confidence']<.94 and all(normalized(text)in normalized(trial_literal)for text in high_original):
                                        # A low-confidence FULL-image CPU error
                                        # may genuinely improve on a larger crop.
                                        # New CPU+VLM exact agreement/stop is still
                                        # mandatory; preserve old text/confidence.
                                        trial_proof['observations']=['original_low_confidence_cpu_changed_on_targeted_crop; exact_old_evidence_retained']
                                    else:
                                        trial_proof['status']='unverified';trial_proof['reasons'].append('targeted_crop_disagrees_with_original_high_confidence_cpu_detection')
                                append_recovery(trial,tile_index)
                            except (InterruptedError,TimeoutError)as error:
                                trial.update(status='cancelled'if isinstance(error,InterruptedError)else 'deadline',
                                             error_type=type(error).__name__,error=str(error))
                                raw['recovery'].append(trial);dump(out/raw_ref,raw)
                                raise
                            except Exception as error:
                                trial.update(status='failed',error_type=type(error).__name__,error=str(error))
                            raw['recovery'].append(trial);dump(out/raw_ref,raw)
                        raw['recovery_call_limit']=a.ocr_recovery_call_limit
                        raw['recovery_budget_remaining']=a.ocr_recovery_call_limit-recovery_calls
                        raw['all_detected_cpu_lines_verified']=bool(trials)and not raw['targeted_cpu_lines_unattempted']and all(
                            trial.get('verification',{}).get('status')=='verified'for trial in raw['recovery'])
                        image_cache[cache_key]['recovery']=raw['recovery']
                        image_cache[cache_key]['recovery_summary']={k:raw[k]for k in ('targeted_cpu_line_count','targeted_cpu_lines_unattempted','all_detected_cpu_lines_verified')}
                        dump(out/raw_ref,raw)
                    mode = 'native+region-text-local-vlm'
            duplicate_candidates(blocks)
            for b in native_blocks:
                if b['type']=='image' and not any(i.startswith('image_ocr_') for i in b['issues']):
                    b['issues'].append('image_ocr_not_attempted; visual_model_candidate_only' if use_vlm or number in evidence else
                                       'image_ocr_not_attempted; native_engine_or_explicit_selection_or_invalid_bbox')
            if not blocks and not blank:
                blocks = [{'id':f'p{number}-b0','type':'image','bbox':[0,0,1,1],'text':'',
                           'quality':'needs_review','issues':['no_transcription_blank_or_visual_unverified'],
                           'assets':[crop(f'p{number}-b0',[0,0,1,1])],'parent_id':None}]
            page_issues = []
            if not blank and not any(b['text'].strip() for b in blocks):
                page_issues.append('no_text_transcription; source_raster_retained')
            if any('\ufffd' in b['text'] for b in blocks):
                page_issues.append('broken_text_layer')
                for b in blocks:
                    if '\ufffd' in b['text']:
                        b['quality']='needs_review';b['issues'].append('broken_text_layer')
            review = page_issues or any(b['quality']=='needs_review' for b in blocks)
            labels = [b['text'] for b in blocks if b['type']=='page_number' and b['text'].strip()]
            manifest['pages'].append({'number':number,'printed_label':' / '.join(labels) or None,'rotation':rotation,
                                     'image':rel,'width':image.width,'height':image.height,
                                     'status':'blank' if blank else 'needs_review' if review else 'text','issues':page_issues,'blocks':blocks})
            model_calls = model_counter['calls']-model_calls_before
            receipt['page_timings'].append({'page':number,'seconds':time.monotonic()-begun,'mode':mode,
                'model_processed':model_calls>0,'model_calls':model_calls,'imported_evidence':number in evidence,
                'vector_paths':vector_paths})
            manifest['coverage'] = coverage_of(manifest)
            dump(out/'manifest.json',manifest)
            dump(out/'receipt.json',receipt)
            print(json.dumps(receipt['page_timings'][-1]),flush=True)
        manifest['complete'] = len(manifest['pages']) == len(doc)
        manifest['coverage'] = coverage_of(manifest)
        if sha256(source) != digest:
            raise ValueError('source changed during parse')
        receipt['validation'] = validate_bundle(out,manifest)

        receipt['status'] = 'complete'
        doc.close()
        return 0
    except BaseException as exc:
        manifest['complete'] = False
        manifest['coverage'] = coverage_of(manifest)
        receipt.update(status='failed',error_type=type(exc).__name__,error=str(exc)[:1600])
        manifest['warnings'].append('Incomplete job; inspect receipt and preserved raw evidence.')
        return 2
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        receipt['independent_ocr']=verifier.info
        receipt['targeted_recovery_calls']=recovery_calls
        if region_client is not None:
            import asyncio
            asyncio.run(region_client.aclose())
        if restore_counter is not None:restore_counter()
        if home is not None and home.is_dir():
            import shutil
            # Runtime-only absolute model paths do not belong to portable bundle.
            shutil.rmtree(home)
        receipt['wall_seconds']=time.monotonic()-start
        dump(out/'manifest.json',manifest)
        dump(out/'receipt.json',receipt)
        print(json.dumps(receipt,ensure_ascii=False),flush=True)


if __name__ == '__main__':
    raise SystemExit(main())
