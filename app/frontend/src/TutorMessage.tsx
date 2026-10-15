import { memo, useMemo, useState } from "react";
import { ArrowUpRight, BookOpen, ChevronDown, Sparkles } from "lucide-react";
import type {
  PresentedQuestion,
  Workspace,
  Message,
  TutorState,
} from "./types";
import TeachingText from "./TeachingText";
import SourceCitations from "./SourceCitations";
import { dateLabel } from "./study";
import { withVersion } from "./stage2";
import {
  optionResponse,
  paragraphChunks,
  tutorNarrative,
} from "./guided-study";

export function QuestionPrompt({
  question,
  workspace,
  disabled = false,
  onOption,
  phase,
}: {
  question: PresentedQuestion;
  workspace: Workspace;
  disabled?: boolean;
  onOption?: (text: string) => void;
  phase?: TutorState["phase"];
}) {
  const group = workspace.session.groups.find(
    (g) => g.id === question.group_id,
  );
  const label =
    phase === "quiz"
      ? "Optional formative practice"
      : phase === "reading"
        ? "Reading discussion"
        : "Practice";
  const questionLabel =
    question.ordinal === undefined ? label : `Question ${question.ordinal}`;
  const sources = [
    ...new Set([
      ...(question.source_label ? [question.source_label] : []),
      ...(question.source_labels || []),
    ]),
  ];
  return (
    <section
      className="guided-question"
      aria-label={questionLabel}
      data-question-id={question.id}
    >
      <div className="guided-question-kicker">
        <BookOpen size={14} />
        <span>{group?.title || label}</span>
        {question.ordinal !== undefined && <span>{questionLabel}</span>}
      </div>
      {group?.description && (
        <div className="guided-word-bank preserve-text">
          {group.description}
        </div>
      )}
      <h3 className="preserve-text">{question.prompt}</h3>
      {(question.answer_slots || 1) > 1 && (
        <p className="guided-slot-note">
          {question.answer_slots} answer parts · include each part in your
          response.
        </p>
      )}
      {!!question.images?.length && (
        <div className="guided-question-images">
          {question.images.map((image) => (
            <a
              key={image.url}
              href={withVersion(image.url, workspace.version?.id)}
              target="_blank"
              rel="noreferrer"
            >
              <img
                src={withVersion(image.url, workspace.version?.id)}
                alt={image.alt || image.label}
                loading="lazy"
              />
              <span>
                {image.label}
                <ArrowUpRight size={12} />
              </span>
            </a>
          ))}
        </div>
      )}
      {!!question.options?.length && (
        <div className="guided-options">
          {question.options.map((option, i) => (
            <button
              key={i}
              type="button"
              disabled={disabled || !onOption}
              onClick={() => onOption?.(optionResponse(question, i))}
            >
              <span>{String.fromCharCode(65 + i)}</span>
              <span>{option}</span>
            </button>
          ))}
        </div>
      )}
      {sources.length > 0 && (
        <details className="guided-question-sources">
          <summary>Sources · {sources.length}</summary>
          {sources.map((source) => (
            <small key={source} className="guided-provenance">
              {source}
            </small>
          ))}
        </details>
      )}
    </section>
  );
}

export function PacedText({
  content,
  active,
}: {
  content: string;
  active: boolean;
}) {
  const chunks = useMemo(() => paragraphChunks(content), [content]);
  const [shown, setShown] = useState(1);
  const count = active ? Math.min(shown, chunks.length) : chunks.length;
  return (
    <>
      <TeachingText>{chunks.slice(0, count).join("\n\n")}</TeachingText>
      {count < chunks.length && (
        <div className="paced-controls">
          <span>
            Paced reading · {count} of {chunks.length} sections
          </span>
          <button
            type="button"
            className="secondary"
            onClick={() => setShown((n) => n + 1)}
          >
            Continue reading <ChevronDown size={14} />
          </button>
          <button
            type="button"
            className="text-button"
            onClick={() => setShown(chunks.length)}
          >
            Show full response
          </button>
        </div>
      )}
    </>
  );
}

export const TutorMessage = memo(
  function TutorMessage({
    message,
    workspace,
    latest,
    paced,
    onQuestion,
    onOption,
    highlighted = false,
  }: {
    message: Message;
    workspace: Workspace;
    latest: boolean;
    paced: boolean;
    onQuestion: (id: string) => void;
    onOption?: (text: string) => void;
    highlighted?: boolean;
  }) {
    const presented =
      message.role === "assistant"
        ? message.metadata?.presented_question ||
          (message.presented_question_id
            ? workspace.session.questions.find(
                (q) => q.id === message.presented_question_id,
              )
            : undefined)
        : undefined;
    const related = message.question_id
      ? workspace.session.questions.find((q) => q.id === message.question_id)
      : undefined;
    const narrative = tutorNarrative(message, presented);
    return (
      <article
        className={`guided-message guided-message-${message.role}${highlighted ? " is-located" : ""}`}
        data-message-id={message.id}
        tabIndex={-1}
      >
        <div className="guided-avatar" aria-hidden="true">
          {message.role === "assistant" ? (
            <Sparkles size={19} />
          ) : (
            workspace.user.name.slice(0, 1)
          )}
        </div>
        <div className="guided-message-body">
          <div className="guided-message-meta">
            <strong>
              {message.role === "assistant"
                ? "AIcademiya"
                : workspace.user.name}
            </strong>
            <time dateTime={message.created_at}>
              {dateLabel(message.created_at)}
            </time>
            {message.role === "assistant" && message.mode === "demo" && (
              <span className="guided-demo-label">Recorded demo</span>
            )}
            {message.role === "assistant" && message.mode === "system" && (
              <span className="guided-system-label">Session guide</span>
            )}
            {related && (
              <button
                type="button"
                className="guided-message-link"
                onClick={() => onQuestion(related.id)}
              >
                Question {related.ordinal}
              </button>
            )}
          </div>
          {narrative && (
            <div
              className={
                message.role === "assistant"
                  ? "markdown-content guided-message-text"
                  : "preserve-text guided-message-text"
              }
            >
              {message.role === "assistant" ? (
                <PacedText content={narrative} active={latest && paced} />
              ) : (
                message.content
              )}
            </div>
          )}
          <SourceCitations citations={message.citations} />
          {!!message.metadata?.document_read_coverage?.length && (
            <details className="source-reading-progress">
              <summary>AI source reading progress</summary>
              <ul>
                {message.metadata.document_read_coverage.map((source) => (
                  <li key={`${source.material_id}:${source.revision_id}`}>
                    <strong>{source.source_label}</strong>: {source.read_characters.toLocaleString()} / {source.available_characters.toLocaleString()} {source.text_view_id ? "selected-view" : "available text"} characters supplied.
                    {source.eligible_text_complete ? (source.text_view_id ? " Selected text view supplied in full." : " Available text supplied in full.") : ` More remains${source.next_page ? ` from source page ${source.next_page}` : ""}. Ask to continue reading.`}
                    {source.available_image_pages !== undefined && ` Original page images supplied: ${source.visual_read_pages ?? 0} / ${source.available_image_pages}.${source.visual_read_complete ? "" : " More images remain."}`}
                    {source.unresolved_blocks > 0 && ` ${source.unresolved_blocks} unresolved ${source.text_view_id ? "selected-view" : "source"} regions remain.`}
                    {source.excluded_blocks > 0 && ` ${source.excluded_blocks} source blocks were explicitly excluded.`}
                    {(source.alternative_text_blocks ?? 0) > 0 && ` ${source.alternative_text_blocks} alternative text blocks retained outside this reading count.`}
                    {(source.alternative_unresolved_blocks ?? 0) > 0 && ` ${source.alternative_unresolved_blocks} alternative blocks need source review.`}
                    {(source.alternative_excluded_blocks ?? 0) > 0 && ` ${source.alternative_excluded_blocks} alternative blocks were explicitly excluded.`}
                  </li>
                ))}
              </ul>
            </details>
          )}
          {presented && (
            <QuestionPrompt
              question={presented}
              phase={message.metadata?.phase}
              workspace={workspace}
              onOption={
                presented.id === workspace.tutor?.current_question_id
                  ? onOption
                  : undefined
              }
              disabled={
                !onOption ||
                presented.id !== workspace.tutor?.current_question_id
              }
            />
          )}
        </div>
      </article>
    );
  },
  (a, b) =>
    a.message === b.message &&
    a.workspace === b.workspace &&
    a.latest === b.latest &&
    a.paced === b.paced &&
    a.highlighted === b.highlighted &&
    !!a.onOption === !!b.onOption,
);
