"""Genuine CPU-only OCR install check; block all outbound requests.

Use the final worker interpreter and account. Supply --models with the three
existing weights and --parser-dir with the packaged material_stage13 directory.
No GPU/model-service calls; optional --output writes only an explicit report.
"""
import argparse
import importlib.metadata as md
import json
import os
from pathlib import Path
import socket
import sys


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--models',type=Path,required=True);p.add_argument('--parser-dir',type=Path,required=True)
    p.add_argument('--output',type=Path);p.add_argument('--expected-uid',type=int);a=p.parse_args()
    if a.expected_uid is not None and os.getuid()!=a.expected_uid:
        raise SystemExit('CPU install check must run as the requested final worker UID')
    os.environ.update(CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',PYTHONDONTWRITEBYTECODE='1')
    def blocked(*args,**kwargs):raise RuntimeError('Network is disabled for offline CPU install check')
    socket.create_connection=blocked
    import requests
    requests.sessions.Session.request=blocked
    sys.path.insert(0,str(a.parser_dir))
    from ocr_verification import CPUVerifier,normalized
    from PIL import Image,ImageDraw,ImageFont
    from packaging.requirements import Requirement
    from packaging.markers import default_environment
    # Check the exact narrow runtime closure; do not demand unrelated optional
    # GPU extras or let pip replace already-installed working dependencies.
    closure={};missing=[];environment={**default_environment(),'extra':''}
    for name in ('rapidocr','omegaconf','opencv-python','colorlog','onnxruntime'):
        d=md.distribution(name);closure[name]={'version':d.version,'location':str(d.locate_file('')),'requirements':[]}
        for raw in d.requires or []:
            r=Requirement(raw)
            if r.marker and not r.marker.evaluate(environment):continue
            try:version=md.version(r.name);ok=version in r.specifier
            except md.PackageNotFoundError:version=None;ok=False
            entry={'requirement':raw,'installed_version':version,'satisfied':ok}
            closure[name]['requirements'].append(entry)
            if not ok:missing.append(entry)
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',32)
    expected=['Verified source line one','Verified source line two','Original final source line']
    image=Image.new('RGB',(800,260),'white');draw=ImageDraw.Draw(image)
    for index,text in enumerate(expected):draw.text((30,30+index*65),text,font=font,fill='black')
    verifier=CPUVerifier(a.models);scan=verifier.scan(image)
    actual='\n'.join(line['text'] for line in scan.get('lines',[]))
    exact=normalized(actual)==normalized('\n'.join(expected))
    result={'scope':'synthetic real CPU OCR install smoke only; not VLM/semantic/material completion',
            'uid':os.getuid(),'interpreter':sys.executable,'parser_file':str(Path(sys.modules['ocr_verification'].__file__).resolve()),
            'gpu_calls':0,'network_blocked':True,'dependency_closure':closure,'missing_dependencies':missing,
            'expected':expected,'exact_groundtruth_agreement':exact,'independent_ocr':scan,
            'status':'passed' if exact and scan['status']=='complete' and not missing else 'failed'}
    if a.output:a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
