"""Stateless full-document parsing worker; never substitutes preview for full output."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,os,shutil,time
BASE=Path('/home/adminz/llm/ocr-stage1-20261009');ROOT=BASE/'whole-document-pilot'
os.environ.update(MINERU_HOME=str(ROOT/'mineru-home'),MINERU_CONFIG=str(ROOT/'mineru-home/config.yaml'),MINERU_MODEL_SOURCE='local',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4',TOKENIZERS_PARALLELISM='false',HF_HUB_OFFLINE='1')


def text_of(block):
    value=block.get('content','')
    if isinstance(value,str):return value
    if isinstance(value,list):
        return '\n'.join(x if isinstance(x,str)else str(x.get('content',''))for x in value)
    return str(value)if value else ''


def main():
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--name',required=True);p.add_argument('--tier',choices=['flash','basic','standard','advanced'],required=True);p.add_argument('--ocr-mode',choices=['txt','ocr','auto'],default='auto');p.add_argument('--expected-pages',type=int,required=True);p.add_argument('--page-range',default='');p.add_argument('--expected-page-ids',default='')
    a=p.parse_args();source=Path(a.input);assert source.is_relative_to(BASE/'data')
    assert not(BASE/'STOP').exists()
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'results'/a.name/stamp;out.mkdir(parents=True,exist_ok=False)
    before=hashlib.file_digest(source.open('rb'),'sha256').hexdigest()
    result={'name':a.name,'tier':a.tier,'ocr_mode':a.ocr_mode,'source':str(source),'source_sha256':before,'expected_pdf_pages':a.expected_pages,'started_at':stamp,'status':'running','quality_accepted':False}
    receipt=out/'run.json';receipt.write_text(json.dumps(result,indent=2)+'\n')
    began=time.monotonic()
    try:
        from mineru.parser import parse
        from mineru.parser.writer import FileBasedDataWriter
        parsed=parse(source,tier=a.tier,ocr_mode=a.ocr_mode,page_range=a.page_range,image_analysis=True)
        result['parse_seconds']=time.monotonic()-began
        parsed.save(FileBasedDataWriter(str(out/'document')))
        data=json.loads((out/'document/structured_content.json').read_text())
        pages=data.get('pages',[]);ids=[x['page_idx']for x in pages]
        middle=json.loads((out/'document/middle_json.json').read_text())
        native_pages={p['page_idx']:p for p in middle['pages']}
        coverage=[];index=[]
        for page in pages:
            texts=[]
            native_blocks=native_pages[page['page_idx']].get('blocks',[])
            assert len(native_blocks)==len(page.get('blocks',[]))
            for ordinal,b in enumerate(page.get('blocks',[])):
                native_index=native_blocks[ordinal]['index']
                assert native_blocks[ordinal]['type']==b['type']
                text=text_of(b);texts.append(text)
                index.append({'locator':f"{a.name}/pdf-page:{page['page_idx']+1}/block:{native_index}",'pdf_page_1based':page['page_idx']+1,'block_index':native_index,'type':b.get('type'),'text':text,'block':b})
            page_text='\n\n'.join(t for t in texts if t)
            coverage.append({'pdf_page_1based':page['page_idx']+1,'blocks':len(page.get('blocks',[])),'text_characters':len(page_text),'requires_image_or_blank_review':not page_text.strip()})
        expected_ids={int(x)-1 for x in a.expected_page_ids.split(',')}if a.expected_page_ids else set(range(a.expected_pages))
        assert len(expected_ids)==a.expected_pages
        exact=set(ids)==expected_ids and len(ids)==a.expected_pages
        result.update(processing_scope='selected_pages'if a.page_range else'full_document',requested_page_indices=sorted(expected_ids))
        result.update(actual_pages=len(ids),exact_page_set=exact,is_full_document=data.get('is_full_document'),image_assets=sum(p.is_file()for p in (out/'document/images').rglob('*'))if(out/'document/images').exists()else 0,status=('parsed_requested_coverage'if a.page_range else'parsed_full_coverage')if exact and(a.page_range or data.get('is_full_document')is True)else'coverage_failed',source_unchanged=hashlib.file_digest(source.open('rb'),'sha256').hexdigest()==before)
        (out/'coverage.json').write_text(json.dumps(coverage,indent=2)+'\n')
        (out/'block-index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n')
        shutil.copy2(source,out/('original'+source.suffix.lower()))
        assert result['source_unchanged']
        (ROOT/'results'/a.name/'latest.json').write_text(json.dumps({'directory':str(out),'status':result['status']},indent=2)+'\n')
    except BaseException as e:
        result.update(status='failed',error_type=type(e).__name__,error=str(e)[:2000]);raise
    finally:
        result['wall_seconds']=time.monotonic()-began;receipt.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False),flush=True)
    if result['status']not in('parsed_full_coverage','parsed_requested_coverage'):raise SystemExit(2)


if __name__=='__main__':main()
