import { createRoot } from "react-dom/client";
import { useState } from "react";
import TeacherSession from "../src/TeacherSession";
import "../src/design-tokens.css";
import "../src/styles.css";
import "../src/contrast.css";
import "../src/stage2.css";
import { confirmNavigation, hasUnsavedChanges } from "../src/navigation-guard";
function Harness() {
  const [sid, setSid] = useState("fixture-s1");
  Object.assign(window, { teacherFixture: { hasUnsavedChanges } });
  return (
    <>
      <header style={{ padding: 16, background: "#e8eee4", fontSize: 12 }}>
        LABELLED SYNTHETIC HTTP FIXTURE · Real React UI · No
        backend/database/model inference.
        <button
          style={{ marginLeft: 14 }}
          onClick={() =>
            setSid(sid === "fixture-s1" ? "fixture-s2" : "fixture-s1")
          }
        >
          Switch fixture session
        </button>
        <span data-testid="fixture-session">{sid}</span>
      </header>
      <a
        href="#fixture-outside"
        onClick={(e) => {
          e.preventDefault();
          if (confirmNavigation()) document.body.dataset.left = "yes";
        }}
      >
        Fixture: leave teacher page
      </a>
      <TeacherSession
        sid={sid}
        viewerId="fixture-teacher"
        onVersions={(courseId) => {
          if (confirmNavigation()) document.body.dataset.versions = courseId;
        }}
        onPreview={() => {
          document.body.dataset.fullPreview = "requested";
        }}
        onRecord={() => {
          throw new Error("Out of fixture scope");
        }}
        onSaved={() => {
          document.body.dataset.saved = "yes";
        }}
      />
    </>
  );
}
createRoot(document.getElementById("root")!).render(<Harness />);
