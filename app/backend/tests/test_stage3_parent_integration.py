"""Parent integration regressions discovered when joining the returned UI/API."""
from .conftest import expect
from .test_stage3_guided import configure, start, turn, ProtocolFixture, use_fixture


def finish_one_question(teacher, student):
    vid = configure(teacher, phases=['worksheet', 'wrap_up'], count=1)
    start(student, vid)
    work = expect(turn(student, vid, 'A reason because evidence supports it.', 'answer-one'))
    assert work['tutor']['phase'] == 'wrap_up'
    work = expect(turn(student, vid, 'Finish this session.', 'finish-one'))
    assert work['tutor']['phase'] == 'complete'
    return vid, work


def test_completed_run_accepts_general_followup_without_new_work(teacher, student):
    vid, before = finish_one_question(teacher, student)
    after = expect(turn(student, vid, 'Why should evidence support an interpretation?', 'after-complete'))
    assert after['tutor']['phase'] == 'complete'
    assert after['attempts'] == before['attempts']
    assert len(after['messages']) == len(before['messages']) + 2
    assert after['submission']['status'] == 'in_progress'
    assert 'because evidence' in after['attempts']['q1']['answer']


def test_completed_run_can_clarify_and_revise_an_actual_previous_question(teacher, student, app):
    vid, before = finish_one_question(teacher, student)
    provider = ProtocolFixture()
    use_fixture(app, student, provider)
    provider.overrides.append({'schema_version':1,'text':'[Protocol fixture] Consider the meaning of the earlier concept.','intent':'ask','question_id':'q1','outcome':'unknown'})
    after = expect(turn(student, vid, 'Why does that earlier concept matter?', 'previous-followup'))
    assert after['attempts'] == before['attempts']
    assert after['tutor']['phase'] == 'complete'
    assert after['messages'][-1]['question_id'] == 'q1'
    provider.overrides.append({'schema_version':1,'text':'[Protocol fixture] The revised reasoning is enough to discuss.','intent':'answer','question_id':'q1','outcome':'sufficient'})
    after = expect(turn(student, vid, 'My revised response because there is clearer evidence.', 'previous-revision'))
    assert after['attempts']['q1']['answer'] == 'My revised response because there is clearer evidence.'
    assert after['tutor']['phase'] == 'complete'
    assert after['submission']['status'] == 'in_progress'


def test_completed_followup_remains_locked_after_explicit_submission(teacher, student):
    vid, before = finish_one_question(teacher, student)
    expect(student.post(f'/api/sessions/s4/submit?version_id={vid}',json={}))
    r=turn(student, vid, 'Why is evidence important?', 'after-submission')
    assert r.status_code in (403,409)
    work=expect(student.get(f'/api/sessions/s4/workspace?version_id={vid}'))
    assert work['submission']['status']=='submitted'
    assert work['messages']==before['messages']


def test_feedback_can_acknowledge_student_supplied_reference_term(teacher, student, app):
    expect(teacher.patch('/api/sessions/s4',json={'reference_answers':{'q1':'Reliability'}}))
    vid=configure(teacher,phases=['worksheet','wrap_up'],count=1)
    provider=ProtocolFixture();use_fixture(app,student,provider)
    start(student,vid)
    provider.overrides.append({'schema_version':1,'text':'You correctly named reliability and explained consistency.','intent':'answer','question_id':'q1','outcome':'sufficient'})
    work=expect(turn(student,vid,'Reliability, because measurements should be consistent.','own-term'))
    assert work['attempts']['q1']['reference_revealed'] is True
    assert work['tutor']['phase']=='wrap_up'


def test_premature_reference_failure_is_not_mislabeled_as_json_corruption(teacher, student, app):
    expect(teacher.patch('/api/sessions/s4',json={'reference_answers':{'q1':'Reliability'}}))
    vid=configure(teacher,phases=['worksheet','wrap_up'],count=1)
    provider=ProtocolFixture();use_fixture(app,student,provider)
    start(student,vid)
    provider.overrides.append({'schema_version':1,'text':'This points to reliability. Try again.','intent':'answer','question_id':'q1','outcome':'needs_retry'})
    response=turn(student,vid,'Validity, because the test measures its target.','early-key')
    assert response.status_code==502
    assert 'focused hint' in response.json()['detail']
    assert 'Reliability' not in response.json()['detail']
    work=expect(student.get(f'/api/sessions/s4/workspace?version_id={vid}'))
    assert 'q1' not in work['attempts']
    assert work['messages'][-1]['content']=='Validity, because the test measures its target.'


def test_premature_reference_gets_one_real_revision_without_changing_assessment(teacher, student, app):
    expect(teacher.patch('/api/sessions/s4',json={'reference_answers':{'q1':'Reliability'}}))
    vid=configure(teacher,phases=['worksheet','wrap_up'],count=1)
    provider=ProtocolFixture();use_fixture(app,student,provider)
    start(student,vid)
    provider.overrides.extend([
        {'schema_version':1,'text':'The answer is Reliability.','intent':'answer','question_id':'q1','outcome':'needs_retry'},
        {'schema_version':1,'text':'Focus on whether results stay stable when ability is unchanged. Which principle concerns that?'}
    ])
    before=len(provider.requests)
    work=expect(turn(student,vid,'Validity, because it measures the target.','revised-hint'))
    assert len(provider.requests)==before+2
    assert work['tutor']['current_question_id']=='q1'
    assert work['tutor']['question_states']['q1']['last_outcome']=='needs_retry'
    assert 'Reliability' not in work['messages'][-1]['content']
    assert not work['attempts']['q1']['reference_revealed']
    expect(turn(student,vid,'Validity, because it measures the target.','revised-hint'))
    assert len(provider.requests)==before+2


def test_partial_reading_response_does_not_advance_past_its_hint(teacher, student, app):
    vid=configure(teacher,phases=['worksheet','reading','wrap_up'],count=1)
    provider=ProtocolFixture();use_fixture(app,student,provider)
    start(student,vid)
    work=expect(turn(student,vid,'Supported required response.','required-before-reading'))
    qid=work['tutor']['current_question_id']
    assert qid.startswith('reading-')
    provider.overrides.append({'schema_version':1,'text':'Please connect that claim to the source evidence.','intent':'answer','question_id':qid,'outcome':'needs_retry'})
    work=expect(turn(student,vid,'An incomplete thought.','reading-partial'))
    assert work['tutor']['current_question_id']==qid
    assert work['tutor']['reading']['answered']==0
    work=expect(turn(student,vid,'A fuller response with source evidence.','reading-fuller'))
    assert work['tutor']['reading']['answered']==1
    assert work['tutor']['current_question_id']!=qid
    assert len(work['attempts'])==1
