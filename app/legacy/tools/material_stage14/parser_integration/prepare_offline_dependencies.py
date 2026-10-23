"""Prepare only four RECORD-verified offline wheels plus three existing weights.

Run with the baseline Python on Ubuntu. No pip index/download, installed venv,
root paths, model services or drivers are changed. Generated wheels are faithful
re-packs of installed wheel files, NOT original publisher wheel hashes.
"""
import base64
import csv
import hashlib
import importlib.metadata as md
import io
import json
from pathlib import Path
import shutil
import zipfile

STAGE=Path('/home/adminz/llm/ocr-stage1-20261009/stage14-parser-integration')
PACKAGES=('rapidocr','omegaconf','colorlog','opencv-python')
MODELS=('PP-OCRv6_det_small.onnx','ch_ppocr_mobile_v2.0_cls_mobile.onnx','PP-OCRv6_rec_small.onnx')


def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    (STAGE/'wheels').mkdir(parents=True,exist_ok=True)
    (STAGE/'models').mkdir(exist_ok=True)
    report={'format':1,'preparation':'offline repack from baseline wheel RECORD; no network or shared-venv copy',
            'python_abi':'Ubuntu x86_64 CPython3.12','wheels':[],'models':[],'skipped_generated_files':{}}
    for name in PACKAGES:
        dist=md.distribution(name);base=Path(dist.locate_file('')).resolve()
        distinfo=next(p.parts[0] for p in dist.files if str(p).endswith('.dist-info/WHEEL'))
        tag=next(line.split(': ',1)[1] for line in dist.read_text('WHEEL').splitlines() if line.startswith('Tag: '))
        wheel=STAGE/'wheels'/f'{name.replace("-","_")}-{dist.version}-{tag}.whl'
        contents={};skipped=[]
        for entry in dist.files:
            if ('..' in entry.parts or '__pycache__' in entry.parts or entry.suffix=='.pyc'
                    or entry.name in ('INSTALLER','REQUESTED','RECORD','direct_url.json')):
                skipped.append(str(entry));continue
            p=Path(dist.locate_file(entry))
            if p.is_symlink() or not p.resolve().is_relative_to(base) or not p.is_file():raise ValueError('Unsafe baseline package entry: '+str(entry))
            data=p.read_bytes()
            if entry.hash is None or entry.hash.mode!='sha256':raise ValueError('Missing original RECORD hash: '+str(entry))
            actual=base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()
            if actual!=entry.hash.value or len(data)!=entry.size:raise ValueError('Original baseline RECORD mismatch: '+str(entry))
            contents[str(entry)]=data
        record=io.StringIO();writer=csv.writer(record,lineterminator='\n')
        for ref,data in sorted(contents.items()):
            writer.writerow((ref,'sha256='+base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode(),len(data)))
        record_name=distinfo+'/RECORD';writer.writerow((record_name,'',''));contents[record_name]=record.getvalue().encode()
        with zipfile.ZipFile(wheel,'x',compression=zipfile.ZIP_DEFLATED) as out:
            for ref,data in sorted(contents.items()):out.writestr(ref,data)
        report['wheels'].append({'distribution':name,'version':dist.version,'path':str(wheel),'filename':wheel.name,
                                'sha256':digest(wheel),'bytes':wheel.stat().st_size,'file_count':len(contents),'tag':tag,
                                'origin_site_packages':str(base),'requires':dist.requires or []})
        report['skipped_generated_files'][name]=skipped
    modelroot=Path(md.distribution('rapidocr').locate_file('rapidocr/models'))
    for name in MODELS:
        source=modelroot/name;target=STAGE/'models'/name
        if target.exists():raise ValueError('New staging model target required')
        shutil.copyfile(source,target)
        if digest(target)!=digest(source):raise ValueError('Staged model hash mismatch')
        report['models'].append({'name':name,'source':str(source),'path':str(target),'sha256':digest(target),'bytes':target.stat().st_size})
    report['payload_bytes']=sum(x['bytes'] for kind in ('wheels','models') for x in report[kind])
    if report['payload_bytes']>1024**3:raise ValueError('Payload over1GiB')
    manifest=STAGE/'dependency-manifest.json';manifest.write_text(json.dumps(report,indent=2)+'\n')
    (STAGE/'requirements-offline.txt').write_text(''.join(f"{x['distribution']}=={x['version']} --hash=sha256:{x['sha256']}\n" for x in report['wheels']))
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
