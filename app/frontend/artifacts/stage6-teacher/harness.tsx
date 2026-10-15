import { createRoot } from "react-dom/client";
import { useState } from "react";
import TeacherSession from "../../src/TeacherSession";
import "../../src/styles.css";
function Harness() {
  const [sid, setSid] = useState("fixture-s1");
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
      <TeacherSession
        sid={sid}
        viewerId="fixture-teacher"
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
