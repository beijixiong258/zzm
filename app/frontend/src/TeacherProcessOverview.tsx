import { ArrowUpRight, FileText, History, MessageSquare } from "lucide-react";
import type { Workspace } from "./types";
import { phaseLabels } from "./guided-study";
import { dateLabel } from "./study";
import { Status } from "./ui";
import { outcomeLabel, processOverview } from "./process-overview";
import "./process-overview.css";

export default function TeacherProcessOverview({
  workspace,
  onMessage,
  onResponse,
}: {
  workspace: Workspace;
  onMessage: (messageId: string) => void;
  onResponse: (questionId: string) => void;
}) {
  const facts = processOverview(workspace);
  const current = workspace.session.questions.find(
    (q) => q.id === workspace.tutor?.current_question_id,
  );
  return (
    <section
      className="process-overview"
      aria-label="Recorded learning process"
    >
      <div className="process-heading">
        <span className="eyebrow">RECORDED FACTS</span>
        <h3>{phaseLabels[workspace.tutor?.phase || "not_started"]}</h3>
        {current && <p>Current worksheet question: {current.ordinal}</p>}
        <Status status={workspace.submission.status} />
        <small>
          {workspace.version?.number
            ? `Edition ${workspace.version.number}`
            : "Selected learning record"}{" "}
          · This student's saved record only
        </small>
      </div>
      <dl className="process-totals">
        <div>
          <dt>Worksheet discussed</dt>
          <dd>
            {facts.discussed} / {facts.rows.length}
          </dd>
        </div>
        <div>
          <dt>Saved response events</dt>
          <dd>{facts.savedResponses}</dd>
        </div>
        <div>
          <dt>Recorded revisions</dt>
          <dd>{facts.revisions}</dd>
        </div>
        <div>
          <dt>Guided help turns</dt>
          <dd>{facts.guidedHelpTurns ?? "Not recorded"}</dd>
        </div>
      </dl>
      <details className="process-details">
        <summary>About these recorded facts</summary>
        <p className="process-note">
          Discussion and formative outcomes are not teacher confirmation. Help
          turns count recorded guided requests, not every hint or every mistake.
        </p>
        <p className="process-note">
          {facts.rawMessages} original messages in this edition. No AI summary
          or engagement score is generated here; unknown past outcomes are not
          reconstructed.
        </p>
      </details>
      {facts.rows.length === 0 && (
        <p>
          No required questions on this worksheet path. The original
          conversation remains available.
        </p>
      )}
      <div className="process-question-list">
        {facts.rows.map((row) => (
          <article
            className="process-question"
            key={row.question.id}
            data-process-question={row.question.id}
          >
            <div className="process-question-top">
              <strong>Question {row.question.ordinal}</strong>
              <span className="small-tag">
                {row.discussion === "discussed"
                  ? "Discussed"
                  : row.discussion === "in_progress"
                    ? "In progress"
                    : "Not started"}
              </span>
            </div>
            <p>{row.question.prompt}</p>
            <details className="process-details">
              <summary>
                Response facts · {row.savedResponses} saved · {row.revisions}{" "}
                revisions
              </summary>
              <dl className="process-question-facts">
                <div>
                  <dt>Responses</dt>
                  <dd>{row.savedResponses}</dd>
                </div>
                <div>
                  <dt>Revisions</dt>
                  <dd>{row.revisions}</dd>
                </div>
                <div>
                  <dt>Guided help</dt>
                  <dd>{row.guidedHelpTurns ?? "Unknown"}</dd>
                </div>
              </dl>
              <small>
                Latest guided outcome · {outcomeLabel(row.latestOutcome)}
              </small>
            </details>
            <div className="button-row">
              {row.latestResponseMessageId && (
                <button
                  type="button"
                  className="text-button"
                  onClick={() => onMessage(row.latestResponseMessageId!)}
                >
                  <MessageSquare size={13} />
                  Locate latest reply
                </button>
              )}
              {row.savedResponses > 0 && (
                <button
                  type="button"
                  className="text-button"
                  onClick={() => onResponse(row.question.id)}
                >
                  <History size={13} />
                  Responses & revisions
                </button>
              )}
            </div>
            {row.relatedMessages.length > 0 && (
              <details className="process-message-list">
                <summary>
                  <FileText size={13} />
                  Related original messages ({row.relatedMessages.length})
                </summary>
                {row.relatedMessages.map((message) => (
                  <button
                    type="button"
                    className="process-message-link"
                    key={message.id}
                    onClick={() => onMessage(message.id)}
                  >
                    <span>
                      <strong>
                        {message.role === "user" ? "Learner" : "Tutor"}
                      </strong>
                      <time dateTime={message.created_at}>
                        {dateLabel(message.created_at)}
                      </time>
                      <ArrowUpRight size={12} />
                    </span>
                    <span className="preserve-text">
                      {message.content.slice(0, 160)}
                      {message.content.length > 160 ? "…" : ""}
                    </span>
                  </button>
                ))}
              </details>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}
