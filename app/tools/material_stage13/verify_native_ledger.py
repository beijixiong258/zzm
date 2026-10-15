"""Independent saved native-bundle/source readback; no rendering or model calls."""
import argparse
import json
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'document_stage12'))
from parser_helpers import sha256,validate_bundle,dump


def main():
    cli=argparse.ArgumentParser();cli.add_argument('--bundles',required=True);cli.add_argument('--sources',required=True)
    cli.add_argument('--ledger',required=True);cli.add_argument('--output',required=True);a=cli.parse_args()
    bundles,sources=Path(a.bundles),Path(a.sources);ledger=json.loads(Path(a.ledger).read_text())
    import pymupdf as fitz
    rows=[]
    for entry in ledger['sources']:
        root=bundles/entry['id'];m=json.loads((root/'manifest.json').read_text());source=sources/(entry['id']+'.'+entry['type'])
        assert sha256(source)==m['source_sha256']==entry['sha256']
        representation=source if entry['type']=='pdf' else root/m['preview_pdf']
        original_count=original_text_chars=source_images=0
        with fitz.open(representation) as doc:
            assert len(doc)==m['page_count']==len(m['pages'])
            for number,page in enumerate(doc,1):
                native=page.get_text('dict',sort=True)['blocks']
                raw=json.loads((root/f'raw/p{number:04}-native.json').read_text())['blocks']
                assert len(native)==len(raw)
                by_id={b['id']:b for b in m['pages'][number-1]['blocks']}
                for index,(source_block,raw_block) in enumerate(zip(native,raw)):
                    ident=f'p{number}-b{index}'
                    text='\n'.join(''.join(s['text'] for s in line['spans']) for line in source_block.get('lines',[]))
                    assert by_id[ident]['text']==raw_block['content']==text
                    assert raw_block['original_bbox_points']==list(source_block['bbox'])
                    source_images += source_block['type']==1
                    original_text_chars += len(text)
                original_count+=len(native)
        assert m['coverage']['native_text_chars']==original_text_chars
        assert m['coverage']['source_image_occurrences']==source_images
        row={'id':entry['id'],'page_count':m['page_count'],'native_blocks':original_count,
             'native_text_chars':original_text_chars,'source_image_occurrences':source_images,
             'every_native_id_text_and_original_bbox_retained':True,'original_source_sha256_preserved':True,
             'validation':validate_bundle(root,m)}
        if entry['id']=='src02':
            assert m['pages'][268]['number']==269 and m['pages'][316]['number']==317
            anomalies=[b for b in m['pages'][96]['blocks'] if any('native_bbox_invalid' in i for i in b['issues'])]
            assert anomalies and all(b['quality']=='needs_review' and b['bbox']==[0,0,1,1] for b in anomalies)
            row['late_pages_verified']=[269,317];row['page97_bbox_anomalies_retained']=len(anomalies)
        rows.append(row)
    assert len(rows)==23 and len({r['id'] for r in rows})==23
    result={'status':'passed','sources':len(rows),'represented_pages':sum(r['page_count'] for r in rows),
        'native_blocks':sum(r['native_blocks'] for r in rows),'native_text_chars':sum(r['native_text_chars'] for r in rows),
        'source_image_occurrences':sum(r['source_image_occurrences'] for r in rows),
        'model_calls':0,'semantic_accuracy_approved':False,'rows':rows}
    dump(Path(a.output),result)
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))


if __name__=='__main__':main()
