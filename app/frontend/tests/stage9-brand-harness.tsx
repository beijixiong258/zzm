// Isolated visual fixture. No App/backend, credentials, auth or model calls.
import { useState } from "react";
import { createRoot } from "react-dom/client";
import Login from "../src/Login";
import { Brand } from "../src/ui";
import { confirmNavigation, useUnsavedChanges } from "../src/navigation-guard";
import "../src/design-tokens.css";
import "../src/styles.css";
import "../src/contrast.css";
import "../src/stage2.css";
import type { Bootstrap } from "../src/types";

const params = new URLSearchParams(location.search);
const appearance = (params.get("appearance") || document.body.dataset.appearance) === "panel" ? "panel" : "standard";
const boot = {app_name:"AIcademiya",demo_enabled:false,default_locale:"en",ai:{mode:"openai",configured:false,base_url:"",model:""}} as Bootstrap;
const w = window as typeof window & {__stage9: {homeCalls:number;authCalls:number;setDirty?:(value:boolean)=>void}};
w.__stage9 = {homeCalls:0,authCalls:0};
function Fixture() {
  const [dirty, setDirty] = useState(false);
  useUnsavedChanges(dirty);
  w.__stage9.setDirty = setDirty;
  if (params.get("mode") === "sidebar") return <div className="app-shell">
    <aside className="sidebar mobile-open"><Brand appearance={appearance} onNavigateHome={() => {
      w.__stage9.homeCalls += 1;
      if (confirmNavigation()) location.hash = "/home";
    }}/><div className="sidebar-label">WORKSPACE</div><nav className="main-nav"><button className="active">Course Home</button><button>My Learning</button><button>Settings</button></nav><div className="sidebar-bottom"><p>Synthetic visual fixture</p></div></aside>
    <main className="main-content"><header className="topbar">Course Home</header><div className="page"><h1>Horizontal brand</h1><p>V4 logo left; name and tagline right. No authentication is available here.</p></div></main>
  </div>;
  // "live" exists only for regression checks on default enabled fields/switch.
  // The fixture server refuses all API requests; never enter a password here.
  return <Login bootstrap={boot} previewAppearance={params.get("mode") === "live" && location.protocol === "http:" ? undefined : appearance} onAuthenticated={async () => {w.__stage9.authCalls += 1; throw new Error("No authentication authorized in this fixture");}}/>;
}
createRoot(document.getElementById("root")!).render(<Fixture/>);
