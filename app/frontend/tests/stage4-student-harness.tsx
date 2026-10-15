// Dedicated synthetic UI harness. Never included by the application entrypoint.
import { createRoot } from "react-dom/client";
import GuidedLearningWorkspace from "../src/GuidedLearningWorkspace";
import "../src/styles.css";
import "../src/stage2.css";
import "../src/contrast.css";
createRoot(document.getElementById("root")!).render(
  <GuidedLearningWorkspace
    sid="stage4-session"
    viewerId="stage4-student"
    onVersion={() => {}}
    onBack={() => {}}
    onChanged={() => {}}
  />,
);
