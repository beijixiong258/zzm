"""Static read-only runtime vision support, never execute/load a model."""
import hashlib,json,subprocess
from pathlib import Path
R=Path('/home/adminz/llm');O=R/'ocr-stage1-20261009/stage14-parser-recovery'
source=R/'operations/strata-20261007/llama.cpp-3cf03257f219afbe7334045ff7c6a06ac68c627d'
binary=R/'runtimes/llama-strata-cuda/bin/llama-server'
selected={}
for rel,needles in [('tools/mtmd/mtmd.cpp',('qwen35','qwen3vl_merger','QWEN3VL','QWEN35')),
                    ('tools/mtmd/clip.cpp',('qwen35','qwen3vl_merger','QWEN3VL')),
                    ('tools/mtmd/models/qwen3vl.cpp',('qwen','merger','QWEN')),
                    ('common/arg.cpp',('mmproj','no-mmproj-offload','image-min-tokens','image-max-tokens'))]:
    path=source/rel
    if path.exists():
        lines=path.read_text().splitlines()
        selected[rel]=[{'line':i+1,'text':line}for i,line in enumerate(lines)if any(n in line for n in needles)][:40]
report={'scope':'static_support_only; no load/inference or teaching endpoint calls',
    'binary':str(binary),'binary_bytes':binary.stat().st_size,'source_commit':'3cf03257f219afbe7334045ff7c6a06ac68c627d',
    'dynamic_dependencies':subprocess.run(['readelf','-d',str(binary)],capture_output=True,text=True).stdout,
    'runtime_libraries':[p.name for p in binary.parent.glob('*.so*')],
    'server_implementation_dependencies':subprocess.run(['readelf','-d',str(binary.parent/'libllama-server-impl.so')],capture_output=True,text=True).stdout,
    'built_mtmd_projector_strings':[s for s in subprocess.run(['strings',str(binary.parent/'libmtmd.so')],capture_output=True,text=True).stdout.splitlines()if 'qwen3vl_merger'in s or 'qwen35'in s][:20],
    'source_matches':selected,'real_image_runtime_test':'unverified; parent exclusive GPU lane only'}
(O/'runtime-vision-support.json').write_text(json.dumps(report,indent=2))
print(json.dumps({k:v for k,v in report.items()if k not in ('dynamic_dependencies','source_matches')},indent=2))
for rel,lines in selected.items():
    print(rel)
    for line in lines[:7]:print(line['line'],line['text'])
