"""Read-only final CT byte/state gate; data stays in files, not SSH argv."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib,json,sqlite3,subprocess
QA=Path('/var/lib/aicademiya-qa/stage15-exact-r3')
LIVE_QA=Path('/var/lib/aicademiya-qa/stage15-fresh-r1/source')
NEW=Path('/opt/aicademiya/releases/AIcademiya_V2-20261013-multimodal-r3')
OLD=Path('/opt/aicademiya/releases/AIcademiya_V2-20261011-documents')
CONF=Path('/etc/aicademiya/aicademiya.conf')
GATE=Path('/run/systemd/system/aicademiya.service.d/90-material-migration.conf')

def sha(p):
 with p.open('rb')as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def main():
 manifest=json.loads((QA/(NEW.name+'.manifest.json')).read_text());assert manifest['release']==NEW.name
 for name,record in manifest['files'].items():assert sha(NEW/name)==record['sha256'],name
 app_names=[n for n in manifest['files']if n.startswith(('backend/','frontend/dist/'))]
 for name in app_names:assert sha(LIVE_QA/name)==manifest['files'][name]['sha256'],name
 staged=json.loads((QA/'release-stage-result.json').read_text());assert staged['status']=='staged_not_promoted'and staged['actual_uid999_app_boot']
 rehearsal=json.loads((QA/'production-rehearsal.json').read_text());assert rehearsal['status']=='passed'and rehearsal['restore']['records_match']and rehearsal['restore']['files_match']
 assert Path('/opt/aicademiya/current').resolve()==OLD and sha(CONF)==rehearsal['config_sha256']and GATE.is_file()
 assert not Path('/var/backups/aicademiya-stage15-r3-cutover').exists()
 assert subprocess.check_output(['systemctl','is-active','aicademiya.service'],text=True).strip()=='active'
 with sqlite3.connect('file:/var/lib/aicademiya/aicademiya.sqlite3?mode=ro',uri=True)as db:
  statuses={t:db.execute('select status,count(*) from '+t+' group by status').fetchall()for t in ('chat_requests','tutor_requests','document_jobs')}
  assert all(status in ('done','failed')for t,rows in statuses.items()for status,count in rows),'Active or unknown work state; inspect before cutover'
  counts={t:db.execute('select count(*) from '+t).fetchone()[0]for t in ('users','courses','messages','attempts','document_jobs')}
  assert db.execute('pragma integrity_check').fetchone()[0]=='ok'and not db.execute('pragma foreign_key_check').fetchall()
 result={'status':'passed','checked_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),'release_files':len(manifest['files']),'exact_qa_app_files':len(app_names),'current_release':str(OLD),'candidate':str(NEW),'requests':statuses,'counts':counts,'read_only_production':True}
 (QA/'final-precheck-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
