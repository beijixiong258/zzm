import {useEffect,useId,useRef,useState,type FormEvent} from "react";
import {Ellipsis,Pencil,Trash2,LoaderCircle} from "lucide-react";
import {api} from "./api";
import type {Course,CourseDetails} from "./types";
import {ErrorBanner,errorMessage} from "./ui";
import {useUnsavedChanges} from "./navigation-guard";
import "./course-actions.css";

type Fields={code:string;title:string;description:string};
type Mode="edit"|"trash";
export const courseFields=(course:Course):Fields=>({code:course.code,title:course.title,description:course.description});
export function courseReadbackMatches(course:CourseDetails,id:string,fields:Fields){
 return course.id===id && course.trashed_at===null && course.code===fields.code && course.title===fields.title && course.description===fields.description;
}
export default function CourseActions({course,onChanged,disabled=false}:{course:Course;onChanged:(course:CourseDetails)=>Promise<void>;disabled?:boolean}){
 const [mode,setMode]=useState<Mode|null>(null),[details,setDetails]=useState<CourseDetails|null>(null);
 const [form,setForm]=useState<Fields>(courseFields(course)),[busy,setBusy]=useState("");
 const [error,setError]=useState(""),[accepted,setAccepted]=useState<{mode:Mode;fields:Fields}|null>(null);
 const dialog=useRef<HTMLDialogElement>(null),menu=useRef<HTMLDetailsElement>(null),summary=useRef<HTMLElement>(null);
 const mounted=useRef(false),generation=useRef(0),locked=useRef(false);const uid=useId();
 const dirty=!!details && JSON.stringify(form)!==JSON.stringify(courseFields(details));
 useUnsavedChanges(!!mode && (dirty||!!busy||!!accepted));
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;generation.current++;};},[course.id]);
 useEffect(()=>{if(mode && !dialog.current?.open)dialog.current?.showModal();},[mode]);
 useEffect(()=>{
  const outside=(event:PointerEvent)=>{if(menu.current&&!menu.current.contains(event.target as Node))menu.current.open=false;};
  document.addEventListener("pointerdown",outside);return()=>document.removeEventListener("pointerdown",outside);
 },[]);
 const current=(token:number)=>mounted.current&&generation.current===token;
 function finish(){setMode(null);setError("");setAccepted(null);setDetails(null);requestAnimationFrame(()=>{if(summary.current?.isConnected)summary.current.focus();});}
 function close(){if(locked.current)return;if(dirty&&!accepted&&!window.confirm("Discard unsaved course changes?"))return;generation.current++;finish();}
 async function open(kind:Mode){
  if(locked.current||disabled)return;
  if(menu.current)menu.current.open=false;
  const token=++generation.current;setMode(kind);setDetails(null);setError("");setAccepted(null);setBusy("load");locked.current=true;
  try{const saved=await api.courseDetails(course.id);if(!current(token))return;if(saved.id!==course.id)throw new Error("Course information did not match this course.");setDetails(saved);setForm(courseFields(saved));
   if(saved.trashed_at)setError("This course is already in trash. Close this dialog and open Trash to restore it.");
   else if(kind==="edit")requestAnimationFrame(()=>dialog.current?.querySelector<HTMLInputElement>("input")?.focus());
  }catch(e){if(current(token))setError(errorMessage(e));}
  finally{if(current(token)){locked.current=false;setBusy("");}}
 }
 async function verify(operation:{mode:Mode;fields:Fields},token:number){
  const saved=await api.courseDetails(course.id);
  if(!current(token))return;
  const valid=operation.mode==="edit"?courseReadbackMatches(saved,course.id,operation.fields):saved.id===course.id&&!!saved.trashed_at;
  if(!valid)throw new Error("The saved course does not match this action. Your inputs are kept; check again or close and reopen to review the current course.");
  setDetails(saved);setForm(courseFields(saved));setAccepted(null);
  await onChanged(saved);
  if(current(token))finish();
 }
 async function submit(event:FormEvent){
  event.preventDefault();if(locked.current||!mode||!details)return;
  const operation=accepted??{mode,fields:{...form}};
  if(!accepted && (details.trashed_at || (mode==="edit"&&(!dirty||!form.code.trim()||!form.title.trim()))))return;
  const token=++generation.current;locked.current=true;setBusy(accepted?"verify":mode);setError("");
  try{
   if(!accepted){
    if(mode==="edit")await api.updateCourse(course.id,operation.fields);else await api.trashCourse(course.id);
    if(!current(token))return;setAccepted(operation);
   }
   await verify(operation,token);
  }catch(e){if(current(token))setError(errorMessage(e));}
  finally{if(current(token)){locked.current=false;setBusy("");}}
 }
 return <>
  <details ref={menu} className="course-actions-menu" onKeyDown={e=>{if(e.key==="Escape"){e.preventDefault();if(menu.current)menu.current.open=false;summary.current?.focus();}}}>
   <summary ref={summary} aria-disabled={disabled} tabIndex={disabled?-1:0} onClick={e=>{if(disabled)e.preventDefault();}}><Ellipsis size={17} aria-hidden="true"/>Course actions</summary>
   <div className="course-actions-popover">
    <button type="button" disabled={disabled} onClick={()=>void open("edit")}><Pencil size={16} aria-hidden="true"/>Edit course</button>
    <button type="button" disabled={disabled} className="course-danger-text" onClick={()=>void open("trash")}><Trash2 size={16} aria-hidden="true"/>Move to trash</button>
   </div>
  </details>
  {mode&&<dialog ref={dialog} className="course-action-dialog" data-mode={mode} aria-labelledby={`${uid}-title`} onCancel={e=>{e.preventDefault();close();}}>
   <h2 id={`${uid}-title`}>{mode==="edit"?"Edit course":"Move course to trash?"}</h2>
   <p className="course-action-target"><strong>{course.title}</strong><span>{course.code}</span></p>
   <ErrorBanner error={error} retry={!details&&!busy?()=>void open(mode):undefined}/>
   {busy==="load"&&<p role="status"><LoaderCircle className="spin" size={17}/> Loading course information…</p>}
   {accepted&&!busy&&<p className="course-action-warning" role="status">The change was sent, but its saved result has not been verified. Check the result before sending another action.</p>}
   <form onSubmit={e=>void submit(e)}>
    {mode==="edit"&&details&&<fieldset disabled={!!busy||!!details.trashed_at}>
     <label htmlFor={`${uid}-code`}>Course code</label><input id={`${uid}-code`} required maxLength={50} value={form.code} readOnly={!!accepted} onChange={e=>setForm({...form,code:e.target.value})}/>
     <label htmlFor={`${uid}-name`}>Course name</label><input id={`${uid}-name`} required maxLength={300} value={form.title} readOnly={!!accepted} onChange={e=>setForm({...form,title:e.target.value})}/>
     <label htmlFor={`${uid}-description`}>Description</label><textarea id={`${uid}-description`} rows={5} maxLength={10000} value={form.description} readOnly={!!accepted} onChange={e=>setForm({...form,description:e.target.value})}/>
     <p className="course-action-help">Save updates the course draft. Publish a new edition to update student-facing information.</p>
    </fieldset>}
    {mode==="trash"&&details&&<>
     <dl className="course-impact"><div><dt>Sessions</dt><dd>{details.session_count}</dd></div><div><dt>Materials</dt><dd>{details.material_count}</dd></div><div><dt>Enrollments</dt><dd>{details.enrollment_count}</dd></div></dl>
     <p>Students will not be able to open or join this course until you restore it.</p>
     <p className="course-action-help">All sessions, materials and learning records are kept. This does not permanently delete the course.</p>
    </>}
    <div className="course-action-buttons">
     <button className="secondary" type="button" disabled={!!busy} onClick={close}>{accepted?"Close":"Cancel"}</button>
     <button className={mode==="trash"&&!accepted?"course-danger":"primary"} type="submit" disabled={!!busy||!details||!!details.trashed_at||(!accepted&&mode==="edit"&&(!dirty||!form.code.trim()||!form.title.trim()))}>
      {busy&&busy!=="load"?<><LoaderCircle size={16} className="spin"/> {busy==="verify"?"Checking…":busy==="trash"?"Moving…":"Saving…"}</>:accepted?"Check saved result":mode==="edit"?"Save changes":"Move to trash"}
     </button>
    </div>
   </form>
  </dialog>}
 </>;
}
