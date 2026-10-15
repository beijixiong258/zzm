"""Real single-image protocol smoke; always restore the authorized teaching service."""
from pathlib import Path
from datetime import datetime, timezone
import base64
import hashlib
import json
import urllib.request
import time
import remote_control as control

ROOT=control.ROOT
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
report={'status':'running','kind':'synthetic_protocol_smoke_not_course_accuracy','model':'paddleocr-vl1.6','created_at':stamp}
paused=False
try:
    budget=json.loads((ROOT/'budget-status.json').read_text());assert not budget['paused'] and budget['remaining_min_percent']>=1 and time.time()-budget['checked_epoch']<120
    manifest=json.loads((ROOT/'download-manifest.json').read_text())
    for item in manifest['items']:
        if item.get('model')=='paddleocr-vl1.6-official-gguf' and item['kind']=='model':
            assert hashlib.file_digest(Path(item['path']).open('rb'),'sha256').hexdigest()==item['sha256']
    report['pause']=control.pause();paused=True
    report['server']=control.start('paddle')
    image=ROOT/'data/smoke.png'
    body={'model':'ocr-eval','messages':[{'role':'user','content':[{'type':'text','text':'OCR:'},{'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(image.read_bytes()).decode()}}]}],'temperature':0,'max_tokens':256,'stream':False}
    began=time.monotonic()
    req=urllib.request.Request('http://127.0.0.1:18891/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=180)as r:response=json.load(r)
    report['elapsed_seconds']=time.monotonic()-began;report['response']=response
    text=response['choices'][0]['message'].get('content','')
    assert 'ALPHA' in text and '17' in text, 'Synthetic visible-text sentinel not recognized'
    report['status']='passed'
except BaseException as exc:
    report.update(status='failed',error_type=type(exc).__name__,error=str(exc)[:1000])
finally:
    if paused:
        try:report['restoration']=control.resume()
        except BaseException as exc:report.update(status='restore_failed',restore_error=str(exc))
    target=ROOT/'evidence'/('paddle-smoke-'+stamp+'.json');target.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'report':str(target),'restoration':report.get('restoration'),'error':report.get('error')}),flush=True)
raise SystemExit(0 if report['status']=='passed'else 1)
