"""Independently validate the read-only research against the original HTML."""
from pathlib import Path
from bs4 import BeautifulSoup
from collections import Counter
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/stage5/reference-review'
def main():
 e=json.loads((OUT/'evidence.json').read_text(encoding='utf-8'));a=json.loads((OUT/'source-audit.json').read_text(encoding='utf-8'));b=json.loads((OUT/'browser-observations.json').read_text(encoding='utf-8'))
 soups={};unchanged=[]
 for row in a['pages']+a['auxiliary']:
  source=Path(row['source']);data=source.read_bytes();expected=row.get('source_sha256_before',row.get('sha256'))
  assert hashlib.sha256(data).hexdigest()==expected,str(source)
  unchanged.append(str(source))
  if 'page_id' in row:soups[row['page_id']]=BeautifulSoup(data.decode('utf-8'),'html.parser')
 claims=[]
 for claim in e['claims']:
  elements=soups[claim['page_id']].select(claim['selector']);assert len(elements)==1
  element=elements[0];text=element.get_text() if element.name=='textarea' else element.get_text(' ',strip=True)
  assert text[claim['span_start']:claim['span_end']]==claim['quote'],claim['id']
  claims.append(claim['id'])
 messages=[];counts={}
 for page in e['pages']:
  actual=soups[page['page_id']].select('[data-vaul-drawer] span.prose[id]')
  assert len(actual)==len(page['messages'])
  for node,record in zip(actual,page['messages']):
   text=node.get_text(' ',strip=True);digest=hashlib.sha256(text.encode()).hexdigest()
   assert node['id']==record['dom_id'] and digest==record['sha256']
   messages.append(digest)
  if actual:counts[page['page_id']]=len(actual)
 shots=[Path(row['path']) for row in b['screenshots']];assert all(p.is_file() for p in shots)
 assert len(soups)==7 and len(unchanged)==28 and len(messages)==108 and len(set(messages))==108
 assert len(claims)==28 and len(shots)==22 and not b['network_requests'] and b['closed']
 result={'status':'passed','primary_pages':len(soups),'original_html_unchanged':len(unchanged),'source_quotes_verified':len(claims),'messages':len(messages),'unique_messages':len(set(messages)),'per_record':counts,'screenshots_exist':len(shots),'browser_closed':b['closed'],'external_network_observed':len(b['network_requests']),'s6_docx_body_available':False,'note':'Independent parent readback; no online platform or model requests.'}
 (OUT/'parent-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
