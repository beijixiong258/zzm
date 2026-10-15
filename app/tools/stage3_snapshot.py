"""Create a source-only baseline for local stage-3 development; no runtime data/secrets."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SKIP = {'.venv', 'node_modules', '__pycache__', '.pytest_cache', 'artifacts', 'dist', 'data', 'logs', '.git'}


def main():
    files = set()
    for directory in ('backend', 'tools', 'frontend/src', 'frontend/public', 'frontend/tests', 'runtime_v2'):
        for p in (ROOT/directory).rglob('*'):
            rel = p.relative_to(ROOT)
            if p.is_file() and not any(part in SKIP for part in rel.parts) and p.suffix not in {'.pyc', '.sqlite3', '.db'}:
                files.add(p)
    for p in ROOT.iterdir():
        if p.is_file() and (p.suffix in {'.md', '.cmd', '.yaml'} or p.name in {'Dockerfile', '.gitignore', '.dockerignore', '.env.example'}):
            files.add(p)
    for p in (ROOT/'frontend').iterdir():
        if p.is_file() and p.suffix in {'.json', '.ts', '.html'}:
            files.add(p)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = ROOT/'artifacts/stage3'; out.mkdir(parents=True, exist_ok=True)
    archive = out/f'source-baseline-{stamp}.zip'
    manifest = []
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(files):
            data=p.read_bytes(); rel=p.relative_to(ROOT).as_posix()
            z.writestr(rel,data)
            manifest.append({'path':rel,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
        z.writestr('BASELINE_MANIFEST.json',json.dumps(manifest,indent=2))
    with zipfile.ZipFile(archive) as z:
        for item in manifest:
            assert hashlib.sha256(z.read(item['path'])).hexdigest()==item['sha256']
    result={'archive':str(archive),'files':len(manifest),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
            'excluded':['runtime databases','credentials/local-settings/.env','sample_data','original archives','node_modules/.venv','QA artifacts']}
    (out/'baseline.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()