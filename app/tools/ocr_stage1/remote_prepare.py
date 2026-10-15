"""Prepare only the isolated OCR environments on Ubuntu. No service changes."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys

ROOT = Path('/home/adminz/llm/ocr-stage1-20261009')
assert Path.home() == Path('/home/adminz') and sys.platform.startswith('linux')
ROOT.mkdir(exist_ok=True)
(ROOT/'tmp').mkdir(exist_ok=True)
os.environ['TMPDIR']=str(ROOT/'tmp')
os.environ['PIP_CACHE_DIR']=str(ROOT/'pip-cache')
for n in ['tools', 'models', 'evidence', 'data', 'runtime']:
    (ROOT / n).mkdir(exist_ok=True)
SOURCE = Path('/home/adminz/llm/runtimes/llama-strata-cuda/bin')
TARGET = ROOT / 'runtime/bin'
if not TARGET.exists():
    shutil.copytree(SOURCE, TARGET, symlinks=True)
records = []
for p in sorted(SOURCE.iterdir()):
    if not p.is_file():
        continue
    q = TARGET / p.name
    source_hash = hashlib.file_digest(p.open('rb'), 'sha256').hexdigest()
    assert hashlib.file_digest(q.open('rb'), 'sha256').hexdigest() == source_hash
    records.append({'name': p.name, 'sha256': source_hash, 'size': p.stat().st_size, 'symlink': p.is_symlink()})
(ROOT / 'evidence/runtime-copy.json').write_text(json.dumps({'source': str(SOURCE), 'target': str(TARGET), 'files': records}, indent=2) + '\n')
settings = {
    '.venv-paddle': ['paddlepaddle==3.3.1', 'paddleocr[doc-parser]==3.7.0', 'psutil', 'rapidfuzz'],
    '.venv-baseline': ['rapidocr==3.9.2', 'onnxruntime==1.30.0', 'pymupdf==1.28.2', 'python-docx==1.2.0', 'python-pptx==1.0.2', 'pillow==12.3.0', 'httpx>=0.28.1,<0.29', 'pydantic>=2.13.5,<3', 'fastapi>=0.142.2,<0.143', 'python-multipart>=0.0.20,<1', 'openpyxl>=3.1,<4', 'beautifulsoup4>=4.13,<5', 'psutil', 'rapidfuzz'],
}
for name, packages in settings.items():
    if (ROOT / 'STOP').exists():
        raise SystemExit('Paused')
    env = ROOT / name
    if not (env / 'bin/python').exists():
        subprocess.run([sys.executable, '-m', 'venv', str(env)], check=True)
    command = [str(env/'bin/python'), '-m', 'pip', 'install', '--disable-pip-version-check', '--no-index', '--find-links', str(ROOT/'linux-wheels'), *packages]
    with (ROOT / 'evidence' / (name[1:] + '-install.log')).open('a') as log:
        r = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    assert r.returncode == 0, name + ' dependency install failed; see retained log'
    freeze = subprocess.check_output([str(env/'bin/python'), '-m', 'pip', 'freeze'], text=True)
    (ROOT/'evidence'/(name[1:]+'-freeze.txt')).write_text(freeze)
    check = subprocess.run([str(env/'bin/python'), '-m', 'pip', 'check'], capture_output=True, text=True)
    (ROOT/'evidence'/(name[1:]+'-pip-check.txt')).write_text(check.stdout+check.stderr)
    assert check.returncode == 0, name
    print(json.dumps({'environment': name, 'status': 'ready'}), flush=True)
print(json.dumps({'status': 'passed', 'services_modified': False, 'runtime_snapshot': str(TARGET)}), flush=True)
