import type { DocumentCapability } from "./document-types";
export const materialKinds = [
  "reading",
  "worksheet",
  "answer_key",
  "slides",
  "reference",
] as const;
export const uploadFormats = {
  preview: [
    "txt",
    "md",
    "pdf",
    "docx",
    "pptx",
    "ppt",
    "xls",
    "xlsx",
    "png",
    "jpg",
    "jpeg",
    "webp",
  ],
  worksheet: ["txt", "md", "docx", "pdf", "pptx"],
  instructions: ["txt", "md", "docx", "pdf"],
  images: ["png", "jpg", "jpeg", "webp"],
};
export const previewUploadBytes = 25 * 1024 * 1024;
export function materialFormats(capability?: DocumentCapability | null) {
  return [
    ...new Set([
      ...uploadFormats.preview,
      ...(capability?.available ? capability.formats : []),
    ]),
  ];
}
export const acceptFormats = (formats: readonly string[]) =>
  formats.map((format) => `.${format}`).join(",");
export function effectiveUploadSettings(
  item: { kind?: string; visibility?: "student" | "teacher" },
  defaults: { kind: string; visibility: "student" | "teacher" },
) {
  const kind = item.kind ?? defaults.kind;
  return {
    kind,
    visibility:
      kind === "answer_key"
        ? ("teacher" as const)
        : (item.visibility ?? defaults.visibility),
  };
}
