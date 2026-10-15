"""Verified narrow offline install recipe for the PARENT root helper.

Default is read-only PLAN. --install explicitly mutates only the chosen venv
(four missing distributions, no dependency upgrades) and a NEW model directory.
No sudo, runuser, services, drivers, shared libraries, environment/config writes
or network access. Final UID999 CPU acceptance remains a separate parent step.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

PACKAGES={'rapidocr':'3.9.2','omegaconf':'2.4.0','colorlog':'6.12.0','opencv-python':'5.0.0.93'}
REUSE={'onnxruntime':'1.31.0','numpy':'2.5.3','Pillow':'12.3.0','pyclipper':'1.4.0','Shapely':'2.2.0',
       'requests':'2.34.2','tqdm':'4.70.1','PyYAML':'6.0.3','six':'1.17.0','flatbuffers':'25.12.19',
       'packaging':'26.3','protobuf':'7.36.2','certifi':'2026.7.22','charset-normalizer':'3.5.2','idna':'3.20','urllib3':'2.8.0'}
MODEL_NAMES={'PP-OCRv6_det_small.onnx','ch_ppocr_mobile_v2.0_cls_mobile.onnx','PP-OCRv6_rec_small.onnx'}


def digest(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def verify_payload(payload):
    manifest=json.loads((payload/'dependency-manifest.json').read_text())
    if {x['distribution']:x['version'] for x in manifest['wheels']}!=PACKAGES:raise ValueError('Unexpected narrow package set')
    if {x['name'] for x in manifest['models']}!=MODEL_NAMES:raise ValueError('Unexpected model set')
    for kind,key in (('wheels','filename'),('models','name')):
        for item in manifest[kind]:
            if Path(item[key]).name!=item[key]:raise ValueError('Unsafe payload filename')
            p=payload/kind/item[key]
            if p.is_symlink() or not p.is_file() or p.stat().st_size!=item['bytes'] or digest(p)!=item['sha256']:
                raise ValueError('Payload size/SHA256 mismatch: '+item[key])
    expected=''.join(f"{x['distribution']}=={x['version']} --hash=sha256:{x['sha256']}\n" for x in manifest['wheels'])
    if (payload/'requirements-offline.txt').read_text()!=expected:raise ValueError('Offline requirement set/hash mismatch')
    return manifest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--payload',type=Path,required=True);p.add_argument('--venv',type=Path,required=True)
    p.add_argument('--models-target',type=Path,required=True);p.add_argument('--install',action='store_true');a=p.parse_args()
    payload=a.payload.resolve();python=a.venv.absolute()/'bin/python';target=a.models_target.absolute()
    if any(x.is_symlink() for x in target.parents) or target.is_symlink() or target.exists():
        raise ValueError('Model destination must be a new non-symlink directory')
    manifest=verify_payload(payload)
    code="import importlib.metadata as m,json,sys;names=json.loads(sys.argv[1]);r={};\nfor n in names:\n try:r[n]=m.version(n)\n except m.PackageNotFoundError:r[n]=None\nprint(json.dumps(r))"
    installed=json.loads(subprocess.check_output([str(python),'-B','-c',code,json.dumps([*PACKAGES,*REUSE])],text=True))
    drift={n:{'expected':v,'actual':installed[n]} for n,v in REUSE.items() if installed[n]!=v}
    conflicts={n:installed[n] for n,v in PACKAGES.items() if installed[n] is not None and installed[n]!=v}
    if drift or conflicts:raise ValueError('Reinspect runtime before installation; package drift/conflicts: '+json.dumps([drift,conflicts]))
    command=[str(python),'-m','pip','install','--disable-pip-version-check','--no-index','--no-deps','--no-compile','--require-hashes',
             '--find-links',str(payload/'wheels'),'-r',str(payload/'requirements-offline.txt')]
    result={'action':'install' if a.install else 'plan','payload_verified':True,'package_additions':PACKAGES,'reuse_unchanged':REUSE,
            'command':command,'models_target':str(target),'payload_bytes':manifest['payload_bytes'],
            'uid999_acceptance':'parent must run cpu_install_check.py --expected-uid 999 against the final packaged parser and new model dir'}
    if a.install:
        if os.geteuid()!=0:raise PermissionError('Only the parent root helper can install into the runtime')
        subprocess.run(command,check=True)
        target.mkdir(mode=0o755)
        for item in manifest['models']:
            source=payload/'models'/item['name'];destination=target/item['name']
            shutil.copyfile(source,destination);destination.chmod(0o644)
            if digest(destination)!=item['sha256']:raise ValueError('Installed model readback mismatch')
        subprocess.run([str(python),'-m','pip','check'],check=True)
        result['installed_models_readback']='size/hash matched; root-owned read-only weights'
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
