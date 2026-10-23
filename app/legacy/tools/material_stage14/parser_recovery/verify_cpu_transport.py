"""Verify exact isolated CPU code transport, not any production/runtime write."""
import hashlib,json,shlex,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[3];O=R/'artifacts/stage14/parser-recovery'
remote='/home/adminz/llm/ocr-stage1-20261009/stage14-parser-recovery/code'
code='import hashlib,json;from pathlib import Path;r=Path('+repr(remote)+');print(json.dumps({n:hashlib.file_digest((r/n).open("rb"),"sha256").hexdigest()for n in("ocr_verification.py","parser_helpers.py")}))'
result=subprocess.run(['ssh','ubuntu-gpu','/home/adminz/llm/ocr-stage1-20261009/whole-document-pilot/.venv/bin/python -c '+shlex.quote(code)],capture_output=True,text=True,check=True,timeout=45)
actual=json.loads(result.stdout);expected={}
for name,folder in [('ocr_verification.py','material_stage13'),('parser_helpers.py','document_stage12')]:
    with (R/'tools'/folder/name).open('rb')as f:expected[name]=hashlib.file_digest(f,'sha256').hexdigest()
report={'scope':'isolated research CPU directory only','expected':expected,'actual':actual,'matched':actual==expected}
assert report['matched'];(O/'cpu-code-readback.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
