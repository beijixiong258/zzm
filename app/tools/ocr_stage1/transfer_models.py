"""Move completed and partial public model artifacts to the authorized GPU host."""
from pathlib import Path
import hashlib
import json
import shlex
import subprocess
from budget import check, OUT

REMOTE = '/home/adminz/llm/ocr-stage1-20261009'
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', 'ubuntu-gpu']
SCP = ['scp', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes']


def remote(code):
    p = subprocess.run(SSH + ['python3 -c ' + shlex.quote(code)], capture_output=True, text=True, encoding='utf-8', timeout=120)
    if p.returncode:
        raise RuntimeError(p.stderr[-1000:])
    return p.stdout


def main():
    check(force=True)
    manifest = json.loads((OUT / 'download-manifest.json').read_text())
    items = [x for x in manifest['items'] if x['kind'] != 'runtime']
    transferred = []
    remote("from pathlib import Path;p=Path(" + repr(REMOTE) + ");[(p/x).mkdir(parents=True,exist_ok=True) for x in ['models/minicpm-v4.5','models/paddleocr-vl1.6','tools','evidence']]")
    for item in items:
        check()
        source = Path(item['path'])
        if not source.exists():
            source = source.with_suffix(source.suffix + '.part')
        item['path'] = REMOTE + '/' + str(Path(item['path']).relative_to(OUT)).replace('\\', '/')
        if not source.exists():
            continue
        relative = str(source.relative_to(OUT)).replace('\\', '/')
        target = REMOTE + '/' + relative
        expected = hashlib.file_digest(source.open('rb'), 'sha256').hexdigest()
        print(json.dumps({'transfer': relative, 'bytes': source.stat().st_size}), flush=True)
        p = subprocess.run(SCP + [str(source), 'ubuntu-gpu:' + target], timeout=2400)
        if p.returncode:
            raise RuntimeError('scp failed: ' + relative)
        code = 'import hashlib;from pathlib import Path;p=Path(' + repr(target) + ');h=hashlib.file_digest(p.open("rb"),"sha256").hexdigest();assert h==' + repr(expected) + ';print(p.stat().st_size)'
        actual = int(remote(code).strip())
        assert actual == source.stat().st_size
        transferred.append({'relative_path': relative, 'bytes': actual, 'sha256': expected, 'partial': source.suffix == '.part', 'remote_path': target})
        (OUT / 'server-transfer.json').write_text(json.dumps({'status': 'running', 'files': transferred}, indent=2) + '\n')
    # Retain the earlier public download total so a server retry cannot silently
    # exceed the user's overall12GB budget. Transfers are recorded separately.
    downloaded = json.loads((OUT / 'download-progress.json').read_text())
    remote_manifest = {'items': items, 'download_budget_bytes': manifest['model_download_budget_bytes'], 'earlier_download_bytes': max(downloaded['network_bytes'], sum(x.stat().st_size for x in (OUT/'models').rglob('*') if x.is_file()) + sum(x.stat().st_size for x in (OUT/'downloads').glob('*.zip')))}
    local = OUT / 'server-download-manifest.json'
    local.write_text(json.dumps(remote_manifest, indent=2) + '\n')
    subprocess.run(SCP + [str(local), 'ubuntu-gpu:' + REMOTE + '/download-manifest.json'], check=True, timeout=60)
    remote('import json;from pathlib import Path;d=json.loads(Path(' + repr(REMOTE + '/download-manifest.json') + ').read_text());assert len(d["items"])==' + str(len(items)))
    (OUT / 'server-transfer.json').write_text(json.dumps({'status': 'passed', 'files': transferred, 'manifest_readback_verified': True}, indent=2) + '\n')
    print(json.dumps({'status': 'passed', 'files': len(transferred), 'remote': REMOTE}), flush=True)


if __name__ == '__main__':
    main()
