"""Create source/baseline hashes and verify exact final UI evidence (no backend edits)."""
from pathlib import Path
import hashlib
import errno
import json
import socket
import urllib.parse
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'artifacts/stage12/ui'
OWNED = [
    'frontend/src/DocumentReader.tsx', 'frontend/src/document-reader.css',
    'frontend/src/document-types.ts', 'frontend/src/document-api.ts', 'frontend/src/document-state.ts',
    'frontend/src/Materials.tsx', 'frontend/src/MaterialManager.tsx', 'frontend/src/material-upload.ts',
    'frontend/src/SourceCitations.tsx', 'frontend/src/api.ts', 'frontend/src/types.ts',
    'frontend/tests/stage12-document-client.test.ts', 'frontend/tests/stage12-document-ui.test.tsx',
    'frontend/tests/stage4-materials.test.tsx', 'frontend/tests/stage12-document-harness.tsx',
    'frontend/tests/stage12-document-harness.html', 'frontend/tests/stage12-document-browser.mjs',
    'frontend/tests/stage12-document-manifest.py',
]
COMMANDS = [
    'NODE_TLS_REJECT_UNAUTHORIZED=1 npm --prefix frontend test -- tests/stage12-document-client.test.ts tests/stage12-document-ui.test.tsx tests/stage4-materials.test.tsx --reporter=default --reporter=junit --outputFile=../artifacts/stage12/ui/frontend-targeted.xml',
    'NODE_TLS_REJECT_UNAUTHORIZED=1 npm --prefix frontend test -- --reporter=default --reporter=junit --outputFile=../artifacts/stage12/ui/frontend-full.xml',
    'NODE_TLS_REJECT_UNAUTHORIZED=1 npm --prefix frontend run build',
    'NODE_TLS_REJECT_UNAUTHORIZED=1 node frontend/tests/stage12-document-browser.mjs',
    '.venv/Scripts/python.exe frontend/tests/stage12-document-manifest.py',
]
def sha(data):
    return hashlib.sha256(data).hexdigest()

def test_counts(file):
    root = ET.parse(file).getroot()
    cases = root.findall('.//testcase')
    return {'tests': len(cases), 'failures': sum(c.find('failure') is not None for c in cases),
            'errors': sum(c.find('error') is not None for c in cases),
            'skipped': sum(c.find('skipped') is not None for c in cases)}

baseline = json.loads((ROOT / 'artifacts/stage12/baseline.json').read_text('utf-8'))
archive = Path(baseline['archive'])
assert sha(archive.read_bytes()) == baseline['sha256']
files = []
with zipfile.ZipFile(archive) as z:
    names = set(z.namelist())
    for name in OWNED:
        value = (ROOT / name).read_bytes()
        old = z.read(name) if name in names else None
        files.append({'path': name, 'bytes': len(value), 'sha256': sha(value),
                      'baseline_sha256': sha(old) if old is not None else None,
                      'state': 'new_since_stage12_baseline' if old is None else 'unchanged' if old == value else 'modified'})
    agents = ROOT / 'AGENTS.md'
    if agents.exists() and 'AGENTS.md' in names:
        assert agents.read_bytes() == z.read('AGENTS.md')

report = json.loads((OUT / 'browser-report.json').read_text('utf-8'))
assert report['passed'] and report['checkCount'] == len(report['checks']) == 12
assert all(c['passed'] for c in report['checks'])
assert not report['errors'] and not report['external']
assert report['cleanup']['chromeClosed'] and report['cleanup']['serverClosed']
address = urllib.parse.urlparse(report['origin'])
sock = socket.socket()
sock.settimeout(5)
try:
    connect_code = sock.connect_ex((address.hostname, address.port))
    listener_closed = connect_code in {errno.ECONNREFUSED, getattr(errno, 'WSAECONNREFUSED', 10061)}
finally:
    sock.close()
assert listener_closed, 'Owned fixture port is still listening'

counts = {name: test_counts(OUT / name) for name in ['frontend-targeted.xml', 'frontend-full.xml']}
assert counts['frontend-targeted.xml'] == {'tests': 28, 'failures': 0, 'errors': 0, 'skipped': 0}
assert counts['frontend-full.xml'] == {'tests': 362, 'failures': 0, 'errors': 0, 'skipped': 0}
artifacts = [{'path': p.relative_to(ROOT).as_posix(), 'sha256': sha(p.read_bytes()), 'bytes': p.stat().st_size}
             for p in sorted(OUT.rglob('*')) if p.is_file() and p.name not in {'changes.json', 'cleanup.json'}]
dist = [{'path': p.relative_to(ROOT).as_posix(), 'sha256': sha(p.read_bytes()), 'bytes': p.stat().st_size}
        for p in sorted((ROOT / 'frontend/dist').rglob('*')) if p.is_file()]
result = {'label': 'Frontend handoff only; not deployed; synthetic UI HTTP fixture',
          'baseline': baseline, 'owned_source_count': len(files), 'owned_sources': files,
          'generated_dist': dist, 'artifact_hashes': artifacts, 'commands': COMMANDS,
          'test_counts': counts, 'browser_checks': report['checkCount'],
          'screenshots': report['screenshots'],
          'cleanup': {'origin': report['origin'], 'listener_closed': listener_closed, 'connect_code': connect_code, **report['cleanup']},
          'limitations': ['No real backend authentication or SQLite proof in UI fixture',
                          'Synthetic SVG page/crop and literal table fixture, not OCR accuracy',
                          'Original endpoint is labelled synthetic HTML, not native PDF-renderer verification',
                          'No real model/search, production data, remote services or deployment touched']}
(OUT / 'changes.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
(OUT / 'cleanup.json').write_text(json.dumps(result['cleanup'], indent=2), encoding='utf-8')
print(json.dumps({'owned_source_count': len(files), 'dist_count': len(dist), 'artifact_count': len(artifacts),
                  'test_counts': counts, 'browser_checks': report['checkCount'], 'cleanup': result['cleanup']}, indent=2))
