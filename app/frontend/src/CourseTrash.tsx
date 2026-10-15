import {useCallback,useEffect,useRef,useState} from "react";
import {ArrowLeft,RefreshCw,RotateCcw,Trash2,LoaderCircle} from "lucide-react";
import {api} from "./api";
import type {CourseDetails} from "./types";
import {Empty,ErrorBanner,Loading,Notice,errorMessage} from "./ui";
import {dateLabel} from "./study";
import {useUnsavedChanges} from "./navigation-guard";
import "./course-actions.css";

export default function CourseTrash({onRestored,onBack}:{onRestored:(course:CourseDetails)=>Promise<void>;onBack:()=>void}){
 const [courses,setCourses]=useState<CourseDetails[]>([]),[loading,setLoading]=useState(true),[busy,setBusy]=useState<string|null>(null);
 const [accepted,setAccepted]=useState<string|null>(null),[error,setError]=useState(""),[notice,setNotice]=useState("");
 const mounted=useRef(false),op=useRef(0),locked=useRef(false);
 useUnsavedChanges(!!busy||!!accepted);
 const load=useCallback(async()=>{
  const token=++op.current;setLoading(true);setError("");
  try{const r=await api.courseTrash();if(mounted.current&&token===op.current)setCourses(r.courses);}
  catch(e){if(mounted.current&&token===op.current)setError(errorMessage(e));}
  finally{if(mounted.current&&token===op.current)setLoading(false);}
 },[]);
 useEffect(()=>{mounted.current=true;void load();return()=>{mounted.current=false;op.current++;};},[load]);
 async function restore(course:CourseDetails){
  if(locked.current)return;
  locked.current=true;const token=++op.current;setBusy(course.id);setError("");setNotice("");
  try{
   if(accepted!==course.id){await api.restoreCourse(course.id);if(!mounted.current||token!==op.current)return;setAccepted(course.id);}
   const current=await api.courseDetails(course.id);if(!mounted.current||token!==op.current)return;
   if(current.id!==course.id||current.trashed_at!==null)throw new Error("Restore could not be verified. Check the saved result before trying another action.");
   setAccepted(null);setCourses(old=>old.filter(c=>c.id!==course.id));setNotice(`${current.title} was restored. It is available in Course Home.`);
   await onRestored(current);
  }catch(e){if(mounted.current&&token===op.current)setError(errorMessage(e));}
  finally{if(mounted.current&&token===op.current){locked.current=false;setBusy(null);}}
 }
 return <div className="page course-trash-page">
  <header className="page-heading"><div><div className="eyebrow">COURSE MANAGEMENT</div><h1 tabIndex={-1}>Course trash</h1><p>Courses stay here until you restore them.</p></div>
   <div className="button-row"><button className="secondary" disabled={!!busy} onClick={onBack}><ArrowLeft size={16}/>Course Home</button><button className="secondary" disabled={loading||!!busy||!!accepted} onClick={()=>void load()}><RefreshCw size={16}/>Refresh</button></div>
  </header>
  <ErrorBanner error={error} retry={!busy&&!accepted?()=>void load():undefined}/>
  {notice&&<div role="status"><Notice>{notice}</Notice></div>}
  {accepted&&!busy&&<p className="course-action-warning" role="status">The restore was sent, but readback has not succeeded. Use Check saved result on the course below.</p>}
  {loading?<Loading/>:courses.length?<div className="course-trash-list">{courses.map(course=><article className="card course-trash-card" key={course.id} data-trash-course={course.id}>
   <div><div className="course-code">{course.code}</div><h2>{course.title}</h2>{course.description&&<p className="course-trash-description">{course.description}</p>}<small>Moved to trash {dateLabel(course.trashed_at)}</small>
    <div className="course-trash-counts"><span>{course.session_count} {course.session_count===1?"session":"sessions"}</span><span>{course.material_count} {course.material_count===1?"material":"materials"}</span><span>{course.enrollment_count} {course.enrollment_count===1?"enrollment":"enrollments"}</span></div>
   </div><button className="secondary" disabled={!!busy||(!!accepted&&accepted!==course.id)} onClick={()=>void restore(course)}>{busy===course.id?<LoaderCircle size={16} className="spin"/>:<RotateCcw size={16}/>} {busy===course.id?"Restoring…":accepted===course.id?"Check saved result":"Restore course"}</button>
  </article>)}</div>:!error?<Empty title="No courses in trash" description="Courses you move to trash will appear here."/>:null}
  <p className="course-trash-footnote"><Trash2 size={15} aria-hidden="true"/>Restoring keeps the same course, invitation code and saved work.</p>
 </div>;
}
