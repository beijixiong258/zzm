import {useContext, type ReactNode} from "react";
import {LiveConnectionContext,liveConnectionLabel} from "./live-connection";
import {
  AlertCircle,
  LoaderCircle,
  BookOpen,
  Check,
  FlaskConical,
  Radio,
  X,
} from "lucide-react";
import { useUiText } from "./uiText";
import type { AiStatus, StudyStatus } from "./types";
import "./brand.css";
export function Brand({onNavigateHome, appearance = "standard"}: {
  onNavigateHome?: () => void;
  appearance?: "standard" | "panel";
} = {}) {
  return (
    <a className={`brand brand--${appearance}`} href="#/home" aria-label="AIcademiya · Course Home"
      onClick={(e) => { if (onNavigateHome && !e.ctrlKey && !e.metaKey && !e.shiftKey && !e.altKey) { e.preventDefault(); onNavigateHome(); } }}>
      <span className="brand-mark">
        <img src={appearance === "panel" ? "/aicademiya-mark-light.svg" : "/aicademiya-mark.svg"} width={72} height={76} alt="" />
      </span>
      <span className="brand-copy">
        <span className="brand-name">AIcademiya</span>
        <span className="brand-sub">LEARN WITH INTENTION</span>
      </span>
    </a>
  );
}
export function Loading() {
  const { t } = useUiText();
  return (
    <div className="loading" role="status">
      <LoaderCircle className="spin" size={22} />
      {t("loading")}
    </div>
  );
}
export function ErrorBanner({
  error,
  onClose,
  retry,
}: {
  error: string;
  onClose?: () => void;
  retry?: () => void;
}) {
  const { t } = useUiText();
  if (!error) return null;
  return (
    <div className="error-banner" role="alert">
      <AlertCircle size={20} />
      <div>
        <strong>{t("error")}</strong>
        <p>{error}</p>
        {retry && (
          <button className="text-button" onClick={retry}>
            {t("retry")}
          </button>
        )}
      </div>
      {onClose && (
        <button
          className="icon-button"
          aria-label={t("close")}
          onClick={onClose}
        >
          <X size={17} />
        </button>
      )}
    </div>
  );
}
export function Notice({ children }: { children: ReactNode }) {
  return (
    <div className="notice">
      <Check size={17} />
      {children}
    </div>
  );
}
export function Status({
  status,
}: {
  status: StudyStatus | "draft" | "published";
}) {
  const { t } = useUiText();
  return (
    <span className={`status status-${status}`}>
      <span />
      {t(status)}
    </span>
  );
}
export function connectionLabel(ai: AiStatus) {
  if (ai.mode === "demo") return {status: "fixture", text: "Test fixture"};
  if (!ai.configured) return {status: "not_configured", text: "Not configured"};
  if (ai.last_error || ai.connection?.status === "error") return {status: "error", text: "Connection issue"};
  if (ai.connection?.status === "connected") return {status: "connected", text: "Last check passed"};
  return {status: "not_checked", text: "Not checked"};
}
export function AiBadge({ai, detail = false}: {ai: AiStatus; detail?: boolean}) {
  const live=useContext(LiveConnectionContext);
  const state = ai.mode!=="demo"&&live ? liveConnectionLabel(live) : connectionLabel(ai);
  const checked = live ? live.checked_at : ai.connection?.checked_at;
  const model = live ? live.model : ai.model;
  return <div className={`ai-badge connection-${state.status}`} title={live?.message}>
    <span className="ai-caption">{ai.mode === "demo" ? <FlaskConical size={14} aria-hidden="true" /> : <Radio size={14} aria-hidden="true" />} {ai.mode === "demo" ? "Development fixture" : "Active AI Model"}</span>
    {detail && <strong className="ai-model-name" title={model}>{ai.mode === "demo" ? "Development fixture" : model || "No model configured"}</strong>}
    <span className="ai-connection-state">{state.status === "connected" ? <Check size={13} aria-hidden="true" /> : state.status === "error" ? <AlertCircle size={13} aria-hidden="true" /> : null}{state.text}</span>
    {detail && checked && <small>Last checked <time dateTime={checked}>{new Date(checked).toLocaleString("en-GB", {dateStyle:"medium",timeStyle:"short"})}</time></small>}
    {detail && ai.mode!=="demo" && live && <small>Auto-check every 30s</small>}
  </div>;
}
export function Empty({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty">
      <BookOpen size={32} strokeWidth={1.3} />
      <h3>{title}</h3>
      {description && <p>{description}</p>}
      {children}
    </div>
  );
}
export const errorMessage = (error: unknown) =>
  error instanceof Error ? error.message : String(error);
