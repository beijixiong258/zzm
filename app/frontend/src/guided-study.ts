import type {
  Message,
  PresentedQuestion,
  TutorState,
  TutorTurn,
  Workspace,
} from "./types";
import { clearDraft, readDraft, type DraftScope } from "./drafts";
import { canReveal } from "./study";

export const phaseLabels: Record<TutorState["phase"], string> = {
  not_started: "Ready to begin",
  warmup: "Recall & connect",
  worksheet: "Guided practice",
  quiz_offer: "Optional practice",
  quiz: "Practice quiz",
  reading: "Reading discussion",
  wrap_up: "Bring it together",
  complete: "Session wrap-up",
};
// Keep native IME confirmation and Shift+Enter editing separate from sending.
// Modified Enter is not a second send shortcut (or an advertised newline).
export function composerEnterAction(
  event: {
    key: string;
    shiftKey?: boolean;
    ctrlKey?: boolean;
    metaKey?: boolean;
    altKey?: boolean;
    repeat?: boolean;
    isComposing?: boolean;
    keyCode?: number;
  },
  composing = false,
): "native" | "ignore" | "send" {
  if (event.key !== "Enter") return "native";
  if (composing || event.isComposing || event.keyCode === 229) return "native";
  if (event.ctrlKey || event.metaKey || event.altKey) return "ignore";
  if (event.shiftKey) return "native";
  return event.repeat ? "ignore" : "send";
}

// Byte-for-byte counterpart of guided_state.presentation_text's question branch.
// No markdown parsing, whitespace normalization or prose-matching regex: only
// this known terminal block can be replaced by its already rendered public card.
export function questionPresentationText(
  question: PresentedQuestion,
  phase: TutorState["phase"] | undefined,
): string {
  const label =
    phase === "quiz"
      ? "Optional formative practice"
      : phase === "reading"
        ? "Reading discussion"
        : "Worksheet question";
  let text = `\n\n${label}:\n${question.prompt}`;
  if (question.options?.length)
    text +=
      "\n" +
      question.options
        .map((option, index) => `${index + 1}. ${option}`)
        .join("\n");
  if (question.images?.length)
    text += "\nRefer to the configured figures shown with this question.";
  return text;
}

type DisplayMessage = Pick<Message, "role" | "content"> & {
  metadata?: Message["metadata"] & {
    narrative_text?: string;
    presentation_text?: string;
  };
};
export function tutorNarrative(
  message: DisplayMessage,
  presented?: PresentedQuestion,
): string {
  if (message.role !== "assistant" || !presented) return message.content;
  const suffix = questionPresentationText(presented, message.metadata?.phase);
  const metadata = message.metadata;
  // New replies carry explicit parts; validate against raw content rather than
  // hiding prose if malformed/stale metadata happens to disagree with it.
  if (
    typeof metadata?.narrative_text === "string" &&
    metadata.presentation_text === suffix &&
    message.content === metadata.narrative_text + suffix
  )
    return metadata.narrative_text;
  // Legacy replies (and a later server-inserted instructor comparison) retain
  // their entire narrative. Suppress only the exact known appended duplicate.
  return message.content.endsWith(suffix)
    ? message.content.slice(0, -suffix.length)
    : message.content;
}
export function recordedSpan(seconds: number): string {
  const minutes = Math.floor(Math.max(0, seconds) / 60);
  if (!minutes) return "Less than a minute";
  return minutes < 60
    ? `${minutes} min`
    : `${Math.floor(minutes / 60)} hr ${minutes % 60} min`;
}
export function conversationQuestion(workspace: Workspace): string {
  return (
    workspace.tutor?.current_question_id ||
    `phase:${workspace.tutor?.phase || "not_started"}`
  );
}
export function conversationScope(
  workspace: Workspace,
  viewer: string,
): DraftScope {
  return {
    user: viewer,
    session: workspace.session.id,
    version: workspace.version?.id ?? null,
    preview: workspace.version?.is_draft ?? false,
    ...(workspace.version?.is_draft && workspace.preview?.id
      ? { preview_run_id: workspace.preview.id }
      : {}),
    question: conversationQuestion(workspace),
    intent: "conversation",
  };
}
export function questionStatus(workspace: Workspace, qid: string): string {
  const state = workspace.tutor?.question_states[qid];
  if (state?.last_outcome === "needs_retry") return "Keep exploring";
  if (state?.status === "discussed") return "Discussed";
  if (workspace.attempts[qid]?.answer) return "Response saved";
  return "Not yet started";
}
export function optionResponse(
  question: PresentedQuestion,
  index: number,
): string {
  const letter = String.fromCharCode(65 + index);
  // Quiz/single-choice scoring expects a bare choice. Other worksheet option
  // banks still insert their full text rather than replacing a word with a letter.
  return question.type === "single_choice"
    ? letter
    : `${letter}. ${question.options?.[index] || ""}`;
}
export function canRevealExample(workspace: Workspace, qid: string): boolean {
  // Submission locks editing, not an eligible explicit after-submit reveal.
  // Historical, inactive and archived restrictions remain independently checked.
  return canReveal(
    workspace.read_only_reason === "submission_locked"
      ? { ...workspace, read_only: false }
      : workspace,
    qid,
  );
}
export function sameTurn(
  a: TutorTurn,
  b: Omit<TutorTurn, "request_id">,
): boolean {
  return (
    a.message === b.message &&
    (a.action || "message") === (b.action || "message") &&
    a.question_id === b.question_id &&
    !!a.web_search === !!b.web_search &&
    a.preview_id === b.preview_id
  );
}
export type PendingTutorTurn = {
  turn: TutorTurn;
  scope: DraftScope;
  clear_draft?: boolean;
};
export const pendingKey = (scope: DraftScope) =>
  `aicademiya.tutor-request.v1:${JSON.stringify([scope.user, scope.session, scope.version, !!scope.preview, ...(scope.preview && scope.preview_run_id ? ["preview-run", scope.preview_run_id] : [])])}`;
export function readPending(
  scope: DraftScope,
  storage: Pick<Storage, "getItem"> = localStorage,
): PendingTutorTurn | null {
  try {
    const value = JSON.parse(
      storage.getItem(pendingKey(scope)) || "null",
    ) as PendingTutorTurn | null;
    if (
      !value ||
      typeof value.turn?.request_id !== "string" ||
      typeof value.turn?.message !== "string" ||
      !value.scope
    )
      return null;
    if (pendingKey(value.scope) !== pendingKey(scope)) return null;
    return value;
  } catch {
    return null;
  }
}
export function storePending(
  value: PendingTutorTurn,
  storage: Pick<Storage, "setItem"> = localStorage,
): boolean {
  try {
    storage.setItem(pendingKey(value.scope), JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}
export function clearPending(
  scope: DraftScope,
  storage: Pick<Storage, "removeItem"> = localStorage,
): void {
  try {
    storage.removeItem(pendingKey(scope));
  } catch {
    /* Unsent draft remains independent. */
  }
}
// Identity acknowledges the commit; draft comparison only protects newer edits.
export function acknowledgePending(
  scope: DraftScope,
  completedRequestId: string | null | undefined,
  storage: Pick<Storage, "getItem" | "removeItem"> = localStorage,
  fallback?: PendingTutorTurn | null,
): PendingTutorTurn | null {
  const saved =
    readPending(scope, storage) ||
    (fallback && pendingKey(fallback.scope) === pendingKey(scope)
      ? fallback
      : null);
  if (!saved || saved.turn.request_id !== completedRequestId) return null;
  clearPending(saved.scope, storage);
  if (
    saved.clear_draft &&
    readDraft(saved.scope, storage) === saved.turn.message
  )
    clearDraft(saved.scope, storage);
  return saved;
}
export function paragraphChunks(text: string): string[] {
  const parts: string[] = [];
  let lines: string[] = [],
    fenced = false;
  for (const line of text.split("\n")) {
    if (/^\s*(```|~~~)/.test(line)) fenced = !fenced;
    if (!line.trim() && !fenced && lines.length) {
      parts.push(lines.join("\n"));
      lines = [];
    } else lines.push(line);
  }
  if (lines.join("\n").trim()) parts.push(lines.join("\n"));
  return parts.length ? parts : [text];
}
