"""Restart and relocate ONLY the isolated Stage14 QA data; no model requests."""
from pathlib import Path
import argparse,json,hashlib,time
import httpx
from prepare_app_acceptance import guest

def main():
    p=argparse.ArgumentParser();p.add_argument('--meta',required=True);a=p.parse_args();meta=json.loads(Path(a.meta).read_text());out=Path(meta['artifact_dir']);prior=json.loads((out/'api-result.json').read_text());browser=json.loads((out/'browser-current/result.json').read_text());assert prior['status'].startswith('api_passed')and browser['status']=='passed'
    assert meta['qa'].startswith('/var/lib/aicademiya-qa/stage14-app-')and meta['data']==meta['qa']+'/data'
    ids=prior['ids'];report={'status':'running','checks':[],'production_changed':False,'real_model_calls_by_this_check':0}
    def save():(out/'persistence-result.json').write_text(json.dumps(report,indent=2)+'\n')
    def check(s):report['checks'].append(s);save();print(json.dumps({'check':s}),flush=True)
    def remote(code):return json.loads(guest([meta['interpreter'],'-c',code]))
    def calls():return remote("from pathlib import Path;import json;p=Path("+repr(meta['qa']+'/model-exchanges.jsonl')+");print(json.dumps(len(p.read_text().splitlines())))")
    def stop_qa():
        if guest(['systemctl','show',meta['unit'],'--property=ActiveState','--value']).strip()in ('active','activating','reloading'):
            guest(['systemctl','stop',meta['unit']])
    def ready():
        until=time.monotonic()+40
        while time.monotonic()<until:
            try:
                if httpx.get(meta['base_url']+'/api/health',trust_env=False,timeout=2).status_code==200:return
            except httpx.RequestError:pass
            time.sleep(.25)
        raise RuntimeError('QA restart not ready')
    def verify():
        with httpx.Client(base_url=meta['base_url'],trust_env=False,timeout=20)as t,httpx.Client(base_url=meta['base_url'],trust_env=False,timeout=20)as s:
            t.post('/api/auth/demo',json={'role':'teacher'}).raise_for_status();s.post('/api/auth/demo',json={'role':'student'}).raise_for_status()
            for kind,key in [('txt','txt_sha256'),('pptx','pptx_sha256')]:
                r=s.get('/api/materials/'+ids[kind]+'/download',params={'version_id':ids['learning_version']});r.raise_for_status();assert hashlib.sha256(r.content).hexdigest()==meta[key]
            assert s.get(ids['note_path'],params={'version_id':ids['learning_version'],'revision_id':ids['note_hidden_revision']}).status_code==404
            old=s.get(ids['note_path'],params={'version_id':ids['version_shared'],'revision_id':ids['note_shared_revision']});old.raise_for_status();assert meta['note']in old.text
            draft=t.get('/api/materials/'+ids['pptx']+'/document');draft.raise_for_status();assert draft.json()['document']['revision_id']==browser['draft_sharing']['after']
            work=s.get('/api/sessions/s12-session/workspace',params={'version_id':ids['learning_version']});work.raise_for_status();w=work.json();assert w['attempts']=={} and w['progress']['answered']==0
            message=next(m for m in w['messages']if m['id']==prior['closing_answer']['id']);assert message==prior['closing_answer']
            for citation in message['citations']:
                if citation.get('kind')=='document':
                    r=s.get(citation['url'].split('#')[0]);r.raise_for_status();assert r.headers['content-type'].startswith('application/pdf')
    initial_calls=calls()
    try:
        if guest(['systemctl','show',meta['unit'],'--property=ActiveState','--value']).strip()=='active':guest(['systemctl','restart',meta['unit']])
        else:guest(meta['start_command'])
        ready();verify();check('Restart preserves originals, private/current versus shared historical notes, draft revision and genuine model citations')
        stop_qa();backup=meta['qa']+'/backup-r2';restored=meta['qa']+'/restored-r2'
        report['backup']=json.loads(guest(['runuser','-u','aicademiya','--',meta['interpreter'],meta['source']+'/tools/backup_data.py','backup','--data-dir',meta['data'],'--materials-root',meta['qa'],'--destination',backup],timeout=90))
        report['restore']=json.loads(guest(['runuser','-u','aicademiya','--',meta['interpreter'],meta['source']+'/tools/backup_data.py','restore','--source',backup,'--destination',restored],timeout=90))
        assert report['restore']['records_match']and report['restore']['files_match']
        guest(['python3','-c',"from pathlib import Path;p=Path("+repr(meta['data'])+");q=p.with_name(p.name+'-retained');assert not q.exists();p.rename(q);assert not p.exists()"])
        restored_meta={**meta,'data':restored,'environment':{**meta['environment'],'AICADEMIYA_DATA_DIR':restored},'start_command':[('--setenv=AICADEMIYA_DATA_DIR='+restored)if x.startswith('--setenv=AICADEMIYA_DATA_DIR=')else x for x in meta['start_command']],'restored_data':True}
        (out/'meta-restored.json').write_text(json.dumps(restored_meta,indent=2)+'\n');guest(restored_meta['start_command']);ready();verify()
        code="from pathlib import Path;import sqlite3,json;r=Path("+repr(restored)+");c=sqlite3.connect('file:'+str(r/'aicademiya.sqlite3')+'?mode=ro',uri=True);ids="+repr([ids['txt'],ids['pptx']])+";paths=[row[0]for row in c.execute('select file_path from materials where id in (?,?)',ids)];assert all(Path(p).is_relative_to(r)and Path(p).is_file()for p in paths);states=[json.loads(x[0])for x in c.execute('select state_json from tutor_runs')];progress=[s.get('document_read_progress',{}).get("+repr(ids['txt'])+",{})for s in states];assert any(p.get('read_characters')=="+repr(meta['txt_characters'])+" for p in progress);print(json.dumps({'integrity':c.execute('PRAGMA integrity_check').fetchone()[0],'foreign_key_violations':len(c.execute('PRAGMA foreign_key_check').fetchall()),'selected_original_paths_relocated':paths,'complete_read_cursor_retained':True,'old_upload_root_unavailable':not Path("+repr(meta['data'])+").exists()}))"
        report['database_readback']=remote(code);assert report['database_readback']['integrity']=='ok'and report['database_readback']['foreign_key_violations']==0
        check('Relocated copy serves both uploaded originals and edition-bound notes/citations with the old upload root unavailable')
        assert calls()==initial_calls;report['status']='passed';check('Restart/restore checks made no new model request; existing curriculum and learning rows retained')
    except BaseException as error:
        report.update(status='failed',error_type=type(error).__name__,error=str(error));raise
    finally:
        stop_qa();report['qa_service_active']=guest(['systemctl','show',meta['unit'],'--property=ActiveState','--value']).strip()=='active';report['production_link_unchanged']=guest(['readlink','-f','/opt/aicademiya/current']).strip()==meta['production_release'];report['production_service_active']=guest(['systemctl','show','aicademiya.service','--property=ActiveState','--value']).strip()=='active';save()
        assert not report['qa_service_active']and report['production_link_unchanged']and report['production_service_active']
        print(json.dumps({'status':report['status'],'result':str(out/'persistence-result.json'),'qa_closed':True}),flush=True)
if __name__=='__main__':main()
