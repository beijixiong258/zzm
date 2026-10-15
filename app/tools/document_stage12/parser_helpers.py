"""Stage12 schema-1 bundle conversion and validation (no model lifecycle)."""
from __future__ import annotations
import hashlib
import json
import math
import re
import unicodedata
from pathlib import Path, PurePosixPath

TYPES = {'text', 'heading', 'list', 'table', 'image', 'caption', 'header', 'footer', 'page_number', 'equation', 'other'}
QUALITIES = {'extracted', 'needs_review', 'excluded'}


def native_text_warning(text):
    """A triage trigger, not an OCR accuracy score or proof of good text."""
    # Test controls before isspace(): bad font mappings can encode a visible
    # glyph as U+001F, which Python otherwise discards as layout whitespace.
    if any(unicodedata.category(c)=='Cc' and c not in '\t\n\r' for c in text):
        return 'native_font_mapping_unusable'
    chars=[c for c in text if not c.isspace()]
    if '\ufffd' in text or any(unicodedata.category(c) in ('Co','Cn') for c in chars):
        return 'native_font_mapping_unusable'
    if len(chars)>=80:
        letters=sum(unicodedata.category(c).startswith('L') for c in chars)
        noisy=sum(unicodedata.category(c)[0] in ('P','S','N') for c in chars)
        # The observed bad PDF maps prose into punctuation/digits. Numeric-only
        # tables are not declared corrupt by this mixed-prose heuristic.
        if letters/len(chars)>=.15 and noisy/len(chars)>.45:
            return 'native_mixed_prose_symbol_density_suspect'
    return None


def localize_native_warnings(blocks, raw_ref):
    """Quarantine source blocks, never an entire page for one special glyph.

    Retain the exact parent. Mixed-font parents may expose exact, positioned
    span fragments, but NOT any span using a font implicated in that parent.
    This is literal representation only, not a table/arrow relationship proof.
    """
    warned=False
    for block in blocks:
        if block['type']!='text':continue
        spans=block.get('source_text_spans',[])
        def span_warning(span):
            # Unlike inserted line separators, these controls came from actual
            # PDF glyphs, including a CR mapped from a visible 'M' in src20.
            if any(unicodedata.category(c['text'])=='Cc' for c in span.get('characters',[])):
                return 'native_font_mapping_unusable'
            return native_text_warning(span['text'])
        bad_fonts={s['font'] for s in spans if span_warning(s)}
        warning=native_text_warning(block['content'])
        if not warning and not bad_fonts:continue
        warned=True
        block['quality']='needs_review'
        block['issues'].append(warning or 'native_font_mapping_unusable')
        block['issues'].append('native_mapping_issue_local_to_source_block; exact_native_retained')
        # A block-level density warning without a localized bad span cannot
        # justify selecting apparently fluent substrings out of suspect prose.
        if not bad_fonts or any('native_bbox_invalid' in issue for issue in block['issues']):continue
        groups=[]
        for span in spans:
            if span['font'] in bad_fonts or native_text_warning(span['text']):continue
            if groups and groups[-1][-1]['line_index']==span['line_index'] and groups[-1][-1]['text_range'][1]==span['text_range'][0]:
                groups[-1].append(span)
            else:groups.append([span])
        children=[]
        for group in groups:
            start,end=group[0]['text_range'][0],group[-1]['text_range'][1]
            text=block['content'][start:end]
            if not text.strip():continue
            box=[min(s['bbox'][0]for s in group),min(s['bbox'][1]for s in group),
                 max(s['bbox'][2]for s in group),max(s['bbox'][3]for s in group)]
            child={'index':str(block['index'])+'-native-fragment'+str(len(children)),
                'type':'text','bbox':box,'content':text,'quality':'extracted',
                'issues':['source_transcription_native','native_exact_source_fragment:'+raw_ref+f'#{block["index"]}:{start}-{end}',
                          'native_literal_only; table_graph_relationships_unverified'],
                'source_parent_index':block['index'],'source_text_range':[start,end],
                'source_text_spans':group,'source_text_lines':[{'text':text,'bbox':box}]}
            children.append(child)
        if children:block['children']=children
    return warned


def dump(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def composite_embedded(image_bytes,mask_bytes=None,*,pdf_softmask=False,evidence=None):
    """Composite decoded source pixels, never a page clip or text overlay.

    PDF soft masks without Matte map independently to the same unit square
    (ISO 32000-1, 11.6.5.2 / Table 145). For an opaque constant-colour base,
    extending that exact colour to a larger mask grid is lossless: no mask
    sample is rescaled. Other unequal grids remain unsupported, not guessed.
    The caller opts in only for a PDF soft mask; generic PNG alpha is retained.
    """
    import io
    from contextlib import nullcontext
    from PIL import Image,ImageChops
    with Image.open(io.BytesIO(image_bytes))as embedded:
        if embedded.width*embedded.height>16_000_000:raise ValueError('Embedded raster exceeds16million source pixels')
        # Read BOTH headers before conversion/decoding or output allocation.
        with (Image.open(io.BytesIO(mask_bytes)) if mask_bytes is not None else nullcontext(None)) as mask:
            if mask is not None and mask.width*mask.height>16_000_000:
                raise ValueError('Embedded softmask exceeds16million source pixels')
            source_size=embedded.size;mask_size=mask.size if mask is not None else None
            unequal=mask is not None and mask_size!=source_size
            if unequal and (not pdf_softmask or mask.mode not in ('1','L') or
                            mask.width<embedded.width or mask.height<embedded.height):
                raise ValueError('Embedded image mask dimensions disagree; unsupported softmask grid')
            rgba=embedded.convert('RGBA')
            operation='same_grid_softmask' if mask is not None else 'source_alpha_only'
            if unequal:
                extrema=rgba.getextrema()
                if not all(lo==hi for lo,hi in extrema) or extrema[3]!=(255,255):
                    raise ValueError('Embedded image mask dimensions disagree; base is not opaque constant colour')
                rgba=Image.new('RGBA',mask_size,rgba.getpixel((0,0)))
                operation='opaque_constant_colour_expanded_to_original_mask_grid; mask_samples_not_rescaled'
            mask_extrema=None
            if mask is not None:
                alpha=mask.convert('L')  # Decode failures propagate; never synthesize blank pixels.
                mask_extrema=list(alpha.getextrema())
                rgba.putalpha(ImageChops.multiply(rgba.getchannel('A'),alpha))
            alpha_extrema=list(rgba.getchannel('A').getextrema())
            result=Image.new('RGB',rgba.size,'white');result.paste(rgba,mask=rgba.getchannel('A'))
            if evidence is not None:
                evidence.update(source_image_size=list(source_size),source_mask_size=list(mask_size) if mask_size else None,
                    output_size=list(result.size),operation=operation,mask_extrema=mask_extrema,
                    effective_alpha_extrema=alpha_extrema,background='white',includes_page_overlays=False,
                    decode_status='complete')
            return result


def text_of(value):
    """Keep full text; do not use dict repr as invented transcription."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return '\n'.join(text_of(v) for v in value)
    if isinstance(value, dict):
        return text_of(value.get('content', value.get('text', '')))
    return ''


def bbox(value):
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError('missing normalized source bbox')
    result = [float(v) for v in value]
    if not all(math.isfinite(v) and 0 <= v <= 1 for v in result):
        raise ValueError('bbox outside normalized image')
    if result[0] > result[2] or result[1] > result[3]:
        raise ValueError('inverted bbox')
    return result


def rotate_bbox(value, degrees):
    x1, y1, x2, y2 = bbox(value)
    return {0: [x1,y1,x2,y2], 90: [1-y2,x1,1-y1,x2],
            180: [1-x2,1-y2,1-x1,1-y1], 270: [y1,1-x2,y2,1-x1]}[degrees]


def convert_middle(page, number, crop, rotation=0):
    """MiddleJson native IDs + recursively retained captions/footnotes.

    Input bbox is already normalized. Only rotate when applying a rotation to
    the evidence raster, not when parsing an already upright derived PDF.
    """
    result = []
    used = set()

    def visit(block, parent=None, fallback='0', inherited=None):
        native = str(block.get('index', fallback))
        native = re.sub(r'[^A-Za-z0-9_-]', '_', native)
        ident = f'p{number}-b{native}'
        if ident in used:
            ident = f'{ident}-n{len(result)}'
        used.add(ident)
        kind = str(block.get('type', 'other'))
        if kind == 'paragraph_title':
            kind = 'heading'
        elif 'caption' in kind:
            kind = 'caption'
        elif kind not in TYPES:
            kind = 'other'
        box = rotate_bbox(block.get('bbox', inherited), rotation)
        content = text_of(block.get('content', ''))
        issues = list(block.get('issues', []))
        quality = block.get('quality', 'extracted')
        # A graph-as-table is not authoritative just because the parser exited0.
        if kind in {'image', 'table', 'other', 'equation'}:
            quality = 'needs_review'
            issues.append('unverified_visual_reconstruction' if content else 'visual_requires_source_review')
        assets = [crop(ident, box)] if kind in {'image', 'table', 'other', 'equation'} else []
        result.append({'id': ident, 'type': kind, 'bbox': box, 'text': content,
                       'quality': quality, 'issues': issues, 'assets': assets, 'parent_id': parent})
        # MinerU4 uses blocks for image/table nested captions and footnotes.
        children = []
        # Native MiddleJson nests labels inside content, not only blocks.
        for child in block.get('content', []) if isinstance(block.get('content'),list) else []:
            if isinstance(child,dict) and 'bbox' in child and ('caption' in child.get('type','') or 'footnote' in child.get('type','')):
                children.append(child)
        for key in ('blocks', 'children', 'captions', 'footnotes'):
            for child in block.get(key, []) or []:
                if isinstance(child, dict):
                    children.append(child)
        for ordinal, child in enumerate(children):
            visit(child, ident, f'{native}-c{ordinal}', box if rotation == 0 else block.get('bbox'))

    for ordinal, block in enumerate(page.get('blocks', [])):
        visit(block, fallback=str(ordinal))
    return result


def literal_response(value):
    """Do not promote observed OCR refusal prose into source transcription.

    Keep the exact response in raw evidence. This is a narrow detector for
    explicit refusal/no-text responses, not a rewrite of arbitrary OCR content.
    """
    refusal = re.fullmatch(r'(?:the image is too blurry to recognize any text content|'
        r'no (?:readable )?text(?: (?:was )?(?:detected|found|recognized))?(?: in (?:the|this) image)?|'
        r'(?:i (?:cannot|can\'t)|unable to) (?:read|recognize|extract)(?: any)? text(?: (?:in|from) (?:the|this) image)?)\.?',
        value.strip(),re.IGNORECASE)
    # Observed retained outputs used multi-sentence no-text descriptions; those
    # are model commentary, not source transcription. Match the explicit lead,
    # not arbitrary prose that merely happens to contain the phrase 'no text'.
    explanatory = re.match(r'^The image (?:contains no (?:discernible|readable) text(?: or characters)?[.!]|'
        r'is (?:too blurry|blank) to (?:recognize|read|extract))',value.strip(),re.IGNORECASE)
    return ('', 'explicit_refusal_not_source_text') if refusal or explanatory else (value, 'literal_candidate' if value.strip() else 'empty_response')


def observe_vlm_http(server_url):
    """Count successful fresh model HTTP responses in this owned process only.

    Native, imported evidence, reused OCR and GET health/model checks count0.
    Observe the exact configured loopback port, never the teaching endpoint.
    """
    import httpx
    from urllib.parse import urlparse
    port=urlparse(server_url).port or 80
    counts={'calls':0,'events':[]}
    original_sync,original_async=httpx.Client.send,httpx.AsyncClient.send
    def model_request(request,response):
        return (request.method=='POST' and request.url.host in ('localhost','127.0.0.1') and
                (request.url.port or 80)==port and request.url.path in
                ('/completion','/completions','/v1/completions','/chat/completions','/v1/chat/completions') and
                response.status_code==200)
    def sync_send(client,request,*args,**kwargs):
        response=original_sync(client,request,*args,**kwargs)
        if model_request(request,response):
            record(response)
        return response
    async def async_send(client,request,*args,**kwargs):
        response=await original_async(client,request,*args,**kwargs)
        if model_request(request,response):
            record(response)
        return response
    def record(response):
        counts['calls']+=1
        event={'finish_reason':None,'finish_metadata_available':False}
        try:
            data=response.json()
            choices=data.get('choices',[])
            if choices:
                event['finish_reason']=choices[0].get('finish_reason')
            elif data.get('stopped_limit'):event['finish_reason']='length'
            elif data.get('stopped_eos')or data.get('stopped_word'):event['finish_reason']='stop'
            event['finish_metadata_available']=event['finish_reason']is not None
            usage=data.get('usage',{})
            event['completion_tokens']=usage.get('completion_tokens',data.get('tokens_predicted'))
        except (ValueError,RuntimeError):
            # Streaming/unread bodies are not consumed just to invent a finish.
            pass
        counts['events'].append(event)
    httpx.Client.send,httpx.AsyncClient.send=sync_send,async_send
    def restore():
        httpx.Client.send,httpx.AsyncClient.send=original_sync,original_async
    return counts,restore


def merge_native_visual(native, visual):
    """Retain correct native evidence; attach model candidates geometrically only.

    A spatial parent is a locator, never an inferred conceptual relationship.
    Visual candidates stay review-only: MinerU image/table prose can interpret
    rather than literally transcribe the source, including worksheet answers.
    """
    result = list(native)
    ids = {b['id'] for b in result}
    remap = {}
    for b in visual:
        new = dict(b)
        ident = b['id'] + '-vlm'
        while ident in ids:
            ident += '-v'
        ids.add(ident)
        remap[b['id']] = ident
        new['id'] = ident
        if b['type'] in {'image', 'table', 'other', 'equation'}:
            new['quality'] = 'needs_review'
            new['issues'] = list(b['issues']) + ['visual_interpretation_unverified; not_literal_source_transcription']
        else:
            new['quality'] = 'needs_review'
            new['issues'] = list(b['issues']) + ['source_transcription_ocr; fullpage_model_candidate']
        result.append(new)
    for b in result[len(native):]:
        if b['parent_id'] in remap:
            b['parent_id'] = remap[b['parent_id']]
        elif b['parent_id'] is None:
            box = b['bbox']
            candidates = [n for n in native if n['type'] == 'image' and
                          n['bbox'][0] <= box[0] and n['bbox'][1] <= box[1] and
                          n['bbox'][2] >= box[2] and n['bbox'][3] >= box[3]]
            if candidates:
                b['parent_id'] = min(candidates, key=lambda n:
                    (n['bbox'][2]-n['bbox'][0])*(n['bbox'][3]-n['bbox'][1]))['id']
    return result


def coverage_of(manifest):
    """Counts inventory/processing separately from semantic accuracy."""
    blocks = [b for p in manifest['pages'] for b in p['blocks']]
    images = [b for b in blocks if b['type'] == 'image' and
              any(i.startswith('source_image_occurrence') for i in b['issues'])]
    def has(b, prefix):
        return any(i.startswith(prefix) for i in b['issues'])
    return {'version': 1, 'representation': 'original_pdf_pages',
            'expected_pages': manifest['page_count'], 'rendered_pages': len(manifest['pages']),
            'page_set_complete': manifest['complete'],
            'native_text_blocks': sum(has(b, 'source_transcription_native') for b in blocks),
            'native_text_chars': sum(len(b['text']) for b in blocks if has(b, 'source_transcription_native')),
            'source_image_occurrences': len(images),
            'image_ocr_attempted': sum(has(b, 'image_ocr_attempted') for b in images),
            'image_ocr_text': sum(has(b, 'image_class_text_bearing') for b in images),
            'image_ocr_empty': sum(has(b, 'image_class_visual_without_recognized_text') for b in images),
            'image_decorative_uniform': sum(has(b, 'image_class_decorative_uniform') for b in images),
            'image_reused_occurrences': sum(has(b, 'image_cache_reuse') for b in images),
            'image_untranscribed': sum(has(b, 'image_ocr_not_attempted') for b in images),
            'literal_ocr_blocks': sum(has(b, 'source_transcription_ocr') for b in blocks),
            'literal_ocr_chars': sum(len(b['text']) for b in blocks if has(b, 'source_transcription_ocr')),
            'visual_interpretation_blocks': sum(has(b, 'visual_interpretation_unverified') for b in blocks),
            'machine_verified_literal_blocks':sum(has(b,'ocr_machine_verified_literal:')for b in blocks),
            'targeted_recovery_blocks':sum(has(b,'targeted_literal_recovery')for b in blocks),
            'native_independent_disagreement_blocks':sum(has(b,'native_independent_ocr_disagreement')for b in blocks),
            'excluded_exact_duplicate_blocks':sum(has(b,'exact_overlapping_duplicate_of:')for b in blocks),
            'needs_review_blocks': sum(b['quality'] == 'needs_review' for b in blocks),
            'semantic_accuracy_approved': False, 'all_visuals_transcribed': False,
            'warnings': ['Page-set completion is not semantic completeness or human approval.',
                         'OCR labels do not establish diagram edges, reading order, or exercise answers.']}


def validate_bundle(root, manifest=None):
    """Fail closed on malformed coverage, identities, paths and missing files."""
    supplied_root = Path(root)
    if supplied_root.is_symlink() or any(p.is_symlink() for p in supplied_root.parents):
        raise ValueError('symlink bundle root')
    root = supplied_root.resolve()
    if any(p.is_symlink() for p in root.rglob('*')):
        raise ValueError('symlink in returned bundle')
    if manifest is None:
        manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema_version') != 1 or not re.fullmatch(r'[0-9a-fA-F]{64}', manifest.get('source_sha256', '')):
        raise ValueError('invalid schema/source hash')
    if not isinstance(manifest.get('complete'), bool):
        raise ValueError('complete must be boolean')
    parser = manifest.get('parser', {})
    if not all(isinstance(parser.get(k), str) and parser[k] for k in ('name','version','recipe')):
        raise ValueError('invalid parser metadata')
    if not isinstance(manifest.get('warnings'), list) or not all(isinstance(v,str) for v in manifest['warnings']):
        raise ValueError('invalid warnings')
    count = manifest.get('page_count')
    if type(count) is not int or count < 1:
        raise ValueError('invalid original page_count')
    pages = manifest.get('pages', [])
    nums = [p['number'] for p in pages]
    if nums != sorted(set(nums)) or any(type(n) is not int or not 1 <= n <= count for n in nums):
        raise ValueError('duplicate/out-of-order original pages')
    if manifest['complete'] and nums != list(range(1, count+1)):
        raise ValueError('complete contradicts exact original page set')
    ids = set()

    def asset(ref):
        if not isinstance(ref, str) or '\\' in ref:
            raise ValueError('invalid relative POSIX asset')
        p = PurePosixPath(ref)
        if p.is_absolute() or '..' in p.parts or ':' in ref or not p.parts or ref != p.as_posix():
            raise ValueError('unsafe asset path')
        target = root.joinpath(*p.parts)
        if any(part.is_symlink() for part in [target, *target.parents] if part != root.parent):
            raise ValueError('symlink asset')
        if not target.is_file() or not target.resolve().is_relative_to(root):
            raise ValueError('missing/outside bundle asset')

    for p in pages:
        if p['rotation'] not in (0,90,180,270) or p['status'] not in ('text','blank','needs_review','failed'):
            raise ValueError('invalid page rotation/status')
        if p.get('printed_label') is not None and not isinstance(p['printed_label'],str):
            raise ValueError('invalid printed label')
        if not all(type(p[k]) is int and p[k] > 0 for k in ('width','height')):
            raise ValueError('invalid raster dimensions')
        asset(p['image'])
        local = set(b['id'] for b in p['blocks'])
        for b in p['blocks']:
            if not re.fullmatch(r'p'+str(p['number'])+r'-b[A-Za-z0-9_-]+', b['id']) or b['id'] in ids:
                raise ValueError('invalid/duplicate block locator')
            ids.add(b['id'])
            bbox(b['bbox'])
            if b['type'] not in TYPES or b['quality'] not in QUALITIES or not isinstance(b['text'],str):
                raise ValueError('invalid block type/quality/text')
            if b['parent_id'] is not None and (b['parent_id'] not in local or b['parent_id'] == b['id']):
                raise ValueError('invalid parent binding')
            if not isinstance(b['issues'],list) or not all(isinstance(i,str) for i in b['issues']):
                raise ValueError('invalid block issues')
            for ref in b['assets']:
                asset(ref)
    fmt = manifest.get('source_format', 'pdf')
    if fmt not in ('pdf','pptx','ppt','docx','doc','xls','xlsx','txt','md','png','jpg','jpeg','webp'):
        raise ValueError('invalid original source format')
    if fmt != 'pdf' or 'preview_pdf' in manifest:
        asset(manifest.get('preview_pdf'))
        import pymupdf as fitz
        with fitz.open(root/manifest['preview_pdf']) as preview:
            if not preview.is_pdf or preview.needs_pass or len(preview) != count:
                raise ValueError('invalid derived PDF or page count')
    coverage = manifest.get('coverage')
    if coverage is not None:
        if not isinstance(coverage,dict) or coverage.get('version') != 1:
            raise ValueError('invalid coverage object')
        if coverage.get('rendered_pages') != len(pages) or coverage.get('expected_pages') != count or coverage.get('page_set_complete') != manifest['complete']:
            raise ValueError('coverage page counts contradict manifest')
        if coverage.get('semantic_accuracy_approved') is not False:
            raise ValueError('machine coverage cannot approve semantic accuracy')
        image_info=coverage.get('original_image')
        if image_info is not None and image_info.get('all_frames_retained'):
            rows=image_info.get('frame_map',[])
            if image_info.get('frames')!=count or len(rows)!=count:
                raise ValueError('Image frame map contradicts represented pages')
            for index,row in enumerate(rows):
                if row.get('page')!=index+1 or row.get('frame_index')!=index or row.get('original_source_sha256')!=manifest['source_sha256']:
                    raise ValueError('Image frame original identity/locator mismatch')
                ref=row.get('decoded_rgba_asset');asset(ref)
                if sha256(root/ref)!=row.get('decoded_rgba_sha256'):
                    raise ValueError('Decoded image frame identity changed')
    return {'valid': True, 'represented_pages': len(pages), 'page_count': count,
            'blocks': len(ids), 'complete': manifest['complete'],
            'needs_review_blocks': sum(b['quality']=='needs_review' for p in pages for b in p['blocks'])}
