import { useEffect, useRef, useState } from "react";
import type {
  AiStatus,
  ConnectionCheck,
  SearchSettings,
  SearchSettingsPatch,
  Settings,
  User,
} from "./types";

export type SettingsSection = "account" | "feedback" | "model" | "search" | "users";
export const SETTINGS_SECTIONS: { id: SettingsSection; label: string }[] = [
  { id: "account", label: "Account" },
  { id: "feedback", label: "Feedback" },
  { id: "model", label: "AI Model" },
  { id: "search", label: "Web Search" },
  { id: "users", label: "Global User Accounts" },
];
export function permittedSection(
  user: User,
  section: SettingsSection = "account",
): SettingsSection {
  return user.role === "admin" || section === "account" || section === "feedback" || (user.role === "teacher" && section === "users") ? section : "account";
}
export type ModelForm = {
  base_url: string;
  model: string;
  api_key: string;
  clear_key: boolean;
};
export type SearchForm = {
  enabled: boolean;
  api_key: string;
  clear_key: boolean;
};
export const modelForm = (s: Settings): ModelForm => ({
  base_url: s.ai.base_url,
  model: s.ai.model,
  api_key: "",
  clear_key: false,
});
export const searchForm = (s: SearchSettings): SearchForm => ({
  enabled: s.enabled,
  api_key: "",
  clear_key: false,
});
export function modelPayload(f: ModelForm) {
  return {
    mode: "openai" as const,
    base_url: f.base_url.trim(),
    model: f.model.trim(),
    ...(f.clear_key
      ? { api_key: "" }
      : f.api_key.trim()
        ? { api_key: f.api_key.trim() }
        : {}),
  };
}
export function searchPayload(f: SearchForm): SearchSettingsPatch {
  return {
    enabled: f.enabled,
    ...(f.clear_key
      ? { clear_api_key: true }
      : f.api_key.trim()
        ? { api_key: f.api_key.trim() }
        : {}),
  };
}
export function modelReadbackMatches(s: Settings, f: ModelForm) {
  const p = modelPayload(f);
  return (
    s.ai.mode === "openai" &&
    s.ai.base_url === p.base_url.replace(/\/+$/, "") &&
    s.ai.model === p.model &&
    (!f.clear_key || !s.api_key_set) &&
    (!f.api_key.trim() || f.clear_key || s.api_key_set)
  );
}
export function searchReadbackMatches(s: SearchSettings, f: SearchForm) {
  return (
    s.enabled === f.enabled &&
    (!f.clear_key || (!s.api_key_set && s.api_key_source === "none")) &&
    (!f.api_key.trim() ||
      f.clear_key ||
      (s.api_key_set && s.api_key_source === "saved"))
  );
}
export function modelConnection(ai: AiStatus): ConnectionCheck {
  if (ai.mode !== "openai" || !ai.configured)
    return { status: "not_configured", checked_at: null, message: null };
  if (ai.last_error && ai.connection?.status !== "error") {
    return {status: "error", checked_at: null, message: ai.last_error};
  }
  return (
    ai.connection ?? {
      status: ai.last_error ? "error" : "not_checked",
      checked_at: null,
      message: ai.last_error ?? null,
    }
  );
}
export function connectionText(
  check: ConnectionCheck,
  dirty = false,
  checking = false,
  unavailable = false,
) {
  if (checking)
    return {
      status: "checking",
      label: "Checking…",
      detail: "Testing the saved configuration.",
    };
  if (dirty)
    return {
      status: "not_checked",
      label: "Not checked",
      detail: "Save changes before testing.",
    };
  if (unavailable)
    return {
      status: "not_checked",
      label: "Status unavailable",
      detail: "The saved connection status could not be read back.",
    };
  const label = {
    not_configured: "Not configured",
    not_checked: "Not checked",
    connected: "Last test succeeded",
    error: "Connection issue",
  }[check.status];
  let detail = check.status === "error" ? check.message ?? "" : "";
  if (check.checked_at) {
    const date = new Date(check.checked_at);
    detail = `Last checked: ${Number.isNaN(date.getTime()) ? check.checked_at : date.toLocaleString("en-GB", {dateStyle: "medium", timeStyle: "short"})}.${detail ? ` ${detail}` : ""}`;
  }
  return { status: check.status, label, detail };
}

// Shared only by the two service forms: drafts live in memory, never browser storage.
// A write response is not acknowledgement: only a matching independent GET clears edits.
export function useSavedSettings<S, F extends object>(options: {
  read: () => Promise<S>;
  write: (form: F) => Promise<unknown>;
  toForm: (saved: S) => F;
  matches: (saved: S, form: F) => boolean;
  onSaved?: (saved: S) => void;
}) {
  const optionsRef = useRef(options);
  optionsRef.current = options;
  const [saved, setSaved] = useState<S | null>(null),
    [form, setForm] = useState<F | null>(null);
  const [loading, setLoading] = useState(true),
    [busy, setBusy] = useState<"" | "save" | "test">("");
  const [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [unavailable, setUnavailable] = useState(false);
  const alive = useRef(false),
    operation = useRef(0),
    revision = useRef(0),
    pending = useRef(false);
  const formRef = useRef<F | null>(null),
    savedRef = useRef<S | null>(null);
  const dirty =
    saved !== null &&
    form !== null &&
    JSON.stringify(form) !== JSON.stringify(options.toForm(saved));
  function report(e: unknown, prefix = "") {
    setError(`${prefix}${e instanceof Error ? e.message : "Request failed."}`);
  }
  function install(s: S, reset: boolean) {
    savedRef.current = s;
    setSaved(s);
    setUnavailable(false);
    if (reset) {
      const f = optionsRef.current.toForm(s);
      formRef.current = f;
      setForm(f);
    }
    optionsRef.current.onSaved?.(s);
  }
  async function load() {
    if (pending.current) return;
    const id = ++operation.current,
      edit = revision.current;
    pending.current = true;
    setLoading(true);
    setError("");
    try {
      const s = await optionsRef.current.read();
      if (alive.current && id === operation.current)
        install(s, edit === revision.current);
    } catch (e) {
      if (alive.current && id === operation.current) report(e);
    } finally {
      if (alive.current && id === operation.current) {
        pending.current = false;
        setLoading(false);
      }
    }
  }
  useEffect(() => {
    alive.current = true;
    pending.current = false;
    void load();
    return () => {
      alive.current = false;
      ++operation.current;
    };
    // Options are held in a ref; rerenders must not start another GET.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  function change(patch: Partial<F>) {
    if (!formRef.current) return;
    revision.current++;
    const f = { ...formRef.current, ...patch };
    formRef.current = f;
    setForm(f);
    setNotice("");
    setError("");
  }
  async function save() {
    if (pending.current || !formRef.current) return;
    const draft = { ...formRef.current },
      edit = revision.current,
      id = ++operation.current;
    pending.current = true;
    setBusy("save");
    setError("");
    setNotice("");
    let written = false;
    try {
      await optionsRef.current.write(draft);
      written = true;
      const fresh = await optionsRef.current.read();
      if (!alive.current || id !== operation.current) return;
      if (!optionsRef.current.matches(fresh, draft))
        throw new Error(
          "The saved values do not match. Your edits have been kept.",
        );
      const unchanged = edit === revision.current;
      install(fresh, unchanged);
      setNotice(
        unchanged
          ? "Changes saved and verified."
          : "Saved values verified. Your newer edits are not saved.",
      );
    } catch (e) {
      if (alive.current && id === operation.current) {
        if (written) setUnavailable(true);
        report(
          e,
          written
            ? "Save could not be verified. Your edits have been kept. "
            : "",
        );
      }
    } finally {
      if (alive.current && id === operation.current) {
        pending.current = false;
        setBusy("");
      }
    }
  }
  async function test(probe: () => Promise<unknown>) {
    if (
      pending.current ||
      !formRef.current ||
      !savedRef.current ||
      JSON.stringify(formRef.current) !==
        JSON.stringify(optionsRef.current.toForm(savedRef.current))
    )
      return;
    const id = ++operation.current,
      edit = revision.current;
    pending.current = true;
    setBusy("test");
    setError("");
    setNotice("");
    let failure: unknown;
    try {
      await probe();
    } catch (e) {
      failure = e;
    }
    // A rejected test can still persist a last-check failure. Always read it back.
    try {
      const fresh = await optionsRef.current.read();
      if (alive.current && id === operation.current) {
        if (edit === revision.current) install(fresh, false);
        else setUnavailable(true);
        if (failure) report(failure);
      }
    } catch (e) {
      if (alive.current && id === operation.current) {
        setUnavailable(true);
        report(
          e,
          failure
            ? "Test failed and status could not be read back. "
            : "Test finished, but status could not be read back. ",
        );
      }
    } finally {
      if (alive.current && id === operation.current) {
        pending.current = false;
        setBusy("");
      }
    }
  }
  return {
    saved,
    form,
    loading,
    busy,
    dirty,
    error,
    notice,
    unavailable,
    change,
    load,
    save,
    test,
  };
}
