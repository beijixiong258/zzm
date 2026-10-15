// Owned Stage8 component fixture. No App, backend, auth or model calls.
import React from "react";
import { createRoot } from "react-dom/client";
import "../src/design-tokens.css";
import "../src/styles.css";
import "../src/contrast.css";
import "../src/stage2.css";
import Login from "../src/Login";
import { Brand, AiBadge } from "../src/ui";
import type { Bootstrap } from "../src/types";
const params = new URLSearchParams(location.search);
const mode = params.get("mode") || "login";
const before = params.get("before") === "1";
const ai = { mode: "demo", configured: true, base_url: "", model: "explicit-brand-fixture", last_error: null };
const bootstrap = { ai } as unknown as Bootstrap;
(window as any).__brandHomeCalls = 0;
const navigate = () => { (window as any).__brandHomeCalls += 1; };
const B = Brand as React.ComponentType<any>;
function Sidebar({ appearance = "panel" }: { appearance?: string }) {
  return <aside className="sidebar mobile-open"><B appearance={appearance} onNavigateHome={navigate}/><div className="sidebar-label">WORKSPACE</div><a className="nav-item active" href="#/home">Course Home</a><a className="nav-item" href="#/history">My Learning</a><div className="sidebar-bottom"><AiBadge ai={ai as any} detail/></div></aside>;
}
function Fixture() {
  if (mode === "sidebar") return <><Sidebar/><main style={{marginLeft:260,padding:40}}><h1>Component fixture</h1><p>Signed-in brand panel; model badge stays below navigation.</p></main></>;
  if (mode === "comparison") return <div className="stage8-comparison"><h1>Standard / inverted · same V4 geometry</h1><div className="comparison-grid">{["standard","panel"].map(appearance => <section className="login-brand-layout" key={appearance}><h2>{appearance}</h2><div className="login-form-panel"><div className="login-form-heading"><B appearance={appearance} onNavigateHome={navigate}/></div></div><div className="sidebar" style={{position:"relative",inset:"auto",minHeight:350}}><B appearance={appearance} onNavigateHome={navigate}/><div className="sidebar-label">WORKSPACE</div><a className="nav-item active" href="#/home">Course Home</a></div></section>)}</div></div>;
  return <>{before && <header className="public-header"><Brand/></header>}<Login bootstrap={bootstrap} onAuthenticated={async () => {throw new Error("No auth calls authorized in brand fixture");}}/></>;
}
createRoot(document.getElementById("root")!).render(<Fixture/>);
const style = document.createElement("style");
style.textContent = `.stage8-comparison { padding:48px;max-width:1320px;margin:auto }.stage8-comparison h1 {font-size:32px;margin-bottom:32px}.comparison-grid {display:grid;grid-template-columns:1fr 1fr;gap:48px}.comparison-grid h2 {font:16px var(--font-ui);margin-bottom:16px}.comparison-grid .login-form-panel {max-width:560px;margin-bottom:28px;padding:30px}.comparison-grid .sidebar {display:flex;width:224px}.comparison-grid .login-form-heading .brand {margin-bottom:0}@media(max-width:820px){.stage8-comparison {padding:20px}.comparison-grid {grid-template-columns:1fr;gap:24px}}`;
document.head.append(style);
