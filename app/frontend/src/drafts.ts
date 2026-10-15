export type DraftScope = {
  user: string;
  session: string;
  version: string | null;
  question: string;
  intent: "answer" | "ask" | "saved-answer" | "conversation";
  preview?: boolean;
  preview_run_id?: string;
};
export const draftKey = (s: DraftScope) =>
  `aicademiya.draft.v1:${JSON.stringify([s.user, s.session, s.version, s.preview ? "teacher-draft" : "learning", s.question, s.intent, ...(s.preview && s.preview_run_id ? ["preview-run", s.preview_run_id] : [])])}`;
export function readDraft(
  s: DraftScope,
  storage: Pick<Storage, "getItem"> = localStorage,
): string | null {
  try {
    return storage.getItem(draftKey(s));
  } catch {
    return null;
  }
}
export function writeDraft(
  s: DraftScope,
  value: string,
  storage: Pick<Storage, "setItem" | "removeItem"> = localStorage,
): boolean {
  try {
    if (value) storage.setItem(draftKey(s), value);
    else storage.removeItem(draftKey(s));
    return true;
  } catch {
    return false;
  }
}
export function clearDraft(
  s: DraftScope,
  storage: Pick<Storage, "removeItem"> = localStorage,
) {
  try {
    storage.removeItem(draftKey(s));
  } catch {
    /* do not erase other drafts */
  }
}
