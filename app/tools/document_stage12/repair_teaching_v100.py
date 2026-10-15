"""Authorized, bounded service restart; no driver/config/cache changes."""
import concurrent.futures
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.request

BASE = Path('/home/adminz/llm/aicademiya-router')
EXPECTED = 'dd79556dedcd75a56d142dba236410a5cefa3b19001b653c6851c68ed9d3e1f1'
MODEL = 'AIcademiya-64kx3-Qwen3.8-27B'
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=False, mode=0o700)
report = {'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'status': 'running'}


def run(*args, timeout=45):
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError(f'{args[0]} exited {p.returncode}: {p.stderr[:700]}')
    return p.stdout


def get(url):
    with urllib.request.urlopen(url, timeout=8) as r:
        return json.load(r)


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def proc_identity(pid):
    p = Path('/proc') / str(pid)
    return {'pid': pid, 'start_ticks': p.joinpath('stat').read_text().split()[21],
            'argv_sha256': sha(p / 'cmdline')}


def cache_inventory(path):
    # Snapshot payloads only; SQLite's transient SHM/WAL are not model snapshots.
    rows = []
    for p in path.rglob('*'):
        if p.is_file() and not any(x in p.name for x in ('.sqlite', '.db')):
            s = p.stat()
            rows.append((str(p.relative_to(path)), s.st_ino, s.st_size, s.st_mtime_ns))
    rows.sort()
    return {'files': len(rows), 'bytes': sum(r[2] for r in rows),
            'metadata_sha256': hashlib.sha256(json.dumps(rows).encode()).hexdigest()}


def gpu_apps():
    text = run('nvidia-smi', '--query-compute-apps=gpu_uuid,pid,used_gpu_memory', '--format=csv,noheader,nounits')
    rows = []
    for line in text.splitlines():
        uuid, pid, mem = (s.strip() for s in line.split(','))
        rows.append({'uuid': uuid, 'pid': int(pid), 'memory_mib': int(mem)})
    return rows


def slots(port):
    return [{'id': s['id'], 'is_processing': s['is_processing']}
            for s in get(f'http://127.0.0.1:{port}/slots')]


def save():
    (OUT / 'result.json').write_text(json.dumps(report, indent=2) + '\n')


interrupted = False
try:
    config = json.loads((BASE / 'config.json').read_text())
    assert sha(BASE / 'config.json') == EXPECTED, 'Config changed; reassess first'
    report['config_sha256'] = EXPECTED
    report['router_sha256'] = sha(BASE / 'router.py')
    report['protected_8027'] = proc_identity(1669)
    report['before_status'] = get('http://127.0.0.1:18280/status')
    assert report['before_status']['queue'] == 0
    assert not any(w['busy'] for w in report['before_status']['workers'])
    report['before_slots'] = {str(p): slots(p) for p in (18330, 18331, 18332)}
    assert not any(s['is_processing'] for rows in report['before_slots'].values() for s in rows)
    report['before_gpu'] = gpu_apps()
    report['before_cache'] = cache_inventory(Path(config['cache_dir']))
    report['previous_cuda_failures'] = [s for s in (BASE / 'logs/v100.log').read_text(errors='replace').splitlines()
                                        if 'failed to initialize CUDA' in s or 'no usable GPU' in s][-6:]
    offsets = {w['name']: (BASE / 'logs' / (w['name'] + '.log')).stat().st_size for w in config['workers']}
    for w in config['workers']:
        env = dict(os.environ, **w.get('env', {}))
        p = subprocess.run([w['command'][0], '--list-devices'], env=env, capture_output=True, text=True, timeout=30)
        assert p.returncode == 0 and 'CUDA0:' in p.stdout, (w['name'], p.stdout, p.stderr)
    save()
    # Close only the authorized ingress, recheck in-flight work, then restart its owner.
    interrupted = True
    started = time.monotonic()
    run('systemctl', '--user', 'stop', 'aicademiya-lan.socket', 'aicademiya-lan.service')
    frozen = get('http://127.0.0.1:18280/status')
    assert frozen['queue'] == 0 and not any(w['busy'] for w in frozen['workers']), 'A request arrived; restore ingress without restarting'
    assert not any(s['is_processing'] for p in (18330, 18331, 18332) for s in slots(p))
    run('systemctl', '--user', 'restart', 'aicademiya-router.service', timeout=85)
    deadline = time.monotonic() + 240
    while True:
        try:
            state = get('http://127.0.0.1:18280/status')
            if state['model'] == MODEL and len(state['workers']) == 3 and all(w['healthy'] for w in state['workers']):
                break
        except (OSError, ValueError):
            pass
        if time.monotonic() >= deadline:
            raise TimeoutError('Three teaching replicas did not become ready')
        time.sleep(1)
    report['after_gpu'] = gpu_apps()
    for worker in config['workers']:
        match = [x for x in report['after_gpu'] if x['uuid'] == worker['env']['CUDA_VISIBLE_DEVICES'] and x['memory_mib'] >= 10000]
        assert len(match) == 1, f"Actual GPU allocation missing for {worker['name']}"
    gate = threading.Barrier(3)
    def completion(i):
        body = {'model': MODEL, 'messages': [{'role': 'user', 'content': 'Write the integers 1 through 10, separated by spaces. No other text.'}],
                'temperature': 0, 'max_tokens': 40, 'stream': False}
        gate.wait(timeout=10)
        start = time.monotonic()
        req = urllib.request.Request('http://127.0.0.1:18280/v1/chat/completions',
                                     data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=75) as response:
            data = json.load(response)
            return {'worker': response.headers.get('X-AIcademiya-Worker'), 'http': response.status,
                    'seconds': time.monotonic() - start, 'response': data}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        report['completions'] = list(pool.map(completion, range(3)))
    assert {x['worker'] for x in report['completions']} == {'v100', 't10a', 't10b'}
    for x in report['completions']:
        assert x['http'] == 200 and x['response']['model'] == MODEL
        assert x['response']['choices'][0]['message']['content'].strip(), 'Empty real completion'
    report['after_cache'] = cache_inventory(Path(config['cache_dir']))
    assert report['before_cache'] == report['after_cache'], 'Snapshot payload metadata changed'
    assert proc_identity(1669) == report['protected_8027'], 'Unrelated 8027 process changed'
    assert sha(BASE / 'config.json') == EXPECTED
    assert sha(BASE / 'router.py') == report['router_sha256']
    report['fresh_gpu_logs'] = {}
    for name, offset in offsets.items():
        with (BASE / 'logs' / (name + '.log')).open('rb') as f:
            f.seek(offset)
            text = f.read().decode(errors='replace')
        (OUT / (name + '-restart.log')).write_text(text)
        assert 'failed to initialize CUDA' not in text and 'no usable GPU' not in text
        report['fresh_gpu_logs'][name] = 'No CUDA-init failure or CPU-fallback warning'
    run('systemctl', '--user', 'start', 'aicademiya-lan.socket')
    lan = get('http://192.168.32.5:18280/status')
    assert len(lan['workers']) == 3 and all(w['healthy'] for w in lan['workers'])
    report['maintenance_seconds'] = time.monotonic() - started
    report['after_status'] = lan
    report['status'] = 'passed'
except BaseException as error:
    report.update(status='failed', error_type=type(error).__name__, error=str(error))
finally:
    if interrupted:
        # Even failed validation must not intentionally leave the original entry point off.
        p = subprocess.run(['systemctl', '--user', 'start', 'aicademiya-router.service', 'aicademiya-lan.socket'],
                           capture_output=True, text=True, timeout=100)
        report['restore_start_returncode'] = p.returncode
    report['finished_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    save()
print(json.dumps({'status': report['status'], 'result': str(OUT / 'result.json'),
                  'maintenance_seconds': report.get('maintenance_seconds'), 'error': report.get('error')}))
raise SystemExit(0 if report['status'] == 'passed' else 1)
