// Read-only real App integration with synthetic GET responses supplied by Chrome.
import { useState } from "react";
import { createRoot } from "react-dom/client";
import App from "../src/App";
import { useUnsavedChanges } from "../src/navigation-guard";
import "../src/design-tokens.css";
import "../src/styles.css";
import "../src/contrast.css";
import "../src/stage2.css";
function Fixture() {
  const [dirty,setDirty] = useState(false);
  useUnsavedChanges(dirty);
  (window as typeof window & {__stage9SetDirty?:(value:boolean)=>void}).__stage9SetDirty = setDirty;
  return <App/>;
}
createRoot(document.getElementById("root")!).render(<Fixture/>);
