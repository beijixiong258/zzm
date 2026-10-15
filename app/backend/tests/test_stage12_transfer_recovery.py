"""Regression for a completed result followed by the observed SSH shutdown failure."""
import json
import pytest
from .test_stage12_document_api import docenv,synthetic_bundle,upload,wait_job,endpoint
from .conftest import expect

def failed_transfer(docenv):
    app,teacher,student,processor=docenv;calls=[]
    def parse(source,root,cancelled):
        calls.append(str(root));synthetic_bundle(source,root)
        (root/'raw/ssh-job.json').write_text(json.dumps({'returncode':255,'bytes_received':1000}))
        (root/'raw/supervisor.json').write_text(json.dumps({'status':'complete','owned_processes_closed':True}))
        (root/'receipt.json').write_text(json.dumps({'status':'complete'}))
        raise RuntimeError('SYNTHETIC completed transfer then shutdown failure')
    app.state.document_queue.processor=parse
    material=expect(upload(teacher));job=wait_job(teacher,material['id']);assert job['status']=='failed'
    return material,job,calls

def test_explicit_retry_recovers_only_validated_complete_transfer_and_preserves_failed_attempt(docenv):
    app,teacher,_,processor=docenv;m,old,calls=failed_transfer(docenv)
    def forbidden(*args):raise AssertionError('Complete valid result should not be parsed again')
    app.state.document_queue.processor=forbidden
    job=expect(teacher.post(endpoint(m['id'])+'/jobs',json={'request_id':'explicit-retry','expected_revision':None}));new=wait_job(teacher,m['id'],job['id'])
    assert new['status']=='completed'and len(calls)==1
    assert expect(teacher.get(endpoint(m['id'])+'/jobs/'+old['id']))['status']=='failed'
    root=app.state.document_queue.uploads/'documents'/new['id'];audit=json.loads((root/'raw/recovery.json').read_text())
    assert audit['source_job_id']==old['id']and audit['retry_job_id']==new['id']and audit['model_rerun']is False
    assert expect(teacher.get(endpoint(m['id'])))['document']['revision_id']==new['revision_id']

@pytest.mark.parametrize('bad',['missing-file','source-hash','partial-receipt','not-transport'])
def test_invalid_old_output_does_not_skip_new_processor(docenv,bad):
    app,teacher,_,processor=docenv;m,old,calls=failed_transfer(docenv);root=app.state.document_queue.uploads/'documents'/old['id']
    if bad=='missing-file':(root/'pages/p1.png').rename(root/'pages/retained-missing.png')
    elif bad=='source-hash':
        p=root/'manifest.json';d=json.loads(p.read_text());d['source_sha256']='f'*64;p.write_text(json.dumps(d))
    elif bad=='partial-receipt':(root/'receipt.json').write_text(json.dumps({'status':'failed'}))
    else:(root/'raw/ssh-job.json').write_text(json.dumps({'returncode':0,'bytes_received':1000}))
    app.state.document_queue.processor=processor
    job=expect(teacher.post(endpoint(m['id'])+'/jobs',json={'request_id':'real-retry','expected_revision':None}));new=wait_job(teacher,m['id'],job['id'])
    assert new['status']=='completed'and len(processor.calls)==1
    assert not(app.state.document_queue.uploads/'documents'/new['id']/'raw/recovery.json').exists()

def test_recovery_does_not_bypass_current_staff_permission(docenv):
    app,teacher,_,_=docenv;m,_,_=failed_transfer(docenv)
    with app.state.database.connect()as conn:conn.execute("DELETE FROM course_staff WHERE user_id='demo-teacher'")
    assert teacher.post(endpoint(m['id'])+'/jobs',json={'request_id':'denied-retry','expected_revision':None}).status_code==403
    with app.state.database.connect()as conn:assert conn.execute('SELECT count(*) FROM document_jobs').fetchone()[0]==1
