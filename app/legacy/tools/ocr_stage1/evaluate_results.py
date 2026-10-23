"""Compute transparent text-reference diagnostics; not human OCR accuracy."""
from pathlib import Path
from collections import Counter
from html import unescape
from html.parser import HTMLParser
import argparse,json,re,statistics,unicodedata
from rapidfuzz.distance import Levenshtein

class VisibleHTML(HTMLParser):
    def __init__(self):super().__init__();self.parts=[]
    def handle_data(self,data):self.parts.append(data)
    def handle_starttag(self,tag,attrs):
        if tag in ('td','th','tr','p','br','li'):self.parts.append(' ')
    def handle_endtag(self,tag):
        if tag in ('td','th','tr','p','li'):self.parts.append(' ')

def normalize(text):
    text=re.sub(r'!\[[^\]]*\]\([^)]*\)',' ',text)
    text=re.sub(r'\[([^\]]+)\]\([^)]*\)',r'\1',text)
    if re.search(r'</?(?:table|tr|td|th|div|p|span|br)\b',text,re.I):
        p=VisibleHTML();p.feed(text);text=' '.join(p.parts)
    text=re.sub(r'^\s*\|?\s*:?-{3,}.*$', '',text, flags=re.M)
    text=re.sub(r'^\s{0,3}#{1,6}\s+','',text,flags=re.M)
    text=text.replace('**','').replace('__','').replace('`','').replace('|',' ')
    return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',unescape(text))).strip().casefold()

def tokens(text):return re.findall(r'[\u3400-\u9fff]|[a-z0-9]+(?:[\u2019\x27-][a-z0-9]+)*|[^\w\s]',text)

def load_rows(path):
    data={}
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            r=json.loads(line);data[r['id']]=r
    return data

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();root=a.root
    dataset=root/'data/dataset';samples=json.loads((dataset/'samples-server.json').read_text())['samples']
    paths={'rapidocr':root/'results/rapidocr/rapidocr.jsonl','minicpm':root/'results/minicpm/results.jsonl','paddle':root/'results/paddle/results.jsonl'}
    rows={k:load_rows(path)for k,path in paths.items()};cases=[]
    for s in samples:
        ref=(dataset/s['native_text_relpath']).read_text(encoding='utf-8') if s.get('native_text_relpath')else None
        normalized=normalize(ref) if ref else None;entry={'id':s['id'],'source_id':s['source_id'],'page_1based':s['page_1based'],'category':s['category'],'reference_kind':s['reference_kind'],'reference_chars':len(normalized or ''),'models':{}}
        for name,allrows in rows.items():
            r=allrows.get(s['id'])
            if not r:entry['models'][name]={'status':'missing'};continue
            text=r.get('plain_text')or r.get('text','');hyp=normalize(text)
            m={'status':r['status'],'elapsed_seconds':r.get('elapsed_seconds'),'gpu_peak_used_mib':r.get('gpu_peak_used_mib'),'output_chars':len(text),'truncated':r.get('truncated'),'finish_reason':r.get('finish_reason')}
            if normalized and r['status']=='ok':
                edit=Levenshtein.distance(normalized,hyp)
                rt=Counter(tokens(normalized));ht=Counter(tokens(hyp));overlap=sum((rt&ht).values())
                m.update(reference_edit_distance=edit,normalized_reference_char_error_rate=edit/len(normalized),reference_token_coverage=overlap/sum(rt.values()) if rt else None,output_token_precision_against_reference=overlap/sum(ht.values()) if ht else 0)
            entry['models'][name]=m
        cases.append(entry)
    summary={}
    for name,allrows in rows.items():
        ms=[c['models'][name]for c in cases];scored=[(c['reference_chars'],c['models'][name])for c in cases if 'reference_edit_distance'in c['models'][name]]
        times=[m['elapsed_seconds']for m in ms if m.get('elapsed_seconds')is not None]
        summary[name]={'expected':len(samples),'records':len(allrows),'missing_ids':[s['id']for s in samples if s['id']not in allrows],'status_counts':dict(Counter(m['status']for m in ms)),'reference_scored_cases':len(scored),'weighted_reference_CER':sum(m['reference_edit_distance']for n,m in scored)/sum(n for n,m in scored)if scored else None,'median_reference_token_coverage':statistics.median(m['reference_token_coverage']for n,m in scored)if scored else None,'sum_image_elapsed_seconds':sum(times),'median_image_elapsed_seconds':statistics.median(times)if times else None,'gpu_peak_used_mib':max((m['gpu_peak_used_mib']for m in ms if m.get('gpu_peak_used_mib')is not None),default=None),'known_truncated_ids':[s['id']for s in samples if allrows.get(s['id'],{}).get('truncated')is True]}
    report={'scope':'Ubuntu same24 image evaluation','quality_caveat':'These are native-text consistency diagnostics, NOT human-gold OCR accuracy. Native references may omit image text or have a different reading order. Do not sum/blend these with AI visual review. No reference means no score. Successful API text is not verified correctness.','normalization':'NFKC,casefold,whitespace collapse; strip Markdown formatting/image links and HTML table tags. Original outputs remain unchanged.','expected_samples':24,'reference_samples':sum(c['reference_chars']>0 for c in cases),'summary':summary,'cases':cases}
    target=root/'results/metrics.json';target.parent.mkdir(exist_ok=True);target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
