import { useEffect, useState, type FormEvent } from "react";
import { api } from "./api";
import type { Material, SessionDetail, WorksheetPreview, WorksheetDraft } from "./types";
import { authoringErrors } from "./stage2";
import { ErrorBanner, errorMessage, Notice } from "./ui";
import Authoring from "./Authoring";
import HelpPopover from "./HelpPopover";
import { useUnsavedChanges } from "./navigation-guard";
export default function WorksheetImport({
  session,
  onCommitted,
}: {
  session: SessionDetail;
  onCommitted: (s: SessionDetail) => void;
}) {
  const [materialId, setMaterialId] = useState(""),
    [answerId, setAnswerId] = useState(""),
    [materials, setMaterials] = useState<Material[]>(session.materials),
    [loading, setLoading] = useState(true),
    [accepted, setAccepted] = useState(false),
    [ai, setAi] = useState(true),
    [preview, setPreview] = useState<WorksheetPreview | null>(null),
    [draft, setDraft] = useState<WorksheetDraft | null>(null),
    [mode, setMode] = useState<"append" | "replace">("append"),
    [reviewed, setReviewed] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [success, setSuccess] = useState("");
  useUnsavedChanges(!!draft || busy);
  useEffect(() => {
    let live = true;
    setLoading(true);
    api.courseMaterials(session.course_id).then((r) => { if (live) setMaterials(r.materials); })
      .catch((e) => { if (live) setError(errorMessage(e)); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [session.course_id, session.materials]);
  const selectable = materials.filter((m) => m.kind !== "link" && m.kind !== "answer_key");
  const selected = materials.find((m) => m.id === materialId);
  const sourceReady = !!selected && selected.status !== "processing";
  async function parse(e: FormEvent) {
    e.preventDefault();
    if (!sourceReady || draft) return;
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      const p = await api.worksheetFromMaterial(session.id, materialId, answerId || null, ai);
      setAccepted(false);
      setPreview(p);
      setDraft({
        ...p.draft,
        questions: p.draft.questions.map((q) => ({
          ...q,
          images: q.images.map((img) => ({
            ...img,
            url:
              img.url ||
              p.assets.find((a) => a.key === img.asset_key)?.url ||
              "",
          })),
        })),
      });
      setReviewed(false);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  async function commit() {
    if (!draft || !preview || !reviewed) return;
    setBusy(true);
    setError("");
    try {
      if (!accepted) {
        await api.worksheetCommit(session.id, preview.import_id, draft, mode);
        setAccepted(true);
      }
      const verified = await api.session(session.id);
      if (
        draft.questions.some(
          (q) => !verified.questions.some((x) => x.id === q.id && x.prompt === q.prompt),
        ) || Object.entries(draft.reference_answers).some(([id, answer]) => verified.reference_answers?.[id] !== answer)
      )
        throw new Error("Saved import could not be verified.");
      onCommitted(verified);
      setPreview(null);
      setDraft(null);
      setAccepted(false);
      setSuccess("Reviewed worksheet saved to content draft, not published.");
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="worksheet-import card form-card">
      <h2>{"Select worksheet from the materials"}</h2>
      <p>
        {
          "Use an uploaded course material—no second upload. AI detects questions and matches supplied answers; review before saving."
        }
      </p>
      <ErrorBanner error={error} />
      {success && <Notice>{success}</Notice>}
      <form onSubmit={(e) => void parse(e)}>
        <label>
          {"Worksheet material"}
          <select aria-label="Worksheet material" value={materialId} required disabled={busy || loading || !!draft}
            onChange={(e) => setMaterialId(e.target.value)}>
            <option value="">{loading ? "Loading materials…" : "Select a material"}</option>
            {selectable.map((m) => <option key={m.id} value={m.id} disabled={m.status === "processing"}>{m.title} · {m.kind}{m.status === "processing" ? " · Processing" : ""}</option>)}
          </select>
        </label>
        <label>
          {"Answer key material (optional)"}
          <select aria-label="Answer key material" value={answerId} disabled={busy || loading || !!draft}
            onChange={(e) => setAnswerId(e.target.value)}>
            <option value="">No separate key · use supplied inline answers only</option>
            {materials.filter((m) => m.kind === "answer_key" && m.visibility === "teacher").map((m) =>
              <option key={m.id} value={m.id} disabled={m.status === "processing"}>{m.title}{m.status === "processing" ? " · Processing" : ""}</option>)}
          </select>
        </label>
        {!loading && !selectable.length && <p>Upload your worksheet in Materials first, then return here.</p>}
        <label className="inline-check">
          <input
            type="checkbox"
            checked={ai}
            disabled={busy || !!draft}
            onChange={(e) => setAi(e.target.checked)}
          />
          AI detection · sends selected content to the configured provider
          <HelpPopover label="AI worksheet extraction">
            Matches supplied answers, never generates missing answers. Turn off for
            a local preview. Saving changes the draft only, not the published course.
          </HelpPopover>
        </label>
        <button className="secondary" disabled={busy || !sourceReady || !!draft}>
          {busy ? "Working…" : "Detect questions & answers"}
        </button>
      </form>
      {preview && draft && (
        <div className="import-review">
          <h3>
            {"Review extracted worksheet"}: {draft.title}
          </h3>
          <p>
            {"Extraction method"}: <strong>{preview.method}</strong> ·{" "}
            {preview.needs_review ? "Review required" : "Ready for your review"}
          </p>
          {preview.warnings.map((w, i) => (
            <p className="material-warning" key={i}>
              {w}
            </p>
          ))}
          {preview.assets.length > 0 && (
            <details>
              <summary>
                {"Extracted figures"} ({preview.assets.length})
              </summary>
              <div className="question-images">
                {preview.assets.map((a) => (
                  <a
                    href={a.url}
                    key={a.key}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <img src={a.url} alt={a.label} />
                    <span>{a.label}</span>
                  </a>
                ))}
              </div>
            </details>
          )}
          <Authoring
            value={draft}
            materials={[...new Map([...session.materials, preview.material].map((m) => [m.id, m])).values()]}
            disabled={busy || accepted}
            onChange={(d) => {
              setDraft(d);
              setReviewed(false);
            }}
          />
          <label>
            {"Save to draft"}
            <select
              value={mode}
              disabled={busy || accepted}
              onChange={(e) => setMode(e.target.value as typeof mode)}
            >
              <option value="append">{"Append groups and questions"}</option>
              <option value="replace">
                {"Replace this session’s draft groups and questions"}
              </option>
            </select>
          </label>
          {mode === "replace" && (
            <p className="material-warning">
              {
                "Only the content draft is replaced. Published editions and student learning records stay unchanged."
              }
            </p>
          )}
          <label className="inline-check">
            <input
              type="checkbox"
              checked={reviewed}
              onChange={(e) => setReviewed(e.target.checked)}
            />
            {"I reviewed the extracted questions, references and figures."}
          </label>
          <div className="button-row">
            <button
              className="primary"
              disabled={
                busy ||
                !reviewed ||
                !draft.questions.length ||
                authoringErrors(draft.groups, draft.questions).length > 0
              }
              onClick={() => void commit()}
            >
              {accepted ? "Verify saved draft" : "Save reviewed draft"}
            </button>
            <button
              className="secondary"
              disabled={busy}
              onClick={() => {
                setPreview(null);
                setDraft(null);
              }}
            >
              {"Discard preview"}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
