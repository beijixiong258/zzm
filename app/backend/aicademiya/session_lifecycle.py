"""Reversible draft-session removal; no relational or learning record deletion."""
import json
from fastapi import Depends,HTTPException
from .db import now
from .services import summary
from .version_context import course_access

PREFIX='session_trash:'
def session_row(conn,sid,user):
 row=conn.execute('SELECT * FROM sessions WHERE id=?',(sid,)).fetchone()
 if row is None:raise HTTPException(404,'Session not found')
 course_access(conn,row['course_id'],user)
 return row

def register_session_lifecycle(app,db,teacher_user):
 @app.get('/api/courses/{course_id}/sessions/trash')
 def trashed(course_id:str,user=Depends(teacher_user)):
  with db.connect()as conn:
   course_access(conn,course_id,user);rows=[]
   for row in conn.execute('SELECT * FROM sessions WHERE course_id=? AND in_draft=0 ORDER BY rowid',(course_id,)):
    marker=conn.execute('SELECT value FROM meta WHERE key=?',(PREFIX+row['id'],)).fetchone()
    if marker:rows.append({**summary(json.loads(row['content_json'])),**json.loads(marker[0])})
   return {'sessions':rows}

 @app.delete('/api/sessions/{session_id}')
 def remove(session_id:str,user=Depends(teacher_user)):
  with db.connect()as conn:
   conn.execute('BEGIN IMMEDIATE');row=session_row(conn,session_id,user)
   marker=conn.execute('SELECT value FROM meta WHERE key=?',(PREFIX+session_id,)).fetchone()
   if not row['in_draft']:
    if marker:return {'id':session_id,'removed':True,**json.loads(marker[0])}
    raise HTTPException(404,'Session is not in the current draft')
   stamp={'removed_at':now(),'removed_by':user['id']}
   conn.execute('INSERT INTO meta(key,value)VALUES(?,?)ON CONFLICT(key)DO UPDATE SET value=excluded.value',(PREFIX+session_id,json.dumps(stamp)))
   conn.execute('UPDATE sessions SET in_draft=0 WHERE id=?',(session_id,))
   return {'id':session_id,'removed':True,**stamp}

 @app.post('/api/sessions/{session_id}/restore')
 def restore(session_id:str,user=Depends(teacher_user)):
  with db.connect()as conn:
   conn.execute('BEGIN IMMEDIATE');row=session_row(conn,session_id,user)
   marker=conn.execute('SELECT value FROM meta WHERE key=?',(PREFIX+session_id,)).fetchone()
   if not marker and not row['in_draft']:raise HTTPException(404,'No deleted session to restore')
   conn.execute('UPDATE sessions SET in_draft=1 WHERE id=?',(session_id,));conn.execute('DELETE FROM meta WHERE key=?',(PREFIX+session_id,))
   return {'id':session_id,'restored':True}
