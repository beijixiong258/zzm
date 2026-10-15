import { useEffect, useState, type FormEvent } from "react";
import { CalendarClock, Check, Lock } from "lucide-react";
import type { SessionDetail, Availability as State } from "./types";
import { api } from "./api";
import {
  effectiveAvailability,
  localDateTime,
  schedulePayload,
} from "./stage2";
import { ErrorBanner, Notice, errorMessage } from "./ui";
import HelpPopover from "./HelpPopover";
import { useUnsavedChanges } from "./navigation-guard";
import "./availability.css";

export function AvailabilityBadge({ session }: { session: State }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 15000);
    return () => clearInterval(timer);
  }, []);
  const e = effectiveAvailability(session, now),
    scheduled = !!(session.starts_at || session.ends_at);
  const reason =
    e.reason === "not_started"
      ? "not started"
      : e.reason === "ended"
        ? "ended"
        : e.active
          ? "open now"
          : "closed now";
  const Icon = scheduled ? CalendarClock : e.active ? Check : Lock;
  return (
    <span
      className={`availability-badge ${scheduled ? "scheduled" : e.active ? "open" : "closed"}`}
    >
      <Icon size={14} aria-hidden="true" />
      {scheduled ? `Scheduled · ${reason}` : e.active ? "Open" : "Closed"}
    </span>
  );
}
export default function Availability({
  session,
  onSaved,
  onDirtyChange,
  onBusyChange,
}: {
  session: SessionDetail;
  onSaved: (s: SessionDetail) => void;
  onDirtyChange?: (dirty: boolean) => void;
  onBusyChange?: (busy: boolean) => void;
}) {
  const [active, setActive] = useState(session.active !== false),
    [start, setStart] = useState(localDateTime(session.starts_at)),
    [end, setEnd] = useState(localDateTime(session.ends_at)),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [success, setSuccess] = useState(false);
  const dirty =
    active !== (session.active !== false) ||
    start !== localDateTime(session.starts_at) ||
    end !== localDateTime(session.ends_at);
  useUnsavedChanges(dirty);
  useEffect(() => {
    onDirtyChange?.(dirty);
    return () => onDirtyChange?.(false);
  }, [dirty, onDirtyChange]);
  useEffect(() => {
    onBusyChange?.(busy);
    return () => onBusyChange?.(false);
  }, [busy, onBusyChange]);
  useEffect(() => {
    setActive(session.active !== false);
    setStart(localDateTime(session.starts_at));
    setEnd(localDateTime(session.ends_at));
  }, [session.active, session.starts_at, session.ends_at]);
  async function save(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    setSuccess(false);
    try {
      const payload = schedulePayload(active, start, end);
      await api.updateSession(session.id, payload);
      const verified = await api.session(session.id);
      if (
        verified.active !== payload.active ||
        (verified.starts_at ? Date.parse(verified.starts_at) : null) !==
          (payload.starts_at ? Date.parse(payload.starts_at) : null) ||
        (verified.ends_at ? Date.parse(verified.ends_at) : null) !==
          (payload.ends_at ? Date.parse(payload.ends_at) : null)
      )
        throw new Error("Availability changes could not be verified.");
      onSaved(verified);
      setSuccess(true);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section id="teacher-availability" className="card availability-editor">
      <div className="section-heading">
        <h2>Classroom availability</h2>
        <AvailabilityBadge session={session} />
      </div>
      <ErrorBanner error={error} />
      {success && <Notice>Availability saved and read back.</Notice>}
      {dirty && (
        <p className="av-dirty" role="status">
          Unapplied availability changes
        </p>
      )}
      <details>
        <summary>Schedule &amp; access</summary>
        <div className="tw-section-heading">
          <p>
            Changes take effect immediately, separately from saving or
            publishing content.
          </p>
          <HelpPopover label="Help with classroom availability">
            A schedule overrides the manual state. Closing stops new learning
            turns; history and materials stay readable.
          </HelpPopover>
        </div>
        <form onSubmit={(e) => void save(e)}>
          <fieldset disabled={busy} className="teacher-config-fields">
            <label className="inline-check">
              <input
                type="checkbox"
                checked={active}
                disabled={!!start || !!end}
                onChange={(e) => {
                  setActive(e.target.checked);
                  setSuccess(false);
                }}
              />
              Open without a schedule
            </label>
            <div className="form-grid">
              <label>
                Starts at (inclusive)
                <input
                  type="datetime-local"
                  value={start}
                  onChange={(e) => {
                    setStart(e.target.value);
                    setSuccess(false);
                  }}
                />
              </label>
              <label>
                Ends at (exclusive)
                <input
                  type="datetime-local"
                  value={end}
                  onChange={(e) => {
                    setEnd(e.target.value);
                    setSuccess(false);
                  }}
                />
              </label>
            </div>
            <small>
              Local timezone: {Intl.DateTimeFormat().resolvedOptions().timeZone}{" "}
              ·{" "}
              {start || end
                ? "Schedule overrides manual access."
                : "Manual access applies."}
            </small>
            <div className="button-row">
              <button className="primary" disabled={!dirty}>
                {busy ? "Applying…" : "Apply availability now"}
              </button>
              <button
                type="button"
                className="secondary"
                disabled={!start && !end}
                onClick={() => {
                  setStart("");
                  setEnd("");
                  setSuccess(false);
                }}
              >
                Clear schedule
              </button>
            </div>
          </fieldset>
        </form>
      </details>
    </section>
  );
}
