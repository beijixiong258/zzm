"""Frozen source-only r6 geometry probe, real original, owner lease; no production writes."""
from pathlib import Path
import sys,os,json,hashlib,subprocess,signal
ROOT=Path(__file__).resolve().parent
os.environ.update(AICADEMIYA_DOCUMENT_BASE='/opt/aicademiya-documents/shared',
 AICADEMIYA_DOCUMENT_RUNTIME=str(ROOT/'runtime'),AICADEMIYA_DOCUMENT_HOME=str(ROOT/'worker-home'),
 AICADEMIYA_DOCUMENT_GPU_UUID='GPU-105b82fb-41db-d6a1-13f0-ceddf5bed313',
 AICADEMIYA_DOCUMENT_GPU_LEASE_SOCKET='/home/adminz/llm/material-gpu-state/maintenance.sock',
 AICADEMIYA_DOCUMENT_GPU_OWNER_UID='1000',AICADEMIYA_RAPIDOCR_MODELS='/opt/aicademiya-documents/shared/rapidocr-models-stage14',
 PYTHONDONTWRITEBYTECODE='1')
sys.path.insert(0,str(ROOT/'tools/document_stage12'))
import document_worker_service as service
for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):signal.signal(sig,lambda *_:service.STOP.set())
SOURCE=Path('/home/adminz/llm/ocr-stage1-20261009/data/dataset/sources/src14.pdf')
EXPECTED='5ffdc6a8dce6d5136397afb13bcaf627a5396f8c004ab1007d6493981ca8e723'
def sha(p):
 with p.open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def allocations():return subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid','--format=csv,noheader,nounits'],text=True).splitlines()
def main():
 assert os.getuid()==1000 and sha(SOURCE)==EXPECTED
 before=allocations();out=ROOT/'real-scan-geometry-r6';report={'scope':'OwnerUID1000 frozen candidate GPU test, NOT installed UID999/app acceptance','source_sha256':EXPECTED,'before_allocations':before}
 try:
  service.run_job(SOURCE,out,timeout=1500,quota_guard=False)
  m=json.loads((out/'manifest.json').read_text());receipt=json.loads((out/'receipt.json').read_text());supervisor=json.loads((out/'raw/supervisor.json').read_text())
  assert m['complete'] and m['page_count']==10 and receipt['status']=='complete' and supervisor['fresh_inference']
  assert sha(SOURCE)==EXPECTED and supervisor['owned_processes_closed'] and supervisor['gpu_return']['teaching_ready']
  after=allocations();anchors=[v for v in before if not v.startswith('GPU-105b82fb-41db-d6a1-13f0-ceddf5bed313')];assert all(v in after for v in anchors)
  report.update(status='executed_requires_source_review',coverage=m['coverage'],receipt=receipt,supervisor=supervisor,after_allocations=after,semantic_accepted=False)
 except BaseException as e:report.update(status='failed',error_type=type(e).__name__,error=str(e));raise
 finally:(ROOT/'probe-result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':report['status'],'output':str(out)}))
if __name__=='__main__':main()
