import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { SessionDetail, SourceReview } from "./types";
import { teachingPreviewInput, teachingPreviewKey } from "./teaching-profile";
import { errorMessage } from "./ui";
import HelpPopover from "./HelpPopover";
import { teachingPhaseLabels } from "./teaching-profile";
import TeacherExtractionReport from "./TeacherExtractionReport";
import "./teacher-workbench.css";
export function sourceEvidenceUsage(review: SourceReview) {
  const count = (items: SourceReview["public_evidence"]) =>
    items.reduce((sum, item) => sum + Array.from(item.excerpt).length, 0);
  return {
    publicChars: count(review.public_evidence),
    privateChars: count(review.private_evidence),
  };
}
const phases = [
  "warmup",
  "worksheet",
  "quiz",
  "reading",
  "wrap_up",
  "complete",
] as const;
export default function TeachingSourceReview({
  saved,
  draft,
  disabled,
}: {
  saved: SessionDetail;
  draft: SessionDetail;
  disabled?: boolean;
}) {
  const [question, setQuestion] = useState("");
  const [phase, setPhase] = useState<(typeof phases)[number]>("worksheet");
  const [overlay, setOverlay] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [result, setResult] = useState<{
    key: string;
    data: SourceReview;
  } | null>(null);
  const key = JSON.stringify([
    saved,
    teachingPreviewKey(draft),
    question,
    phase,
    overlay,
  ]);
  const current = useRef(key);
  current.current = key;
  const request = useRef(0);
  useEffect(() => {
    request.current++;
    setBusy(false);
    setError("");
    return () => {
      request.current++;
    };
  }, [key]);
  useEffect(() => {
    if (question && !saved.questions.some((q) => q.id === question))
      setQuestion("");
  }, [saved.questions, question]);
  async function review() {
    const token = ++request.current,
      requested = key;
    setBusy(true);
    setError("");
    try {
      const data = await api.sourceReview(saved.id, {
        ...(overlay ? teachingPreviewInput(draft) : {}),
        question_id: question || null,
        phase,
      });
      if (token === request.current && requested === current.current)
        setResult({ key: requested, data });
    } catch (e) {
      if (token === request.current && requested === current.current)
        setError(errorMessage(e));
    } finally {
      if (token === request.current) setBusy(false);
    }
  }
  const visible = result?.key === key ? result.data : null;
  const usage = visible ? sourceEvidenceUsage(visible) : null;
  return (
    <section
      className="tw-source card"
      aria-label="Sources & instructions"
      aria-busy={busy}
    >
      {error && (
        <p role="alert" className="tw-warning">
          {error} Your edits are unchanged.
        </p>
      )}
      {result && !visible && (
        <p role="status" className="tw-warning">
          Review inputs changed. Old results are hidden; review again.
        </p>
      )}
      <details className="tw-review-entry">
        <summary>Sources &amp; instructions</summary>
        <div className="tw-section-heading">
          <p>
            Review server-compiled instructions and selected evidence. No AI
            request.
          </p>
          <HelpPopover label="Help with source review">
            This selection uses saved questions, answers and materials. It is
            not a full live request with learner history or web search, or proof
            that every figure was read.
          </HelpPopover>
        </div>
        <div className="tw-review-controls">
          <label>
            Saved question
            <select
              aria-label="Source review question"
              value={question}
              disabled={disabled}
              onChange={(e) => setQuestion(e.target.value)}
            >
              <option value="">No specific question</option>
              {saved.questions.map((q) => (
                <option key={q.id} value={q.id}>
                  Q{q.ordinal} · {q.prompt}
                </option>
              ))}
            </select>
          </label>
          <label>
            Teaching phase
            <select
              aria-label="Source review phase"
              value={phase}
              disabled={disabled}
              onChange={(e) => setPhase(e.target.value as typeof phase)}
            >
              {phases.map((p) => (
                <option key={p} value={p}>
                  {p === "complete" ? "Complete" : teachingPhaseLabels[p]}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label className="tw-checkbox">
          <input
            type="checkbox"
            checked={overlay}
            disabled={disabled}
            onChange={(e) => setOverlay(e.target.checked)}
          />
          Use unsaved teaching instructions
        </label>
        <p className="tw-muted">
          Only instructions, framework, goals, language and eligibility use this
          overlay. Questions, answers and materials always use the saved draft.
        </p>
        <button
          className="secondary"
          disabled={disabled || busy}
          onClick={() => void review()}
        >
          {busy ? "Reviewing…" : "Review sources & instructions"}
        </button>
        {visible && (
          <div className="tw-source-result">
            <p className="tw-source-label">
              {visible.scope === "unsaved_instruction_overlay"
                ? "Unsaved instruction overlay"
                : "Saved draft"}{" "}
              · {visible.public_evidence.length} public snippet
              {visible.public_evidence.length === 1 ? "" : "s"} ·{" "}
              {visible.private_evidence.length} private snippet
              {visible.private_evidence.length === 1 ? "" : "s"}
            </p>
            {!!visible.warnings.length && (
              <ul className="tw-warning">
                {visible.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            )}
            {!!visible.compiled.warnings.length && (
              <ul className="tw-warning">
                {visible.compiled.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            )}
            <details>
              <summary>Exact compiled instructions</summary>
              <pre className="tw-exact-text">{visible.compiled.text}</pre>
              {visible.compiled.sections.map((s) => (
                <section key={s.id}>
                  <h4>{s.title}</h4>
                  <p>{s.text}</p>
                </section>
              ))}
            </details>
            {(
              [
                ["Public selected evidence", visible.public_evidence],
                [
                  "Private selected evidence · teacher-only",
                  visible.private_evidence,
                ],
              ] as const
            ).map(([title, evidence]) => (
              <details key={title}>
                <summary>
                  {title} ({evidence.length})
                </summary>
                {!evidence.length && <p>No snippets for this selection.</p>}
                {evidence.map((item, i) => (
                  <details key={`${item.material_id}:${i}`}>
                    <summary>
                      {item.source_label} · Source {i + 1}
                    </summary>
                    <p className="tw-muted">
                      Material ID: <code>{item.material_id}</code>
                    </p>
                    {item.warning && (
                      <p className="tw-warning">{item.warning}</p>
                    )}
                    <pre className="tw-exact-text">{item.excerpt}</pre>
                  </details>
                ))}
              </details>
            ))}
            <details>
              <summary>Current instructor example · teacher-only</summary>
              {visible.private_reference ? (
                <>
                  <p>
                    Question ID:{" "}
                    <code>{visible.private_reference.question_id}</code> ·
                    eligibility: {visible.private_reference.eligibility} ·
                    delivery: {visible.private_reference.delivery}
                  </p>
                  <pre className="tw-exact-text">
                    {visible.private_reference.text}
                  </pre>
                </>
              ) : (
                <p>No current private reference for this selection.</p>
              )}
            </details>
            <details>
              <summary>
                Material roles &amp; extraction coverage (
                {visible.materials.length})
              </summary>
              {visible.materials.map((m) => (
                <article className="tw-material-review" key={m.id}>
                  <h4>{m.title}</h4>
                  <p>
                    ID: <code>{m.id}</code>
                  </p>
                  <p>
                    {m.kind} · {m.visibility} · {m.status} ·{" "}
                    {m.role.replaceAll("_", " ")}
                  </p>
                  <p>
                    {m.selected ? "Selected" : "Not selected"} ·{" "}
                    {m.included ? "Included" : "Excluded"} ·{" "}
                    {m.included_chars.toLocaleString("en-US")} /{" "}
                    {m.available_chars.toLocaleString("en-US")} available
                    characters
                  </p>
                  <p>
                    <strong>Reason:</strong> {m.reason}
                  </p>
                  {m.warning && <p className="tw-warning">{m.warning}</p>}
                  {m.extraction_report && (
                    <TeacherExtractionReport report={m.extraction_report} />
                  )}
                </article>
              ))}
            </details>
            <details>
              <summary>Selection limits &amp; technical details</summary>
              <p>
                Selected snippets: {usage!.publicChars.toLocaleString("en-US")}{" "}
                / {visible.budgets.public_chars.toLocaleString("en-US")} public
                characters · {usage!.privateChars.toLocaleString("en-US")} /{" "}
                {visible.budgets.private_chars.toLocaleString("en-US")} private
                characters.
              </p>
              <p>
                Whole request limit:{" "}
                {visible.budgets.request_bytes.toLocaleString("en-US")} UTF-8
                bytes, including instructions, protocol and learner history.
                This is a limit, not this preview's request size.
              </p>
              <p>
                Saved revision: <code>{visible.saved_revision}</code> · phase:{" "}
                {visible.phase} · question ID:{" "}
                <code>{visible.question_id || "none"}</code>
              </p>
            </details>
          </div>
        )}
      </details>
    </section>
  );
}
