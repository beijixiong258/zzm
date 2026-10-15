"""Lightweight health protocol fixtures, no generation or external network."""
import json
import httpx
from .conftest import expect
from backend.aicademiya.service_settings import invalidate_check

def configured(app,model='fixture-model',base='http://127.0.0.1:9999/v1'):
 with app.state.database.connect()as conn:
  for key,value in {'mode':'openai','model':model,'base_url':base,'api_key':'SYNTHETIC_SECRET_KEY'}.items():conn.execute('insert into settings(key,value)values(?,?)on conflict(key)do update set value=excluded.value',('ai_'+key,value))
  invalidate_check(conn,'ai')

def test_connection_uses_shared_bounded_model_listing_without_generation(app,teacher,student):
 configured(app);calls=[]
 def handle(request):
  calls.append(request);assert request.method=='GET'and request.url.path=='/v1/models';return httpx.Response(200,json={'data':[{'id':'fixture-model'}]})
 app.state.tutor.transport=httpx.MockTransport(handle)
 first=expect(teacher.get('/api/ai/connection'));second=expect(student.get('/api/ai/connection'))
 assert first==second and first['status']=='connected'and first['check_kind']=='model_listing';assert len(calls)==1
 assert 'SYNTHETIC_SECRET_KEY'not in json.dumps(first)and first['expires_at']>first['checked_at']
 app.state.model_connection_monitor.saved['time']-=31
 expect(student.get('/api/ai/connection'));assert len(calls)==2

def test_unreachable_and_missing_model_are_real_error_not_stale_success(app,teacher):
 configured(app);app.state.tutor.transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'data':[{'id':'fixture-model'}]}));assert expect(teacher.get('/api/ai/connection'))['status']=='connected'
 configured(app,'different-model');assert expect(teacher.get('/api/ai/connection'))['status']=='error'
 configured(app)
 def fail(request):raise httpx.ConnectError('SYNTHETIC_SECRET_KEY should not appear',request=request)
 app.state.tutor.transport=httpx.MockTransport(fail);result=expect(teacher.get('/api/ai/connection'));assert result['status']=='error'and 'SYNTHETIC_SECRET_KEY'not in json.dumps(result)

def test_changed_settings_discard_inflight_old_result(app,teacher):
 configured(app)
 def changed(request):
  configured(app,'new-model');return httpx.Response(200,json={'data':[{'id':'fixture-model'}]})
 app.state.tutor.transport=httpx.MockTransport(changed);result=expect(teacher.get('/api/ai/connection'));assert result['status']=='checking'and result['model']=='new-model'
 assert app.state.model_connection_monitor.saved is None

def test_router_health_exposes_capacity_not_generation_proof(app,teacher,monkeypatch):
 monkeypatch.setenv('AICADEMIYA_AI_PROVIDER','aicademiya-router');configured(app,'AIcademiya-64kx3-Qwen3.8-27B','http://127.0.0.1:18280/v1');calls=[]
 def health(request):calls.append(request.url.path);return httpx.Response(200,json={'model':'AIcademiya-64kx3-Qwen3.8-27B','teaching_capacity':2,'vision_teaching_capacity':0})
 app.state.tutor.transport=httpx.MockTransport(health);r=expect(teacher.get('/api/ai/connection'));assert calls==['/health']and r['status']=='connected'and r['teaching_capacity']==2 and r['vision_teaching_capacity']==0

def test_bad_health_object_does_not_throw_server_error(app,teacher):
 configured(app);app.state.tutor.transport=httpx.MockTransport(lambda r:httpx.Response(200,json=[]));assert expect(teacher.get('/api/ai/connection'))['status']=='error'
