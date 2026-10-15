import {useCallback,useEffect,useState} from "react";
import {createRoot} from "react-dom/client";
import Home from "../src/Home";
import CourseTrash from "../src/CourseTrash";
import {api} from "../src/api";
import type {Course,CourseDetails} from "../src/types";
import {confirmNavigation} from "../src/navigation-guard";
import "../src/design-tokens.css";import "../src/styles.css";import "../src/contrast.css";import "../src/stage2.css";
function Fixture(){
 const [courses,setCourses]=useState<Course[]>([]),[page,setPage]=useState("home");
 const refresh=useCallback(async()=>setCourses(await api.courses()),[]);
 useEffect(()=>{void refresh()},[refresh]);
 const changed=async(_:CourseDetails)=>{await refresh()};
 const go=(p:string)=>{if(confirmNavigation())setPage(p)};
 return <><div style={{padding:"10px 24px",background:"#23352e",color:"white",display:"flex",gap:20,alignItems:"center"}}><span>Explicit course HTTP fixture · no real backend/model</span><button onClick={()=>go("away")}>Navigate away</button></div>
 {page==="trash"?<CourseTrash onRestored={changed} onBack={()=>go("home")}/>:page==="away"?<div className="page"><h1>Other page</h1><button onClick={()=>go("home")}>Back to courses</button></div>:<Home user={{id:"fixture-owner",name:"Synthetic owner",email:"owner@example.invalid",role:"teacher"}} courses={courses} sessionMap={{}} loading={false} history={false} onOpen={()=>{}} onPreview={()=>{}} onRefresh={refresh} onRoster={()=>{}} onVersions={()=>{}} onTrash={()=>go("trash")} onCourseChanged={changed}/>}
 </>;
}
createRoot(document.querySelector("#root")!).render(<Fixture/>);
