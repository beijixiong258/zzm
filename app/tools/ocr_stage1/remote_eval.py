"""One real-model document evaluation batch, executed only on Ubuntu."""
from pathlib import Path
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
import subprocess
import threading
import time
import urllib.request

ROOT = Path('/home/adminz/llm/ocr-stage1-20261009')
os.environ['PADDLE_PDX_CACHE_HOME'] = str(ROOT/'paddle-cache')
os.environ['PADDLE_PDX_MODEL_SOURCE'] = 'bos'
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'
os.environ['OMP_NUM_THREADS'] = '4'
os.environ['OPENBLAS_NUM_THREADS'] = '4'

PROMPT = ('Transcribe the visible page faithfully in its original language. Preserve headings, '
          'paragraphs, reading order, numbers and table structure using Markdown. '
          'Do not answer exercises, paraphrase, explain, or fill in missing words. '
          'Mark genuinely unreadable text [unclear]. For diagrams transcribe visible labels; '
          'do not invent connections. Return only the transcription.')


def request_json(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.load(r)


class GPUSamples:
    def __init__(self, index):
        self.index=index
        self.rows=[]
        self.stop=threading.Event()
        self.thread=threading.Thread(target=self.run, daemon=True)
    def run(self):
        while not self.stop.is_set():
            p=subprocess.run(['nvidia-smi','-i',str(self.index),'--query-gpu=memory.used,utilization.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True)
            if p.returncode==0:
                vals=p.stdout.strip().split(',')
                self.rows.append({'elapsed':time.monotonic()-self.started,'used_mib':int(vals[0]),'utilization_percent':int(vals[1])})
            self.stop.wait(1)
    def __enter__(self):
        self.started=time.monotonic();self.thread.start();return self
    def __exit__(self,*args):
        self.stop.set();self.thread.join(timeout=5)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--model',choices=['minicpm','paddle'],required=True)
    parser.add_argument('--manifest',required=True)
    parser.add_argument('--ids',default='')
    parser.add_argument('--port',type=int,default=18891)
    parser.add_argument('--gpu-index',type=int,default=2)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    assert os.name=='posix' and Path.home()==Path('/home/adminz')
    if (ROOT/'STOP').exists():raise SystemExit('Paused')
    data=json.loads(Path(args.manifest).read_text())
    samples=data['samples']
    if args.ids:
        ids=set(args.ids.split(','));samples=[s for s in samples if s['id'] in ids]
        assert {s['id']for s in samples}==ids
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    rawdir=out.parent/(out.stem+'-raw');rawdir.mkdir(exist_ok=True)
    done={}
    if out.exists():
        for line in out.read_text().splitlines():
            row=json.loads(line);done[row['id']]=row
    pipeline=None
    init_start=time.monotonic()
    if args.model=='paddle':
        from paddleocr import PaddleOCRVL
        pipeline=PaddleOCRVL(pipeline_version='v1.6',device='cpu',cpu_threads=4,enable_mkldnn=False,
            use_doc_orientation_classify=False,use_doc_unwarping=False,
            use_layout_detection=True,use_chart_recognition=True,use_seal_recognition=True,
            use_ocr_for_image_block=True,use_queues=False,
            vl_rec_backend='llama-cpp-server',vl_rec_server_url=f'http://127.0.0.1:{args.port}/v1',
            vl_rec_api_model_name='ocr-eval',vl_rec_max_concurrency=1)
    initialization_seconds=time.monotonic()-init_start
    consecutive_failures=0
    for sample in samples:
        if (ROOT/'STOP').exists():raise SystemExit('Paused between samples')
        if done.get(sample['id'],{}).get('status')=='ok':continue
        image=Path(sample['image_path'])
        assert image.is_relative_to(ROOT/'data') and image.exists()
        image_sha=hashlib.file_digest(image.open('rb'),'sha256').hexdigest()
        began=time.monotonic()
        row={'id':sample['id'],'model':args.model,'image_path':str(image),'image_sha256':image_sha,
            'started_at':datetime.now(timezone.utc).isoformat(),'model_client_initialization_seconds':initialization_seconds,
            'host':'ubuntu-gpu','gpu_index':args.gpu_index,'status':'error'}
        with GPUSamples(args.gpu_index) as telemetry:
            try:
                if args.model=='minicpm':
                    body={'model':'ocr-eval','messages':[{'role':'user','content':[{'type':'text','text':PROMPT},
                        {'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(image.read_bytes()).decode()}}]}],
                        'temperature':0,'max_tokens':4096,'seed':17,'stream':False,
                        'chat_template_kwargs':{'enable_thinking':False}}
                    response=request_json(f'http://127.0.0.1:{args.port}/v1/chat/completions',body)
                    (rawdir/(sample['id']+'.json')).write_text(json.dumps(response,ensure_ascii=False,indent=2)+'\n')
                    choice=response['choices'][0]
                    row.update(text=choice['message'].get('content') or '',usage=response.get('usage'),finish_reason=choice.get('finish_reason'),prompt=PROMPT)
                    row['truncated']=choice.get('finish_reason')=='length'
                else:
                    results=pipeline.predict(str(image),temperature=0,max_new_tokens=4096,use_queues=False)
                    texts=[];plain=[];blocks=[]
                    for i,result in enumerate(results):
                        raw=result.json
                        (rawdir/(sample['id']+f'-{i}.json')).write_text(json.dumps(raw,ensure_ascii=False,indent=2)+'\n')
                        md=result.markdown
                        texts.append(md['markdown_texts'])
                        payload=raw.get('res',raw)
                        for block in payload.get('parsing_res_list',[]):
                            blocks.append(block);plain.append(block.get('block_content',''))
                    row.update(text='\n\n'.join(texts),plain_text='\n\n'.join(plain),blocks=blocks,truncated=None,
                        truncation_note='Pipeline does not expose per-region finish reasons; raw blocks retained.',
                        pipeline='PP-DocLayoutV3 CPU + PaddleOCR-VL1.6 official GGUF on isolated T10',
                        orientation=False,unwarping=False,max_new_tokens_per_region=4096)
                row['status']='ok' if row['text'].strip() else 'no_text'
            except Exception as exc:
                row.update(error_type=type(exc).__name__,error=str(exc)[:1200])
        row['elapsed_seconds']=time.monotonic()-began
        row['gpu_peak_used_mib']=max((x['used_mib']for x in telemetry.rows),default=None)
        (rawdir/(sample['id']+'-telemetry.json')).write_text(json.dumps(telemetry.rows,indent=2)+'\n')
        with out.open('a')as f:f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush()
        print(json.dumps({k:row[k]for k in ['id','model','status','elapsed_seconds','gpu_peak_used_mib']}),flush=True)
        if row['status']=='error':print(row['error'],flush=True)
        consecutive_failures = consecutive_failures + 1 if row['status'] in ('error','no_text') else 0
        if consecutive_failures >= 2:
            raise SystemExit('Two consecutive unusable responses; retained evidence, stopping this candidate for diagnosis')
    print(json.dumps({'batch_finished':True,'requested_ids':[x['id']for x in samples],'output':str(out)}),flush=True)


if __name__=='__main__':main()
