"""Read back exact public production targets; no credentials or learning writes."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re
import httpx
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/stage11'
RELEASE='AIcademiya_V2-20261008-people'
BASE='http://192.168.32.55:18773'
def main():
 manifest=json.loads((OUT/'release-people'/(RELEASE+'.manifest.json')).read_text())
 with httpx.Client(base_url=BASE,trust_env=False,timeout=10) as c:
  index=c.get('/');assert index.status_code==200
  b=c.get('/api/bootstrap').json();api=c.get('/openapi.json').json()
  assert not b['demo_enabled'] and b['ai']['mode']=='openai'
  assert api['info']['version']=='0.9.0' and b['ai']['model']=='AIcademiya-64kx3-Qwen3.8-27B'
  assert c.get('/api/courses').status_code==401
  assert c.post('/api/auth/demo',json={'role':'student'}).status_code==403
  assert isinstance(b['registration_enabled'],bool)
  assert '<title>AIcademiya</title>' in index.text
  assert c.get('/api/admin/access-settings').status_code==401
  assert index.headers.get('x-content-type-options')=='nosniff' and index.headers.get('x-frame-options')=='SAMEORIGIN'
  assert "frame-ancestors 'self'" in index.headers.get('content-security-policy','')
  assert 'no-store' in c.get('/api/bootstrap').headers.get('cache-control','')
  assert c.get('/api/health',headers={'Host':'untrusted.example.invalid'}).status_code==400
  protected_figures=[]
  for name in manifest['files']:
   if name.startswith('sample_data/assets/'):
    url='/api/assets/'+name.removeprefix('sample_data/assets/')
    response=c.get(url);assert response.status_code==401 and 'no-store' in response.headers.get('cache-control','')
    protected_figures.append(url)
  assert protected_figures, 'Exact catalog figure paths must be checked, not only a guessed missing path'
  routes=['/api/admin/users','/api/admin/users/{user_id}','/api/admin/users/{user_id}/status','/api/admin/users/import/preview','/api/admin/users/import/{import_id}','/api/admin/users/import/{import_id}/commit','/api/admin/courses','/api/courses/{course_id}/staff','/api/courses/{course_id}/staff/primary','/api/admin/access-settings','/api/auth/avatar','/api/users/{user_id}/avatar','/api/feedback','/api/feedback/requests/{request_id}','/api/feedback/{feedback_id}','/api/admin/feedback','/api/admin/feedback/{feedback_id}','/api/courses/trash','/api/courses/{course_id}','/api/courses/{course_id}/trash','/api/courses/{course_id}/restore','/api/teacher/search-settings','/api/teacher/search-settings/test','/api/teacher/sessions/{session_id}/preview','/api/teacher/sessions/{session_id}/preview/reset','/api/teacher/sessions/{session_id}/source-review','/api/teacher/sessions/{session_id}/instruction-import/preview','/api/courses/{course_id}/materials','/api/sessions/{session_id}/materials/attach','/api/sessions/{session_id}/materials/{material_id}/reprocess']
  assert all(p in api['paths'] for p in routes)
  for path in ('/api/admin/users','/api/admin/courses','/api/courses/unknown/staff','/api/teacher/settings','/api/teacher/search-settings','/api/courses/trash','/api/feedback','/api/admin/feedback','/api/users/nonexistent/avatar?v=none'):
   assert c.get(path).status_code==401
  assert b['ai']['connection']['status'] in ('not_configured','not_checked','connected','error')
  checked=[]
  for name,info in manifest['files'].items():
   if not name.startswith('frontend/dist/'):continue
   url='/'+name.removeprefix('frontend/dist/');response=c.get(url)
   assert response.status_code==200 and hashlib.sha256(response.content).hexdigest()==info['sha256'],url
   checked.append({'url':url,'matches_release':True})
  report={'status':'passed','checked_at':datetime.now(timezone.utc).isoformat(),'url':BASE,'release':RELEASE,'api_version':'0.9.0','demo_enabled':False,'anonymous_courses':401,'demo_login':403,'model':b['ai']['model'],'ai_mode':b['ai']['mode'],'material_routes_present':True,'security_headers_verified':True,'generic_document_title':True,'global_account_staff_routes_present_and_anonymous_denied':True,'untrusted_host_rejected':True,'registration_enabled':b['registration_enabled'],'anonymous_admin_access':401,'anonymous_exact_figures_blocked':protected_figures,'static_files':checked}
 (OUT/'production-readback.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'status':'passed','api_version':'0.9.0','static_files_verified':len(checked),'report':str(OUT/'production-readback.json')}))
if __name__=='__main__':main()
