"""Download the explicit official artifact manifest, resume and verify SHA256."""
from pathlib import Path
from datetime import datetime, timezone
import concurrent.futures
import hashlib
import json
import threading
import time
import urllib.request
import zipfile
from budget import check, OUT, STOP

LOCK = threading.Lock()
STATE = OUT / 'download-progress.json'
MANIFEST = json.loads((OUT / 'download-manifest.json').read_text(encoding='utf-8'))
assert sum(x['size'] for x in MANIFEST['items']) <= MANIFEST['model_download_budget_bytes']
state = json.loads(STATE.read_text()) if STATE.exists() else {'network_bytes': 0, 'items': {}}


def save():
    state['updated_at'] = datetime.now(timezone.utc).isoformat()
    tmp = STATE.with_suffix('.tmp')
    tmp.write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')
    tmp.replace(STATE)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def download(item):
    dest = Path(item['path'])
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        assert dest.stat().st_size == item['size'] and digest(dest) == item['sha256'], item['name']
        with LOCK:
            state['items'][item['name']] = {'status': 'verified', 'bytes': item['size'], 'sha256': item['sha256']}
            save()
        return
    part = dest.with_suffix(dest.suffix + '.part')
    start = part.stat().st_size if part.exists() else 0
    with LOCK:
        check()
        state['items'][item['name']] = {'status': 'downloading', 'bytes': start}
        save()
    req = urllib.request.Request(item['url'], headers={'User-Agent': 'AIcademiya-OCR-Evaluation', **({'Range': f'bytes={start}-'} if start else {})})
    began = time.monotonic()
    tick = began
    with urllib.request.urlopen(req, timeout=90) as response:
        if start:
            assert response.status == 206 and response.headers.get('Content-Range', '').startswith(f'bytes {start}-'), 'Server did not honor resume; partial preserved'
        with part.open('ab' if start else 'wb') as f:
            size = start
            while True:
                if STOP.exists():
                    raise RuntimeError('Paused by quota STOP marker')
                data = response.read(4 * 1024 * 1024)
                if not data:
                    break
                with LOCK:
                    if state['network_bytes'] + len(data) > MANIFEST['model_download_budget_bytes']:
                        raise RuntimeError('Download traffic budget reached')
                    state['network_bytes'] += len(data)
                f.write(data)
                size += len(data)
                assert size <= item['size'], 'Response larger than declared artifact'
                if time.monotonic() - tick > 15:
                    f.flush()
                    with LOCK:
                        state['items'][item['name']] = {'status': 'downloading', 'bytes': size, 'expected': item['size']}
                        save()
                        check()
                    print(json.dumps({'name': item['name'], 'bytes': size, 'expected': item['size']}), flush=True)
                    tick = time.monotonic()
    assert size == item['size'], 'Incomplete artifact'
    actual = digest(part)
    assert actual == item['sha256'], 'SHA256 mismatch; partial preserved'
    part.replace(dest)
    with LOCK:
        state['items'][item['name']] = {'status': 'verified', 'bytes': size, 'sha256': actual, 'elapsed_seconds': time.monotonic() - began}
        save()
    print(json.dumps({'name': item['name'], 'status': 'verified', 'sha256': actual}), flush=True)


def main():
    check(force=True)
    items = sorted(MANIFEST['items'], key=lambda i: (i['kind'] != 'runtime', i['size']))
    errors = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        jobs = {pool.submit(download, item): item for item in items}
        for future, item in [(f, jobs[f]) for f in concurrent.futures.as_completed(jobs)]:
            try:
                future.result()
            except BaseException as exc:
                errors.append({'name': item['name'], 'error_type': type(exc).__name__, 'error': str(exc)[:200]})
                print(json.dumps(errors[-1]), flush=True)
    if errors:
        with LOCK:
            state['errors'] = errors
            save()
        raise SystemExit(1)
    runtime = OUT / 'runtime/llama-b11524-cuda12.4'
    runtime.mkdir(parents=True, exist_ok=True)
    for item in items:
        if item['kind'] == 'runtime':
            with zipfile.ZipFile(item['path']) as z:
                for member in z.infolist():
                    if member.is_dir():
                        continue
                    target = runtime / Path(member.filename).name
                    content = z.read(member)
                    if target.exists() and target.read_bytes() != content:
                        raise RuntimeError('Conflicting runtime member: ' + target.name)
                    target.write_bytes(content)
    print(json.dumps({'status': 'passed', 'runtime': str(runtime), 'artifacts': len(items), 'network_bytes': state['network_bytes']}), flush=True)


if __name__ == '__main__':
    main()
