import { Globe } from "lucide-react";
import "./web-search.css";
import type { AiStatus } from "./types";
import { useUiText } from "./uiText";

export function webSearchAvailable(ai?: AiStatus) {
  return (
    ai?.mode === "openai" &&
    !!ai.web_search?.enabled &&
    !!ai.web_search?.configured
  );
}

export default function SearchToggle({
  ai,
  value,
  disabled,
  onChange,
}: {
  ai: AiStatus;
  value: boolean;
  disabled?: boolean;
  onChange: (value: boolean) => void;
}) {
  const { t } = useUiText();
  const available = webSearchAvailable(ai);
  const checked = available && value;
  return (
    <div className="composer-search">
      <button
        type="button"
        className={`web-search-switch ${checked ? "active" : ""}`}
        role="switch"
        aria-label={t("searchToggle")}
        aria-checked={checked}
        disabled={disabled || !available}
        onClick={() => onChange(!value)}
      >
        <Globe size={14} />
        <span>{t("searchToggle")}</span>
        <span className="switch-track" aria-hidden="true">
          <span />
        </span>
        <small>{t(checked ? "searchOn" : "searchOff")}</small>
      </button>
      {!available && (
        <small className="search-unavailable">
          {t(ai.mode === "demo" ? "searchDemo" : "searchUnavailable")}
        </small>
      )}
    </div>
  );
}
