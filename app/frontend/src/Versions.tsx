import { useCallback, useEffect, useState } from "react";
import type {
  VersionList,
  VersionSnapshot,
  VersionDiff,
  VersionEntry,
} from "./types";
import { api } from "./api";

import { dateLabel } from "./study";
import { Loading, Empty, ErrorBanner, Notice, errorMessage } from "./ui";
import Materials from "./Materials";
export function readablePath(path: string) {
  const labels: Record<string, string> = {
    course: "Course",
    sessions: "Sessions",
    questions: "Questions",
    groups: "Groups",
    materials: "Materials",
    _materials: "Materials",
    metadata: "Content",
    order: "Order",
    reference_answers: "Reference answers",
    instructions: "Teaching instructions",
    source_material_ids: "Material sources",
    source_links: "External sources",
    learning_objectives: "Learning objectives",
    title: "Title",
    prompt: "Prompt",
    description: "Description",
    status: "Publication status",
    visibility: "Visibility",
    teaching_language: "Teaching language",
    reference_policy: "Reference policy",
    options: "Options",
    images: "Images",
    excerpt: "Extracted content",
    source_label: "Provenance",
  };
  return path
    .replace(/^\//, "")
    .split(/[/.]/)
    .map((p) => {
      const bracket = p.indexOf("[");
      const field = bracket < 0 ? p : p.slice(0, bracket);
      return (
        (labels[field] || field.replaceAll("_", " ")) +
        (bracket < 0 ? "" : p.slice(bracket))
      );
    })
    .join(" › ");
}
export function ReadableValue({ value }: { value: unknown }) {
  if (value == null) return <span className="diff-empty">—</span>;
  if (typeof value !== "object")
    return (
      <span className="preserve-text">
        {typeof value === "boolean" ? (value ? "Yes" : "No") : String(value)}
      </span>
    );
  if (Array.isArray(value))
    return (
      <ul className="diff-values">
        {value.map((v, i) => (
          <li key={i}>
            <ReadableValue value={v} />
          </li>
        ))}
      </ul>
    );
  return (
    <dl className="diff-properties">
      {Object.entries(value).map(([k, v]) => (
        <div key={k}>
          <dt>{readablePath(k)}</dt>
          <dd>
            <ReadableValue value={v} />
          </dd>
        </div>
      ))}
    </dl>
  );
}
export default function Versions({
  courseId,
  unsaved = false,
  onChanged,
  onOpen,
}: {
  courseId: string;
  unsaved?: boolean;
  onChanged: () => void;
  onOpen?: (sid: string, vid: string) => void;
}) {
  const [list, setList] = useState<VersionList | null>(null),
    [snapshot, setSnapshot] = useState<VersionSnapshot | null>(null),
    [diff, setDiff] = useState<VersionDiff | null>(null),
    [selected, setSelected] = useState<VersionEntry | null>(null),
    [label, setLabel] = useState(""),
    [restore, setRestore] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [success, setSuccess] = useState("");
  const load = useCallback(async () => {
    try {
      setList(await api.versions(courseId));
    } catch (e) {
      setError(errorMessage(e));
    }
  }, [courseId]);
  useEffect(() => {
    void load();
  }, [load]);
  async function browse(v: VersionEntry) {
    setBusy(true);
    setError("");
    try {
      const [s, d] = await Promise.all([
        api.version(courseId, v.id),
        api.versionDiff(courseId, v.id),
      ]);
      setSnapshot(s);
      setDiff(d);
      setSelected(v);
      setRestore(false);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  async function publish(restoring = false) {
    if (restoring && !selected) return;
    setBusy(true);
    setError("");
    try {
      const v = restoring
        ? await api.restoreVersion(courseId, selected!.id, label)
        : await api.publishVersion(courseId, label);
      const next = await api.versions(courseId);
      if (
        next.current_version_id !== v.id ||
        !next.versions.some((x) => x.id === v.id)
      )
        throw new Error("Published version could not be verified.");
      setList(next);
      setSnapshot(null);
      setDiff(null);
      setSelected(null);
      setRestore(false);
      setLabel("");
      setSuccess(
        `Course version ${v.number} published. Historical records are unchanged.`,
      );
      onChanged();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="versions-panel">
      <div className="section-heading">
        <h2>{"Course versions"}</h2>
        <button
          className="secondary"
          disabled={busy}
          onClick={() => void load()}
        >
          {"Refresh versions"}
        </button>
      </div>
      <p className="section-intro">
        {
          "An immutable edition covers the complete course: sessions, groups, questions, instructions, references and materials. Availability is operational and is never restored. Save local edits before publishing."
        }
      </p>
      <ErrorBanner error={error} />
      {success && <Notice>{success}</Notice>}
      {!list ? (
        <Loading />
      ) : (
        <>
          <div className="card form-card">
            <div className="section-heading">
              <strong>
                {list.has_unpublished_changes
                  ? "Saved draft has unpublished changes"
                  : "Saved draft matches the published edition"}
              </strong>
              <span>
                {"Current edition"}:{" "}
                {list.versions.find((v) => v.id === list.current_version_id)
                  ?.number || "—"}
              </span>
            </div>
            {unsaved && (
              <p className="material-warning">
                {"Local unsaved edits are not included. Save them first."}
              </p>
            )}
            <label>
              {"Publication / restore label (optional)"}
              <input value={label} onChange={(e) => setLabel(e.target.value)} />
            </label>
            <button
              className="primary"
              disabled={busy || unsaved}
              onClick={() => void publish()}
            >
              {"Publish complete course draft"}
            </button>
          </div>
          <div className="table-wrap card">
            <table>
              <thead>
                <tr>
                  <th>{"Edition"}</th>
                  <th>{"Label"}</th>
                  <th>{"Created"}</th>
                  <th>{"Author"}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {list.versions.map((v) => (
                  <tr key={v.id}>
                    <td>
                      v{v.number}{" "}
                      {v.id === list.current_version_id && (
                        <span className="small-tag">{"Current"}</span>
                      )}
                    </td>
                    <td>{v.label || "—"}</td>
                    <td>{dateLabel(v.created_at)}</td>
                    <td>{v.created_by}</td>
                    <td>
                      <button
                        className="text-button"
                        disabled={busy}
                        onClick={() => void browse(v)}
                      >
                        {"Browse & compare"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!list.versions.length && (
              <Empty title={"No published editions yet"} />
            )}
          </div>
        </>
      )}
      {snapshot && selected && (
        <section className="card form-card version-snapshot">
          <div className="section-heading">
            <h2>
              {"Immutable edition"} v{snapshot.number} · {snapshot.label}
            </h2>
            <button
              className="secondary"
              disabled={busy || unsaved}
              onClick={() => setRestore(true)}
            >
              {"Restore as new edition"}
            </button>
          </div>
          {restore && (
            <div className="notice confirmation">
              <span>
                {
                  "Replace the saved course draft with this snapshot and publish a NEW edition? Learning records and availability schedules remain unchanged."
                }
              </span>
              <button
                className="primary"
                disabled={busy || unsaved}
                onClick={() => void publish(true)}
              >
                {"Confirm restore"}
              </button>
              <button className="secondary" onClick={() => setRestore(false)}>
                {"Cancel"}
              </button>
            </div>
          )}
          <h3>
            {snapshot.course.code} · {snapshot.course.title}
          </h3>
          <p>{snapshot.course.description}</p>
          <h3>{"Compared with current saved draft"}</h3>
          {diff?.changes.length ? (
            <div className="diff-list">
              {diff.changes.map((c, i) => (
                <article className="diff-card" key={i}>
                  <h4>{readablePath(c.path)}</h4>
                  <div className="diff-columns">
                    <section>
                      <strong>{"Selected edition"}</strong>
                      <ReadableValue value={c.before} />
                    </section>
                    <section>
                      <strong>{"Current draft"}</strong>
                      <ReadableValue value={c.after} />
                    </section>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <p>{"No content differences."}</p>
          )}
          {snapshot.sessions.map((s) => (
            <details key={s.id} className="snapshot-session">
              <summary>
                {s.number}. {s.title} · {s.questions.length} {"questions"}
              </summary>
              {onOpen && (
                <button
                  className="text-button"
                  onClick={() => onOpen(s.id, snapshot.id)}
                >
                  {"Open historical teaching workspace"}
                </button>
              )}
              <p>{s.subtitle}</p>
              <h4>{"Teaching instructions"}</h4>
              <p className="preserve-text">{s.instructions}</p>
              {s.groups.map((g) => (
                <div key={g.id}>
                  <h4>{g.title}</h4>
                  <p>{g.description}</p>
                  {s.questions
                    .filter((q) => q.group_id === g.id)
                    .map((q) => (
                      <article className="snapshot-question" key={q.id}>
                        <strong>
                          {q.ordinal}. {q.prompt}
                        </strong>
                        {q.options.length > 0 && (
                          <ul>
                            {q.options.map((o, i) => (
                              <li key={i}>{o}</li>
                            ))}
                          </ul>
                        )}
                        <div className="question-images">
                          {q.images.map((img, i) => (
                            <img key={i} src={img.url} alt={img.alt} />
                          ))}
                        </div>
                        <p>
                          <strong>{"Reference"}</strong> ·{" "}
                          {s.reference_answers?.[q.id] || "—"}
                        </p>
                        <small>{q.source_label}</small>
                      </article>
                    ))}
                </div>
              ))}
              <Materials
                teacher
                materials={s.materials}
                versionId={snapshot.id}
              />
            </details>
          ))}
        </section>
      )}
    </section>
  );
}
