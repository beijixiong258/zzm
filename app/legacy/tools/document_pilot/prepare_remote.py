"""Prepare the task-local MinerU environment without touching system/services."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,tarfile
BASE=Path('/home/adminz/llm/ocr-stage1-20261009')
ROOT=BASE/'whole-document-pilot'
for d in ['tools','evidence','results','tmp','mineru-home']: (ROOT/d).mkdir(parents=True,exist_ok=True)
os.environ['TMPDIR']=str(ROOT/'tmp');os.environ['PIP_CACHE_DIR']=str(ROOT/'pip-cache')
with tarfile.open(ROOT/'wheels-delta.tar')as t:t.extractall(ROOT,filter='data')
m=json.loads((ROOT/'wheels-manifest.json').read_text())
for f in m['new_files']:
 p=ROOT/'wheels'/f['name'];assert p.stat().st_size==f['size']and hashlib.file_digest(p.open('rb'),'sha256').hexdigest()==f['sha256']
env=ROOT/'.venv'
if not(env/'bin/python').exists():subprocess.run([sys.executable,'-m','venv',str(env)],check=True)
with(ROOT/'evidence/install.log').open('a')as log:
 p=subprocess.run([str(env/'bin/python'),'-m','pip','install','--no-index','--find-links',str(ROOT/'wheels'),'--find-links',str(BASE/'linux-wheels'),'-r',str(ROOT/'requirements.txt')],stdout=log,stderr=subprocess.STDOUT)
assert p.returncode==0,'Isolated install failed; see install.log'
freeze=subprocess.check_output([str(env/'bin/python'),'-m','pip','freeze'],text=True);(ROOT/'evidence/freeze.txt').write_text(freeze)
p=subprocess.run([str(env/'bin/python'),'-m','pip','check'],capture_output=True,text=True);(ROOT/'evidence/pip-check.txt').write_text(p.stdout+p.stderr);assert p.returncode==0
config={'log':{'level':'info'},'model':{'base_dir':str(ROOT/'mineru-home/models'),'source':'local','small_backend':'onnx','vlm':{'engine':'llama-cpp','server_url':'http://127.0.0.1:18892','model':'mineru-doc','http_timeout':600,'max_concurrency':1}},'llm_aided':{'api_key':'','base_url':'http://127.0.0.1:18892/v1','model':'mineru-doc','features':{'title_leveling':False,'cross_page_table_cell_merge':False}}}
(ROOT/'mineru-home/config.yaml').write_text(json.dumps(config,indent=2)+'\n')
child_env={**os.environ,'MINERU_HOME':str(ROOT/'mineru-home'),'MINERU_CONFIG':str(ROOT/'mineru-home/config.yaml'),'MINERU_MODEL_SOURCE':'local','LD_LIBRARY_PATH':str(BASE/'native-libs/usr/lib/x86_64-linux-gnu'),'OMP_NUM_THREADS':'4','OPENBLAS_NUM_THREADS':'4'}
code="import importlib.metadata,inspect;from mineru.parser import parse;from mineru.config import config;print(importlib.metadata.version('mineru'));print(inspect.signature(parse));print(config.model.small_backend,config.model.vlm.server_url,config.llm_aided.features)"
p=subprocess.run([str(env/'bin/python'),'-c',code],env=child_env,capture_output=True,text=True,timeout=60)
(ROOT/'evidence/import-check.txt').write_text(p.stdout+p.stderr);print(p.stdout,p.stderr);assert p.returncode==0
print(json.dumps({'status':'ready','system_modified':False,'services_modified':False,'home':str(ROOT/'mineru-home'),'venv':str(env)}),flush=True)
