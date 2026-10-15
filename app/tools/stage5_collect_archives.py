"""Read provided saved HTML, extract visible text/form fields, retain an inventory.
Never modify originals or run their scripts. Derivatives stay under stage5.
"""
from pathlib import Path
import json,re
from collections import Counter
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path('D:/中转站/Z')
OUT=ROOT/'artifacts/stage5/reference-review'
GROUPS=['Chatbot prompts','Records for Session 4','Records for Session 5']
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 inventory=[];primary=[]
 for group_index,group in enumerate(GROUPS,1):
  folder=SOURCE/group;assert folder.is_dir(),str(folder)
  files=sorted([p for p in folder.rglob('*') if p.is_file() and p.suffix.lower() in ('.html','.htm','.mhtml','.mht')],key=lambda p:str(p).casefold())
  for path in files:
   main_page=path.parent==folder
   row={'group':group,'source':str(path),'name':path.name,'primary':main_page,'bytes':path.stat().st_size}
   if path.suffix.lower() not in ('.html','.htm'):
    row['needs_mime_extraction']=True;inventory.append(row);continue
   soup=BeautifulSoup(path.read_text(encoding='utf-8',errors='replace'),'html.parser')
   row['title']=soup.title.get_text(' ',strip=True) if soup.title else ''
   for node in soup(['script','style','noscript','template','iframe']):node.decompose()
   fields=[]
   for node in soup.find_all(['textarea','input','select']):
    if node.get('type','').lower() in ('password','hidden'):continue
    fields.append({'tag':node.name,'id':node.get('id'),'name':node.get('name'),'type':node.get('type'),'placeholder':node.get('placeholder'),'aria_label':node.get('aria-label'),'value':node.get('value') if node.name=='input' else node.get_text('\n',strip=True)})
   content='\n'.join(x.strip() for x in soup.get_text('\n').splitlines() if x.strip())
   row.update(text_chars=len(content),form_field_count=len(fields))
   if main_page:
    alias=f'page-{len(primary)+1:02d}'
    record={**row,'form_fields':fields,'buttons':[n.get_text(' ',strip=True) or n.get('aria-label','') for n in soup.find_all(['button'])],
      'images':[{'src':n.get('src'),'alt':n.get('alt'),'width':n.get('width'),'height':n.get('height')} for n in soup.find_all('img')],
      'visible_text':content,'source_is_untrusted_data':True}
    (OUT/(alias+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/(alias+'.txt')).write_text(content,encoding='utf-8')
    row['extracted_json']=str(OUT/(alias+'.json'));row['extracted_text']=str(OUT/(alias+'.txt'));primary.append(row)
   inventory.append(row)
  # Persist each folder batch before processing the next.
  (OUT/'inventory.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2),encoding='utf-8')
 summary={'folders':GROUPS,'html_total':len(inventory),'primary_pages':len(primary),'auxiliary_pages':sum(not r['primary'] for r in inventory),'primary_by_folder':dict(Counter(r['group'] for r in primary)),'primary':primary,'originals_modified':False}
 (OUT/'manifest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'folders':len(GROUPS),'html_total':len(inventory),'primary_pages':len(primary),'auxiliary_pages':summary['auxiliary_pages'],'primary_by_folder':summary['primary_by_folder'],'pages':[{'name':r['name'],'text_chars':r['text_chars'],'fields':r['form_field_count'],'extracted':r['extracted_json']} for r in primary]},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
