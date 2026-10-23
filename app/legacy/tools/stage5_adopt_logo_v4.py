"""Adopt the selected smoothed V4 assets; retain the previous public originals."""
from pathlib import Path
import json,shutil
ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'artifacts/stage5/logo-v4-smooth';PUBLIC=ROOT/'frontend/public'
def main():
 backup=ART/'previous-public';backup.mkdir(exist_ok=False)
 names=['aicademiya-mark.svg','aicademiya-mark-small.svg','aicademiya-mark-light.svg','favicon.svg','favicon-32.png','favicon-48.png','favicon.ico','apple-touch-icon.png']
 for name in names:shutil.copy2(PUBLIC/name,backup/name)
 green=(ART/'logo-v4-green.svg').read_text();white=(ART/'logo-v4-white.svg').read_text();design=json.loads((ART/'design.json').read_text());x,y,w,h=design['viewbox']
 (PUBLIC/'aicademiya-mark.svg').write_text(green,encoding='utf-8')
 # Use the chosen shape at every scale rather than retain the previous hand-redrawn small icon.
 (PUBLIC/'aicademiya-mark-small.svg').write_text(green,encoding='utf-8')
 (PUBLIC/'aicademiya-mark-light.svg').write_text(white,encoding='utf-8')
 rect=f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="40" fill="#f5f3e8"/>'
 favicon=green.replace('<path ',rect+'<path ',1)
 (PUBLIC/'favicon.svg').write_text(favicon,encoding='utf-8')
 print(json.dumps({'installed_svg':names[:4],'previous_assets':str(backup),'design_source':design['source'],'backend_changes':False,'model_calls':0}))
if __name__=='__main__':main()
