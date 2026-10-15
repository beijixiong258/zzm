import { useEffect, useRef, useState } from "react";
import {
  FileText,
  Download,
  AlertTriangle,
  LoaderCircle,
  ShieldCheck,
  ExternalLink,
  Eye,
  X,
  CheckCircle2,
} from "lucide-react";
import type { Material } from "./types";
import { api } from "./api";
import { useUiText } from "./uiText";
import { safeExternal, withVersion } from "./stage2";
import { Empty, ErrorBanner, errorMessage } from "./ui";
import "./material-manager.css";
import DocumentReader from "./DocumentReader";
export default function Materials({
  materials,
  teacher = false,
  disabled = false,
  versionId,
  onEdit,
  onArchive,
  onReprocess,
  onDocumentChanged,
}: {
  materials: Material[];
  teacher?: boolean;
  disabled?: boolean;
  versionId?: string | null;
  onEdit?: (m: Material) => void;
  onArchive?: (m: Material) => Promise<void>;
  onReprocess?: (m: Material) => Promise<void>;
  onDocumentChanged?: () => void;
}) {
  const { t } = useUiText();
  const [documentMaterial, setDocumentMaterial] = useState<Material | null>(
    null,
  );
  const [preview, setPreview] = useState<Material | null>(null),
    [archive, setArchive] = useState<Material | null>(null),
    [busy, setBusy] = useState(false),
    [operationError, setOperationError] = useState("");
  const visible = teacher
    ? materials
    : materials.filter((m) => m.visibility === "student");
  return (
    <div className="material-list">
      <ErrorBanner
        error={operationError}
        onClose={() => setOperationError("")}
      />
      {visible.length ? (
        visible.map((m) => (
          <article className="material-card" key={m.id}>
            <div className="material-heading">
              <span className="file-icon">
                {m.kind === "link" ? (
                  <ExternalLink size={21} />
                ) : (
                  <FileText size={21} />
                )}
              </span>
              <div>
                <h4>{m.title}</h4>
                <small>{m.source_label}</small>
              </div>
              <span className={`material-status ${m.status}`}>
                {m.status === "ready" && <CheckCircle2 size={13} />}
                {(m.status === "error" || m.status === "needs_review") && (
                  <AlertTriangle size={13} />
                )}
                {m.status === "processing" && (
                  <LoaderCircle className="spin" size={13} />
                )}{" "}
                {t(m.status === "error" ? "materialError" : m.status)}
              </span>
            </div>
            {teacher && (
              <div className="material-visibility">
                <ShieldCheck size={13} />
                {t(
                  m.visibility === "teacher"
                    ? "teacherMaterial"
                    : "studentMaterial",
                )}{" "}
                · {m.kind}
              </div>
            )}
            {m.warning && (
              <div className="material-warning">
                <AlertTriangle size={14} />
                {m.warning}
              </div>
            )}
            {teacher && m.extraction_report?.visual_review_required && (
              <p className="material-warning">
                <AlertTriangle size={14} /> Check diagrams and visual
                relationships in the original.
              </p>
            )}
            <details className="material-extraction-details">
              <summary>
                {t("extraction")}
                {teacher && m.extraction_report ? " & coverage" : ""}
              </summary>
              {teacher && m.extraction_report && (
                <div
                  className="extraction-coverage"
                  aria-label="Extraction coverage"
                >
                  <strong>
                    Processed {m.extraction_report.units_processed} of{" "}
                    {m.extraction_report.units_total} parts
                  </strong>
                  <span>
                    OCR used on {m.extraction_report.ocr_units} ·{" "}
                    {m.extraction_report.images_detected} images detected
                  </span>
                  <span>
                    {m.extraction_report.chars_extracted.toLocaleString()}{" "}
                    characters extracted ·{" "}
                    {m.extraction_report.excerpt_chars.toLocaleString()}{" "}
                    available in the text excerpt
                  </span>
                  {m.extraction_report.visual_review_required && (
                    <small>
                      Check diagrams and visual relationships in the original.
                      OCR recognizes text, not all visual meaning.
                    </small>
                  )}
                  {m.extraction_report.truncated && (
                    <small>
                      The excerpt is limited; the original file is retained.
                    </small>
                  )}
                  {m.extraction_report.failed_units.map((reason, i) => (
                    <small key={i}>{reason}</small>
                  ))}
                  {m.extraction_report.notes.length > 0 && (
                    <details className="coverage-notes">
                      <summary>Coverage notes & limits</summary>
                      <ul>
                        {m.extraction_report.notes.map((note, i) => (
                          <li key={i}>{note}</li>
                        ))}
                      </ul>
                    </details>
                  )}
                </div>
              )}
              {teacher && (
                <p className="extraction-note">
                  {m.document
                    ? "Complete document saved. Tutor requests read selected page/block evidence, not every page at once."
                    : "Preview only: the tutor uses selected excerpts, not the full text of every file."}
                </p>
              )}
              <p className="preserve-text">
                {m.excerpt ||
                  (m.document
                    ? "Complete page/block text is available in Read complete document; this legacy excerpt is not the whole corpus."
                    : "No extracted body is available. This is not full-text evidence.")}
              </p>
            </details>
            <div className="button-row">
              {(m.document || m.preview_kind === "pdf" || ["pptx", "docx", "doc", "txt", "md", "png", "jpg", "jpeg", "webp"].includes(m.source_format ?? "")) && (
                <button
                  className="text-button"
                  disabled={disabled || busy}
                  onClick={() => setDocumentMaterial(m)}
                >
                  {m.document
                    ? "Read complete document"
                    : m.source_format && m.source_format !== "pdf" ? "Complete document / processing status" : "Full PDF / processing status"}
                </button>
              )}
              {m.kind === "link" && safeExternal(m.url) ? (
                <a
                  className="text-button"
                  href={safeExternal(m.url)!}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <ExternalLink size={14} />
                  {"Open source link"}
                </a>
              ) : m.preview_kind === "pdf" ? (
                <a
                  className="text-button"
                  href={withVersion(
                    m.preview_url || api.previewUrl(m.id),
                    versionId,
                  )}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <ExternalLink size={14} />
                  Open PDF preview
                </a>
              ) : (
                <button className="text-button" onClick={() => setPreview(m)}>
                  <Eye size={14} />
                  {"Preview material"}
                </button>
              )}
              {m.download_url && (
                <a
                  className="text-button"
                  href={withVersion(m.download_url, versionId)}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <Download size={14} />
                  {t("download")}
                </a>
              )}
              {onEdit && (
                <button
                  className="text-button"
                  disabled={disabled || busy}
                  onClick={() => onEdit(m)}
                >
                  {"Edit"}
                </button>
              )}
              {onArchive && (
                <button className="text-button danger" disabled={disabled || busy}
                  onClick={() => { setArchive(m); setOperationError(""); }}>
                  Remove from this session
                </button>
              )}
              {onReprocess && (
                <details className="material-management-details">
                  <summary>More actions</summary>
                  <div className="button-row">
                    {onReprocess &&
                      !m.document &&
                      m.status !== "processing" &&
                      m.download_url &&
                      m.kind !== "link" && (
                        <button
                          className="text-button"
                          disabled={disabled || busy}
                          onClick={async () => {
                            setBusy(true);
                            setOperationError("");
                            try {
                              await onReprocess(m);
                            } catch (e) {
                              setOperationError(errorMessage(e));
                            } finally {
                              setBusy(false);
                            }
                          }}
                        >
                          Re-extract text / OCR
                        </button>
                      )}

                  </div>
                </details>
              )}
            </div>
          </article>
        ))
      ) : (
        <Empty title={t("noMaterials")} />
      )}
      {archive && (
        <div className="notice confirmation">
          <span>
            {
              "Remove this session's link? The file stays in Course Materials, other sessions and published editions."
            }
            : {archive.title}
          </span>
          <button
            className="secondary"
            disabled={busy || disabled}
            onClick={async () => {
              setBusy(true);
              try {
                await onArchive?.(archive);
                setArchive(null);
              } catch (e) {
                setOperationError(errorMessage(e));
              } finally {
                setBusy(false);
              }
            }}
          >
            {"Confirm removal"}
          </button>
          <button
            className="secondary"
            disabled={busy || disabled}
            onClick={() => setArchive(null)}
          >
            {t("cancel")}
          </button>
        </div>
      )}
      {documentMaterial && (
        <DocumentReader
          key={JSON.stringify([documentMaterial.id, versionId ?? null])}
          material={documentMaterial}
          teacher={teacher}
          versionId={versionId}
          onChanged={onDocumentChanged}
          onClose={() => setDocumentMaterial(null)}
        />
      )}
      {preview && (
        <MaterialPreview
          material={preview}
          versionId={versionId}
          onClose={() => setPreview(null)}
        />
      )}
    </div>
  );
}
function MaterialPreview({
  material: m,
  versionId,
  onClose,
}: {
  material: Material;
  versionId?: string | null;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null),
    [text, setText] = useState(""),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(false);
  const url = withVersion(m.preview_url || api.previewUrl(m.id), versionId);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    ref.current?.showModal();
    return () => previous?.focus();
  }, []);
  useEffect(() => {
    if (m.preview_kind === "image") return;
    const control = new AbortController();
    setLoading(true);
    fetch(url, { credentials: "include", signal: control.signal })
      .then(async (r) => {
        if (!r.ok) throw new Error(`Preview failed (${r.status})`);
        setText(await r.text());
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(errorMessage(e));
      })
      .finally(() => setLoading(false));
    return () => control.abort();
  }, [url, m.preview_kind]);
  return (
    <dialog
      ref={ref}
      className="preview-modal"
      aria-labelledby="preview-heading"
      onCancel={onClose}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="preview-heading">
        <h2 id="preview-heading">{m.title}</h2>
        <button
          className="icon-button"
          aria-label={"Close preview"}
          onClick={onClose}
        >
          <X />
        </button>
      </div>
      <p>
        {
          "Basic authenticated preview; Office layout may differ from the original."
        }
      </p>
      <ErrorBanner error={error} />
      {m.preview_kind === "image" ? (
        <img src={url} alt={m.title} />
      ) : loading ? (
        <p>{"Loading preview…"}</p>
      ) : (
        <pre className="preview-text">{text}</pre>
      )}
      <a
        className="text-button"
        href={url}
        target="_blank"
        rel="noopener noreferrer"
      >
        {"Open authenticated preview"}
      </a>
    </dialog>
  );
}
