import { request } from "./api";
import type {
  DocumentCapability,
  DocumentSummary,
  DocumentPage,
  DocumentJob,
  DocumentJobRequest,
  DocumentReviewRequest,
  DocumentReviewReceipt,
  DocumentSupplementSharing,
} from "./document-types";
const id = encodeURIComponent;
const base = (mid: string) => `/materials/${id(mid)}/document`;
export function documentQuery(versionId?: string | null, revisionId?: string) {
  const params = new URLSearchParams();
  if (versionId != null) params.set("version_id", versionId);
  if (revisionId !== undefined) params.set("revision_id", revisionId);
  return params.size ? `?${params.toString()}` : "";
}
export const documentApi = {
  supplementUrl: (mid: string, sid: string, revisionId: string, versionId?: string | null) =>
    `/api${base(mid)}/supplements/${id(sid)}/text${documentQuery(versionId, revisionId)}`,
  shareSupplements: (mid: string, payload: DocumentSupplementSharing) =>
    request<DocumentReviewReceipt>(`${base(mid)}/supplements/sharing`, {method:"POST",body:JSON.stringify(payload)}),
  renderedUrl: (mid: string, revisionId: string, versionId?: string | null) =>
    `/api${base(mid)}/pdf${documentQuery(versionId, revisionId)}`,
  capability: (signal?: AbortSignal) =>
    request<DocumentCapability>("/document-processing", { signal }),
  summary: (mid: string, versionId?: string | null, signal?: AbortSignal) =>
    request<DocumentSummary>(base(mid) + documentQuery(versionId), { signal }),
  page: (
    mid: string,
    page: number,
    revisionId: string,
    versionId?: string | null,
    signal?: AbortSignal,
  ) =>
    request<DocumentPage>(
      `${base(mid)}/pages/${page}${documentQuery(versionId, revisionId)}`,
      { signal },
    ),
  start: (mid: string, payload: DocumentJobRequest) =>
    request<DocumentJob>(`${base(mid)}/jobs`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  job: (mid: string, jid: string) =>
    request<DocumentJob>(`${base(mid)}/jobs/${id(jid)}`),
  jobByRequest: (mid: string, requestId: string) =>
    request<DocumentJob>(`${base(mid)}/jobs/requests/${id(requestId)}`),
  review: (mid: string, payload: DocumentReviewRequest) =>
    request<DocumentReviewReceipt>(`${base(mid)}/reviews`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  reviewByRequest: (mid: string, requestId: string) =>
    request<DocumentReviewReceipt>(`${base(mid)}/reviews/${id(requestId)}`),
};
