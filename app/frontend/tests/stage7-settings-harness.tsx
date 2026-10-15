import { createRoot } from "react-dom/client";
import { useRef, useState } from "react";
import { api } from "../src/api";
import {
  modelForm,
  modelPayload,
  modelReadbackMatches,
  useSavedSettings,
} from "../src/stage7-settings";
import SettingsWorkspace, {
  type SettingsSection,
} from "../src/SettingsWorkspace";
import { confirmNavigation, hasUnsavedChanges } from "../src/navigation-guard";
import type { User } from "../src/types";
import "../src/design-tokens.css";
import "../src/styles.css";
import "../src/contrast.css";
import "../src/stage2.css";

function RaceHarness() {
  const state = useSavedSettings({
    read: api.settings,
    write: (f: ReturnType<typeof modelForm>) =>
      api.saveSettings(modelPayload(f)),
    toForm: modelForm,
    matches: modelReadbackMatches,
  });
  if (!state.form) return <p>Loading race fixture</p>;
  return (
    <section>
      <h1>Synthetic delayed-response hook fixture</h1>
      <label>
        Race model
        <input
          value={state.form.model}
          onChange={(e) => state.change({ model: e.target.value })}
        />
      </label>
      <button onClick={() => void state.save()}>Race save</button>
      <button onClick={() => void state.test(api.testSettings)}>
        Race test
      </button>
      <p data-testid="race-dirty">{String(state.dirty)}</p>
      <p data-testid="race-busy">{state.busy || "idle"}</p>
      <p data-testid="race-notice">{state.notice}</p>
      <p data-testid="race-error">{state.error}</p>
      <p data-testid="race-unavailable">{String(state.unavailable)}</p>
    </section>
  );
}
function Harness() {
  const query = new URLSearchParams(location.search);
  const initialRole = query.get("role") ?? "admin";
  const role =
    initialRole === "teacher" || initialRole === "student"
      ? initialRole
      : "admin";
  const [user, setUser] = useState<User>({
    id: `fixture-${role}`,
    name: "Alex Fixture",
    email: "alex@example.invalid",
    role,
    is_demo: false,
  });
  const [section, setSection] = useState<SettingsSection>(
    (query.get("section") ?? "model") as SettingsSection,
  );
  const [shown, setShown] = useState(true);
  const updates = useRef<string[]>([]);
  Object.assign(window, {
    settingsFixture: {
      setSection,
      setUser,
      hasUnsavedChanges,
      updates: updates.current,
    },
  });
  return (
    <>
      <aside
        style={{
          padding: "12px 24px",
          color: "#355c98",
          background: "#eef3fc",
          font: "14px Segoe UI",
        }}
      >
        Synthetic HTTP fixture — UI tests only; no backend, SQLite, model or
        Tavily service.
      </aside>
      <a
        href="#outside"
        style={{ display: "inline-block", margin: "12px 24px" }}
        onClick={(e) => {
          e.preventDefault();
          if (confirmNavigation()) setShown(false);
        }}
      >
        Fixture: leave settings
      </a>
      {shown ? (
        <SettingsWorkspace
          user={user}
          section={section}
          onSection={(s) => {
            if (confirmNavigation()) setSection(s);
          }}
          onUserUpdate={setUser}
          onAiUpdate={(ai) => {
            updates.current.push(ai.model);
          }}
        />
      ) : (
        <p>Fixture outside page</p>
      )}
    </>
  );
}
createRoot(document.getElementById("root")!).render(
  new URLSearchParams(location.search).has("race") ? (
    <RaceHarness />
  ) : (
    <Harness />
  ),
);
