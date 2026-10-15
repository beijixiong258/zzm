// Isolated labelled harness; never loaded by the application entrypoint.
import { createRoot } from "react-dom/client";
import { useEffect, useState } from "react";
import Home from "../src/Home";
import CourseLibrary from "../src/CourseLibrary";
import GuidedLearningWorkspace from "../src/GuidedLearningWorkspace";
import MaterialManager from "../src/MaterialManager";
import Authoring from "../src/Authoring";
import WorksheetImport from "../src/WorksheetImport";
import LearningHistory from "../src/LearningHistory";
import { api } from "../src/api";
import { confirmNavigation, hasUnsavedChanges } from "../src/navigation-guard";
import type {
  Course,
  SessionDetail,
  SessionSummary,
  WorksheetDraft,
} from "../src/types";
import fixture from "./stage7-learning-fixture.json";
import "../src/design-tokens.css";
import "../src/styles.css";
import "../src/contrast.css";
import "../src/stage2.css";
import "../src/help-popover.css";
const events: { action: string; id?: string }[] = [];
function Harness() {
  const query = new URLSearchParams(location.search);
  const [view, setView] = useState(query.get("view") || "home");
  const [sid, setSid] = useState("fixture-session");
  const [courses, setCourses] = useState<Course[]>([]);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [session, setSession] = useState<SessionDetail>(
    fixture.sessions[0] as SessionDetail,
  );
  const [loading, setLoading] = useState(true);
  const [draft, setDraft] = useState<WorksheetDraft>({
    title: "Fixture worksheet",
    groups: session.groups,
    questions: session.questions,
    reference_answers: session.reference_answers || {},
  });
  const refresh = async () => {
    const [c, s] = await Promise.all([
      api.courses(),
      api.sessions("fixture-course"),
    ]);
    setCourses(c);
    setSessions(s);
    setLoading(false);
  };
  useEffect(() => {
    void refresh();
  }, []);
  useEffect(() => {
    if (view === "materials") void api.session(sid).then(setSession);
  }, [sid, view]);
  function navigate(next: string, action = next, id?: string) {
    if (!confirmNavigation()) return;
    events.push({ action, id });
    if (id) setSid(id);
    setView(next);
  }
  Object.assign(window, { learningFixture: { events, hasUnsavedChanges } });
  return (
    <>
      <aside
        style={{
          padding: "10px 24px",
          background: "var(--blue-soft)",
          color: "var(--blue)",
          fontSize: 13,
        }}
      >
        Synthetic HTTP fixture — no real backend, SQLite, model or Tavily calls.
      </aside>
      <nav
        aria-label="Fixture views"
        className="button-row"
        style={{ padding: "10px 24px" }}
      >
        {[
          "home",
          "library",
          "student",
          "record",
          "materials",
          "authoring",
          "import",
          "history",
        ].map((name) => (
          <button
            key={name}
            className="text-button"
            onClick={() => navigate(name)}
          >
            {name}
          </button>
        ))}
      </nav>
      {view === "home" && (
        <Home
          user={{
            ...fixture.workspace.user,
            role: query.get("role") === "student" ? "student" : "teacher",
          }}
          courses={courses}
          sessionMap={{ "fixture-course": sessions }}
          loading={loading}
          history={false}
          onOpen={(id) =>
            navigate(
              query.get("role") === "student" ? "student" : "materials",
              "open-session",
              id,
            )
          }
          onPreview={(id) => navigate("student", "preview", id)}
          onRefresh={refresh}
          onRoster={(id) => events.push({ action: "roster", id })}
          onVersions={(id) => events.push({ action: "versions", id })}
          onMaterials={(id) => navigate("library", "library", id)}
        />
      )}
      {view === "library" && (
        <CourseLibrary
          courseId="fixture-course"
          onOpenSession={(id) => navigate("materials", "manage-session", id)}
        />
      )}
      {(view === "student" || view === "record" || view === "preview") && (
        <GuidedLearningWorkspace
          key={view}
          sid="fixture-session"
          viewerId={view === "record" ? "fixture-teacher" : "fixture-student"}
          preview={view === "preview"}
          studentId={view === "record" ? "fixture-student" : undefined}
          onBack={() => navigate("home")}
          onChanged={() => {}}
          onVersion={(id) => events.push({ action: "edition", id })}
        />
      )}
      {view === "materials" && (
        <div className="page">
          <h1>Session {session.number} materials</h1>
          <MaterialManager session={session} onChanged={setSession} />
        </div>
      )}
      {view === "authoring" && (
        <div className="page">
          <h1>Questions & answers</h1>
          <Authoring
            value={draft}
            onChange={setDraft}
            materials={session.materials}
          />
        </div>
      )}
      {view === "import" && (
        <div className="page">
          <WorksheetImport session={session} onCommitted={setSession} />
        </div>
      )}
      {view === "history" && (
        <LearningHistory
          onOpen={(id, version) =>
            events.push({ action: `history:${version}`, id })
          }
        />
      )}
    </>
  );
}
createRoot(document.getElementById("root")!).render(<Harness />);
