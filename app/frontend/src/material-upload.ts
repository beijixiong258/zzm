import type { Material } from "./types";
import { api, type UploadProgress } from "./api";
import { errorText as errorMessage } from "./vue/utils";
import type { DocumentCapability } from "./document-types";

export type MaterialUpload = {
  key: string;
  file: File;
  status: "queued" | "uploading" | "uploaded" | "failed";
  material?: Material;
  error?: string;
  visibility?: "student" | "teacher";
  kind?: string;
  processing?: "preview" | "full_document";
  maxBytes?: number;
  relativePath?: string;
  progress?: UploadProgress;
};
export function selectMaterialFiles(
  files: File[],
  capability: boolean | DocumentCapability = false,
): MaterialUpload[] {
  const formats =
    typeof capability === "boolean"
      ? capability
        ? ["pdf"]
        : []
      : capability.available
        ? capability.formats
        : [];
  const maximum =
    typeof capability === "boolean"
      ? 64 * 1024 * 1024
      : capability.max_upload_bytes;
  return files.map((file, index) => ({
    key: `${index}-${file.webkitRelativePath || file.name}`,
    file,
    relativePath: file.webkitRelativePath || file.name,
    status: "queued",
    processing: formats.includes(
      file.name.split(".").pop()?.toLowerCase() ?? "",
    )
      ? "full_document"
      : "preview",
    maxBytes: formats.includes(file.name.split(".").pop()?.toLowerCase() ?? "")
      ? maximum
      : 25 * 1024 * 1024,
  }));
}
// A bounded queue prevents several CPU OCR jobs from saturating the small app guest.
// Store the successful server response before readback so a failed refresh cannot
// turn a completed upload into a second upload on retry.
export async function uploadMaterialQueue(
  sid: string,
  items: MaterialUpload[],
  defaults: { visibility: "student" | "teacher"; kind: string },
  changed: (item: MaterialUpload) => void,
  isActive: () => boolean,
  upload = api.upload,
): Promise<Material[]> {
  const accepted: Material[] = [];
  for (const item of items) {
    if (!isActive()) break;
    if (item.status !== "queued" && item.status !== "failed") continue;
    let running: MaterialUpload = {
      ...item,
      status: "uploading",
      error: undefined,
      visibility: item.visibility ?? defaults.visibility,
      kind: item.kind ?? defaults.kind,
      processing: item.processing ?? "preview",
      progress: { loaded: 0, total: null, complete: false },
    };
    if (running.kind === "answer_key") running.visibility = "teacher";
    changed(running);
    try {
      const limit =
        item.maxBytes ??
        (running.processing === "full_document" ? 64 : 25) * 1024 * 1024;
      if (item.file.size > limit)
        throw new Error(
          `The upload limit is ${limit / (1024 * 1024)} MiB per file.`,
        );
      const response = await upload(
        sid,
        item.file,
        running.visibility!,
        running.kind!,
        running.processing,
        (progress) => {
          running = { ...running, progress };
          if (isActive()) changed(running);
        },
      );
      const material = { ...response, processing: running.processing };
      accepted.push(material);
      if (isActive()) changed({ ...running, status: "uploaded", material });
    } catch (error) {
      if (isActive())
        changed({ ...running, status: "failed", error: errorMessage(error) });
    }
  }
  return accepted;
}
export function uploadSuccessMessage(accepted: Material[]): string {
  const prefix = `${accepted.length} ${accepted.length === 1 ? "file" : "files"} saved.`;
  const complete = accepted.filter(
    (m) => m.processing === "full_document",
  ).length;
  if (!complete)
    return `${prefix} Text/OCR preview only; check each file’s status below.`;
  if (complete === accepted.length)
    return `${prefix} Complete-document processing requested; check each file’s status below.`;
  return `${prefix} This batch includes complete-document processing and text/OCR previews. Check each file’s status below.`;
}

export function materialReadbackMatches(
  expected: Material,
  actual?: Material,
): boolean {
  if (
    expected.processing === "full_document" &&
    expected.status === "processing"
  ) {
    // The original was accepted; CPU work may finish before this independent GET.
    return (
      !!actual &&
      actual.id === expected.id &&
      actual.title === expected.title &&
      actual.visibility === expected.visibility &&
      actual.kind === expected.kind &&
      actual.source_label === expected.source_label &&
      actual.url === expected.url &&
      actual.download_url === expected.download_url &&
      actual.preview_url === expected.preview_url &&
      actual.processing !== "preview" &&
      (!expected.document ||
        actual.document?.source_sha256 === expected.document.source_sha256)
    );
  }
  return (
    !!actual &&
    actual.id === expected.id &&
    actual.title === expected.title &&
    actual.visibility === expected.visibility &&
    actual.kind === expected.kind &&
    actual.status === expected.status &&
    actual.excerpt === expected.excerpt &&
    actual.url === expected.url &&
    JSON.stringify(actual.extraction_report ?? null) ===
      JSON.stringify(expected.extraction_report ?? null)
  );
}
