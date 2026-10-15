import type { FormEvent } from "react";
import {
  AlertCircle,
  CheckCircle2,
  CircleHelp,
  LoaderCircle,
  PlugZap,
  Save,
} from "lucide-react";
import { api } from "./api";
import type { AiStatus, ConnectionCheck } from "./types";
import { AiBadge, ErrorBanner, Loading } from "./ui";
import HelpPopover from "./HelpPopover";
import { useUnsavedChanges } from "./navigation-guard";
import {
  connectionText,
  modelConnection,
  modelForm,
  modelPayload,
  modelReadbackMatches,
  useSavedSettings,
} from "./stage7-settings";
import "./settings-workspace.css";

export function SettingsConnection({
  check,
  dirty,
  checking,
  unavailable,
  title = "Connection",
}: {
  check: ConnectionCheck;
  dirty: boolean;
  checking: boolean;
  unavailable: boolean;
  title?: string;
}) {
  const state = connectionText(check, dirty, checking, unavailable);
  const Icon =
    state.status === "checking"
      ? LoaderCircle
      : state.status === "connected"
        ? CheckCircle2
        : state.status === "error"
          ? AlertCircle
          : CircleHelp;
  return (
    <div className="settings-connection" aria-live="polite">
      <div className="settings-connection-heading">
        <strong>{title}</strong>
        <span className={`settings-check settings-check-${state.status}`}>
          <Icon
            size={16}
            aria-hidden="true"
            className={checking ? "spin" : undefined}
          />
          {state.label}
        </span>
      </div>
      {state.detail && <p className="settings-helper">{state.detail}</p>}
    </div>
  );
}
export default function ModelSettings({
  onUpdate,
}: {
  onUpdate: (ai: AiStatus) => void;
}) {
  const state = useSavedSettings({
    read: api.settings,
    write: (f: ReturnType<typeof modelForm>) =>
      api.saveSettings(modelPayload(f)),
    toForm: modelForm,
    matches: modelReadbackMatches,
    onSaved: (s) => onUpdate(s.ai),
  });
  const { saved, form, busy } = state;
  const dirty = state.dirty || saved?.ai.mode === "demo";
  useUnsavedChanges(dirty || !!busy);
  async function save(event: FormEvent) {
    event.preventDefault();
    await state.save();
  }
  if (state.loading) return <Loading />;
  if (!saved || !form)
    return (
      <div className="settings-service">
        <h2>AI Model</h2>
        <ErrorBanner error={state.error} retry={() => void state.load()} />
      </div>
    );
  const configured = saved.ai.mode === "openai" && saved.ai.configured;
  return (
    <section
      className="settings-service"
      aria-labelledby="model-settings-title"
      aria-busy={!!busy}
    >
      <h2 id="model-settings-title">AI Model</h2>
      <AiBadge ai={saved.ai} detail />
      <ErrorBanner error={state.error} />
      {state.notice && (
        <p className="settings-notice" role="status">
          <CheckCircle2 size={17} aria-hidden="true" />
          {state.notice}
        </p>
      )}
      <form onSubmit={save}>
        <fieldset disabled={!!busy} className="settings-fields">
          <label htmlFor="settings-model-url">API base URL</label>
          <input
            id="settings-model-url"
            type="url"
            required
            value={form.base_url}
            onChange={(e) => state.change({ base_url: e.target.value })}
            placeholder="https://api.example.com/v1"
            spellCheck={false}
          />
          <label htmlFor="settings-model-name">Model name</label>
          <input
            id="settings-model-name"
            required
            value={form.model}
            onChange={(e) => state.change({ model: e.target.value })}
            placeholder="Model identifier"
            spellCheck={false}
          />
          <div className="settings-field-title">
            <label htmlFor="settings-model-key">API key</label>
            <HelpPopover label="Help with model API key">
              Leave blank to keep the current key. Some local providers do not
              require a key. Keys are stored on the server, not in browser
              storage.
            </HelpPopover>
          </div>
          <input
            id="settings-model-key"
            type="password"
            autoComplete="off"
            spellCheck={false}
            value={form.api_key}
            disabled={form.clear_key}
            onChange={(e) => state.change({ api_key: e.target.value })}
            placeholder={
              saved.api_key_set
                ? "Leave blank to keep the current key"
                : "Optional provider key"
            }
            aria-describedby="model-key-state"
          />
          <p id="model-key-state" className="settings-helper">
            {saved.api_key_set
              ? "A key is configured."
              : "No key is configured."}
          </p>
          {saved.api_key_set && (
            <label className="settings-checkbox">
              <input
                type="checkbox"
                checked={form.clear_key}
                onChange={(e) =>
                  state.change({ clear_key: e.target.checked, api_key: "" })
                }
              />
              Clear the current key on save
            </label>
          )}
        </fieldset>
        <SettingsConnection
          title="Generation check"
          check={modelConnection(saved.ai)}
          dirty={dirty}
          checking={busy === "test"}
          unavailable={state.unavailable}
        />
        <div className="settings-actions">
          <button type="submit" className="primary" disabled={!!busy || !dirty}>
            <Save size={16} aria-hidden="true" />
            {busy === "save" ? "Saving…" : "Save changes"}
          </button>
          <button
            type="button"
            className="secondary"
            disabled={!!busy || dirty || !configured || state.unavailable}
            onClick={() =>
              void state.test(async () => {
                const result = await api.testSettings();
                if (!result.ok || result.mode !== "openai")
                  throw new Error(
                    result.mode !== "openai"
                      ? "The saved configuration did not test a configured model."
                      : result.message,
                  );
              })
            }
          >
            <PlugZap size={16} aria-hidden="true" />
            {busy === "test" ? "Testing…" : "Test connection"}
          </button>
          <HelpPopover label="About testing the model">Uses saved settings for one short model request, not a teaching conversation.</HelpPopover>
          {dirty && (
            <span className="settings-unsaved" role="status">
              Unsaved changes
            </span>
          )}
        </div>

        {state.unavailable && (
          <button
            type="button"
            className="text-button"
            disabled={!!busy || dirty}
            onClick={() => void state.load()}
          >
            Refresh saved status
          </button>
        )}
      </form>
    </section>
  );
}
