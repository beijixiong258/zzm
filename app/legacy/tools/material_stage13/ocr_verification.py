"""Independent CPU literal-text verification and source-positioned recovery.

No model lifecycle/downloads. Exact responses/native evidence are never rewritten.
'Verified' means strict two-engine literal agreement in a linear text crop with
recorded non-truncated generation, NOT diagram/table semantics or human approval.
"""
from __future__ import annotations
import hashlib
import importlib.util
import math
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path


def normalized(text):
    # Only NFC and layout whitespace. Case, punctuation, digits, math and glyphs
    # remain significant: O/0, I/l and 1.5/15 must not be approved as equivalent.
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFC', text)).strip()


def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


class CPUVerifier:
    """RapidOCR ONNX CPU, existing explicit local weights only, lazy/once."""
    def __init__(self, models=None):
        self.models=models;self.engine=None;self.initialized=False
        self.info={'engine':'rapidocr-onnx-cpu','available':False,'providers':['CPUExecutionProvider']}
        self.cache={}

    def initialize(self):
        if self.initialized:return
        self.initialized=True
        try:
            spec=importlib.util.find_spec('rapidocr')
            if spec is None:raise ImportError('RapidOCR is not installed; no independent verification')
            root=Path(self.models)if self.models else Path(spec.origin).parent/'models'
            names={'Det':'PP-OCRv6_det_small.onnx','Cls':'ch_ppocr_mobile_v2.0_cls_mobile.onnx','Rec':'PP-OCRv6_rec_small.onnx'}
            paths={key:root/name for key,name in names.items()}
            if not all(p.is_file()and not p.is_symlink()for p in paths.values()):
                raise FileNotFoundError('Existing RapidOCR det/cls/rec local ONNX weights required; no download')
            from rapidocr import RapidOCR,EngineType
            params={'Global.text_score':0.0,'Global.log_level':'error','Global.max_side_len':2048,
                    'Det.limit_side_len':2048,'Det.limit_type':'max',
                    'EngineConfig.onnxruntime.use_cuda':False,'EngineConfig.onnxruntime.use_dml':False,
                    'EngineConfig.onnxruntime.use_cann':False,'EngineConfig.onnxruntime.use_coreml':False,
                    'EngineConfig.onnxruntime.intra_op_num_threads':4,'EngineConfig.onnxruntime.inter_op_num_threads':1}
            for key,path in paths.items():
                params[key+'.model_path']=str(path);params[key+'.engine_type']=EngineType.ONNXRUNTIME
            self.engine=RapidOCR(params=params)
            # Verify actual sessions rather than claim CPU from a flag alone.
            providers=[]
            for name in ('text_det','text_cls','text_rec'):
                component=getattr(self.engine,name,None)
                session=getattr(getattr(component,'session',None),'session',None)
                if session is not None:providers.extend(session.get_providers())
            if len(providers)!=3 or set(providers)!={'CPUExecutionProvider'}:
                raise RuntimeError('Independent OCR must use CPUExecutionProvider only')
            self.info.update(available=True,models={k:{'name':p.name,'sha256':file_hash(p),'bytes':p.stat().st_size}for k,p in paths.items()},
                             actual_providers=sorted(set(providers)))
        except (InterruptedError,TimeoutError):raise
        except (ImportError,OSError,ValueError,TypeError,RuntimeError)as error:
            self.engine=None;self.info.update(error_type=type(error).__name__,error=str(error))

    def scan(self,image):
        self.initialize()
        if self.engine is None:return {**self.info,'status':'unavailable','lines':[]}
        digest=hashlib.sha256(image.convert('RGB').tobytes()+str(image.size).encode()).hexdigest()
        if digest in self.cache:return {**self.cache[digest],'cache_reused':True}
        try:
            import numpy as np
            result=self.engine(np.asarray(image.convert('RGB')))
            lines=[]
            if result.txts is not None:
                if result.scores is None or result.boxes is None or not len(result.txts)==len(result.scores)==len(result.boxes):
                    raise ValueError('Independent OCR text/box/confidence count mismatch')
                for text,score,poly in zip(result.txts,result.scores,result.boxes):
                    points=[[float(x)/image.width,float(y)/image.height]for x,y in poly]
                    if not math.isfinite(float(score))or not 0<=float(score)<=1 or not points or any(not math.isfinite(v)for p in points for v in p):
                        raise ValueError('Independent OCR confidence/geometry is invalid')
                    box=[min(p[0]for p in points),min(p[1]for p in points),max(p[0]for p in points),max(p[1]for p in points)]
                    lines.append({'text':str(text),'confidence':float(score),'polygon':points,
                                  'bbox':[max(0,min(1,v))for v in box]})
            answer={**self.info,'status':'complete','lines':lines,'seconds':float(result.elapse),
                    'input_pixel_sha256':digest,'input_size':list(image.size),'cache_reused':False}
            # Bounded memoization; each persisted raw result keeps its occurrence.
            if len(self.cache)<256:self.cache[digest]=answer
            return answer
        except (InterruptedError,TimeoutError):raise
        except (ValueError,RuntimeError,OSError)as error:
            return {**self.info,'status':'failed','lines':[],'error_type':type(error).__name__,'error':str(error)}


def inline_prefix(first,second):
    """A detected bullet/rating numeral beside prose is still one literal row."""
    a,b=first['bbox'],second['bbox']
    return bool(re.fullmatch(r'(?:\d+[+\-]?|[•\-*])',first['text'].strip()))and a[2]-a[0]<=.04 and b[2]-b[0]>=.20 and -.005<=b[0]-a[2]<=.035


def vertical_overlap_ratio(first,second):
    """Measure skewed line bands at a shared x, not overlapping AABBs."""
    a,b=first['bbox'],second['bbox']
    left,right=max(a[0],b[0]),min(a[2],b[2])
    x=(left+right)/2
    def band(line):
        box=line['bbox'];polygon=line.get('polygon',[])
        if left>=right or len(polygon)!=4:return box[1],box[3]
        ys=[]
        for p,q in zip(polygon,polygon[1:]+polygon[:1]):
            if abs(q[0]-p[0])>1e-9 and min(p[0],q[0])<=x<=max(p[0],q[0]):
                ys.append(p[1]+(x-p[0])*(q[1]-p[1])/(q[0]-p[0]))
        return (min(ys),max(ys))if len(ys)>=2 else (box[1],box[3])
    ay,az=band(first);by,bz=band(second)
    return max(0,min(az,bz)-max(ay,by))/max(1e-9,min(az-ay,bz-by))


def recovery_allowance(limit,used,page,page_count):
    """Cumulative page share; unused calls carry, late pages are not starved."""
    return max(0,min(8,limit*page//page_count-used))


def linear_layout(lines):
    """Do not flatten tables/graphs/jumbled letters into an approved reading order."""
    if not lines:return False
    boxes=[line['bbox']for line in lines]
    if any(b[3]<=b[1]or b[2]<=b[0]for b in boxes):return False
    if any(b[3]-b[1]>(b[2]-b[0])*1.2 and len(lines[i]['text'].strip())>3 for i,b in enumerate(boxes)):return False
    for index,(a,b)in enumerate(zip(boxes,boxes[1:])):
        # Side-by-side same-row detections and backward order are not prose.
        if vertical_overlap_ratio(lines[index],lines[index+1])>.35:
            if inline_prefix(lines[index],lines[index+1]):continue
            return False
        if b[1]<a[1]:return False
    if len(lines)>2:
        starts=[b[0]for b in boxes];heights=sorted(b[3]-b[1]for b in boxes)
        if max(starts)-min(starts)>max(.04,heights[len(heights)//2]*2):return False
    return True


def orientation_needed(scan):
    lines=scan.get('lines',[])
    if not lines:return True
    total=sum(len(normalized(line['text']))for line in lines)
    vertical=sum(len(normalized(line['text']))for line in lines if len(line['text'].strip())>3 and
                 line['bbox'][3]-line['bbox'][1]>(line['bbox'][2]-line['bbox'][0])*1.2)
    return total>0 and vertical>total*.7


def compare_literal(candidate,scan,generation):
    """Exact agreement + confidence + actual finish metadata; near matches fail."""
    lines=scan.get('lines',[]);cpu='\n'.join(line['text']for line in lines)
    a,b=normalized(candidate),normalized(cpu);reasons=[]
    if scan.get('status')!='complete':reasons.append('independent_ocr_unavailable_or_failed')
    if not a or not b:reasons.append('empty_literal_or_no_independent_text')
    if a!=b:reasons.append('independent_text_disagreement')
    if len(a)>max(100,len(b)*5):reasons.append('candidate_length_disproportionate_to_detected_source')
    nonempty=[line.strip()for line in candidate.splitlines()if line.strip()]
    if len(nonempty)>20 and len(set(nonempty))<len(nonempty)*.1:reasons.append('repetitive_generation_suspect')
    if lines and any(not math.isfinite(line['confidence'])or not .94<=line['confidence']<=1 for line in lines):reasons.append('independent_low_or_invalid_confidence')
    if not linear_layout(lines):reasons.append('nonlinear_reading_order_or_structure_unverified')
    events=generation.get('events',[])if isinstance(generation,dict)else []
    finishes=[event.get('finish_reason')for event in events]
    if not finishes or any(reason not in ('stop','eos','eos_token')for reason in finishes):
        reasons.append('generation_truncated'if any(reason in ('length','max_tokens','limit')for reason in finishes)else 'generation_finish_unknown')
    differences=[]
    if a!=b:
        matcher=SequenceMatcher(None,b,a,autojunk=False)
        for tag,i,j,k,l in matcher.get_opcodes():
            if tag!='equal':differences.append({'operation':tag,'cpu_span':[i,j],'candidate_span':[k,l],
                                               'cpu_text':b[i:j],'candidate_text':a[k:l]})
    return {'version':1,'status':'verified'if not reasons else 'unverified','scope':'literal_text_only; not graph/table semantics',
            'normalization':'NFC + whitespace collapse (word boundaries retained)','exact_nonwhitespace_agreement':a==b and bool(a),
            'cpu_characters':len(b),'candidate_characters':len(a),
            'similarity':SequenceMatcher(None,b,a,autojunk=False).ratio(),
            'reasons':reasons,'differences':differences[:64],'difference_count':len(differences),
            'cpu_lines':lines,'generation':generation}


def compare_native_literal(candidate, scan, native_lines):
    """Native is not a model generation: do not invent a VLM finish event.

    Only complete, one-to-one spatial line evidence can contradict a whole
    native block. Missing OCR lines are missing evidence, not bad native text.
    Strict case/punctuation/digit/confidence gates remain identical.
    """
    proof=compare_literal(candidate,scan,{})
    proof['reasons']=[r for r in proof['reasons']if r!='generation_finish_unknown']
    proof['scope']='native_vs_independent_ocr_literal_only; not graph/table semantics'
    proof['evidence_types']=['exact_pdf_native','independent_cpu_ocr']
    source=[line for line in native_lines if line['text'].strip()]
    detected=scan.get('lines',[])
    pairs=[];used=set()
    for line in source:
        a=line['bbox'];matches=[]
        for i,other in enumerate(detected):
            b=other['bbox']
            overlap=max(0,min(a[3],b[3])-max(a[1],b[1]))/max(1e-9,min(a[3]-a[1],b[3]-b[1]))
            tolerance=max(.006,(a[2]-a[0])*.15)
            if i not in used and overlap>=.5 and abs(a[0]-b[0])<=tolerance and abs(a[2]-b[2])<=tolerance:
                matches.append(i)
        if len(matches)==1:
            used.add(matches[0]);pairs.append(matches[0])
        else:pairs.append(None)
    complete=bool(source) and len(source)==len(detected) and all(i is not None for i in pairs)
    proof['source_line_count']=len(source)
    proof['source_line_to_cpu_line']=pairs
    proof['native_geometry_complete']=complete
    if not complete:proof['reasons'].append('native_independent_spatial_coverage_incomplete_or_ambiguous')
    proof['status']='verified'if not proof['reasons']else 'unverified'
    proof['native_disagreement_actionable']=bool(complete and scan.get('status')=='complete' and
        detected and all(math.isfinite(line['confidence'])and .94<=line['confidence']<=1 for line in detected) and
        not proof['exact_nonwhitespace_agreement'])
    return proof


def apply_native_verification(block, scan, native_lines, proof_ref):
    """Shared worker/replay policy. Never replace literal text or clear warnings."""
    proof=compare_native_literal(block['text'],scan,native_lines)
    issues=block['issues']
    if 'native_independent_verification_not_performed'in issues:
        issues.remove('native_independent_verification_not_performed')
    if proof['native_disagreement_actionable']:
        block['quality']='needs_review'
        issues.append('native_independent_ocr_disagreement; exact_native_retained')
    # Exact OCR agreement does not erase a known mapping/geometry anomaly.
    mapping_suspect=any(i.startswith(('native_font_mapping_unusable','native_mixed_prose_symbol_density_suspect',
                                    'native_mapping_issue_local','native_bbox_invalid'))for i in issues)
    if mapping_suspect:
        proof['status']='unverified'
        proof['reasons'].append('native_mapping_or_geometry_anomaly_retained')
    if proof['status']=='verified':
        issues.append('native_machine_verified_literal:'+proof_ref)
    else:
        issues.append('native_literal_retained_without_independent_verification:'+proof_ref)
    return proof


def source_crop_bounds(group,lines):
    xs=[line['bbox'][i]for line in group for i in (0,2)];ys=[line['bbox'][i]for line in group for i in (1,3)]
    pad=max(.003,min(.015,(max(ys)-min(ys))*.15))
    box=[max(0,min(xs)-pad),max(0,min(ys)-pad),min(1,max(xs)+pad),min(1,max(ys)+pad)]
    for other in lines:
        if any(other is member for member in group):continue
        b=other['bbox']
        if min(max(xs),b[2])>max(min(xs),b[0]):
            if b[3]<=min(ys):box[1]=max(box[1],(b[3]+min(ys))/2)
            if b[1]>=max(ys):box[3]=min(box[3],(b[1]+max(ys))/2)
        if min(max(ys),b[3])>max(min(ys),b[1]):
            if b[2]<=min(xs):box[0]=max(box[0],(b[2]+min(xs))/2)
            if b[0]>=max(xs):box[2]=min(box[2],(b[0]+max(xs))/2)
    return box


def complete_source_groups(groups,lines):
    """Include whole detected neighbour lines instead of clipped fragments.

    A skewed paragraph may need a larger crop than the initial grouping cap.
    Keep exact line indices; merge intersecting groups before selecting a budget.
    This changes pixels selected, never text or verification thresholds.
    """
    indices={id(line):i for i,line in enumerate(lines)}
    pending=[{indices[id(line)]for line in group}for group in groups];finished=[]
    while pending:
        members=pending.pop(0)
        while True:
            before=set(members);box=source_crop_bounds([lines[i]for i in sorted(members)],lines)
            for i,line in enumerate(lines):
                b=line['bbox']
                if min(box[2],b[2])>max(box[0],b[0]) and min(box[3],b[3])>max(box[1],b[1]):members.add(i)
            for collection in (pending,finished):
                for other in collection[:]:
                    if members&other:members.update(other);collection.remove(other)
            if members==before:break
        finished.append(members)
    return [[lines[i]for i in sorted(group)]for group in finished]


def recovery_tiles(scan,max_tiles=8,candidate_text=''):
    """Disjoint CPU-positioned text crops. No fabricated graph/worksheet order.

    Linear prose seeds <=1000-character groups, enlarged only to avoid cutting
    a detected neighbour line. Nonlinear
    layouts use individual source labels/lines; full semantics remains unresolved.
    Bounds use detector polygons, not guessed textual region names.
    """
    lines=scan.get('lines',[])
    if scan.get('status')!='complete'or not lines or max_tiles<=0:return []
    groups=[]
    ordered=[lines]if linear_layout(lines)else []
    if not ordered:
        # Real scanned chapters are two facing-page prose columns. Retrying
        # only the first eight individual detector lines would recover headers,
        # not the missing paragraphs. Cluster broad-line LEFT positions only;
        # narrow scattered diagram labels remain independent, never graph edges.
        anchors=[]
        for item in lines:
            box=item['bbox']
            if box[2]-box[0]<.20:continue
            cluster=next((a for a in anchors if abs(a['x']-box[0])<=.06),None)
            if cluster is None:anchors.append({'x':box[0],'count':1})
            else:cluster['count']+=1
        anchors=sorted(a['x']for a in anchors if a['count']>=4)
        if len(anchors)>=2 and max(anchors)-min(anchors)>=.15:
            columns=[[]for _ in anchors]
            for item in lines:
                index=min(range(len(anchors)),key=lambda i:abs(item['bbox'][0]-anchors[i]))
                columns[index].append(item)
            ordered=[sorted(column,key=lambda item:(item['bbox'][1],item['bbox'][0]))for column in columns if column]
    if ordered:
        for column in ordered:
            group=[];chars=0
            for item in column:
                box=item['bbox'];last=group[-1]['bbox']if group else box
                boundary=group and (chars+len(item['text'])>1000 or len(group)>=12 or
                    abs(box[0]-group[0]['bbox'][0])>.06 or box[1]-last[3]>.05 or
                    (vertical_overlap_ratio(group[-1],item)>.35 and not inline_prefix(group[-1],item)))
                if boundary:groups.append(group);group=[];chars=0
                group.append(item);chars+=len(item['text'])
            if group:groups.append(group)
    else:groups=[[item]for item in lines]
    # Prioritize source lines omitted/disagreed by the real primary response,
    # then dense paragraphs. Restore source detector order among chosen crops.
    groups=complete_source_groups(groups,lines)
    primary=normalized(candidate_text)
    def priority(group):
        missing=sum(len(normalized(item['text']))for item in group if normalized(item['text'])not in primary)
        return (-missing,-sum(len(item['text'])for item in group))
    chosen=sorted(groups,key=priority)[:max_tiles]
    chosen.sort(key=lambda group:min(i for i,item in enumerate(lines)if any(item is member for member in group)))
    tiles=[]
    for group in chosen:
        box=source_crop_bounds(group,lines)
        tiles.append({'bbox':box,'expected_cpu_text':'\n'.join(line['text']for line in group),
                      'cpu_line_indices':[i for i,line in enumerate(lines)if any(line is member for member in group)],
                      'minimum_original_cpu_confidence':min(line['confidence']for line in group),
                      'scope':('linear_text_crop'if linear_layout(group)else 'spatial_text_crop')+'; no_relationship_inferred'})
    return tiles


def pixel_crop(image,box):
    left=max(0,int(math.floor(box[0]*image.width)));top=max(0,int(math.floor(box[1]*image.height)))
    right=min(image.width,max(left+1,int(math.ceil(box[2]*image.width))));bottom=min(image.height,max(top+1,int(math.ceil(box[3]*image.height))))
    return image.crop((left,top,right,bottom))


def duplicate_candidates(blocks):
    """Exclude exact overlapping OCR duplicates, retain every original block/raw.

    Native is preferred. Otherwise only verified literal evidence may suppress an
    unverified full-page candidate; different text or separate occurrences remain.
    """
    def area(box):return max(0,box[2]-box[0])*max(0,box[3]-box[1])
    for candidate in blocks:
        if candidate['quality']=='excluded'or not candidate['text']or not any('fullpage_model_candidate'in i for i in candidate['issues']):continue
        for source in blocks:
            if source is candidate or source['quality']!='extracted':continue
            if not any(i.startswith(('source_transcription_native','ocr_machine_verified_literal:'))for i in source['issues']):continue
            a,b=source['bbox'],candidate['bbox'];inter=[max(a[0],b[0]),max(a[1],b[1]),min(a[2],b[2]),min(a[3],b[3])]
            haystack,needle=normalized(source['text']),normalized(candidate['text'])
            exact=haystack==needle
            # A verified whole linear source span also covers a unique exact
            # paragraph inside it. Do not use partial spatial-parent-only tiles
            # to suppress text at an unknown fine-grained position.
            contained=(not any(i.startswith('targeted_literal_recovery')for i in source['issues'])and
                haystack.count(needle)==1 and bool(re.search(r'(?<!\w)'+re.escape(needle)+r'(?!\w)',haystack))and area(inter)>=.95*area(b))
            if (exact or contained)and area(inter)>=.95*min(area(a),area(b))and min(area(a),area(b))>0:
                candidate['quality']='excluded';candidate['issues'].append('exact_overlapping_duplicate_of:'+source['id']);break
