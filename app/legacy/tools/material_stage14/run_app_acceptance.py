"""Actual isolated CT app -> installed restricted worker -> real teaching model.
Synthetic TXT/PPTX and accounts; no processor/provider fixtures. Keeps a bounded
QA service only after API success so the parent can exercise the real browser.
"""
from pathlib import Path
import argparse,hashlib,json,time
import httpx
from prepare_app_acceptance import guest


def main():
    p=argparse.ArgumentParser();p.add_argument('--meta',required=True);a=p.parse_args();meta=json.loads(Path(a.meta).read_text());out=Path(meta['artifact_dir']);result=out/'api-result.json'
    report=json.loads(result.read_text())if result.exists()else {'status':'running','scope':'Synthetic source/accounts; actual HTTP, installed restricted worker and real model','ids':{},'checks':[],'turns':[]}
    report['status']='running';report.pop('error',None);report.pop('error_type',None)
    def save():result.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    def check(text):
        if text not in report['checks']:report['checks'].append(text)
        save();print(json.dumps({'check':text}),flush=True)
    def remote(code):return json.loads(guest([meta['interpreter'],'-c',code]))
    def model_calls():return remote("from pathlib import Path;import json;p=Path("+repr(meta['qa']+'/model-exchanges.jsonl')+");print(json.dumps(len(p.read_text().splitlines())if p.exists()else 0))")
    def call(c,method,url,body=None,**kwargs):
        r=c.request(method,url,**({'json':body}if body is not None else{}),**kwargs)
        if r.status_code!=200:raise RuntimeError(f'{method} {url}: {r.status_code} {r.text[:1200]}')
        return r.json()
    try:
        if guest(['systemctl','show',meta['unit'],'--property=ActiveState','--value']).strip()!='active':guest(meta['start_command'])
        deadline=time.monotonic()+40
        with httpx.Client(base_url=meta['base_url'],trust_env=False,timeout=650)as teacher,httpx.Client(base_url=meta['base_url'],trust_env=False,timeout=650)as student:
            while True:
                try:
                    boot=teacher.get('/api/bootstrap',timeout=2)
                    if boot.status_code==200:break
                except httpx.RequestError:pass
                if time.monotonic()>deadline:raise RuntimeError('QA app readiness failed')
                time.sleep(.25)
            assert boot.json()['demo_enabled'] and boot.json()['ai']['mode']=='openai'
            assert guest(['readlink','-f','/opt/aicademiya/current']).strip()==meta['production_release']
            call(teacher,'POST','/api/auth/demo',{'role':'teacher'});call(student,'POST','/api/auth/demo',{'role':'student'})
            assert call(teacher,'GET','/api/document-processing')['available'];check('Isolated current app and explicit real provider ready; production link unchanged')
            summaries={}
            for kind,name,digest in [('txt','source-ledger.txt',meta['txt_sha256']),('pptx','source-notes.pptx',meta['pptx_sha256'])]:
                mid=report['ids'].get(kind)
                if not mid:
                    with(out/'fixture'/name).open('rb')as f:item=call(teacher,'POST','/api/sessions/s12-session/materials',files={'file':(name,f,'application/octet-stream')},data={'processing':'full_document','kind':'reading','visibility':'student'})
                    mid=item['id'];report['ids'][kind]=mid;report['ids'][kind+'_download']=item['download_url'];save()
                ep='/api/materials/'+mid+'/document';deadline=time.monotonic()+1250
                while True:
                    summary=call(teacher,'GET',ep);job=summary['latest_job'];(out/(kind+'-job.json')).write_text(json.dumps(job,indent=2))
                    if job and job['status']=='failed':raise RuntimeError('Actual '+kind+' processing failed: '+str(job))
                    if job and job['status']=='completed':break
                    if time.monotonic()>deadline:raise TimeoutError(kind+' worker deadline')
                    time.sleep(2)
                doc=summary['document'];assert doc['source_sha256']==digest and doc['source_format']==kind
                download=teacher.get(report['ids'][kind+'_download']);assert download.status_code==200 and hashlib.sha256(download.content).hexdigest()==digest
                root=meta['data']+'/uploads/documents/'+job['id']
                evidence=remote("from pathlib import Path;import json;p=Path("+repr(root)+");print(json.dumps({n:json.loads((p/n).read_text())for n in ['manifest.json','receipt.json','raw/supervisor.json','raw/ssh-job.json']}))")
                assert evidence['raw/supervisor.json']['status']=='complete' and evidence['raw/supervisor.json']['owned_processes_closed']
                assert evidence['raw/ssh-job.json']['returncode']==0
                (out/(kind+'-actual-worker.json')).write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
                if kind=='txt':
                    assert not evidence['raw/supervisor.json']['gpu_lease_used']
                    literal=''.join(b['text']for page in evidence['manifest.json']['pages']for b in page['blocks'])
                    assert literal==(out/'fixture'/name).read_bytes().decode()
                summaries[kind]=summary;check('Actual '+kind+' upload, restricted worker, original identity and application commit passed')
            txtid=report['ids']['txt'];pptid=report['ids']['pptx'];ep='/api/materials/'+pptid+'/document'
            if not report['ids'].get('version_before_share'):
                notes=summaries['pptx']['supplements'];note=next(n for n in notes if n['kind']=='speaker_notes');rid=summaries['pptx']['document']['revision_id']
                note_path=ep+'/supplements/'+note['id']+'/text';actual=teacher.get(note_path,params={'revision_id':rid});assert actual.status_code==200 and meta['note']in actual.text
                report['ids'].update(note=note['id'],note_path=note_path,note_original_revision=rid);save()
                detail=call(teacher,'GET','/api/sessions/s12-session');questions=detail['questions']
                for q in questions:q['source_material_ids']=[txtid];q['source_links']=[]
                call(teacher,'PATCH','/api/sessions/s12-session',{'questions':questions,'teaching_profile':{**detail['teaching_profile'],'phases':['worksheet','wrap_up']}})
                version=call(teacher,'POST','/api/teacher/courses/s12-course/versions/publish',{'label':'Synthetic notes hidden by default'})
                report['ids']['version_before_share']=version['id'];save()
            old=report['ids']['version_before_share'];rid=report['ids']['note_original_revision'];note_path=report['ids']['note_path']
            if not report['ids'].get('version_shared'):
                assert call(student,'GET',ep,params={'version_id':old})['supplements']==[]
                assert student.get(note_path,params={'version_id':old,'revision_id':rid}).status_code==404
            else:
                denied=student.get(note_path,params={'version_id':old,'revision_id':rid})
                assert denied.status_code==403 and denied.json()['detail']=='Only your existing learning history is available'
            check('Actual original PPTX notes excluded from student AI/source-note projection in old edition')
            if not report['ids'].get('version_shared'):
                payload={'request_id':'explicit-source-note-share','expected_revision':rid,'visible_to_students':True,'reason':'Synthetic QA explicit sharing; original Office remains unredacted'}
                receipt=call(teacher,'POST',ep+'/supplements/sharing',payload)
                assert call(teacher,'GET',ep+'/reviews/explicit-source-note-share')==receipt
                current=call(teacher,'GET',ep);assert current['document']['revision_id']==receipt['document']['revision_id']
                version=call(teacher,'POST','/api/teacher/courses/s12-course/versions/publish',{'label':'Synthetic explicit shared source notes'})
                report['ids'].update(version_shared=version['id'],note_shared_revision=current['document']['revision_id']);save()
            vid=report['ids']['version_shared'];shared=student.get(note_path,params={'version_id':vid,'revision_id':report['ids']['note_shared_revision']});assert shared.status_code==200 and meta['note']in shared.text
            denied=student.get(note_path,params={'version_id':old,'revision_id':rid})
            assert denied.status_code==403 and denied.json()['detail']=='Only your existing learning history is available'
            check('Explicit note sharing read back; new publication visible, unsaved old edition correctly denies history access')
            if not report['ids'].get('learning_version'):
                call(student,'POST','/api/sessions/s12-session/tutor/start',{'request_id':'history-probe-start'},params={'version_id':vid})
                current=call(teacher,'GET',ep)
                hidden=call(teacher,'POST',ep+'/supplements/sharing',{'request_id':'hide-note-with-real-history','expected_revision':current['document']['revision_id'],'visible_to_students':False,'reason':'Synthetic QA: hide draft notes while preserving the prior explicitly shared historical edition'})
                assert call(teacher,'GET',ep+'/reviews/hide-note-with-real-history')==hidden
                newversion=call(teacher,'POST','/api/teacher/courses/s12-course/versions/publish',{'label':'Synthetic hidden notes with real prior learning history'})
                report['ids'].update(learning_version=newversion['id'],note_hidden_revision=hidden['document']['revision_id']);save()
            historical=student.get(note_path,params={'version_id':vid,'revision_id':report['ids']['note_shared_revision']})
            assert historical.status_code==200 and meta['note']in historical.text
            vid=report['ids']['learning_version']
            assert student.get(note_path,params={'version_id':vid,'revision_id':report['ids']['note_hidden_revision']}).status_code==404
            check('Genuine saved historical edition retains explicitly shared notes; newly hidden edition denies them')
            if not report.get('reading_complete'):
                call(student,'POST','/api/sessions/s12-session/tutor/start',{'request_id':'sequential-start'},params={'version_id':vid})
                previous=report['turns'][-1]['coverage']['read_characters']if report['turns']else 0
                for index in range(len(report['turns']),8):
                    message=('Read the entire source-ledger.txt material in source order using sequential reading, starting at the beginning. 'if index==0 else 'Continue reading the next unread portion of source-ledger.txt in source order using the saved sequential cursor. ')+ 'Quote one exact line from the current chunk. Do not grade my work or skip to a keyword search.'
                    body={'request_id':'sequential-read-'+str(index),'message':message};url='/api/sessions/s12-session/tutor/turn';work=call(student,'POST',url,body,params={'version_id':vid});last=work['messages'][-1]
                    coverage=next(c for c in last.get('metadata',{}).get('document_read_coverage',[])if c['material_id']==txtid)
                    assert coverage['read_characters']>previous,'Real planner did not advance sequential reading'
                    assert work['attempts']=={} and work['progress']['answered']==0
                    citations=[c for c in last.get('citations',[])if c.get('kind')=='document'];assert citations
                    for c in citations:
                        assert c['material_id']==txtid and c['version_id']==vid
                        response=student.get(c['url'].split('#')[0]);assert response.status_code==200 and response.headers['content-type'].startswith('application/pdf')
                    calls=model_calls();repeated=call(student,'POST',url,body,params={'version_id':vid});assert model_calls()==calls and repeated['messages'][-1]==last
                    report['turns'].append({'request_id':body['request_id'],'coverage':coverage,'message':last});previous=coverage['read_characters'];save()
                    check('Real sequential source turn '+str(index+1)+' accepted once with exact scoped citations')
                    if coverage['eligible_text_complete']:
                        assert coverage['read_characters']==coverage['available_characters']==meta['txt_characters'];assert coverage['all_stored_regions_read'];report['reading_complete']=True;save();break
                assert report.get('reading_complete'),'Bounded live reading did not reach end of source'
            if not report.get('closing_answer'):
                work=call(student,'POST','/api/sessions/s12-session/tutor/turn',{'request_id':'read-closing-record','message':'Quote the exact Closing record sentence at the very end of source-ledger.txt. Do not infer or correct it.'},params={'version_id':vid});last=work['messages'][-1]
                # The request asks for the sentence, not its "Closing record:" label.
                sentence=meta['closing_line'].partition(': ')[2]
                assert sentence in last['content'],last['content']
                matches=[c for c in last.get('citations',[])if c.get('kind')=='document'and c.get('quote')in (sentence,meta['closing_line'])]
                assert matches and all(c['material_id']==txtid and c['version_id']==vid and c['page']==summaries['txt']['document']['page_count']for c in matches)
                for c in matches:assert student.get(c['url'].split('#')[0]).status_code==200
                report['closing_answer']=last;check('Actual model quoted the unknown-to-request final source sentence after the initial window')
            report['real_model_calls']=model_calls();report['status']='api_passed_browser_restart_restore_pending';report['qa_service_retained_for_parent_browser']=True;save()
            print(json.dumps({'status':report['status'],'result':str(result),'base_url':meta['base_url'],'model_calls':report['real_model_calls']}),flush=True)
    except BaseException as e:
        report.update(status='failed',error_type=type(e).__name__,error=str(e));save()
        guest(['systemctl','stop',meta['unit']]);(out/'server.log').write_text(guest(['journalctl','-u',meta['unit'],'--no-pager','-n','160']),encoding='utf-8')
        raise
if __name__=='__main__':main()
