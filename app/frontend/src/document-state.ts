import { t } from "./i18n";
import { ApiError } from "./api";
import type {
  DocumentInfo,
  DocumentJob,
  DocumentPage,
  DocumentReviewChange,
} from "./document-types";

/** Accept only server-authenticated assets for this exact material/revision/edition. */
export function authorizedDocumentAsset(
  value: string,
  mid: string,
  rid: string,
  versionId?: string | null,
) {
  const prefix = `/api/materials/${encodeURIComponent(mid)}/document/assets/`;
  if (!value.startsWith(prefix)) return null;
  try {
    const url = new URL(value, "http://local");
    if (
      !url.pathname.startsWith(prefix) ||
      url.searchParams.get("revision_id") !== rid ||
      (versionId != null && url.searchParams.get("version_id") !== versionId)
    )
      return null;
    return `${url.pathname}${url.search}`;
  } catch {
    return null;
  }
}
export function jobIsActive(job: DocumentJob | null) {
  return job?.status === "queued" || job?.status === "running";
}
export function processingLabel(job: DocumentJob) {
  if (job.status === "queued") return t("Queued for full document processing");
  if (job.status === "failed")
    return t("Processing failed — the original is retained");
  if (job.status === "completed") return t("Complete document saved");
  // Never synthesize percentages from elapsed time or a guessed page total.
  return job.page_count !== null && job.processed_pages > 0
    ? t("Processing · {0} of {1} PDF pages reported", [
        job.processed_pages,
        job.page_count,
      ])
    : t("Processing complete document…");
}
export function uncertainDocumentWrite(error: unknown) {
  return (
    !(error instanceof ApiError) || error.status >= 500 || error.status === 408
  );
}
export function reviewReadbackMatches(
  before: DocumentInfo,
  receipt: DocumentInfo,
  current: DocumentInfo,
  page: DocumentPage,
  changes: DocumentReviewChange[],
) {
  if (
    receipt.revision_id === before.revision_id ||
    current.revision_id !== receipt.revision_id ||
    receipt.source_sha256 !== before.source_sha256 ||
    current.source_sha256 !== before.source_sha256 ||
    current.page_count !== receipt.page_count ||
    current.block_count !== receipt.block_count ||
    current.review_count !== receipt.review_count ||
    current.quality !== receipt.quality
  )
    return false;
  return (
    changes.length > 0 &&
    changes.every((change) => {
      const block = page.blocks.find((b) => b.id === change.block_id);
      return (
        !!block &&
        block.quality === change.quality &&
        (change.text === undefined || block.text === change.text) &&
        block.review?.reason === change.reason &&
        !!block.review.by &&
        !!block.review.at
      );
    })
  );
}
export function reviewChangeError(text: string, reason: string) {
  if (Array.from(text).length > 100000)
    return t("A block cannot exceed 100,000 characters.");
  if (!reason.trim()) return t("Describe what you checked in the original.");
  if (Array.from(reason).length > 2000)
    return t("Keep the source-review reason within 2,000 characters.");
  return "";
}
