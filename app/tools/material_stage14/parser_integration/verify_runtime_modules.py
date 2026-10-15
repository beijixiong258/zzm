"""Snapshot ONLY exact allowlisted Python runtime files; not a full release.

The application is still changing. This isolated snapshot proves import/native
CLI packaging only; it must not be promoted as a frozen/deployed release.
"""
import ast
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

APP=Path(__file__).resolve().parents[3]
OUT=APP/'artifacts/stage14/parser-integration'


def main():
    sys.path.insert(0,str(APP))
    from tools.build_v2_release import collect
    files=collect(APP)
    selected={name:item for name,item in files.items() if name.endswith('.py') and
              (name.startswith('backend/') or name.startswith('tools/document_stage12/') or name.startswith('tools/material_stage13/'))}
    assert 'tools/material_stage13/ocr_verification.py' in selected
    # Resolve every static local import in parser/adapter modules against the
    # exact allowed files, without treating optional external engines as local.
    known={p.stem for directory in ('tools/document_stage12','tools/material_stage13') for p in (APP/directory).glob('*.py')}
    missing=[]
    for name,item in selected.items():
        if not name.startswith('tools/'):continue
        for node in ast.walk(ast.parse(item['data'])):
            mods=([node.module] if isinstance(node,ast.ImportFrom) else [x.name for x in node.names] if isinstance(node,ast.Import) else [])
            for mod in mods:
                if mod and mod.split('.')[0] in known:
                    found=any(x.endswith('/'+mod.split('.')[0]+'.py') for x in selected)
                    if not found:missing.append({'file':name,'module':mod})
    assert not missing,missing
    scratch=Path(os.environ['TMPDIR'])
    root=Path(tempfile.mkdtemp(prefix='s14-allowlist-smoke-',dir=scratch))
    archive=OUT/'runtime-modules-snapshot.tar.gz'
    with tarfile.open(archive,'x:gz') as tar:
        for name,item in sorted(selected.items()):
            info=tarfile.TarInfo(name);info.size=len(item['data']);info.mode=0o644;info.mtime=0
            tar.addfile(info,io.BytesIO(item['data']))
    with tarfile.open(archive,'r:gz') as tar:tar.extractall(root,filter='data')
    manifest={'scope':'scoped mutable-source runtime-module snapshot, NOT final release/deployment',
              'file_count':len(selected),'archive':str(archive),'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
              'files':{name:{'bytes':len(item['data']),'sha256':hashlib.sha256(item['data']).hexdigest()} for name,item in sorted(selected.items())},
              'extracted_root':str(root),'static_local_imports_missing':missing}
    code="import pathlib,sys;sys.path.insert(0,sys.argv[1]);from backend.aicademiya.main import create_app;from backend.aicademiya.document_bundle import source_identity;import backend.aicademiya.main as m;assert pathlib.Path(m.__file__).is_relative_to(pathlib.Path(sys.argv[1]));print('extracted backend import passed')"
    result=subprocess.run([sys.executable,'-B','-c',code,str(root)],cwd=root,capture_output=True,text=True,timeout=60)
    manifest['backend_import']={'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
    (OUT/'runtime-module-snapshot.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:manifest[k] for k in ('scope','file_count','archive_sha256','extracted_root','backend_import')}))
    return result.returncode


if __name__=='__main__':raise SystemExit(main())
