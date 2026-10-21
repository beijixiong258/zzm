import type { Workspace, Question } from "./types";
import { effectiveAvailability } from "./stage2";
export function activeQuestions(workspace: Workspace): Question[] {
  const ids = new Set(workspace.progress.active_question_ids);
  return workspace.session.questions.filter((q) => ids.has(q.id));
}
export function referenceBlockedReason(
  workspace: Workspace,
  question_id: string,
): string | null {
  const a = workspace.attempts[question_id];
  if (a?.reference_revealed) return null;
  if (
    workspace.read_only ||
    (workspace.version &&
      !workspace.version.is_current &&
      !workspace.version.is_draft) ||
    (workspace.user.role === "student" &&
      !effectiveAvailability(workspace.session).active)
  )
    return "References cannot be requested in this read-only or closed session.";
  if (!a?.answer.trim()) return "Save an answer to this question first.";
  if (
    workspace.session.reference_policy === "after_submit" &&
    !["submitted", "confirmed", "needs_revision"].includes(
      workspace.submission.status,
    )
  )
    return "Submit your work before requesting an example.";
  if (
    workspace.session.reference_policy === "after_feedback" &&
    !workspace.messages.some(
      (m) =>
        m.role === "assistant" &&
        m.question_id === question_id &&
        (m.mode === "demo" || m.mode === "openai") &&
        Date.parse(m.created_at) >= Date.parse(a.updated_at),
    )
  )
    return "Receive tutor feedback on your latest saved answer first.";
  return null;
}
export function canReveal(workspace: Workspace, question_id: string): boolean {
  return referenceBlockedReason(workspace, question_id) === null;
}
export function isLocked(workspace: Workspace): boolean {
  return (
    !!workspace.read_only ||
    !!(
      workspace.version &&
      !workspace.version.is_current &&
      !workspace.version.is_draft
    ) ||
    (workspace.user.role === "student" &&
      !effectiveAvailability(workspace.session).active) ||
    ["submitted", "confirmed"].includes(workspace.submission.status)
  );
}
export function canSubmit(workspace: Workspace): boolean {
  return (
    workspace.progress.total > 0 &&
    workspace.progress.answered === workspace.progress.total &&
    (!workspace.session.groups.some((g) => g.kind === "reading") ||
      !!workspace.selected_reading) &&
    !isLocked(workspace)
  );
}
export function dateLabel(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString("en-GB", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
}
