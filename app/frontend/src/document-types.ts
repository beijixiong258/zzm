export type DocumentQuality = "extracted" | "needs_review" | "approved";
export type BlockQuality = DocumentQuality | "excluded";
export type DocumentInfo = {
  source_format?: string | null;
  has_rendered_pdf?: boolean | null;
  revision_id: string;
  source_sha256: string;
  page_count: number;
  block_count: number;
  quality: DocumentQuality;
  review_count: number;
  parser: { name: string; version: string; recipe: string };
  created_at: string;
  warnings: string[];
};
export type DocumentJob = {
  id: string;
  material_id: string;
  status: "queued" | "running" | "completed" | "failed";
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  page_count: number | null;
  processed_pages: number;
  error: string | null;
  revision_id: string | null;
};
export type DocumentPageSummary = {
  number: number;
  printed_label: string | null;
  status: "text" | "blank" | "needs_review" | "failed";
  block_count: number;
  review_count: number;
};
export type DocumentBlock = {
  id: string;
  type:
    | "text"
    | "heading"
    | "list"
    | "table"
    | "image"
    | "caption"
    | "header"
    | "footer"
    | "page_number"
    | "equation"
    | "other";
  bbox: [number, number, number, number];
  text: string;
  text_format?: "plain" | "markdown";
  visual_description?: string;
  quality: BlockQuality;
  issues: string[];
  assets: string[];
  parent_id: string | null;
  raw_text?: string;
  review?: { by: string; at: string; reason: string };
};
export type DocumentPage = Omit<
  DocumentPageSummary,
  "block_count" | "review_count"
> & {
  rotation: 0 | 90 | 180 | 270;
  image_url: string;
  width: number;
  height: number;
  issues: string[];
  blocks: DocumentBlock[];
};
export type DocumentSummary = {
  document: DocumentInfo | null;
  latest_job: DocumentJob | null;
  pages: DocumentPageSummary[];
  supplements?: DocumentSupplementSummary[];
};
export type DocumentSupplementSummary = {
  id: string;
  kind: string;
  source_part: string;
  source_node: string;
  page_hint: number | null;
  visibility: "teacher" | "student";
  characters: number;
  preview: string;
};
export type DocumentSupplementSharing = {
  request_id: string;
  expected_revision: string;
  visible_to_students: boolean;
  reason: string;
};
export type DocumentCapability = {
  available: boolean;
  formats: string[];
  max_upload_bytes: number;
  max_pages: number;
};
export type DocumentJobRequest = {
  request_id: string;
  expected_revision: string | null;
};
export type DocumentReviewChange = {
  block_id: string;
  text?: string;
  quality: "approved" | "excluded";
  reason: string;
};
export type DocumentReviewRequest = {
  request_id: string;
  expected_revision: string;
  changes: DocumentReviewChange[];
};
export type DocumentReviewReceipt = { document: DocumentInfo };
export type DocumentCitation = {
  kind: "document";
  version_id: string | null;
  source_label: string;
  url: string;
  material_id: string;
  revision_id: string;
  page: number;
  printed_label: string | null;
  block_id: string;
  quote: string;
};
