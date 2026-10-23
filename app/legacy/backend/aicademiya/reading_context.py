"""Bounded reads of already-authorized immutable document manifests.

This module never opens a file or grants material access. Callers must supply
course/edition-selected documents; rejected qualities do not enter evidence.
"""
from collections import Counter
import hashlib
import json
import math
import re
from pydantic import Field, StrictInt
from typing import Literal
from .models import Payload

ALLOWED_QUALITY = {"extracted", "approved"}
TEXT_VIEW_POLICY = 'whole-page-markdown-v1'

def whole_page_markdown(block):
    """Recognize the adapter's explicit full-page body, never similar prose.

    Extracted quality means technical completion, not independently proven
    semantic accuracy. Local OCR, image descriptions and generic Markdown do
    not declare an alternative full-page transcription.
    """
    tags={tag.strip()for issue in block.get('issues',[])for tag in issue.split(';')}
    return (block['type']=='text' and block.get('text_format')=='markdown'
            and {'source_transcription_ocr','machine_extracted_vlm',
                 'body_geometry_unlocalized','whole_source_locator'}<=tags)

def page_text_view(page):
    """Return a read-only projection plus retained alternatives, in source order.

    Any approved original text keeps the original page view. Otherwise prefer
    the first approved, then first extracted, explicitly whole-page body. This
    is a stable presentation policy, not an accuracy ranking. Image blocks are
    never suppressed and rejected qualities are never promoted.
    """
    blocks=page['blocks'];candidates=[b for b in blocks if whole_page_markdown(b)]
    ready=[b for b in candidates if b['quality']in ALLOWED_QUALITY and b['text'].strip()]
    if not ready:return blocks,[],None
    candidate_ids={b['id']for b in candidates}
    original=[b for b in blocks if b['type']!='image' and b['id']not in candidate_ids]
    if any(b['quality']=='approved' and b['text'].strip()for b in original):
        primary='source-blocks';omitted=candidate_ids
    else:
        chosen=next((b for b in ready if b['quality']=='approved'),ready[0])
        primary='whole-page-markdown:'+chosen['id']
        omitted={b['id']for b in original+candidates if b['id']!=chosen['id']}
    alternatives=[b for b in blocks if b['id']in omitted]
    return [b for b in blocks if b['id']not in omitted],alternatives,primary if alternatives else None

def text_view_identity(document, *, include_staff_supplements=False):
    # Legacy cursors remain valid only where the legacy sequence is unchanged.
    if not any(page_text_view(p)[1]for p in document['manifest']['pages']):return None
    sequence=[(p['number'],b['id'])for p,b in all_blocks(document,include_staff_supplements=include_staff_supplements)]
    encoded=json.dumps([TEXT_VIEW_POLICY,include_staff_supplements,sequence],ensure_ascii=False,separators=(',',':'))
    return TEXT_VIEW_POLICY+':'+hashlib.sha256(encoded.encode('utf-8')).hexdigest()

def cursor_matches(document,cursor,include_staff_supplements,view_id):
    return bool(cursor and cursor.get('revision_id')==document['revision_id']
                and cursor.get('staff_supplements',False)==include_staff_supplements
                and cursor.get('text_view_id')==view_id)

def text_view_metadata(page,block):
    _,alternatives,primary=page_text_view(page)
    if primary is None or block['type']=='image':return {}
    return {'text_view_policy':TEXT_VIEW_POLICY,'text_view_role':'alternative'if any(b['id']==block['id']for b in alternatives)else'primary',
            'page_text_view':'whole-page-markdown:'+block['id']if whole_page_markdown(block)else'source-blocks',
            'primary_page_text_view':primary}

class QuotationMismatch(ValueError):
    """A real supplied ref exists, but its proposed quotation is not literal."""

class ReadSelection(Payload):
    material_id: str = Field(min_length=1,max_length=100)
    pages: list[StrictInt] = Field(default_factory=list,max_length=4)
    block_ids: list[str] = Field(default_factory=list,max_length=12)
    supplement_ids: list[str] = Field(default_factory=list,max_length=8)
    query: str = Field(default="",max_length=600)
    mode: Literal["lookup","sequential"] = "lookup"
    restart: bool = False
    include_images: bool = False

class ReadPlan(Payload):
    requests: list[ReadSelection] = Field(default_factory=list,max_length=4)

def read_plan_schema(material_ids):
    """Make selector fields unavoidable in the local constrained decoder.

    Keep server-side defaults for older callers. The generation schema puts
    mode before selectors and requires explicit empty values for unused fields,
    so emitting mode/restart cannot skip optional earlier selectors and end JSON.
    """
    schema=ReadPlan.model_json_schema();selection=schema['$defs']['ReadSelection']
    order=('material_id','mode','restart','include_images','pages','block_ids','supplement_ids','query')
    selection['properties']={name:selection['properties'][name]for name in order}
    selection['required']=list(order)
    selection['properties']['material_id']['enum']=list(material_ids)
    schema['required']=['requests']
    return schema

def eligible_documents(documents, *, private=False):
    return [d for d in documents if d.get("kind")!="answer_key"
            and not(d.get("visibility")!="student"and d.get("kind")=="worksheet")
            and (private or d.get("visibility")=="student")]

def tokens(text):
    # Latin words and CJK bigrams allow deterministic whole-corpus lookup.
    parts=re.findall(r"[A-Za-z0-9]+|[\u3400-\u9fff]",text.casefold())
    cjk=re.findall(r"[\u3400-\u9fff]{2,}",text)
    return parts+[s[i:i+2]for s in cjk for i in range(len(s)-1)]

def catalogue(documents, *, private=False, char_budget=12000, progress=None, include_staff_supplements=False):
    eligible=eligible_documents(documents,private=private)
    output=[{"material_id":d["material_id"],"title":d["title"],"pdf_pages":len(d["manifest"]["pages"]),
             "source_format":d['manifest'].get('source_format')or'pdf',
             "page_kind":"slide"if d['manifest'].get('source_format')=='pptx'else"rendered_page"if d['manifest'].get('preview_pdf')else"pdf_page",
             "outline":[],"outline_complete":False,"full_document_search_available":True}for d in eligible]
    for d,item in zip(eligible,output):
        item['page_images_available']=any(p.get('image') for p in d['manifest']['pages'])
        item['visual_regions']=[]
        item['visual_regions_complete']=False
    from .document_supplements import eligible_supplements
    for d,item in zip(eligible,output):
        visible=eligible_supplements(d,include_staff_supplements)
        if visible:item.update(supplement_count=len(visible),supplements=[])
        saved=(progress or {}).get(d["material_id"])
        view_id=text_view_identity(d,include_staff_supplements=include_staff_supplements)
        if cursor_matches(d,saved,include_staff_supplements,view_id):
            item["sequential_reading"]={k:saved[k]for k in ("read_characters","available_characters","eligible_text_complete","unresolved_blocks",
                "text_view_id","text_view_policy","coverage_basis","alternative_text_blocks","alternative_text_characters",
                "alternative_unresolved_blocks","alternative_excluded_blocks") if k in saved}
    size=lambda:len(json.dumps(output,ensure_ascii=False))
    if size()>char_budget:raise ValueError("Selected document catalogue is too large; narrow the question's material selection")
    for d,item in zip(eligible,output):
        visual_complete=True
        for page in d['manifest']['pages']:
            for block in page['blocks']:
                if block['type'] not in ('image','table','equation') or block['quality']=='excluded':continue
                item['visual_regions'].append({'page':page['number'],'block_id':block['id'],
                    'type':block['type'],'description':(block.get('visual_description')or block['text'])[:160]})
                if len(item['visual_regions'])>24 or size()>char_budget:
                    item['visual_regions'].pop();visual_complete=False;break
            if not visual_complete:break
        item['visual_regions_complete']=visual_complete
        for note in eligible_supplements(d,include_staff_supplements):
            info={k:note[k]for k in ('id','kind','source_part','page_hint')}
            item['supplements'].append(info)
            if size()>char_budget:item['supplements'].pop();break
        outline_complete=True
        for p in d["manifest"]["pages"]:
            for b in page_text_view(p)[0]:
                if b["type"]!="heading"or b["quality"]not in ALLOWED_QUALITY:continue
                heading={"page":p["number"],"printed_label":p.get("printed_label"),"block_id":b["id"],"text":b["text"][:180]}
                item["outline"].append(heading)
                if size()>char_budget:
                    item["outline"].pop();outline_complete=False
        item['outline_complete']=outline_complete
    return output

def all_blocks(document, *, include_staff_supplements=False, include_alternatives=False):
    for page in document["manifest"]["pages"]:
        for block in page['blocks']if include_alternatives else page_text_view(page)[0]:
            yield page,block
    from .document_supplements import eligible_supplements,supplement_block
    for note in eligible_supplements(document,include_staff_supplements):yield supplement_block(note)

def ranked_blocks(document,query, *, include_staff_supplements=False):
    rows=[(p,b)for p,b in all_blocks(document,include_staff_supplements=include_staff_supplements)if b["quality"]in ALLOWED_QUALITY and b["text"].strip()]
    if not query.strip():return rows
    wanted=set(tokens(query));counts=[Counter(tokens(b["text"]))for _,b in rows]
    frequencies=Counter(t for c in counts for t in wanted if t in c)
    scored=[]
    for ordinal,((p,b),counts)in enumerate(zip(rows,counts)):
        score=sum((1+math.log(1+counts[t]))*math.log(1+len(rows)/(1+frequencies[t]))for t in wanted if counts[t])
        if query.casefold()in b["text"].casefold():score+=5
        if score:scored.append((score,ordinal,p,b))
    scored.sort(key=lambda x:(-x[0],x[1]))
    return [(p,b)for _,_,p,b in scored]

def excerpt_window(text,query,maximum):
    if len(text)<=maximum:return text,0,len(text)
    words=[t for t in tokens(query)if len(t)>2]
    positions=[text.casefold().find(t)for t in words];positions=[p for p in positions if p>=0]
    start=max(0,min(positions)-maximum//3)if positions else 0
    return text[start:start+maximum],start,min(len(text),start+maximum)

def transcription_metadata(block):
    result={}
    if block.get('text_format')=='markdown':result['text_format']='markdown'
    if any('machine_extracted_vlm' in i for i in block.get('issues',[])):
        result['transcription_source']='vision_model; not independently verified'
    notes=[i.split(':',1)[1]for i in block.get('issues',[])if i.startswith('model_uncertainty:')]
    if notes:result['source_notes']=notes[:2]
    return result

def sequential_read(document, cursor, *, char_budget, max_blocks, ref_start=0, byte_budget=None, include_staff_supplements=False):
    """Continue exact source spans; a 6k window never hides the rest of a block.

    The cursor is server-owned lesson state, not a provider-supplied offset. It
    becomes durable only with the successfully validated assistant turn.
    """
    rows=list(all_blocks(document,include_staff_supplements=include_staff_supplements))
    previous=cursor or {}
    view_id=text_view_identity(document,include_staff_supplements=include_staff_supplements)
    cursor=previous if cursor_matches(document,previous,include_staff_supplements,view_id)else{}
    index,offset=cursor.get('block_index',0),cursor.get('char_offset',0)
    if type(index)is not int or type(offset)is not int or not 0<=index<=len(rows)or offset<0:
        raise ValueError('Invalid server reading cursor')
    if index<len(rows)and offset>len(rows[index][1]['text']):raise ValueError('Reading cursor exceeds source block')
    if index==len(rows)and offset:raise ValueError('Reading cursor exceeds document')
    blocks=[];remaining=char_budget;bytes_remaining=byte_budget
    while index<len(rows):
        page,b=rows[index]
        if b['quality']not in ALLOWED_QUALITY or not b['text'].strip():
            index+=1;offset=0;continue
        if remaining<=0 or len(blocks)>=max_blocks:break
        end=min(len(b['text']),offset+min(6000,remaining))
        text=b['text'][offset:end]
        if bytes_remaining is not None:
            text=text.encode('utf-8')[:bytes_remaining].decode('utf-8',errors='ignore')
            end=offset+len(text)
            if not text:break
        context={'ref':f'D{ref_start+len(blocks)+1}','material_id':document['material_id'],
                 'revision_id':document['revision_id'],'source_label':document.get('source_label')or document['title'],
                 'page':page['number'],'printed_label':page.get('printed_label'),'block_id':b['id'],
                 'quality':b['quality'],'text':text,'char_start':offset,'char_end':end,
                 'block_truncated':offset>0 or end<len(b['text']),'visibility':document.get('visibility')}
        context.update(transcription_metadata(b))
        if not page.get('supplement_id'):context.update(text_view_metadata(page,b))
        if page.get('supplement_id'):
            context.update({k:page[k]for k in ('supplement_id','source_part','source_kind')})
            if b.get('supplement_visibility')!='student':context['visibility']='teacher'
        if document['manifest'].get('preview_pdf'):context['_rendered_pdf']=True
        blocks.append(context);remaining-=len(text);offset=end
        if bytes_remaining is not None:bytes_remaining-=len(text.encode('utf-8'))
        if offset==len(b['text']):index+=1;offset=0
    eligible=lambda b:b['quality']in ALLOWED_QUALITY and b['text'].strip()
    available=sum(len(b['text'])for _,b in rows if eligible(b))
    read=sum(len(b['text'])for _,b in rows[:index]if eligible(b))+offset
    unresolved=sum(b['quality']=='needs_review'for _,b in rows)
    excluded=sum(b['quality']=='excluded'for _,b in rows)
    progress={'revision_id':document['revision_id'],'block_index':index,'char_offset':offset,
              'read_characters':read,'available_characters':available,'eligible_text_complete':index==len(rows),
              'unresolved_blocks':unresolved,'excluded_blocks':excluded,'visibility':document.get('visibility'),'staff_supplements':include_staff_supplements,
              'all_stored_regions_read':index==len(rows)and unresolved==0 and excluded==0}
    if view_id is not None:
        alternatives=[b for p in document['manifest']['pages']for b in page_text_view(p)[1]]
        progress.update(text_view_id=view_id,text_view_policy=TEXT_VIEW_POLICY,
            coverage_basis='selected text-view codepoints; not unique source characters or semantic verification',
            alternative_text_blocks=len(alternatives),alternative_text_characters=sum(len(b['text'])for b in alternatives),
            alternative_unresolved_blocks=sum(b['quality']=='needs_review'for b in alternatives),
            alternative_excluded_blocks=sum(b['quality']=='excluded'for b in alternatives),
            selected_view_regions_read=progress['all_stored_regions_read'],all_stored_regions_read=False)
    # Source-image traversal is independent of this text projection. Preserve
    # its position across text-only turns and text-view/supplement resets.
    if previous.get('revision_id')==document['revision_id']:
        progress.update({k:previous[k]for k in ('visual_page_index','visual_read_pages','available_image_pages','visual_read_complete')if k in previous})
    coverage={'material_id':document['material_id'],'source_label':document.get('source_label')or document['title'],**{k:v for k,v in progress.items()if k not in ('block_index','char_offset','visibility','staff_supplements')}}
    coverage['next_page']=rows[index][0]['number']if index<len(rows)else None
    return {'blocks':blocks,'coverage':coverage,'progress':progress,'included_characters':char_budget-remaining}


def execute_plan(documents,plan, *, private=False,char_budget=24000,max_blocks=24,progress=None,byte_budget=None,include_staff_supplements=False):
    """Resolve only planned reads, retaining exact evidence for citation checks."""
    if not isinstance(plan,ReadPlan):plan=ReadPlan.model_validate(plan)
    allowed={d["material_id"]:d for d in eligible_documents(documents,private=private)}
    contexts=[];notices=[];seen=set();remaining=char_budget;updates={};coverage=[];bytes_remaining=byte_budget
    for request in plan.requests:
        d=allowed.get(request.material_id)
        if d is None:raise ValueError("Read plan selected an unavailable material")
        if request.mode=='sequential':
            if request.pages or request.block_ids or request.supplement_ids or request.query:
                raise ValueError('Sequential reading cannot skip ahead with page/block/query selectors')
            previous=None if request.restart else updates.get(d['material_id'],(progress or {}).get(d['material_id']))
            chunk=sequential_read(d,previous,char_budget=remaining,max_blocks=max_blocks-len(contexts),ref_start=len(contexts),byte_budget=bytes_remaining,include_staff_supplements=include_staff_supplements)
            contexts.extend(chunk['blocks']);remaining-=chunk['included_characters']
            if bytes_remaining is not None:bytes_remaining-=sum(len(b['text'].encode('utf-8'))for b in chunk['blocks'])
            updates[d['material_id']]=chunk['progress'];coverage.append(chunk['coverage'])
            if not chunk['coverage']['eligible_text_complete']:
                notices.append({'material_id':d['material_id'],'reason':'Sequential source reading continues from the returned position; the whole document has not yet entered model requests.'})
            if chunk['coverage']['unresolved_blocks']:
                notices.append({'material_id':d['material_id'],'reason':'Some source regions remain unresolved; finishing the available text does not certify complete visual recognition.'})
            continue
        page_map={p["number"]:p for p in d["manifest"]["pages"]}
        block_map={b["id"]:(p,b)for p,b in all_blocks(d,include_staff_supplements=include_staff_supplements,include_alternatives=True)}
        if any(p not in page_map for p in request.pages):raise ValueError("Read plan selected a non-existent PDF page")
        if any(b not in block_map for b in request.block_ids+request.supplement_ids):raise ValueError("Read plan selected a non-existent block")
        selected=[]
        for bid in request.block_ids+request.supplement_ids:selected.append(block_map[bid])
        for number in request.pages:
            selected.extend((page_map[number],b)for b in page_text_view(page_map[number])[0])
        if request.query:selected.extend(ranked_blocks(d,request.query,include_staff_supplements=include_staff_supplements)[:12])
        for page,b in selected:
            key=(d["material_id"],d["revision_id"],b["id"])
            if key in seen:continue
            seen.add(key)
            if b["quality"]not in ALLOWED_QUALITY:
                notices.append({"material_id":d["material_id"],"page":page["number"],"block_id":b["id"],"reason":"Source region is not verified for teaching evidence; inspect the original or request staff source review."})
                continue
            if not b["text"].strip():continue
            if remaining<=0 or len(contexts)>=max_blocks:
                notices.append({"material_id":d["material_id"],"reason":"The bounded read budget was reached; this is not a claim that the entire document entered the model context."});break
            text,start,end=excerpt_window(b["text"],request.query,min(6000,remaining))
            if bytes_remaining is not None:
                text=text.encode('utf-8')[:bytes_remaining].decode('utf-8',errors='ignore');end=start+len(text)
                if not text:
                    notices.append({'material_id':d['material_id'],'reason':'The source text UTF-8 byte budget was reached; use sequential reading to continue.'});break
            context={"ref":f"D{len(contexts)+1}","material_id":d["material_id"],"revision_id":d["revision_id"],"source_label":d.get("source_label")or d["title"],"page":page["number"],"printed_label":page.get("printed_label"),"block_id":b["id"],"quality":b["quality"],"text":text,"char_start":start,"char_end":end,"block_truncated":start>0 or end<len(b["text"]),"visibility":d.get("visibility")}
            context.update(transcription_metadata(b))
            if not page.get('supplement_id'):context.update(text_view_metadata(page,b))
            if page.get('supplement_id'):
                context.update({k:page[k]for k in ('supplement_id','source_part','source_kind')})
                if b.get('supplement_visibility')!='student':context['visibility']='teacher'
            contexts.append(context);remaining-=len(text)
            if bytes_remaining is not None:bytes_remaining-=len(text.encode('utf-8'))
            if d['manifest'].get('preview_pdf'):
                context['_rendered_pdf'] = True
    result={"blocks":contexts,"notices":notices,"included_characters":char_budget-remaining}
    if updates:result.update(coverage=coverage,_progress_updates=updates)
    if any(r.include_images for r in plan.requests):
        from .visual_context import select_images
        select_images(allowed,plan,result,progress=progress)
    return result

def normalized_quote(text):return re.sub(r"\s+"," ",text).strip()

def citation_quote_match(block,quote):
    """Exact text, or supported <br> whitespace inside ONE Markdown HTML cell.

    Keep model quote/source bytes unchanged. A rendered match records the exact
    raw source span; no case, numbers, punctuation, entities or cell joins change.
    Other markup and code remain on the original literal path.
    """
    wanted=normalized_quote(quote);text=block['text']
    if wanted in normalized_quote(text):return {}
    if block.get('text_format')!='markdown' or '`'in text or '~~~'in text or not re.search(r'<table(?:\s|>)',text,re.I):return None
    br=re.compile(r'<br\s*/?\s*>',re.I)
    cells=re.compile(r'''<(?P<tag>td|th)(?:\s+(?:rowspan|colspan)\s*=\s*(?:"[1-9][0-9]?"|'[1-9][0-9]?'|[1-9][0-9]?))*\s*>(?P<body>.*?)</(?P=tag)\s*>''',re.I|re.S)
    for cell in cells.finditer(text):
        body=cell.group('body')
        if not br.search(body) or '<'in br.sub('',body):continue
        chars=[];spans=[]
        for token in re.finditer(br.pattern+r'|\s+|.',body,re.I|re.S):
            value=token.group();space=bool(br.fullmatch(value))or value.isspace()
            if space:
                if not chars:continue
                if chars[-1]==' ':spans[-1]=(spans[-1][0],token.end());continue
                value=' '
            chars.append(value);spans.append((token.start(),token.end()))
        if chars and chars[-1]==' ':chars.pop();spans.pop()
        index=''.join(chars).find(wanted)
        if index>=0:
            origin=block.get('char_start',0)+cell.start('body')
            return {'quote_basis':'rendered_html_cell_line_breaks',
                    'quote_char_start':origin+spans[index][0],
                    'quote_char_end':origin+spans[index+len(wanted)-1][1]}
    return None

def validate_citations(citations,evidence, *, allow_private=False):
    """Validate against actual read excerpts, not any text anywhere in corpus."""
    if not isinstance(citations,list)or len(citations)>12:raise ValueError("Invalid document citations")
    refs={b["ref"]:b for b in evidence["blocks"]};validated=[];seen=set();selected=[]
    for c in citations:
        if not isinstance(c,dict)or set(c)!={"ref","quote"}or not isinstance(c.get("ref"),str):raise ValueError("Invalid document citation fields")
        b=refs.get(c["ref"]);quote=c["quote"]
        if b is None or not isinstance(quote,str)or not quote.strip()or len(quote)>2000:
            raise ValueError("Document citation does not identify supplied evidence")
        if b["visibility"]!="student"and not allow_private:raise ValueError("Private document citations cannot be exposed")
        selected.append((b,quote))
    # Check every identity/privacy gate before identifying a repairable mismatch.
    for b,quote in selected:
        proof=citation_quote_match(b,quote)
        if proof is None:raise QuotationMismatch("Document quotation does not match the supplied block")
        key=(b["ref"],quote)
        if key in seen:continue
        seen.add(key);validated.append({k:b[k]for k in("material_id","revision_id","source_label","page","printed_label","block_id")}|{"quote":quote}|proof)
        if b.get('supplement_id'):
            validated[-1].update({k:b[k]for k in ('supplement_id','source_part','source_kind')})
        if b.get('_rendered_pdf'):
            validated[-1]['_rendered_pdf'] = True
    return validated
