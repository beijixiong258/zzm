"""Managed full-preview synchronous mutations must carry the current generation."""
import pytest
from .conftest import expect
from .test_stage6_preview import reset
from .test_stage3_guided import configure


def test_full_preview_can_save_submit_and_reveal_with_current_identity(teacher, student):
    configure(teacher, phases=["worksheet", "wrap_up"], count=1)
    expect(teacher.patch('/api/sessions/s4', json={'reference_policy':'after_submit'}))
    student_before=expect(student.get('/api/sessions/s4/workspace'))
    pid=reset(teacher)['preview']['id']
    base='/api/sessions/s4/'
    expect(teacher.post(base+'answers/q1',json={'answer':'Queued without identity'}),409)
    saved=expect(teacher.post(base+'answers/q1?preview_id='+pid,json={'answer':'A saved preview response because evidence.'}))
    assert saved['attempts']['q1']['answer']=='A saved preview response because evidence.'
    expect(teacher.post(base+'references/q1?preview_id='+pid,json={}),409)
    submitted=expect(teacher.post(base+'submit?preview_id='+pid,json={}))
    assert submitted['submission']['status']=='submitted'
    assert expect(teacher.post(base+'references/q1?preview_id='+pid,json={}))['reference']
    expect(teacher.post(base+'answers/q1?preview_id='+pid,json={'answer':'Editing after submit'}),409)
    assert expect(student.get('/api/sessions/s4/workspace'))==student_before


def test_full_preview_can_select_reading_with_current_identity(teacher):
    pid=reset(teacher,'s2')['preview']['id']
    work=expect(teacher.post('/api/sessions/s2/reading?preview_id='+pid,json={'group_id':'II-Pong'}))
    assert work['selected_reading']=='II-Pong'


@pytest.mark.parametrize('operation,body,sid',[
    ('answers/q1',{'answer':'Queued old answer'},'s4'),
    ('reading',{'group_id':'II-Pong'},'s2'),
    ('references/q1',{},'s4'),('submit',{},'s4'),
])
def test_old_or_missing_full_preview_identity_cannot_mutate_reset_run(teacher,operation,body,sid):
    old=reset(teacher,sid)['preview']['id']
    fresh=reset(teacher,sid)
    before=expect(teacher.get(f'/api/sessions/{sid}/workspace'))
    for suffix in ('','?preview_id='+old):
        expect(teacher.post(f'/api/sessions/{sid}/{operation}'+suffix,json=body),409)
    after=expect(teacher.get(f'/api/sessions/{sid}/workspace'))
    assert after==before and after['preview']['id']==fresh['preview']['id']


@pytest.mark.parametrize('operation,body,sid',[
    ('answers/q1',{'answer':'Saved against stale teaching'},'s4'),
    ('reading',{'group_id':'II-Pong'},'s2'),
    ('references/q1',{},'s4'),('submit',{},'s4'),
])
def test_full_preview_sync_mutation_rejects_changed_saved_revision(teacher,operation,body,sid):
    pid=reset(teacher,sid)['preview']['id']
    expect(teacher.patch(f'/api/sessions/{sid}',json={'instructions':'Meaningfully changed saved instructions.'}))
    expect(teacher.post(f'/api/sessions/{sid}/{operation}?preview_id='+pid,json=body),409)
    assert expect(teacher.get(f'/api/sessions/{sid}/workspace'))['preview']['stale']


def test_managed_legacy_chat_stays_unavailable_even_with_query_identity(teacher):
    pid=reset(teacher)['preview']['id']
    expect(teacher.post('/api/sessions/s4/chat?preview_id='+pid,json={'message':'Old endpoint','intent':'ask','request_id':'legacy'}),409)
