import { useState, type FormEvent } from "react";
import {
  ArrowRight,
  Compass,
  MessageSquare,
  LoaderCircle,
} from "lucide-react";
import { api } from "./api";
import type { Bootstrap } from "./types";
import { useUiText } from "./uiText";
import { Brand, ErrorBanner, errorMessage } from "./ui";
export default function Login({
  bootstrap,
  onAuthenticated,
}: {
  bootstrap: Bootstrap | null;
  onAuthenticated: () => Promise<void>;
}) {
  const { t } = useUiText();
  const [register, setRegister] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [fields, setFields] = useState({
    name: "",
    email: "",
    password: "",
    join_code: "",
  });
  const update = (key: keyof typeof fields, value: string) =>
    setFields((f) => ({ ...f, [key]: value }));
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy("login");
    setError("");
    try {
      if (register)
        await api.register(
          fields.name,
          fields.email,
          fields.password,
          fields.join_code,
        );
      else await api.login(fields.email, fields.password);
      await onAuthenticated();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy("");
    }
  }
  return (
    <div className="login-layout login-brand-layout">
      <section className="login-story">
        <div className="eyebrow">
          <span className="small-line" /> {t("learningSpace")}
        </div>
        <h1>{t("welcome")}</h1>
        <p>{t("loginIntro")}</p>
        <div className="study-illustration" aria-hidden="true">
          <div className="illustration-orbit" />
          <div className="illustration-card card-one">
            <Compass size={30} strokeWidth={1.2} />
            <span>{t("exploreIdea")}</span>
            <div className="ink-line" />
            <div className="ink-line short" />
          </div>
          <div className="illustration-card card-two">
            <MessageSquare size={29} strokeWidth={1.3} />
            <span>{t("findVoice")}</span>
            <div className="ink-line" />
            <div className="ink-line short" />
          </div>
          <span className="orbit-dot" />
        </div>
        <div className="story-footer">
          <span>01 / {t("think")}</span>
          <span>02 / {t("discuss")}</span>
          <span>03 / {t("reflect")}</span>
        </div>
      </section>
      <section className="login-form-panel">
        <div className="login-form-heading">
          <Brand appearance="panel" />
          <h2>{register ? t("register") : t("loginTitle")}</h2>
        </div>
        <ErrorBanner error={error} />
        <form onSubmit={submit}>
          {register && (
            <label>
              {t("name")}
              <input
                required
                autoComplete="name"
                value={fields.name}
                onChange={(e) => update("name", e.target.value)}
              />
            </label>
          )}
          <label>
            {t("email")}
            <input
              type="email"
              required
              autoComplete="username"
              value={fields.email}
              onChange={(e) => update("email", e.target.value)}
              placeholder="you@example.edu"
            />
          </label>
          <label>
            {t("password")}
            <input
              type="password"
              required
              autoComplete={register ? "new-password" : "current-password"}
              minLength={register ? 8 : undefined}
              maxLength={512}
              pattern={
                register ? "(?=.*[A-Za-z])(?=.*[0-9]).{8,512}" : undefined
              }
              value={fields.password}
              onChange={(e) => update("password", e.target.value)}
            />
          </label>
          {register && (
            <label>
              {t("joinCode")}
              <input
                required
                value={fields.join_code}
                onChange={(e) => update("join_code", e.target.value)}
              />
            </label>
          )}
          <button className="primary full" disabled={!!busy || !bootstrap}>
            {busy === "login" ? (
              <LoaderCircle size={17} className="spin" />
            ) : (
              <ArrowRight size={17} />
            )}{" "}
            {register ? t("register") : t("signIn")}
          </button>
        </form>
        <p className="switch-auth">
          {register ? t("haveAccount") : t("needAccount")}{" "}
          <button
            className="text-button"
            onClick={() => setRegister(!register)}
          >
            {register ? t("signIn") : t("register")}
          </button>
        </p>
      </section>
    </div>
  );
}
