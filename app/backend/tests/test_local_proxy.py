"""Regression for observed Windows system-proxy routing of loopback model calls."""
import httpx
import pytest
from backend.aicademiya import ai


@pytest.mark.parametrize('url,expected',[
    ('http://127.0.0.1:1234/v1',False),
    ('http://localhost:1234/v1',False),
    ('http://[::1]:1234/v1',False),
    ('http://192.168.5.108:1234/v1',False),
    ('http://host.docker.internal:1234/v1',False),
    ('https://api.example.invalid/v1',True),
])
def test_local_model_connections_bypass_system_proxy(url,expected):
    assert ai.use_environment_proxy(url) is expected


def test_proxy_decision_is_used_by_actual_adapter(monkeypatch):
    real_client=httpx.Client
    flags=[]
    def client(**kwargs):
        flags.append(kwargs['trust_env'])
        return real_client(**kwargs)
    monkeypatch.setattr(ai.httpx,'Client',client)
    transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'choices':[{'message':{'content':'Synthetic protocol response'}}]}))
    tutor=ai.Tutor(None,transport=transport)
    for url in ['http://127.0.0.1:1234/v1','https://api.example.invalid/v1']:
        result=tutor.complete({'base_url':url,'model':'synthetic-test','api_key':''},[{'role':'user','content':'Synthetic request'}])
        assert result=='Synthetic protocol response'
    assert flags==[False,True]
