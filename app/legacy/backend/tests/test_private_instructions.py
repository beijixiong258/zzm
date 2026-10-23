"""Teacher instructions may themselves contain keys; keep them server-side."""
import json
import httpx
from .conftest import expect, admin_request, publish


def test_private_teaching_instructions_are_not_in_student_payloads(teacher,student):
    private='PRIVATE_TEACHER_INSTRUCTIONS_WITH_EMBEDDED_KEY: synthetic-key-only'
    expect(teacher.patch('/api/sessions/s4',json={'instructions':private}))
    publish(teacher)
    assert expect(teacher.get('/api/sessions/s4'))['instructions']==private
    for endpoint in ['/api/sessions/s4','/api/sessions/s4/workspace','/api/sessions/s4/export']:
        response=student.get(endpoint);expect(response)
        assert private not in response.text
        detail=response.json().get('session',response.json())
        assert detail['instructions']==''


def test_model_still_receives_private_teaching_instructions(app,teacher,student):
    private='PRIVATE_TEACHER_INSTRUCTION_FOR_CURRENT_LESSON'
    expect(teacher.patch('/api/sessions/s4',json={'instructions':private}))
    publish(teacher)
    captured=[]
    def model(request):
        payload=json.loads(request.content)
        captured.append(json.loads(payload['messages'][0]['content'].split('\n',1)[1]))
        return httpx.Response(200,json={'choices':[{'message':{'content':'Synthetic protocol feedback, not real model output.'}}]})
    app.state.tutor.transport=httpx.MockTransport(model)
    expect(admin_request(teacher, "PUT", '/api/teacher/settings',json={'mode':'openai','base_url':'http://localhost/v1','model':'synthetic-protocol-model','api_key':''}))
    response=student.post('/api/sessions/s4/chat',json={'message':'A synthetic answer','question_id':'q1','intent':'answer'})
    expect(response)
    assert captured[0]['teaching_instructions']==private
    assert private not in response.text
