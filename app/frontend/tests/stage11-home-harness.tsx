// Labelled synthetic presentation fixture; does not implement production auth.
import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import Home from "../src/Home";
import Login from "../src/Login";
import { Brand } from "../src/ui";
import { pageTitle } from "../src/course-presentation";
import type { Course, CourseDetails, SessionSummary, User } from "../src/types";
import "../src/design-tokens.css";
import "../src/styles.css";
import "../src/contrast.css";
import "../src/stage2.css";
const user:User={id:"synthetic-teacher",role:"teacher",name:"Synthetic teacher",email:"synthetic@example.invalid"};
const description="This is synthetic course content for layout verification. The description should use the available course banner width rather than remain restricted to the former narrow column.\n\n(1) Preserve the first separate teaching objective exactly as entered.\n(2) Preserve the second objective on its own line, including the empty line above the numbered items.";
const initial:Course[]=[{id:"first",code:"EDUC7703",title:"Synthetic multi-teacher course",description,admin_count:1,teacher_count:2,student_count:1,join_code:"SYNTHETIC-ONLY"},{id:"second",code:"EDUC1145",title:"Synthetic second course",description:"Second course description.\nA separate line.",admin_count:0,teacher_count:1,student_count:2,join_code:"SYNTHETIC-SECOND"}];
const makeSession=(id:string,cid:string,number:number):SessionSummary=>({id,course_id:cid,title:"Synthetic session "+number,subtitle:"Fixture only",number,status:"draft",question_count:0,estimated_minutes:40,learning_objectives:[]});
const sessions={first:[makeSession("s1","first",1)],second:[makeSession("s2","second",1),makeSession("s3","second",2)]};
function Fixture(){
 const [courses,setCourses]=useState(initial),[selected,setSelected]=useState<string>(),[mode,setMode]=useState<"home"|"settings"|"login">("home");
 const title=pageTitle(mode==="login"?null:user,{page:mode==="login"?"home":mode},courses.find(c=>c.id===selected),undefined);
 useEffect(()=>{document.title=title;},[title]);
 const changed=async(c:CourseDetails)=>{setCourses(old=>old.map(x=>x.id===c.id?c:x));};
 return <>
  <aside className="sidebar"><Brand appearance="panel"/><nav aria-label="Synthetic fixture modes"><button onClick={()=>setMode("home")}>Fixture Course Home</button><button onClick={()=>setMode("settings")}>Fixture Settings</button><button onClick={()=>setMode("login")}>Fixture Login</button></nav></aside>
  <main className="main-content"><div className="topbar">Synthetic presentation fixture — not a signed-in production session</div>
   {mode==="home"&&<Home user={user} courses={courses} sessionMap={sessions} loading={false} history={false} onActiveCourseChange={setSelected} onOpen={()=>{}} onPreview={()=>{}} onRefresh={async()=>{}} onRoster={()=>{}} onVersions={()=>{}} onCourseChanged={changed}/>}
   {mode==="settings"&&<section className="page"><h1>Settings fixture</h1></section>}
   {mode==="login"&&<Login bootstrap={{app_name:"AIcademiya",demo_enabled:false,registration_enabled:true,default_locale:"en",ai:{mode:"openai",configured:false,model:"",base_url:""}}} onAuthenticated={async()=>{throw Error("Fixture authentication not implemented");}}/>}
  </main>
 </>;
}
createRoot(document.getElementById("root")!).render(<Fixture/>);
