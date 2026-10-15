import type { FormEvent } from "react";
import { CheckCircle2, Search, Save } from "lucide-react";
import { api } from "./api";
import { ErrorBanner, Loading } from "./ui";
import HelpPopover from "./HelpPopover";
import { useUnsavedChanges } from "./navigation-guard";
import {
  searchForm,
  searchPayload,
  searchReadbackMatches,
  useSavedSettings,
} from "./stage7-settings";
import { SettingsConnection } from "./ModelSettings";
import "./settings-workspace.css";

export default function SearchSettings() {
  const state = useSavedSettings({
    read: api.searchSettings,
    write: (f: ReturnType<typeof searchForm>) =>
      api.saveSearchSettings(searchPayload(f)),
    toForm: searchForm,
    matches: searchReadbackMatches,
  });
  const { saved, form, dirty, busy } = state;
  useUnsavedChanges(dirty || !!busy);
  async function save(event: FormEvent) {
    event.preventDefault();
    await state.save();
  }
  if (state.loading) return <Loading />;
  if (!saved || !form)
    return (
      <div className="settings-service">
        <h2>Web Search</h2>
        <ErrorBanner error={state.error} retry={() => void state.load()} />
      </div>
    );
  const keyState =
    saved.api_key_source === "environment"
      ? "Using an environment key."
      : saved.api_key_set
        ? "A key is saved."
        : "No key is configured.";
  return (
    <section
      className="settings-service"
      aria-labelledby="search-settings-title"
      aria-busy={!!busy}
    >
      <div className="settings-section-heading">
        <h2 id="search-settings-title">Web Search</h2>
        <span className="settings-provider">Tavily</span>
      </div>
      <ErrorBanner error={state.error} />
      {state.notice && (
        <p className="settings-notice" role="status">
          <CheckCircle2 size={17} aria-hidden="true" />
          {state.notice}
        </p>
      )}
      <form onSubmit={save}>
        <fieldset disabled={!!busy} className="settings-fields">
          <label className="settings-checkbox">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(e) => state.change({ enabled: e.target.checked })}
            />
            Allow web search
          </label>
          <p className="settings-helper">
            Makes search available. Learners still choose whether to search in
            each conversation.
          </p>
          <div className="settings-field-title">
            <label htmlFor="settings-search-key">API key</label>
            <HelpPopover label="Help with Tavily API key">
              Leave blank to keep the current key, or enter a replacement.
              Clearing creates an explicit server override; an environment key
              will not be reused.
            </HelpPopover>
          </div>
          <input
            id="settings-search-key"
            type="password"
            autoComplete="off"
            spellCheck={false}
            value={form.api_key}
            disabled={form.clear_key}
            onChange={(e) => state.change({ api_key: e.target.value })}
            placeholder={
              saved.api_key_set
                ? "Leave blank to keep the current key"
                : "Enter a Tavily key"
            }
            aria-describedby="search-key-state"
          />
          <p id="search-key-state" className="settings-helper">
            {keyState}
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
          {form.clear_key && (
            <p className="settings-clear-note">
              Search will have no key after saving, including any environment
              key.
            </p>
          )}
        </fieldset>
        <SettingsConnection
          check={saved.connection}
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
            disabled={
              !!busy ||
              dirty ||
              !saved.enabled ||
              !saved.configured ||
              state.unavailable
            }
            onClick={() =>
              void state.test(async () => {
                const result = await api.testSearchSettings();
                if (!result.ok) throw new Error(result.message);
              })
            }
          >
            <Search size={16} aria-hidden="true" />
            {busy === "test" ? "Testing…" : "Test search"}
          </button>
          <HelpPopover label="About testing web search">Uses saved settings for one public query and consumes search quota. No classroom content is sent.</HelpPopover>
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
