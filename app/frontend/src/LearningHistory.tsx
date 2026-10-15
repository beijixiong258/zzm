import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import type { LearningRun } from "./types";

import { dateLabel } from "./study";
import { Loading, ErrorBanner, Empty, Status, errorMessage } from "./ui";
export default function LearningHistory({
  onOpen,
}: {
  onOpen: (sid: string, vid: string) => void;
}) {
  const [runs, setRuns] = useState<LearningRun[]>([]),
    [loading, setLoading] = useState(true),
    [error, setError] = useState("");
  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setRuns(await api.history());
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <div className="eyebrow">YOUR SAVED WORK</div>
          <h1>{"My Learning"}</h1>
          <p>
            {
              "Revisit your original responses and conversations in the edition you studied."
            }
          </p>
        </div>
        <button
          className="secondary"
          disabled={loading}
          onClick={() => void load()}
        >
          {"Refresh"}
        </button>
      </div>
      <ErrorBanner error={error} retry={load} />
      {loading ? (
        <Loading />
      ) : !runs.length ? (
        <Empty title={"No saved learning runs yet"} />
      ) : (
        <section className="card history-list">
          {runs.map((r) => (
            <button
              className="history-row"
              key={`${r.session.id}:${r.version.id}`}
              onClick={() => onOpen(r.session.id, r.version.id)}
            >
              <span className="session-number">{r.session.number}</span>
              <span className="history-title">
                <small>
                  {r.course.code} · {r.course.title}
                </small>
                <strong>{r.session.title}</strong>
                <span>
                  Edition {r.version.number} · {r.version.label} · {r.answered}/
                  {r.total} responses saved
                </span>
                <small>{dateLabel(r.last_active)}</small>
              </span>
              <Status status={r.status} />
            </button>
          ))}
        </section>
      )}
    </div>
  );
}
