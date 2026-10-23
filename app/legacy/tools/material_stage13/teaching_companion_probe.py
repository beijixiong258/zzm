"""One bounded real teaching generation alongside owned document runtime."""
import json
import time
import urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
start=time.monotonic()
with urllib.request.urlopen('http://127.0.0.1:18280/status',timeout=5) as r:before=json.load(r)
with urllib.request.urlopen('http://127.0.0.1:18894/health',timeout=5) as r:document=json.load(r)
assert document.get('status')=='ok' and all(w['healthy'] for w in before['workers'])
body={'model':'AIcademiya-64kx3-Qwen3.8-27B','messages':[{'role':'user','content':'Operational synthetic smoke test: reply only READY.'}],
      'temperature':0,'max_tokens':8,'stream':False}
request=urllib.request.Request('http://127.0.0.1:18280/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
with urllib.request.urlopen(request,timeout=60) as r:
    result={'http_status':r.status,'teaching_worker':r.headers.get('X-AIcademiya-Worker'),'response':json.load(r)}
result.update(seconds=time.monotonic()-start,label='Real short teaching generation while document server ready; not teaching quality/load or simultaneous GPU-kernel proof')
with urllib.request.urlopen('http://127.0.0.1:18280/status',timeout=5) as r:after=json.load(r)
result['workers_healthy_after']=all(w['healthy'] for w in after['workers'])
(ROOT/'teaching-companion.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
