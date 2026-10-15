import { useEffect, useState } from "react";
import { ArrowRight, BookOpen, History, Save } from "lucide-react";
import type { Question, Reference, Workspace } from "./types";
import { activeQuestions, dateLabel } from "./study";
import {
  clearDraft,
  draftKey,
  readDraft,
  writeDraft,
  type DraftScope,
} from "./drafts";
import { canRevealExample, questionStatus } from "./guided-study";
import { QuestionPrompt } from "./TutorMessage";

export default function SavedResponses({
  workspace,
  selected,
  viewerId,
  locked,
  busy,
  teacherRecord,
  references,
  onSelect,
  onDiscuss,
  onSave,
  onReveal,
  onUseDraft,
  onStorageWarning,
}: {
  workspace: Workspace;
  selected: string;
  viewerId: string;
  locked: boolean;
  busy: boolean;
  teacherRecord: boolean;
  references: Record<string, Reference>;
  onSelect: (id: string) => void;
  onDiscuss: (question: Question) => void;
  onSave: (question: Question, answer: string) => Promise<boolean>;
  onReveal: (question: Question) => void;
  onUseDraft: (text: string, scope: DraftScope) => void;
  onStorageWarning: () => void;
}) {
  const questions = activeQuestions(workspace);
  const question = questions.find((q) => q.id === selected) || questions[0];
  const qid = question?.id || "";
  const attempt = workspace.attempts[qid];
  const scope: DraftScope = {
    user: viewerId,
    session: workspace.session.id,
    version: workspace.version?.id ?? null,
    question: qid,
    intent: "saved-answer",
    preview: workspace.version?.is_draft ?? false,
    ...(workspace.version?.is_draft && workspace.preview?.id
      ? { preview_run_id: workspace.preview.id }
      : {}),
  };
  const key = draftKey(scope);
  const [answer, setAnswer] = useState("");
  useEffect(() => {
    setAnswer((!locked ? readDraft(scope) : null) ?? attempt?.answer ?? "");
  }, [key, attempt?.answer, locked]);
  const legacy = !locked
    ? (["answer", "ask"] as const)
        .map((intent) => {
          const old = { ...scope, intent };
          return {
            scope: old,
            text: readDraft(old),
            label: intent === "answer" ? "Unsent response" : "Unsent question",
          };
        })
        .filter((item) => item.text)
    : [];
  const reference = references[qid];
  const teacherReference = teacherRecord
    ? workspace.session.reference_answers?.[qid]
    : undefined;
  if (!question)
    return (
      <p className="guided-empty-note">
        No worksheet responses yet. Your conversation is saved separately.
      </p>
    );
  return (
    <div className="saved-responses">
      <div className="saved-response-overview">
        <strong>
          {workspace.progress.answered} / {workspace.progress.total}
        </strong>
        <span>responses saved</span>
      </div>
      <label className="guided-field">
        Browse questions
        <select
          aria-label="Browse questions"
          value={qid}
          disabled={busy}
          onChange={(e) => onSelect(e.target.value)}
        >
          {workspace.session.groups.map((group) => (
            <optgroup key={group.id} label={group.title}>
              {questions
                .filter((q) => q.group_id === group.id)
                .map((q) => (
                  <option key={q.id} value={q.id}>
                    {q.ordinal}. {q.prompt.slice(0, 65)}
                  </option>
                ))}
            </optgroup>
          ))}
        </select>
      </label>
      <div className="guided-question-status">
        <span>{questionStatus(workspace, qid)}</span>
        {workspace.tutor?.question_states[qid] && (
          <small>
            {workspace.tutor.question_states[qid].answer_count} responses ·{" "}
            {workspace.tutor.question_states[qid].hint_count} help turns
          </small>
        )}
      </div>
      <QuestionPrompt question={question} workspace={workspace} disabled />
      {!locked && (
        <button
          className="secondary full"
          disabled={
            busy || (!attempt && workspace.tutor?.current_question_id !== qid)
          }
          onClick={() => onDiscuss(question)}
        >
          Discuss this question <ArrowRight size={15} />
        </button>
      )}
      <section className="guided-saved-answer">
        <h3>
          <Save size={15} /> Saved response
        </h3>
        {locked ? (
          <p className="preserve-text">
            {attempt?.answer || "No response has been saved."}
          </p>
        ) : (
          <>
            <textarea
              aria-label="Edit saved response"
              rows={5}
              value={answer}
              onChange={(e) => {
                setAnswer(e.target.value);
                if (!writeDraft(scope, e.target.value)) onStorageWarning();
              }}
              disabled={busy}
            />
            <button
              className="primary full"
              disabled={
                busy || !answer.trim() || answer === (attempt?.answer || "")
              }
              onClick={async () => {
                if (await onSave(question, answer)) clearDraft(scope);
              }}
            >
              Save response
            </button>
            <small>
              {answer !== (attempt?.answer || "")
                ? "Draft on this device · not saved to your record"
                : "Saved to your record."}
            </small>
          </>
        )}
        {attempt && (
          <small className="saved-response-metadata">
            Saved {dateLabel(attempt.updated_at)} · revision{" "}
            {attempt.revision_count}
          </small>
        )}
        {!!attempt?.revisions?.length && (
          <details className="guided-revisions">
            <summary>
              <History size={14} /> Earlier responses
            </summary>
            {attempt.revisions.map((revision, i) => (
              <div key={i}>
                <time dateTime={revision.created_at}>
                  {dateLabel(revision.created_at)}
                </time>
                <p className="preserve-text">{revision.answer}</p>
              </div>
            ))}
          </details>
        )}
      </section>
      {legacy.length > 0 && (
        <details className="guided-legacy-drafts">
          <summary>Earlier unsent drafts</summary>
          {legacy.map((item) => (
            <div key={item.scope.intent}>
              <strong>{item.label}</strong>
              <p className="preserve-text">{item.text}</p>
              <button
                className="text-button"
                disabled={busy}
                onClick={() => onUseDraft(item.text!, item.scope)}
              >
                Use in conversation
              </button>
            </div>
          ))}
        </details>
      )}
      <section className="guided-reference">
        <h3>
          <BookOpen size={15} /> Instructor example
        </h3>
        {teacherReference ? (
          <p className="preserve-text">{teacherReference}</p>
        ) : (
          <>
            {!teacherRecord && (
              <button
                className="text-button"
                disabled={busy || !canRevealExample(workspace, qid)}
                onClick={() => onReveal(question)}
              >
                {attempt?.reference_revealed
                  ? "Read example again"
                  : "Request instructor example"}
              </button>
            )}
            {reference && (
              <>
                <p className="preserve-text">{reference.reference}</p>
                <small>{reference.source_label}</small>
              </>
            )}
            {!reference && !attempt?.reference_revealed && (
              <small>
                {!attempt?.answer
                  ? "Try and save your response first."
                  : workspace.session.reference_policy === "after_submit"
                    ? "Available after submitting your work."
                    : workspace.session.reference_policy === "after_feedback"
                      ? "Available after feedback on your response."
                      : "You can request a comparison with the instructor example."}
              </small>
            )}
          </>
        )}
      </section>
    </div>
  );
}
