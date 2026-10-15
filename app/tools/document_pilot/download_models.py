"""Resume authorized official downloads on Ubuntu after verified local transfer."""
from pathlib import Path
import concurrent.futures
import hashlib
import json
import threading
import time
import urllib.request

ROOT = Path('/home/adminz/llm/ocr-stage1-20261009/whole-document-pilot')
MANIFEST = json.loads((ROOT/'download-manifest.json').read_text())
RESULT = ROOT/'evidence/model-downloads.json'
LOCK = threading.Lock()
state = json.loads(RESULT.read_text()) if RESULT.exists() else {'network_bytes': 0, 'files': {}}


def save():
    tmp = RESULT.with_suffix('.tmp')
    tmp.write_text(json.dumps(state, indent=2)+'\n')
    tmp.replace(RESULT)


def download(item):
    dest = Path(item['path'])
    assert dest.is_relative_to(ROOT/'mineru-home/models')
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        assert dest.stat().st_size == item['size']
        assert hashlib.file_digest(dest.open('rb'), 'sha256').hexdigest() == item['sha256']
        with LOCK:
            state['files'][item['name']] = {'status': 'verified', 'bytes': item['size'], 'sha256': item['sha256'], 'source': 'verified_transfer'}
            save()
        return
    partial = dest.with_suffix(dest.suffix+'.part')
    offset = partial.stat().st_size if partial.exists() else 0
    began = time.monotonic()
    headers = {'User-Agent': 'AIcademiya-OCR-Evaluation'}
    if offset:
        headers['Range'] = f'bytes={offset}-'
    with urllib.request.urlopen(urllib.request.Request(item['url'], headers=headers), timeout=90) as response:
        if offset:
            assert response.status == 206 and response.headers.get('Content-Range','').startswith(f'bytes {offset}-'), 'Resume refused; retained partial'
        size = offset
        tick = time.monotonic()
        with partial.open('ab' if offset else 'wb') as f:
            while True:
                if (ROOT/'STOP').exists() or (ROOT.parent/'STOP').exists():
                    raise RuntimeError('Paused by STOP marker')
                data = response.read(4*1024*1024)
                if not data:
                    break
                with LOCK:
                    total = MANIFEST['earlier_download_bytes'] + state['network_bytes'] + len(data)
                    assert total + MANIFEST.get('reserved_layout_bytes', 0) <= MANIFEST['download_budget_bytes'], 'Authorized20GB model download budget exhausted'
                    state['network_bytes'] += len(data)
                f.write(data)
                size += len(data)
                assert size <= item['size']
                if time.monotonic()-tick > 20:
                    f.flush()
                    with LOCK:
                        state['files'][item['name']] = {'status':'downloading','bytes':size,'expected':item['size']}
                        save()
                    print(json.dumps({'file':item['name'],'bytes':size,'expected':item['size']}), flush=True)
                    tick = time.monotonic()
    assert size == item['size']
    h = hashlib.file_digest(partial.open('rb'), 'sha256').hexdigest()
    assert h == item['sha256'], 'SHA256 mismatch; partial retained'
    partial.replace(dest)
    with LOCK:
        state['files'][item['name']] = {'status':'verified','bytes':size,'sha256':h,'resumed_from':offset,'elapsed_seconds':time.monotonic()-began}
        save()
    print(json.dumps({'file':item['name'],'status':'verified'}), flush=True)


def main():
    errors=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(download,x):x for x in sorted(MANIFEST['items'], key=lambda x:(x.get('model')!='paddleocr-vl1.6-official-gguf', x['size']))}
        for f in concurrent.futures.as_completed(futures):
            try:
                f.result()
            except Exception as e:
                errors.append({'file':futures[f]['name'],'error_type':type(e).__name__,'error':str(e)[:250]})
                print(json.dumps(errors[-1]), flush=True)
    state['errors']=errors
    state['status']='failed' if errors else 'passed'
    state['total_public_download_bytes']=MANIFEST['earlier_download_bytes']+state['network_bytes']
    save()
    print(json.dumps({'status':state['status'],'files':len(state['files']),'total_public_download_bytes':state['total_public_download_bytes']}), flush=True)
    raise SystemExit(1 if errors else 0)


if __name__ == '__main__':
    main()
