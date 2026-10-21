import type { Group, Question, WorksheetDraft } from "./types";
import { clientId } from "./ids";

export const newGroup = (): Group => ({
  id: `g-${clientId()}`,
  title: "",
  kind: "core",
  description: "",
});
export const newQuestion = (groupId: string, ordinal: number): Question => ({
  id: `q-${clientId()}`,
  group_id: groupId,
  ordinal,
  type: "open_response",
  prompt: "",
  options: [],
  answer_slots: 1,
  images: [],
  source_label: "",
  source_material_ids: [],
  source_links: [],
});

/** Compare authored fields; omit server-normalized external links and private asset keys. */
export function worksheetReadbackMatches(
  expected: WorksheetDraft,
  actual: WorksheetDraft,
): boolean {
  const groups = (value: WorksheetDraft) =>
    value.groups.map((g) => [g.id, g.title, g.kind, g.description || ""]);
  const questions = (value: WorksheetDraft) =>
    value.questions.map((q) => [
      q.id,
      q.group_id,
      q.ordinal,
      q.type,
      q.prompt,
      q.options || [],
      q.answer_slots || 1,
      q.images.map((image) => [image.label || "", image.url, image.alt || ""]),
      q.source_label || "",
      q.hint || "",
      q.source_material_ids || [],
    ]);
  return (
    JSON.stringify(groups(expected)) === JSON.stringify(groups(actual)) &&
    JSON.stringify(questions(expected)) === JSON.stringify(questions(actual)) &&
    JSON.stringify(Object.entries(expected.reference_answers).sort()) ===
      JSON.stringify(Object.entries(actual.reference_answers).sort())
  );
}
