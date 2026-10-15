import type { Message, Question, Workspace } from "./types";
import { activeQuestions } from "./study";

export type ProcessQuestion = {
  question: Question;
  savedResponses: number;
  revisions: number;
  guidedHelpTurns: number | null;
  discussion: "not_started" | "in_progress" | "discussed";
  latestOutcome: "unknown" | "needs_retry" | "sufficient";
  relatedMessages: Message[];
  latestResponseMessageId: string | null;
};
// Facts from this already-authorized workspace, never a model-generated summary.
// A question presentation can be related to a message whose feedback targets
// another question; preserve both relations rather than relabel the raw record.
export function questionProcessFacts(workspace: Workspace): ProcessQuestion[] {
  return activeQuestions(workspace).map((question) => {
    const attempt = workspace.attempts[question.id];
    const state = workspace.tutor?.question_states[question.id];
    const savedResponses = attempt
      ? Math.max(
          attempt.revisions?.length ?? attempt.revision_count + 1,
          attempt.answer.trim() ? 1 : 0,
        )
      : 0;
    const relatedMessages = workspace.messages.filter(
      (m) =>
        m.question_id === question.id ||
        m.metadata?.presented_question?.id === question.id ||
        m.presented_question_id === question.id,
    );
    const replies = relatedMessages.filter(
      (m) => m.role === "user" && m.question_id === question.id,
    );
    return {
      question,
      savedResponses,
      revisions: attempt?.revision_count ?? 0,
      guidedHelpTurns: state?.hint_count ?? null,
      discussion:
        state?.status ?? (savedResponses ? "in_progress" : "not_started"),
      latestOutcome: state?.last_outcome ?? "unknown",
      relatedMessages,
      latestResponseMessageId:
        replies.at(-1)?.id ?? relatedMessages.at(-1)?.id ?? null,
    };
  });
}
export function processOverview(workspace: Workspace) {
  const rows = questionProcessFacts(workspace);
  return {
    rows,
    discussed: rows.filter((r) => r.discussion === "discussed").length,
    savedResponses: rows.reduce((n, r) => n + r.savedResponses, 0),
    revisions: rows.reduce((n, r) => n + r.revisions, 0),
    guidedHelpTurns: rows.every((r) => r.guidedHelpTurns !== null)
      ? rows.reduce((n, r) => n + (r.guidedHelpTurns ?? 0), 0)
      : null,
    rawMessages: workspace.messages.length,
  };
}
export const outcomeLabel = (outcome: ProcessQuestion["latestOutcome"]) =>
  outcome === "sufficient"
    ? "Sufficient to discuss"
    : outcome === "needs_retry"
      ? "Another attempt invited"
      : "Not assessed / unknown";
