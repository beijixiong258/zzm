import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import Materials from "../src/Materials";
import MaterialManager from "../src/MaterialManager";
import SourceCitations from "../src/SourceCitations";
import { hasUnsavedChanges } from "../src/navigation-guard";
import "../src/styles.css";
import "../src/stage2.css";
import "../src/design-tokens.css";
import type { SessionDetail } from "../src/types";
const material = {
  id: "m1",
  title: "Synthetic 317-page PDF",
  kind: "reading",
  visibility: "student" as const,
  source_label: "UI-only source",
  status: "ready" as const,
  excerpt: "Preview only",
  preview_kind: "pdf" as const,
  preview_url: "/api/materials/m1/preview",
  download_url: "/api/materials/m1/download",
};
const initial: SessionDetail = {
  id: "s1",
  course_id: "c1",
  title: "Synthetic session",
  subtitle: "",
  number: 1,
  status: "draft",
  question_count: 0,
  estimated_minutes: 10,
  learning_objectives: [],
  instructions: "",
  teaching_language: "en",
  reference_policy: "after_attempt",
  questions: [],
  groups: [],
  materials: [material],
};
function Harness() {
  const [mode, setMode] = useState("teacher"),
    [session, setSession] = useState(initial),
    [account, setAccount] = useState("staff-a");
  Object.assign(window, {
    stage12: { setMode, setAccount, dirty: hasUnsavedChanges },
  });
  return (
    <main style={{ padding: 20, maxWidth: 1400, margin: "auto" }}>
      <p>
        UI-only synthetic fixture — not backend authentication, OCR or model
        evidence.
      </p>
      <div className="button-row">
        {["teacher", "student", "history", "manager", "other"].map((m) => (
          <button key={m} onClick={() => setMode(m)}>
            {m} fixture
          </button>
        ))}
      </div>
      {mode === "manager" ? (
        <MaterialManager
          key={account}
          session={session}
          onChanged={setSession}
        />
      ) : (
        <Materials
          key={account + mode}
          teacher={mode !== "student"}
          materials={[
            mode === "other"
              ? { ...material, id: "m2", title: "Other source" }
              : material,
          ]}
          versionId={
            mode === "history"
              ? "edition-old"
              : mode === "student"
                ? "edition-student"
                : null
          }
        />
      )}
      <div
        className="fixture-chat"
        style={{ height: 220, overflow: "auto", marginTop: 20 }}
      >
        <div style={{ height: 280 }}>Synthetic nested chat pane</div>
        <SourceCitations
          citations={[
            {
              kind: "document",
              source_label: "Late-page source",
              url: "/api/materials/m1/preview?version_id=edition-old#page=269",
              quote: "Exact synthetic quote <table>literal</table>",
              text: "Exact synthetic quote <table>literal</table>",
              material_id: "m1",
              revision_id: "old-r1",
              page: 269,
              printed_label: "A147",
              block_id: "p269-b1",
              version_id: "edition-old",
            },
          ]}
        />
      </div>
    </main>
  );
}
createRoot(document.getElementById("root")!).render(<Harness />);
