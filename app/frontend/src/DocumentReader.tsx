import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import DocumentBlockContent from "./DocumentBlockContent";
import { api, ApiError } from "./api";
import { documentApi } from "./document-api";
import { clientId } from "./ids";
import { useUnsavedChanges } from "./navigation-guard";
import { ErrorBanner, errorMessage } from "./ui";
import { withVersion } from "./stage2";
import {
  jobIsActive,
  processingLabel,
  reviewChangeError,
  reviewReadbackMatches,
  uncertainDocumentWrite,
  authorizedDocumentAsset,
} from "./document-state";
import type { Material } from "./types";
import type {
  DocumentCapability,
  DocumentInfo,
  DocumentJobRequest,
  DocumentPage,
  DocumentReviewRequest,
  DocumentSummary,
  DocumentSupplementSharing,
} from "./document-types";
import "./document-reader.css";

type Draft = {
  blockId: string;
  text: string;
  quality: "approved" | "excluded";
  reason: string;
  revision: string;
  page: number;
};
type Pending =
  | { kind: "sharing"; payload: DocumentSupplementSharing; before: DocumentInfo; supplementIds: string[] }
  | { kind: "job"; payload: DocumentJobRequest; before: DocumentInfo | null }
  | {
      kind: "review";
      payload: DocumentReviewRequest;
      before: DocumentInfo;
      page: number;
    };
type Saved = { draft: Draft | null; pending: Pending | null };

/** Existing materials' authenticated reader; no model or external image requests. */
export default function DocumentReader({
  material,
  teacher = false,
  versionId,
  onClose,
  onChanged,
}: {
  material: Material;
  teacher?: boolean;
  versionId?: string | null;
  onClose: () => void;
  onChanged?: () => void;
}) {
  const canReview = teacher && versionId == null;
  const dialog = useRef<HTMLDialogElement>(null);
  const generation = useRef(0),
    pageGeneration = useRef(0),
    flight = useRef(false);
  const [scope, setScope] = useState("");
  const [summary, setSummary] = useState<DocumentSummary | null>(null);
  const [capability, setCapability] = useState<DocumentCapability | null>(null);
  const [pageNumber, setPageNumber] = useState(1),
    [page, setPage] = useState<DocumentPage | null>(null);
  const [loading, setLoading] = useState(true),
    [pageLoading, setPageLoading] = useState(false),
    [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null),
    [pending, setPending] = useState<Pending | null>(null);
  const [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [conflict, setConflict] = useState(false);
  const [zoom, setZoom] = useState(1),
    [highlight, setHighlight] = useState<string | null>(null);
  const [storageError, setStorageError] = useState("");
  useUnsavedChanges(!!draft || !!pending || busy);
  const revision = summary?.document?.revision_id;
  const active = jobIsActive(summary?.latest_job ?? null);
  function saveLocal(value: Saved, key = scope) {
    if (!key) return;
    try {
      if (value.draft || value.pending)
        sessionStorage.setItem(key, JSON.stringify(value));
      else sessionStorage.removeItem(key);
    } catch {
      setStorageError(
        "Browser recovery storage is unavailable. Keep this reader open until the request is verified.",
      );
    }
  }
  function changeDraft(value: Draft | null) {
    saveLocal({ draft: value, pending });
    setDraft(value);
  }
  function close() {
    if (busy) return;
    if (
      (draft || pending) &&
      !window.confirm(
        "Close the reader? Unconfirmed work is retained for this account in this browser tab; reopening recovers by GET only.",
      )
    )
      return;
    onClose();
  }
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    dialog.current?.showModal();
    return () => previous?.focus();
  }, []);
  useEffect(() => {
    const g = ++generation.current;
    const control = new AbortController();
    setSummary(null);
    setPage(null);
    setLoading(true);
    setDraft(null);
    setPending(null);
    setScope("");
    setError("");
    Promise.all([
      api.me(),
      documentApi.summary(material.id, versionId, control.signal),
      documentApi.capability(control.signal),
    ])
      .then(([me, data, cap]) => {
        if (g !== generation.current) return;
        const key = `aicademiya:document:${JSON.stringify([me.user.id, material.id, versionId ?? null])}`;
        setScope(key);
        setSummary(data);
        setCapability(cap);
        try {
          const saved: Saved | null = JSON.parse(
            sessionStorage.getItem(key) || "null",
          );
          if (canReview && saved) {
            setDraft(saved.draft);
            setPending(saved.pending);
            if (saved.draft) setPageNumber(saved.draft.page);
            if (saved.pending)
              setNotice(
                "Unconfirmed request restored. Inspect its outcome with GET only; do not submit it again.",
              );
          }
        } catch {
          setStorageError("Could not restore browser recovery data.");
        }
      })
      .catch((e) => {
        if (g === generation.current && !control.signal.aborted)
          setError(errorMessage(e));
      })
      .finally(() => {
        if (g === generation.current) setLoading(false);
      });
    return () => {
      generation.current++;
      pageGeneration.current++;
      control.abort();
    };
  }, [material.id, versionId, canReview]);

  useEffect(() => {
    const g = ++pageGeneration.current;
    const control = new AbortController();
    setPage(null);
    if (!revision) return;
    setPageLoading(true);
    documentApi
      .page(material.id, pageNumber, revision, versionId, control.signal)
      .then((value) => {
        if (g === pageGeneration.current) {
          setPage(value);
          setHighlight(null);
        }
      })
      .catch((e) => {
        if (g === pageGeneration.current && !control.signal.aborted) {
          setError(errorMessage(e));
          if (e instanceof ApiError && e.status === 409) setConflict(true);
        }
      })
      .finally(() => {
        if (g === pageGeneration.current) setPageLoading(false);
      });
    return () => {
      pageGeneration.current++;
      control.abort();
    };
  }, [material.id, revision, versionId, pageNumber]);

  // Poll only genuine server job states. Closing the reader never cancels the job.
  useEffect(() => {
    if (!active || busy || draft || pending) return;
    const g = generation.current;
    const control = new AbortController();
    const timer = window.setTimeout(() => {
      documentApi
        .summary(material.id, versionId, control.signal)
        .then((data) => {
          if (g !== generation.current || control.signal.aborted) return;
          setSummary(data);
          if (!jobIsActive(data.latest_job)) onChanged?.();
        })
        .catch((e) => {
          if (!control.signal.aborted && g === generation.current)
            setError(errorMessage(e));
        });
    }, 3000);
    return () => {
      clearTimeout(timer);
      control.abort();
    };
  }, [active, summary, material.id, versionId, busy, draft, pending]);

  async function refresh() {
    if (flight.current) return;
    const g = generation.current;
    flight.current = true;
    setBusy(true);
    setError("");
    try {
      const data = await documentApi.summary(material.id, versionId);
      if (g !== generation.current) return;
      if (data.document) {
        const freshPage = await documentApi.page(
          material.id,
          pageNumber,
          data.document.revision_id,
          versionId,
        );
        if (g !== generation.current) return;
        setPage(freshPage);
      }
      setSummary(data);
      if (!draft && !pending) setConflict(false);
      setNotice(
        draft
          ? "Current source refreshed. Your correction is retained; compare it again before using the new revision."
          : "Source status refreshed.",
      );
    } catch (e) {
      if (g === generation.current) setError(errorMessage(e));
    } finally {
      flight.current = false;
      if (g === generation.current) setBusy(false);
    }
  }

  async function verify(request: Pending, g: number) {
    if (request.kind === "job") {
      const receipt = await documentApi.jobByRequest(
        material.id,
        request.payload.request_id,
      );
      if (receipt.material_id !== material.id)
        throw new Error("The exact job receipt does not match this material.");
      const exact = await documentApi.job(material.id, receipt.id);
      if (exact.id !== receipt.id || exact.material_id !== material.id)
        throw new Error("Job identity could not be verified.");
      const current = await documentApi.summary(material.id, versionId);
      if (exact.status === "completed") {
        if (
          !current.document ||
          exact.revision_id !== current.document.revision_id ||
          (request.before &&
            current.document.source_sha256 !== request.before.source_sha256)
        )
          throw new Error(
            "The completed job's exact document revision could not be confirmed. Keep this request for inspection.",
          );
        await documentApi.page(
          material.id,
          pageNumber,
          current.document.revision_id,
          versionId,
        );
      }
      if (g !== generation.current) return;
      setSummary(current);
      setNotice(
        "Job accepted and independently verified. The original is saved; processing continues without this browser. This does not publish a course edition.",
      );
    } else if (request.kind === "sharing") {
      const receipt = await documentApi.reviewByRequest(material.id, request.payload.request_id);
      const current = await documentApi.summary(material.id, versionId);
      const expectedVisibility = request.payload.visible_to_students ? "student" : "teacher";
      if (!current.document || current.document.revision_id !== receipt.document.revision_id || current.document.source_sha256 !== request.before.source_sha256 || current.document.revision_id === request.before.revision_id ||
          current.supplements?.length !== request.supplementIds.length || !current.supplements.every((s) => request.supplementIds.includes(s.id) && s.visibility === expectedVisibility)) {
        throw new Error("Source-note sharing could not be independently verified. Keep this request for inspection; do not resubmit.");
      }
      if (g !== generation.current) return;
      setSummary(current);setConflict(false);
      setNotice("Source-note sharing saved and verified in the draft. Publish a new course edition explicitly to apply it to students.");
    } else {
      const receipt = await documentApi.reviewByRequest(
        material.id,
        request.payload.request_id,
      );
      const current = await documentApi.summary(material.id, versionId);
      if (!current.document)
        throw new Error("The reviewed document is unavailable.");
      const readPage = await documentApi.page(
        material.id,
        request.page,
        receipt.document.revision_id,
        versionId,
      );
      if (
        readPage.number !== request.page ||
        !reviewReadbackMatches(
          request.before,
          receipt.document,
          current.document,
          readPage,
          request.payload.changes,
        )
      )
        throw new Error(
          "The review receipt and exact source blocks could not be independently verified. Correction retained; inspect rather than resubmit.",
        );
      if (g !== generation.current) return;
      setSummary(current);
      setPage(readPage);
      setDraft(null);
      setConflict(false);
      setNotice(
        "Source review saved and independently verified. Raw text and audit are retained. Publish a new course edition explicitly to share this correction.",
      );
    }
    if (g !== generation.current) return;
    const keptDraft = request.kind === "review" ? null : draft;
    saveLocal({ draft: keptDraft, pending: null });
    setPending(null);
    onChanged?.();
  }
  async function mutate(request: Pending | null) {
    if (!canReview || !scope || flight.current) return;
    const target = request ?? pending;
    if (!target || (request && pending)) return;
    const g = generation.current;
    flight.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    if (request) {
      saveLocal({ draft, pending: target });
      setPending(target);
    }
    try {
      if (request) {
        try {
          if (target.kind === "job")
            await documentApi.start(material.id, target.payload);
          else if (target.kind === "sharing") await documentApi.shareSupplements(material.id, target.payload);
          else await documentApi.review(material.id, target.payload);
        } catch (e) {
          if (!uncertainDocumentWrite(e)) {
            if (g === generation.current) {
              saveLocal({ draft, pending: null });
              setPending(null);
              if (e instanceof ApiError && e.status === 409) setConflict(true);
            }
            throw e;
          }
          // Unknown acknowledgement: exact receipt GET is the only recovery path.
        }
      }
      await verify(target, g);
    } catch (e) {
      if (g === generation.current) setError(errorMessage(e));
    } finally {
      flight.current = false;
      if (g === generation.current) setBusy(false);
    }
  }
  const selectedBlock = page?.blocks.find((b) => b.id === highlight);
  const sourceFormat = material.source_format ?? summary?.document?.source_format ?? (material.preview_kind === "pdf" ? "pdf" : material.title.split(".").pop()?.toLowerCase());
  const canProcess = !!capability?.available && !!sourceFormat && capability.formats.includes(sourceFormat);
  const sourceView = summary?.document?.has_rendered_pdf && revision
    ? documentApi.renderedUrl(material.id, revision, versionId)
    : withVersion(sourceFormat && sourceFormat !== "pdf" ? `/api/materials/${encodeURIComponent(material.id)}/download` : api.previewUrl(material.id), versionId);
  const image =
    revision && page
      ? authorizedDocumentAsset(
          page.image_url,
          material.id,
          revision,
          versionId,
        )
      : null;
  return (
    <dialog
      ref={dialog}
      className="document-reader"
      aria-labelledby="document-reader-heading"
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
    >
      <header className="preview-heading">
        <h2 id="document-reader-heading">
          {material.title} · complete document
        </h2>
        <button
          className="icon-button"
          aria-label="Close document reader"
          disabled={busy}
          onClick={close}
        >
          <X />
        </button>
      </header>
      <p>{summary?.document?.has_rendered_pdf ? "Compare the rendered source page with its extracted text." : "Compare the original page with its extracted text."}</p>
      <div className="button-row">
        <a
          className="text-button"
          target="_blank"
          rel="noopener noreferrer"
          href={`${sourceView}#page=${pageNumber}`}
        >
          {summary?.document?.has_rendered_pdf ? "Open rendered source" : sourceFormat && sourceFormat !== "pdf" ? "Download original file" : "Open original PDF"} · page {pageNumber}
        </a>
        <button
          className="secondary"
          disabled={busy || loading}
          onClick={() => void refresh()}
        >
          Refresh source status
        </button>
      </div>
      <ErrorBanner error={error} />
      <ErrorBanner error={storageError} />
      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}
      {loading ? (
        <p>Loading document…</p>
      ) : (
        <>
          {summary?.latest_job && (
            <section
              className="document-job"
              aria-label="Background job status"
            >
              <strong>{processingLabel(summary.latest_job)}</strong>
              {summary.latest_job.error && <p>{summary.latest_job.error}</p>}
              {jobIsActive(summary.latest_job) && <p>You may leave this page. Processing continues in the background.</p>}
            </section>
          )}
          {!!summary?.supplements?.length && revision && (
            <details className="document-supplements">
              <summary>Source notes and supplementary text ({summary.supplements.length})</summary>
              {teacher && <p>Notes stay out of student AI reads until explicitly shared and published. Original Office downloads still contain their embedded notes.</p>}
              <ul>{summary.supplements.map((item) => <li key={item.id}>
                <strong>{item.kind.replaceAll("_", " ")}</strong> · {item.source_part} · {item.characters.toLocaleString()} characters · {item.visibility === "teacher" ? "Staff AI context" : "Student AI context in this edition"}
                <p className="preserve-text">{item.preview}</p>
                <a href={documentApi.supplementUrl(material.id,item.id,revision,versionId)} target="_blank" rel="noopener noreferrer">Open full source note</a>
              </li>)}</ul>
              {canReview && summary.document && <button className="secondary" disabled={busy || active || conflict || !!draft || !!pending} onClick={() => {
                const shared = summary.supplements!.every((s) => s.visibility === "student");
                void mutate({kind:"sharing",before:summary.document!,supplementIds:summary.supplements!.map((s) => s.id),payload:{request_id:clientId(),expected_revision:revision,visible_to_students:!shared,reason:shared ? "Teacher explicitly restricted supplementary source text to staff." : "Teacher explicitly selected supplementary source text for student sharing on publication."}});
              }}>{summary.supplements.every((s) => s.visibility === "student") ? "Exclude notes from student AI reads" : "Share source notes on next publication"}</button>}
            </details>
          )}
          {summary?.document ? (
            <section aria-label="Document summary" className="document-summary">
              <strong>
                {summary.document.page_count} {sourceFormat === "pptx" ? "slides" : sourceFormat === "pdf" ? "PDF pages" : "source pages"} ·{" "}
                {summary.document.block_count} source blocks ·{" "}
                {summary.document.quality.replaceAll("_", " ")}
              </strong>
              <details>
                <summary>Revision & extraction notes · {summary.document.review_count} reviewed block{summary.document.review_count === 1 ? "" : "s"}</summary>
                <small>Revision {summary.document.revision_id} · {summary.document.parser.name} {summary.document.parser.version}</small>
                {summary.document.warnings.map((w, i) => (<p className="material-warning" key={i}>{w}</p>))}
              </details>
            </section>
          ) : (
            <p>
              No complete document has been saved. The original file is retained;
              existing excerpts are preview only.
            </p>
          )}
          {canReview && (
            <div className="button-row">
              <button
                className="secondary"
                disabled={
                  busy ||
                  !!pending ||
                  !!draft ||
                  active ||
                  !canProcess ||
                  !scope ||
                  conflict
                }
                onClick={() =>
                  void mutate({
                    kind: "job",
                    payload: {
                      request_id: clientId(),
                      expected_revision: summary?.document?.revision_id ?? null,
                    },
                    before: summary?.document ?? null,
                  })
                }
              >
                {summary?.document
                  ? "Reprocess complete document"
                  : summary?.latest_job?.status === "failed"
                    ? "Retry full document processing"
                    : "Start full document processing"}
              </button>
              {!canProcess && (
                <small>
                  {capability?.available ? "Complete processing is not enabled for this file format." : "Complete document processing is not configured. No silent preview fallback."}
                </small>
              )}
            </div>
          )}
          {pending && (
            <section
              className="notice"
              aria-label="Unconfirmed document request"
            >
              <p>
                Unconfirmed {pending.kind} request {pending.payload.request_id}.
                Do not submit another POST.
              </p>
              <button
                className="secondary"
                disabled={busy}
                onClick={() => void mutate(null)}
              >
                Inspect request outcome (GET only)
              </button>
            </section>
          )}
          {conflict && (
            <p className="material-warning">
              Source revision changed or a conflicting job is active. Your
              correction is retained. Refresh the source and explicitly
              reconfirm; nothing was automatically retried.
            </p>
          )}
          {!!summary?.pages.length && (
            <nav className="document-page-controls" aria-label="PDF pages">
              <button
                className="secondary"
                disabled={
                  busy || !!draft || !!pending || pageLoading || pageNumber <= 1
                }
                onClick={() => setPageNumber((n) => n - 1)}
              >
                Previous
              </button>
              <label>
                PDF page
                <select
                  aria-label="PDF page"
                  value={pageNumber}
                  disabled={busy || !!draft || !!pending}
                  onChange={(e) => setPageNumber(Number(e.target.value))}
                >
                  {summary.pages.map((p) => (
                    <option key={p.number} value={p.number}>
                      {p.number}
                      {p.printed_label
                        ? ` · printed ${p.printed_label}`
                        : ""} · {p.status}
                    </option>
                  ))}
                </select>
              </label>
              <button
                className="secondary"
                disabled={
                  busy ||
                  !!draft ||
                  !!pending ||
                  pageLoading ||
                  pageNumber >= summary.pages.length
                }
                onClick={() => setPageNumber((n) => n + 1)}
              >
                Next
              </button>
              <label>
                Image zoom
                <select
                  aria-label="Image zoom"
                  value={zoom}
                  onChange={(e) => setZoom(Number(e.target.value))}
                >
                  {[1, 1.5, 2, 3].map((z) => (
                    <option key={z} value={z}>
                      {z === 1 ? "Fit page" : `${z * 100}%`}
                    </option>
                  ))}
                </select>
              </label>
            </nav>
          )}
          {pageLoading ? (
            <p>Loading source page…</p>
          ) : (
            page &&
            revision && (
              <>
                <h3>
                  PDF page {page.number}
                  {page.printed_label
                    ? ` · printed ${page.printed_label}`
                    : ""}{" "}
                  · {page.status.replaceAll("_", " ")}
                </h3>

                {page.issues.length > 0 && <details>
                  <summary>Page processing notes</summary>
                  {page.issues.map((issue, i) => <p key={i}>{issue}</p>)}
                </details>}
                <div className="document-page-layout">
                  <section
                    className="document-image-pane"
                    aria-label="Original retained page image"
                  >
                    <div className="document-image-scroll">
                      <div
                        className="document-image-canvas"
                        style={{ width: `${zoom * 100}%` }}
                      >
                        {image ? (
                          <img
                            src={image}
                            alt={`Retained source PDF page ${page.number}`}
                          />
                        ) : (
                          <p>Authorized page image unavailable.</p>
                        )}
                        {selectedBlock && image && (
                          <div
                            className="document-bbox"
                            aria-label={`Source coordinates ${selectedBlock.id}`}
                            style={{
                              left: `${selectedBlock.bbox[0] * 100}%`,
                              top: `${selectedBlock.bbox[1] * 100}%`,
                              width: `${(selectedBlock.bbox[2] - selectedBlock.bbox[0]) * 100}%`,
                              height: `${(selectedBlock.bbox[3] - selectedBlock.bbox[1]) * 100}%`,
                            }}
                          />
                        )}
                      </div>
                    </div>
                    {image && (
                      <a
                        href={image}
                        className="text-button"
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        Open full-size retained page image
                      </a>
                    )}
                  </section>
                  <section
                    className="document-blocks"
                    aria-label="Source blocks"
                  >
                    {page.blocks.map((block) => (
                      <article
                        className={`document-block ${highlight === block.id ? "is-selected" : ""}`}
                        key={block.id}
                        data-block-id={block.id}
                      >
                        <div className="button-row">
                          <strong>
                            {block.id} · {block.type}
                          </strong>
                          <span className={`material-status ${block.quality}`}>
                            {block.quality.replaceAll("_", " ")}
                          </span>
                          <button
                            className="text-button"
                            onClick={() => setHighlight(block.id)}
                          >
                            Locate on page
                          </button>
                        </div>
                        <details><summary>Source coordinates</summary><small>Source box [{block.bbox.join(", ")}]{block.parent_id && ` · Child of ${block.parent_id}`}</small></details>
                        {page.blocks.some(
                          (child) => child.parent_id === block.id,
                        ) && (
                          <p>
                            Associated captions/children:{" "}
                            {page.blocks
                              .filter((child) => child.parent_id === block.id)
                              .map((child) => child.id)
                              .join(", ")}
                          </p>
                        )}
                        {block.quality === "needs_review" && (
                          <p className="material-warning">
                            Needs a source check before the tutor can use this region.
                          </p>
                        )}
                        {block.issues.length > 0 && <details>
                          <summary>Block processing notes</summary>
                          {block.issues.map((issue, i) => <p key={i}>{issue}</p>)}
                        </details>}
                        <DocumentBlockContent text={block.text} format={block.text_format} />
                        {block.visual_description && <p className="document-block-note"><strong>Image description:</strong> {block.visual_description}</p>}
                        {block.assets.map((asset) => {
                          const url = authorizedDocumentAsset(
                            asset,
                            material.id,
                            revision,
                            versionId,
                          );
                          return url ? (
                            <a
                              key={asset}
                              href={url}
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              <img
                                className="document-crop"
                                src={url}
                                loading="lazy"
                                alt={`Original crop for ${block.id}`}
                              />
                            </a>
                          ) : (
                            <p key={asset}>Authorized crop unavailable.</p>
                          );
                        })}
                        {block.raw_text !== undefined && (
                          <details>
                            <summary>Preserved raw transcription</summary>
                            <pre className="document-source-text">
                              {block.raw_text}
                            </pre>
                          </details>
                        )}
                        {block.review && (
                          <details>
                            <summary>Source-review audit</summary>
                            <p>
                              {block.review.by} · {block.review.at}
                            </p>
                            <p className="preserve-text">
                              {block.review.reason}
                            </p>
                          </details>
                        )}
                        {canReview && (
                          <button
                            className="secondary"
                            disabled={busy || active || !!draft || !!pending}
                            onClick={() => {
                              setHighlight(block.id);
                              changeDraft({
                                blockId: block.id,
                                text: block.text,
                                quality: "approved",
                                reason: "",
                                revision,
                                page: pageNumber,
                              });
                            }}
                          >
                            Review this source block
                          </button>
                        )}
                      </article>
                    ))}
                  </section>
                </div>
              </>
            )
          )}
          {canReview && draft && (
            <form
              className="document-review"
              aria-label="Explicit source review"
              onSubmit={(e) => {
                e.preventDefault();
                const invalid = reviewChangeError(draft.text, draft.reason);
                if (invalid) {
                  setError(invalid);
                  return;
                }
                if (draft.revision !== revision || conflict) {
                  setError(
                    "Refresh and explicitly reconfirm the changed source revision first.",
                  );
                  return;
                }
                void mutate({
                  kind: "review",
                  before: summary!.document!,
                  page: draft.page,
                  payload: {
                    request_id: clientId(),
                    expected_revision: draft.revision,
                    changes: [
                      {
                        block_id: draft.blockId,
                        text: draft.text,
                        quality: draft.quality,
                        reason: draft.reason,
                      },
                    ],
                  },
                });
              }}
            >
              <h3>Explicit source review · {draft.blockId}</h3>
              <p>
                Check the retained original. Approving this block is not
                approval of every page and does not publish the course.
              </p>
              <fieldset disabled={busy || !!pending}>
                <label>
                  Checked source text
                  <textarea
                    aria-label="Checked source text"
                    value={draft.text}
                    onChange={(e) =>
                      changeDraft({ ...draft, text: e.target.value })
                    }
                  />
                </label>
                <label>
                  Evidence decision
                  <select
                    aria-label="Evidence decision"
                    value={draft.quality}
                    onChange={(e) =>
                      changeDraft({
                        ...draft,
                        quality: e.target.value as Draft["quality"],
                      })
                    }
                  >
                    <option value="approved">
                      Approved — checked against original
                    </option>
                    <option value="excluded">
                      Excluded — do not use as evidence
                    </option>
                  </select>
                </label>
                <label>
                  Source-review reason
                  <textarea
                    aria-label="Source-review reason"
                    value={draft.reason}
                    onChange={(e) =>
                      changeDraft({ ...draft, reason: e.target.value })
                    }
                  />
                </label>
                {(draft.revision !== revision || conflict) && (
                  <button
                    type="button"
                    className="secondary"
                    disabled={!revision || active || pageLoading || !page}
                    onClick={() => {
                      if (
                        window.confirm(
                          "I compared the refreshed source with my retained correction and want to use this revision.",
                        )
                      ) {
                        changeDraft({ ...draft, revision: revision! });
                        setConflict(false);
                      }
                    }}
                  >
                    Use refreshed revision after checking
                  </button>
                )}
                <div className="button-row">
                  <button
                    className="primary"
                    disabled={active || conflict || draft.revision !== revision}
                  >
                    Save checked block (not publish)
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => {
                      if (
                        window.confirm(
                          "Discard this unsaved source correction?",
                        )
                      )
                        changeDraft(null);
                    }}
                  >
                    Discard correction
                  </button>
                </div>
              </fieldset>
            </form>
          )}
        </>
      )}
    </dialog>
  );
}
