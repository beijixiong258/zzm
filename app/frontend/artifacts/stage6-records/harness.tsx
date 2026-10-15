import {useState} from "react";
import {createRoot} from "react-dom/client";
import GuidedLearningWorkspace from "../../src/GuidedLearningWorkspace";
import "../../src/styles.css";
import "../../src/stage2.css";
function Harness(){const[mode,setMode]=useState("record");return <main style={{maxWidth:1400,margin:"auto",padding:20}}><div style={{display:"flex",gap:12,alignItems:"center",marginBottom:15}}><strong>Synthetic HTTP fixtures — not backend/model evidence</strong><button onClick={()=>setMode("record")}>Record fixture</button><button onClick={()=>setMode("preview")}>Preview fixture</button></div><GuidedLearningWorkspace key={mode} sid="synthetic-session" viewerId="teacher-one" studentId={mode==="record"?"student-one":undefined} preview={mode==="preview"} versionId={mode==="record"?"edition-one":undefined} onVersion={()=>{}} onBack={()=>{}} onChanged={()=>{}}/></main>}
createRoot(document.getElementById("root")!).render(<Harness/>);
