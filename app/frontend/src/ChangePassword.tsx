import { useState, type FormEvent } from "react";
import { KeyRound, LoaderCircle, LogOut } from "lucide-react";
import { api } from "./api";
import type { User } from "./types";
import { useUiText } from "./uiText";
import { ErrorBanner, errorMessage } from "./ui";

export default function ChangePassword({
  user,
  onComplete,
  onLogout,
}: {
  user: User;
  onComplete: (user: User) => void;
  onLogout: () => Promise<void>;
}) {
  const { t } = useUiText();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (next !== repeat) {
      setError(t("passwordMismatch"));
      return;
    }
    if (next === current) {
      setError(t("passwordUnchanged"));
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api.changePassword(current, next);
      const verified = (await api.me()).user;
      if (verified.must_change_password)
        throw new Error("The password change was not confirmed by the server.");
      setCurrent("");
      setNext("");
      setRepeat("");
      onComplete(verified);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="password-setup-page">
      <section className="password-setup-card card">
        <span className="password-setup-icon">
          <KeyRound size={25} />
        </span>
        <div className="eyebrow">AIcademiya · {user.name}</div>
        <h1>{t("firstPasswordTitle")}</h1>
        <p className="password-setup-intro">{t("firstPasswordIntro")}</p>
        <p className="password-account">{user.email}</p>
        <ErrorBanner error={error} />
        <form onSubmit={submit}>
          <label>
            {t("temporaryPassword")}
            <input
              type="password"
              autoComplete="current-password"
              required
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              disabled={busy}
            />
          </label>
          <label>
            {t("newPassword")}
            <input
              type="password"
              autoComplete="new-password"
              minLength={8}
              pattern="(?=.*[A-Za-z])(?=.*[0-9]).{8,512}"
              maxLength={512}
              required
              value={next}
              onChange={(e) => setNext(e.target.value)}
              disabled={busy}
            />
          </label>
          <label>
            {t("repeatPassword")}
            <input
              type="password"
              autoComplete="new-password"
              minLength={8}
              pattern="(?=.*[A-Za-z])(?=.*[0-9]).{8,512}"
              maxLength={512}
              required
              value={repeat}
              onChange={(e) => setRepeat(e.target.value)}
              disabled={busy}
            />
          </label>
          <small>{t("passwordLengthHelp")}</small>
          {repeat && next !== repeat && (
            <p className="password-validation" role="status">
              {t("passwordMismatch")}
            </p>
          )}
          <button
            className="primary full"
            disabled={busy || !current || next.length < 8 || repeat !== next}
          >
            {busy ? (
              <LoaderCircle className="spin" size={16} />
            ) : (
              <KeyRound size={16} />
            )}{" "}
            {t("passwordContinue")}
          </button>
        </form>
        <button
          className="text-button password-signout"
          disabled={busy}
          onClick={() => void onLogout()}
        >
          <LogOut size={14} />
          {t("logout")}
        </button>
      </section>
    </main>
  );
}
