import type { FormEvent } from "react";
import type { AccessSettings as AccessSettingsValue } from "./types";
import { api } from "./api";
import { ErrorBanner, Loading } from "./ui";
import { useSavedSettings } from "./stage7-settings";
import { useUnsavedChanges } from "./navigation-guard";

export const accessForm = (saved: AccessSettingsValue): AccessSettingsValue => ({
  registration_enabled: saved.registration_enabled,
});
export const accessReadbackMatches = (saved: AccessSettingsValue, draft: AccessSettingsValue) =>
  saved.registration_enabled === draft.registration_enabled;

export default function AccessSettings() {
  const state = useSavedSettings({
    read: api.accessSettings,
    write: api.saveAccessSettings,
    toForm: accessForm,
    matches: accessReadbackMatches,
  });
  const { saved, form, busy, dirty } = state;
  useUnsavedChanges(dirty || !!busy || state.unavailable);
  async function save(event: FormEvent) {
    event.preventDefault();
    await state.save();
  }
  return <section className="card form-card settings-service" aria-labelledby="registration-settings-title" aria-busy={!!busy}>
    <h2 id="registration-settings-title">New student registration</h2>
    <p>Control self-service registration. A valid course invite code is still required when registration is open.</p>
    <p className="settings-helper">Existing accounts can always sign in. Teachers can still create student accounts for their own courses.</p>
    <ErrorBanner error={state.error} retry={!form ? () => void state.load() : undefined} />
    {state.loading ? <Loading /> : saved && form && <>
      <p className="registration-saved-status" role="status">
        {state.unavailable ? "Saved status could not be verified." : `Saved status: ${saved.registration_enabled ? "Open" : "Closed"}`}
      </p>
      {state.notice && <p className="settings-notice" role="status">{state.notice}</p>}
      <form onSubmit={save}>
        <fieldset disabled={!!busy || state.unavailable} className="settings-fields">
          <label className="settings-checkbox">
            <input type="checkbox" checked={form.registration_enabled} onChange={e => state.change({registration_enabled: e.target.checked})} />
            Allow new student registration
          </label>
        </fieldset>
        <div className="settings-actions">
          <button type="submit" className="primary" disabled={!!busy || !dirty || state.unavailable}>{busy === "save" ? "Saving…" : "Save registration setting"}</button>
          {dirty && <span className="settings-unsaved" role="status">Unsaved changes</span>}
          {state.unavailable && <button type="button" className="secondary" disabled={!!busy} onClick={() => void state.load()}>Reload saved setting</button>}
        </div>
      </form>
    </>}
  </section>;
}
