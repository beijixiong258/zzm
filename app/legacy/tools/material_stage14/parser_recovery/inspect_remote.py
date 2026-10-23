"""Read-only inventory of existing parser evidence and CPU/vision assets."""
import json
from pathlib import Path
import subprocess
R=Path('/home/adminz/llm/ocr-stage1-20261009')
def files(root,pattern,limit=40):
    return [str(p.relative_to(root)) for p in root.rglob(pattern)][:limit]
report={}
for name in ('gpu-additive-literal-final','gpu-final','native-v2/bundles'):
    root=R/'stage13-parser'/name
    report[name]=files(root,'manifest.json')
report['venvs']=[str(p) for p in R.rglob('pyvenv.cfg')]
report['rapidocr_modules']=[str(p) for p in R.rglob('rapidocr*')][:40]
report['onnx']=[{'path':str(p),'bytes':p.stat().st_size}for p in R.rglob('*.onnx')][:50]
report['gguf']=[{'path':str(p),'bytes':p.stat().st_size}for p in Path('/home/adminz/llm').rglob('*.gguf')][:80]
report['running_commands']=subprocess.run(['ps','-eo','pid,args'],capture_output=True,text=True).stdout
print(json.dumps(report,ensure_ascii=False,indent=2))
