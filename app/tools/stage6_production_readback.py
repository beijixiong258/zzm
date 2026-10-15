"""Read back exact public production targets; no credentials or learning writes."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re
import httpx
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/stage6'
RELEASE='AIcademiya_V2-20261007-workbench'
BASE='http://192.168.32.55:18773'
def main():
 manifest=json.loads((OUT/'release-workbench'/(RELEASE+'.manifest.json')).read_text())
 with httpx.Client(base_url=BASE,trust_env=False,timeout=10) as c:
  index=c.get('/');assert index.status_code==200
  b=c.get('/api/bootstrap').json();api=c.get('/openapi.json').json()
  assert not b['demo_enabled'] and b['ai']['mode']=='openai'
  assert api['info']['version']=='0.5.0' and b['ai']['model']=='AIcademiya-64kx3-Qwen3.8-27B'
  assert c.get('/api/courses').status_code==401
  assert c.post('/api/auth/demo',json={'role':'student'}).status_code==403
  routes=['/api/teacher/sessions/{session_id}/preview','/api/teacher/sessions/{session_id}/preview/reset','/api/teacher/sessions/{session_id}/source-review','/api/teacher/sessions/{session_id}/instruction-import/preview','/api/courses/{course_id}/materials','/api/sessions/{session_id}/materials/attach','/api/sessions/{session_id}/materials/{material_id}/reprocess']
  assert all(p in api['paths'] for p in routes)
  checked=[]
  for name,info in manifest['files'].items():
   if not name.startswith('frontend/dist/'):continue
   url='/'+name.removeprefix('frontend/dist/');response=c.get(url)
   assert response.status_code==200 and hashlib.sha256(response.content).hexdigest()==info['sha256'],url
   checked.append({'url':url,'matches_release':True})
  report={'status':'passed','checked_at':datetime.now(timezone.utc).isoformat(),'url':BASE,'release':RELEASE,'api_version':'0.5.0','demo_enabled':False,'anonymous_courses':401,'demo_login':403,'model':b['ai']['model'],'ai_mode':b['ai']['mode'],'material_routes_present':True,'static_files':checked}
 (OUT/'production-readback.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'status':'passed','api_version':'0.5.0','static_files_verified':len(checked),'report':str(OUT/'production-readback.json')}))
if __name__=='__main__':main()
