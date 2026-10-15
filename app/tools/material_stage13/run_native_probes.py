"""Real Ubuntu source ledger + full native Office/PDF probes (no GPU calls)."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'document_stage12'))
from parser_helpers import dump,sha256,validate_bundle
from office_inventory import preflight,binary_doc_inventory,xml_part,rels,P,R


def main():
    cli=argparse.ArgumentParser()
    cli.add_argument('--sources',required=True)
    cli.add_argument('--expected-ledger',required=True)
    cli.add_argument('--output',required=True)
    cli.add_argument('--full-cases',default='src11,src15,src16,src17,src19,src02,src01,src23')
    a=cli.parse_args();source_root=Path(a.sources);out=Path(a.output);out.mkdir(parents=True,exist_ok=False)
    ledger=json.loads(Path(a.expected_ledger).read_text(encoding='utf-8'))
    assert ledger['count']==23 and len(ledger['sources'])==23
    rows=[]
    import pymupdf as fitz
    import zipfile
    for entry in ledger['sources']:
        src=source_root/(entry['id']+'.'+entry['type'])
        row={'id':entry['id'],'source_format':entry['type'],'bytes':src.stat().st_size,
             'sha256':sha256(src),'original_bytes_match_inventory':False}
        assert row['bytes']==entry['bytes'] and row['sha256']==entry['sha256']
        row['original_bytes_match_inventory']=True
        if entry['type']=='pdf':
            with fitz.open(src) as doc:
                pages=[]
                for n,page in enumerate(doc,1):
                    # Inventory text/image occurrence geometry without rendering.
                    txt=page.get_text('text')
                    imgs=page.get_image_info(hashes=True)
                    pages.append({'page':n,'native_chars':len(txt),'image_occurrences':len(imgs),
                        'max_raster_pixels':max((i['width']*i['height'] for i in imgs),default=0)})
                row.update(pages=len(doc),native_chars=sum(p['native_chars'] for p in pages),
                    image_occurrences=sum(p['image_occurrences'] for p in pages),
                    mixed_pages=[p['page'] for p in pages if p['native_chars']>=40 and p['image_occurrences']],
                    inventory_pages=pages)
        elif entry['type'] in ('pptx','docx'):
            media=preflight(src,entry['type']);row['media_parts']=len(media)
            if entry['type']=='pptx':
                with zipfile.ZipFile(src) as archive:
                    tree=xml_part(archive,'ppt/presentation.xml');mapping=rels(archive,'ppt/presentation.xml')
                    row['slides']=len(tree.findall('.//'+P+'sldId'))
        else:row['binary_doc_inventory']=binary_doc_inventory(src)
        row['processing_scope']='inventory_only; no semantic completeness claim'
        rows.append(row)
        dump(out/'source-ledger.json',{'count':len(rows),'sources':rows})
        print(json.dumps({k:v for k,v in row.items() if k not in ('inventory_pages','binary_doc_inventory','mixed_pages')}),flush=True)
    assert len(rows)==23 and len({r['id'] for r in rows})==23
    checks=[]
    env=dict(os.environ,CUDA_VISIBLE_DEVICES='',HF_HUB_OFFLINE='1',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4')
    for ident in a.full_cases.split(','):
        entry=next(e for e in ledger['sources'] if e['id']==ident)
        src=source_root/(ident+'.'+entry['type']);dest=out/'bundles'/ident
        cmd=[sys.executable,str(HERE/'parse_material.py'),'--input',str(src),'--output',str(dest),
             '--engine','native','--dpi','96','--deadline-seconds','240']
        began=time.monotonic()
        with (out/(ident+'.log')).open('w') as log:
            result=subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=250)
        row={'id':ident,'returncode':result.returncode,'seconds':time.monotonic()-began,'source_unchanged':sha256(src)==entry['sha256']}
        m=json.loads((dest/'manifest.json').read_text(encoding='utf-8'))
        receipt=json.loads((dest/'receipt.json').read_text(encoding='utf-8'))
        row.update(page_count=m['page_count'],complete=m['complete'],coverage=m.get('coverage'),status=receipt['status'])
        if result.returncode==0:
            row['validation']=validate_bundle(dest,m)
            assert m['source_sha256']==entry['sha256'] and row['source_unchanged']
            assert all(p['width']*p['height']<=4_000_000 for p in m['pages'])
            assert all(not p.is_symlink() for p in dest.rglob('*'))
            if entry['type']!='pdf':
                assert m['preview_pdf']=='preview.pdf' and m['source_format']==entry['type']
                with fitz.open(dest/'preview.pdf') as doc:assert len(doc)==m['page_count']
                native=json.loads((dest/'raw/office-inventory.json').read_text(encoding='utf-8'))
                assert m['coverage']['notes_integrated_in_reading'] is False
                assert m['coverage']['office_media_parts']==len(native['media'])
        else:row['error']=receipt.get('error')
        checks.append(row);dump(out/'native-probes.json',{'cases':checks,'real_source_count':len(checks),'model_calls':0})
        print(json.dumps({k:v for k,v in row.items() if k!='coverage'}),flush=True)
    assert all(r['returncode']==0 for r in checks),'Real source failures retained; inspect receipts'
    return 0


if __name__=='__main__':raise SystemExit(main())
