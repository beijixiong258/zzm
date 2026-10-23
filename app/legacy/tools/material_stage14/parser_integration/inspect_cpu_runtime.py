"""Read-only Ubuntu package/import/model inventory; no service/model calls."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path('/home/adminz/llm/ocr-stage1-20261009')
NATIVE = '/opt/aicademiya-documents/shared/native-libs/usr/lib/x86_64-linux-gnu'
PROBE = r'''
import importlib, importlib.metadata as md, json, sys
names = ['rapidocr','onnxruntime','opencv-python','opencv-python-headless','numpy','Pillow','omegaconf','antlr4-python3-runtime','pyclipper','Shapely','requests','tqdm','colorlog','PyYAML','six','flatbuffers','packaging','protobuf','certifi','charset-normalizer','idna','urllib3','mineru','mineru-vl-utils','PyMuPDF','olefile']
result = {'python':sys.version,'executable':sys.executable,'packages':{},'imports':{}}
for name in names:
    try:
        d=md.distribution(name)
        result['packages'][name]={'version':d.version,'requires':d.requires or [],'location':str(d.locate_file(''))}
    except md.PackageNotFoundError:result['packages'][name]=None
for name in ['rapidocr','onnxruntime','cv2','numpy','PIL','omegaconf','pyclipper','shapely']:
    try:
        m=importlib.import_module(name)
        result['imports'][name]={'ok':True,'file':m.__file__}
        if name=='onnxruntime':result['imports'][name]['available_providers']=m.get_available_providers()
    except Exception as e:result['imports'][name]={'ok':False,'error_type':type(e).__name__,'error':str(e)}
print(json.dumps(result))
'''


def main():
    report = {'scope':'read-only package/import inventory; no inference, no root/venv modifications', 'environments':{}}
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE':'1', 'CUDA_VISIBLE_DEVICES':'', 'LD_LIBRARY_PATH':NATIVE}
    venvs = {'installed':Path('/opt/aicademiya-documents/runtime/.venv'),
             'baseline':ROOT/'.venv-baseline', 'research':ROOT/'whole-document-pilot/.venv'}
    for label, path in venvs.items():
        p=subprocess.run([str(path/'bin/python'),'-B','-c',PROBE],env=env,capture_output=True,text=True,timeout=60)
        report['environments'][label]={'returncode':p.returncode, 'data':json.loads(p.stdout) if p.returncode==0 else None, 'stderr':p.stderr}
    models=ROOT/'.venv-baseline/lib/python3.12/site-packages/rapidocr/models'
    report['models']=[]
    for name in ('PP-OCRv6_det_small.onnx','ch_ppocr_mobile_v2.0_cls_mobile.onnx','PP-OCRv6_rec_small.onnx'):
        p=models/name
        with p.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
        report['models'].append({'path':str(p),'name':name,'bytes':p.stat().st_size,'sha256':digest})
    report['native_libs']={'path':NATIVE,'present':Path(NATIVE).is_dir()}
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
