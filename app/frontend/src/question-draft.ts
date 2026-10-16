import type { Group, Question } from "./types";
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
