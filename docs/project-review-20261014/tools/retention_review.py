"""Reproduce cross-role retention using isolated synthetic data."""
from pathlib import Path
from datetime import datetime, timezone
import json,uuid
from backend.aicademiya.db import Database
from backend.aicademiya.services import ensure_workspace,save_message
from backend.aicademiya.course_staff import establish_assignment,assigned
from backend.aicademiya.global_accounts import change_role
from backend.aicademiya.version_context import session_access
from backend.aicademiya.teacher_preview import saved_revision
from backend.aicademiya.roster import maintenance
ROOT=Path('D:/HermesProjects/EDUC7703');OUT=ROOT/'docs/project-review-20261014/evidence'
SCRATCH=Path('C:/Users/17193/AppData/Local/hermes/cache/scratch')/('aicademiya-retention-review-'+uuid.uuid4().hex[:10]);SCRATCH.mkdir()
catalog={'schema_version':1,'course':{'id':'review-course','code':'SYNTHETIC','title':'Synthetic review','description':''},'sessions':[{'id':'review-session','course_id':'review-course','number':1,'title':'Synthetic session','subtitle':'','status':'published','estimated_minutes':10,'learning_objectives':[],'instructions':'','reference_policy':'after_attempt','teaching_language':'en','groups':[],'questions':[],'reference_answers':{},'materials':[]}]}
(SCRATCH/'catalog.json').write_text(json.dumps(catalog),encoding='utf-8');db=Database(SCRATCH/'data/aicademiya.sqlite3');db.initialize(SCRATCH/'catalog.json',demo_enabled=False)
with db.connect()as c:
    c.execute('BEGIN IMMEDIATE')
    c.execute("INSERT INTO users(id,name,email,role) VALUES('review-admin','Synthetic Admin','review-admin@example.invalid','admin')")
    c.execute("INSERT INTO users(id,name,email,role) VALUES('review-learner','Synthetic Learner','review-learner@example.invalid','student')")
    c.execute("INSERT INTO enrollments(course_id,user_id,archived_at,purge_at) VALUES('review-course','review-learner','2000-01-01T00:00:00+00:00','2000-02-01T00:00:00+00:00')")
    actor={'id':'review-admin','role':'admin'}
    change_role(c,actor,'review-learner','teacher',demo_enabled=False)
    establish_assignment(c,'review-course','review-learner')
    teacher={'id':'review-learner','role':'teacher'};detail=session_access(c,'review-session',teacher)
    ensure_workspace(c,'review-session','review-learner','')
    save_message(c,'review-session','review-learner','user','Synthetic new teacher preview',None,'demo',version_id='')
    revision=saved_revision(c,detail)
    c.execute("INSERT INTO teacher_previews VALUES('review-session','review-learner','review-preview',?,'2026-10-14T00:00:00+00:00')",(revision,))
    def count(table):return c.execute('SELECT count(*) FROM '+table+" WHERE user_id='review-learner'").fetchone()[0]
    before={'workspace':count('workspaces'),'messages':count('messages'),'preview_binding':count('teacher_previews'),'staff_assigned':assigned(c,'review-course','review-learner')}
    result=maintenance(c,at=datetime(2026,10,14,tzinfo=timezone.utc))
    after={'workspace':count('workspaces'),'messages':count('messages'),'preview_binding':count('teacher_previews'),'staff_assigned':assigned(c,'review-course','review-learner'),'account_role':c.execute("SELECT role FROM users WHERE id='review-learner'").fetchone()[0]}
    assert before['workspace']==before['messages']==1 and after['workspace']==after['messages']==0
    assert after['preview_binding']==1 and after['staff_assigned']and after['account_role']=='teacher'
proof={'status':'reproduced','method':'Current role-change, staff assignment, access and maintenance helpers over a fresh synthetic database','before':before,'after':after,'maintenance':result,'production_writes':False,'model_calls':0,'scratch':str(SCRATCH)}
(OUT/'retention-role-reproduction.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(proof,ensure_ascii=False,indent=2))
