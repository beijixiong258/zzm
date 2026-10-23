"""Parent integration regressions found using the real built UI and API."""
import json
from .conftest import expect, publish
from .test_stage2_authoring import public_link_fixture, editable_question


def test_clearing_a_saved_authored_link_has_no_hidden_material_selection(teacher, public_link_fixture):
    q=editable_question(teacher)
    q['source_links']=['https://example.org/roundtrip']
    saved=expect(teacher.patch('/api/sessions/s4',json={'questions':[q]}))
    mid=next(m['id'] for m in saved['materials'] if m['kind']=='link')
    # Use the exact readback, as the real UI does, not the original unsaved request.
    q=saved['questions'][0]
    assert q['source_material_ids']==[]
    q['source_links']=['   ']
    cleared=expect(teacher.patch('/api/sessions/s4',json={'questions':[q]}))
    assert cleared['questions'][0]['source_material_ids']==[]
    assert cleared['questions'][0]['source_links']==[]
    assert all(m['id']!=mid for m in cleared['materials'])


def test_explicitly_selected_link_is_distinct_from_authored_link(teacher, public_link_fixture):
    link=expect(teacher.post('/api/sessions/s4/materials/link',json={'url':'https://example.org/manual-checked','visibility':'student'}))
    q=editable_question(teacher);q.update(source_material_ids=[link['id']],source_links=[link['url']])
    q=expect(teacher.patch('/api/sessions/s4',json={'questions':[q]}))['questions'][0]
    q['source_links']=[]
    updated=expect(teacher.patch('/api/sessions/s4',json={'questions':[q]}))
    assert updated['questions'][0]['source_material_ids']==[link['id']]
    assert any(m['id']==link['id'] for m in updated['materials'])
    expect(teacher.delete('/api/sessions/s4/materials/'+link['id']),409)


def test_editing_link_url_updates_authored_reference_without_mutating_old_version(teacher, public_link_fixture):
    q=editable_question(teacher);q['source_links']=['https://example.org/old-authored']
    saved=expect(teacher.patch('/api/sessions/s4',json={'questions':[q]}))
    mid=next(m['id'] for m in saved['materials'] if m['kind']=='link')
    v=publish(teacher)['id']
    expect(teacher.patch('/api/sessions/s4/materials/'+mid,json={'url':'https://example.org/new-authored'}))
    current=expect(teacher.get('/api/sessions/s4'))
    assert current['questions'][0]['source_material_ids']==[]
    assert current['questions'][0]['source_links']==['https://example.org/new-authored']
    historical=expect(teacher.get('/api/teacher/courses/synthetic-course/versions/'+v))
    old=next(s for s in historical['sessions'] if s['id']=='s4')
    assert old['questions'][0]['source_links']==['https://example.org/old-authored']


def test_added_material_diff_contains_structured_metadata_not_private_storage_paths(teacher):
    v=publish(teacher)['id']
    expect(teacher.post('/api/sessions/s4/materials',files={'file':('new-diff.txt',b'Synthetic readable diff source.','text/plain')}))
    changes=expect(teacher.get('/api/teacher/courses/synthetic-course/versions/'+v+'/diff'))['changes']
    serialized=json.dumps(changes)
    assert 'new-diff.txt' in serialized
    assert 'file_path' not in serialized and 'assets_dir' not in serialized
    assert 'content_json' not in serialized
