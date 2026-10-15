import {useEffect,useId,useRef,useState} from 'react';
import {api} from './api';
import type {SessionSummary} from './types';
import {ErrorBanner,errorMessage} from './ui';
import {useUnsavedChanges} from './navigation-guard';
import './course-actions.css';

type Fields={title:string;subtitle:string;number:number};
const fields=(s:SessionSummary):Fields=>({title:s.title,subtitle:s.subtitle,number:s.number});
export default function SessionActions({session,onChanged}:{session:SessionSummary;onChanged:()=>Promise<void>}){
 const [mode,setMode]=useState<'edit'|'delete'|null>(null),[form,setForm]=useState(fields(session)),[original,setOriginal]=useState(fields(session));
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[accepted,setAccepted]=useState(false),[loaded,setLoaded]=useState(false);
 const dialog=useRef<HTMLDialogElement>(null),alive=useRef(true),locked=useRef(false),trigger=useRef<HTMLButtonElement|null>(null);const uid=useId();
 const dirty=JSON.stringify(form)!==JSON.stringify(original);useUnsavedChanges(!!mode&&(dirty||busy||accepted));
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[session.id]);
 useEffect(()=>{if(mode&&!dialog.current?.open)dialog.current?.showModal();},[mode]);
 function close(){if(locked.current)return;if(dirty&&!accepted&&!window.confirm('Discard unsaved session changes?'))return;setMode(null);setError('');setAccepted(false);trigger.current?.focus();}
 async function open(kind:'edit'|'delete',button:HTMLButtonElement){
  if(locked.current)return;trigger.current=button;setMode(kind);setError('');setAccepted(false);setLoaded(false);locked.current=true;setBusy(true);
  try{const s=await api.session(session.id);if(!alive.current)return;setOriginal(fields(s));setForm(fields(s));setLoaded(true);}
  catch(e){if(alive.current)setError(errorMessage(e));}
  finally{locked.current=false;if(alive.current)setBusy(false);}
 }
 async function submit(){
  if(locked.current||!mode||!loaded)return;locked.current=true;setBusy(true);setError('');
  try{
   if(!accepted){if(mode==='edit')await api.updateSession(session.id,form);else await api.deleteSession(session.id);if(!alive.current)return;setAccepted(true);}
   if(mode==='edit'){
    const saved=await api.session(session.id);if(JSON.stringify(fields(saved))!==JSON.stringify(form))throw Error('Saved session fields could not be confirmed.');
   }else{
    const saved=await api.deletedSessions(session.course_id);if(!saved.sessions.some(x=>x.id===session.id))throw Error('Deleted session could not be confirmed.');
   }
   if(!alive.current)return;await onChanged();if(alive.current){setMode(null);setAccepted(false);}
  }catch(e){if(alive.current)setError(errorMessage(e));}
  finally{locked.current=false;if(alive.current)setBusy(false);}
 }
 return <>
  <div className="button-row"><button className="text-button" aria-label={`Edit session ${session.title}`} disabled={busy} onClick={e=>void open('edit',e.currentTarget)}>Edit session</button><button className="text-button danger" aria-label={`Delete session ${session.title}`} disabled={busy} onClick={e=>void open('delete',e.currentTarget)}>Delete session</button></div>
  {mode&&<dialog ref={dialog} className="course-action-dialog" aria-labelledby={`${uid}-heading`} onCancel={e=>{e.preventDefault();close();}}>
   <h2 id={`${uid}-heading`}>{mode==='edit'?'Edit session':'Delete session from draft?'}</h2><ErrorBanner error={error}/>
   <form onSubmit={e=>{e.preventDefault();void submit();}}>
    {mode==='edit'?<fieldset disabled={busy||accepted}>
     <label htmlFor={`${uid}-title`}>Session title</label><input id={`${uid}-title`} value={form.title} required maxLength={300} onChange={e=>setForm({...form,title:e.target.value})}/>
     <label htmlFor={`${uid}-number`}>Session number</label><input id={`${uid}-number`} type="number" required min={1} max={9999} value={form.number} onChange={e=>setForm({...form,number:Number(e.target.value)})}/>
     <label htmlFor={`${uid}-subtitle`}>Description</label><textarea id={`${uid}-subtitle`} value={form.subtitle} rows={4} onChange={e=>setForm({...form,subtitle:e.target.value})}/>
    </fieldset>:<p>{session.title} will move to Deleted sessions. Materials and learning records are kept.</p>}
    <p className="course-action-help">This changes the draft. Publish a new course edition to update the student view.</p>
    <div className="course-action-buttons"><button type="button" className="secondary" disabled={busy} onClick={close}>Cancel</button><button className={mode==='delete'?'course-danger':'primary'} disabled={busy||!loaded||(mode==='edit'&&!form.title.trim())}>{busy?'Working…':accepted?'Check saved result':mode==='edit'?'Save changes':'Delete session'}</button></div>
   </form>
  </dialog>}
 </>;
}

export function DeletedSessions({courseId,onChanged}:{courseId:string;onChanged:()=>Promise<void>}){
 const [items,setItems]=useState<(SessionSummary&{removed_at:string})[]>([]),[busy,setBusy]=useState(false),[error,setError]=useState('');const alive=useRef(true),lock=useRef(false);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[courseId]);
 async function load(){try{const data=await api.deletedSessions(courseId);if(alive.current)setItems(data.sessions);}catch(e){if(alive.current)setError(errorMessage(e));}}
 async function restore(id:string){if(lock.current)return;lock.current=true;setBusy(true);setError('');try{await api.restoreSession(id);const current=await api.sessions(courseId);if(!current.some(x=>x.id===id))throw Error('Restored session not confirmed.');if(alive.current){await load();await onChanged();}}catch(e){if(alive.current)setError(errorMessage(e));}finally{lock.current=false;if(alive.current)setBusy(false);}}
 return <details className="card" onToggle={e=>{if(e.currentTarget.open)void load();}}><summary>Deleted sessions</summary><ErrorBanner error={error}/>{items.length?items.map(s=><div className="button-row" key={s.id}><span>{s.number}. {s.title}</span><button className="secondary" disabled={busy} onClick={()=>void restore(s.id)}>Restore session</button></div>):<p>No deleted sessions.</p>}</details>;
}
