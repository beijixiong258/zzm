import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, ApiError } from "./api";
import { clientId } from "./ids";
import { useUnsavedChanges } from "./navigation-guard";
import { ErrorBanner, Notice, errorMessage } from "./ui";
import type {
  FeedbackCategory,
  FeedbackCreate,
  FeedbackItem,
  FeedbackPage,
  FeedbackStatus,
  FeedbackUpdate,
  User,
} from "./types";
import "./feedback.css";

type Draft = {
  category: FeedbackCategory;
  subject: string;
  message: string;
  attempt: FeedbackCreate | null;
  acceptedId: string | null;
};
type ReplyDraft = FeedbackUpdate;
const categories: FeedbackCategory[] = ["bug", "idea", "general"];
const statuses: FeedbackStatus[] = ["new", "reviewed"];
const emptyDraft = (): Draft => ({
  category: "general",
  subject: "",
  message: "",
  attempt: null,
  acceptedId: null,
});
export const feedbackDraftKey = (accountId: string) =>
  `aicademiya:feedback:v1:${encodeURIComponent(accountId)}`;
const length = (text: string) => Array.from(text).length;
export function feedbackValidation(subject: string, message: string): string {
  if (!subject.trim() || !message.trim())
    return "Enter a subject and a message.";
  if (length(subject) > 160 || length(message) > 6000)
    return "The subject must be at most 160 characters and the message at most 6,000 characters.";
  return "";
}
export function feedbackSubmissionMatches(
  item: FeedbackItem,
  payload: FeedbackCreate,
): boolean {
  return (
    item.request_id === payload.request_id &&
    item.category === payload.category &&
    item.subject === payload.subject.trim() &&
    item.message === payload.message.trim()
  );
}
export function feedbackReplyMatches(
  item: FeedbackItem,
  id: string,
  payload: FeedbackUpdate,
  revision: number,
): boolean {
  return (
    item.id === id &&
    revision === payload.expected_revision + 1 &&
    item.status === payload.status &&
    item.reply === payload.reply.trim() &&
    item.revision === revision
  );
}
export function parseFeedbackDraft(raw: string | null): Draft {
  if (!raw) return emptyDraft();
  try {
    const d = JSON.parse(raw) as Draft;
    if (
      !categories.includes(d.category) ||
      typeof d.subject !== "string" ||
      typeof d.message !== "string"
    )
      return emptyDraft();
    if (
      d.attempt &&
      (!/^[A-Za-z0-9_-]{1,80}$/.test(d.attempt.request_id) ||
        !categories.includes(d.attempt.category) ||
        typeof d.attempt.subject !== "string" ||
        typeof d.attempt.message !== "string" ||
        feedbackValidation(d.attempt.subject, d.attempt.message))
    )
      return emptyDraft();
    return {
      ...d,
      attempt: d.attempt || null,
      acceptedId: typeof d.acceptedId === "string" ? d.acceptedId : null,
    };
  } catch {
    return emptyDraft();
  }
}
function loadDraft(id: string): Draft {
  try {
    return parseFeedbackDraft(localStorage.getItem(feedbackDraftKey(id)));
  } catch {
    return emptyDraft();
  }
}
const titleCase = (value: string) => value[0].toUpperCase() + value.slice(1);
function Time({ value }: { value: string }) {
  return (
    <time dateTime={value}>
      {new Date(value).toLocaleString("en-GB", {
        dateStyle: "medium",
        timeStyle: "short",
      })}
    </time>
  );
}
function Badge({ status }: { status: FeedbackStatus }) {
  return (
    <span className={`feedback-status feedback-status--${status}`}>
      {titleCase(status)}
    </span>
  );
}
export default function Feedback({ user }: { user: User }) {
  return <AccountFeedback key={`${user.id}:${user.role}`} user={user} />;
}
function AccountFeedback({ user }: { user: User }) {
  const [draft, setDraft] = useState<Draft>(() => loadDraft(user.id));
  const [storageError, setStorageError] = useState("");
  const draftRef = useRef(draft);
  const alive = useRef(true);
  const [submitBusy, setSubmitBusy] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [notice, setNotice] = useState("");
  const [scope, setScope] = useState<"mine" | "inbox">("mine");
  const [category, setCategory] = useState<FeedbackCategory | "">("");
  const [status, setStatus] = useState<FeedbackStatus | "">("");
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<FeedbackPage | null>(null);
  const [listBusy, setListBusy] = useState(true);
  const [listError, setListError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [item, setItem] = useState<FeedbackItem | null>(null);
  const [detailBusy, setDetailBusy] = useState(false);
  const [detailError, setDetailError] = useState("");
  const detailGeneration = useRef(0);
  const detailHeading = useRef<HTMLHeadingElement>(null);
  const [replies, setReplies] = useState<Record<string, ReplyDraft>>({});
  const [replyBusy, setReplyBusy] = useState(false);
  const [replyError, setReplyError] = useState("");
  const [conflict, setConflict] = useState(false);
  const [pendingReply, setPendingReply] = useState<{
    id: string;
    payload: FeedbackUpdate;
    revision: number;
    accepted: boolean;
  } | null>(null);
  const admin = scope === "inbox";
  const mutationBusy = submitBusy || replyBusy;
  const reply = item
    ? replies[item.id] || {
        reply: item.reply,
        status: item.status,
        expected_revision: item.revision,
      }
    : null;
  const replyDirty =
    !!item &&
    !!reply &&
    (reply.reply !== item.reply || reply.status !== item.status);
  useUnsavedChanges(
    !!draft.subject ||
      !!draft.message ||
      !!draft.attempt ||
      Object.keys(replies).length > 0 ||
      mutationBusy ||
      listBusy ||
      detailBusy ||
      !!pendingReply,
  );
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      detailGeneration.current++;
    };
  }, []);
  useEffect(() => {
    if (!selected) return;
    detailHeading.current?.focus({ preventScroll: true });
    detailHeading.current?.scrollIntoView({ block: "start" });
  }, [selected]);
  // Persist synchronously before writes so refresh/retry keeps the exact request identity.
  function keepDraft(next: Draft) {
    draftRef.current = next;
    setDraft(next);
    try {
      if (!next.subject && !next.message && !next.attempt)
        localStorage.removeItem(feedbackDraftKey(user.id));
      else
        localStorage.setItem(feedbackDraftKey(user.id), JSON.stringify(next));
      setStorageError("");
    } catch {
      setStorageError(
        "Local draft storage is unavailable. Keep this page open until your submission is verified.",
      );
    }
  }
  useEffect(() => {
    let active = true;
    setListBusy(true);
    setListError("");
    setPage(null);
    api
      .feedbackList(
        {
          offset,
          limit: 25,
          ...(category ? { category } : {}),
          ...(status ? { status } : {}),
        },
        admin,
      )
      .then((result) => {
        if (!active) return;
        if (
          result.offset !== offset ||
          result.limit < 1 ||
          result.total < result.items.length
        )
          throw new Error("The feedback page could not be verified.");
        if (offset > 0 && !result.items.length && result.total <= offset) {
          setOffset(Math.max(0, Math.ceil(result.total / 25) * 25 - 25));
          return;
        }
        setPage(result);
      })
      .catch((e) => {
        if (active) setListError(errorMessage(e));
      })
      .finally(() => {
        if (active) setListBusy(false);
      });
    return () => {
      active = false;
    };
  }, [offset, category, status, admin, refresh]);
  function clearDetail() {
    detailGeneration.current++;
    setSelected(null);
    setItem(null);
    setDetailBusy(false);
    setDetailError("");
    setReplyError("");
    setConflict(false);
  }
  function changeScope(next: "mine" | "inbox") {
    if (mutationBusy || pendingReply || listBusy || next === scope) return;
    if (
      Object.keys(replies).length &&
      !window.confirm(
        "Keep your unsaved inbox replies for this page and switch lists?",
      )
    )
      return;
    setScope(next);
    setOffset(0);
    setCategory("");
    setStatus("");
    clearDetail();
    setNotice("");
  }
  async function openDetail(id: string, allowDirty = false) {
    if (mutationBusy || pendingReply) return;
    if (
      !allowDirty &&
      replyDirty &&
      selected !== id &&
      !window.confirm(
        "Keep this unsaved reply for its item and open another feedback item?",
      )
    )
      return;
    const generation = ++detailGeneration.current;
    setSelected(id);
    setItem(null);
    setDetailBusy(true);
    setDetailError("");
    setReplyError("");
    setConflict(false);
    try {
      const result = await api.feedbackGet(id, admin);
      if (!alive.current || generation !== detailGeneration.current) return;
      if (result.id !== id)
        throw new Error("The feedback detail did not match the selected item.");
      setItem(result);
    } catch (e) {
      if (alive.current && generation === detailGeneration.current)
        setDetailError(errorMessage(e));
    } finally {
      if (alive.current && generation === detailGeneration.current)
        setDetailBusy(false);
    }
  }
  async function acknowledgeSubmission(
    saved: FeedbackItem,
    payload: FeedbackCreate,
  ) {
    if (!feedbackSubmissionMatches(saved, payload))
      throw new Error(
        "The saved feedback does not match this request. Your draft is retained.",
      );
    if (!alive.current) return;
    keepDraft(emptyDraft());
    setSubmitError("");
    setNotice(
      "Feedback sent and verified. You can follow its status and any human reply in My feedback.",
    );
    setRefresh((n) => n + 1);
    if (!admin) {
      detailGeneration.current++;
      setDetailBusy(false);
      setSelected(saved.id);
      setItem(saved);
      setDetailError("");
    }
  }
  async function submit(e?: FormEvent) {
    e?.preventDefault();
    if (mutationBusy || pendingReply) return;
    const savedDraft = draftRef.current;
    const validation = feedbackValidation(
      savedDraft.subject,
      savedDraft.message,
    );
    if (validation) {
      setSubmitError(validation);
      return;
    }
    const payload = savedDraft.attempt || {
      request_id: clientId(),
      category: savedDraft.category,
      subject: savedDraft.subject,
      message: savedDraft.message,
    };
    keepDraft({ ...savedDraft, attempt: payload });
    setSubmitBusy(true);
    setSubmitError("");
    setNotice("");
    let acceptedId = savedDraft.acceptedId;
    try {
      if (savedDraft.attempt) {
        if (acceptedId) {
          const verified = await api.feedbackGet(acceptedId);
          if (verified.id !== acceptedId)
            throw new Error("The saved feedback ID did not match.");
          await acknowledgeSubmission(verified, payload);
          return;
        }
        try {
          await acknowledgeSubmission(
            await api.feedbackByRequest(payload.request_id),
            payload,
          );
          return;
        } catch (e) {
          if (!(e instanceof ApiError && e.status === 404)) throw e;
        }
      }
      let accepted: FeedbackItem;
      try {
        accepted = await api.feedbackCreate(payload);
      } catch (writeError) {
        // A lost POST response may already have committed; recover with an exact independent GET.
        try {
          await acknowledgeSubmission(
            await api.feedbackByRequest(payload.request_id),
            payload,
          );
          return;
        } catch (readError) {
          if (
            readError instanceof ApiError &&
            readError.status === 404 &&
            writeError instanceof ApiError &&
            writeError.status >= 400 &&
            writeError.status < 500 &&
            writeError.status !== 409
          ) {
            if (alive.current)
              keepDraft({ ...savedDraft, attempt: null, acceptedId: null });
            throw writeError;
          }
          throw new Error(
            `Submission could not be confirmed. Retry checks the same request without creating a duplicate. ${errorMessage(writeError)}`,
          );
        }
      }
      acceptedId = accepted.id;
      if (!alive.current) return;
      keepDraft({ ...draftRef.current, acceptedId });
      if (!feedbackSubmissionMatches(accepted, payload))
        throw new Error("The submission response did not match your feedback.");
      const verified = await api.feedbackGet(accepted.id);
      if (verified.id !== accepted.id)
        throw new Error("The saved feedback ID did not match.");
      await acknowledgeSubmission(verified, payload);
    } catch (e) {
      if (alive.current)
        setSubmitError(
          `${acceptedId ? "Feedback was accepted, but verification is incomplete. Check the saved submission. " : ""}${errorMessage(e)}`,
        );
    } finally {
      if (alive.current) setSubmitBusy(false);
    }
  }
  function editReply(values: Partial<FeedbackUpdate>) {
    if (!item || !reply || replyBusy || pendingReply) return;
    const next = { ...reply, ...values };
    setReplies((previous) => {
      const copy = { ...previous };
      if (
        next.reply === item.reply &&
        next.status === item.status &&
        next.expected_revision === item.revision
      )
        delete copy[item.id];
      else copy[item.id] = next;
      return copy;
    });
    setNotice("");
  }
  async function verifyReply(target: NonNullable<typeof pendingReply>) {
    const verified = await api.feedbackGet(target.id, true);
    if (
      !feedbackReplyMatches(
        verified,
        target.id,
        target.payload,
        target.revision,
      )
    )
      throw new Error(
        "The saved reply differs or has a newer revision. Load the latest revision and review your retained draft.",
      );
    if (!alive.current) return;
    setItem(verified);
    setPendingReply(null);
    setReplies((previous) => {
      const copy = { ...previous };
      delete copy[target.id];
      return copy;
    });
    setConflict(false);
    setReplyError("");
    setNotice(
      "Reply and status saved and verified. Reviewed does not mean the issue is resolved.",
    );
    setRefresh((n) => n + 1);
  }
  async function saveReply(checkOnly = false) {
    if (mutationBusy || !item || !reply || (!checkOnly && pendingReply)) return;
    if (length(reply.reply) > 6000) {
      setReplyError("Reply must be at most 6,000 characters.");
      return;
    }
    setReplyBusy(true);
    setReplyError("");
    setNotice("");
    let target = pendingReply;
    try {
      if (!checkOnly) {
        const payload = { ...reply };
        try {
          const accepted = await api.feedbackUpdate(item.id, payload);
          target = {
            id: item.id,
            payload,
            revision: accepted.revision,
            accepted: true,
          };
          if (!alive.current) return;
          setPendingReply(target);
          if (
            !feedbackReplyMatches(
              accepted,
              item.id,
              payload,
              payload.expected_revision + 1,
            )
          )
            throw new Error(
              "The reply response did not match the requested update.",
            );
        } catch (e) {
          if (e instanceof ApiError && e.status >= 400 && e.status < 500) {
            if (e.status === 409 && alive.current) setConflict(true);
            throw e;
          }
          if (!target) {
            target = {
              id: item.id,
              payload,
              revision: payload.expected_revision + 1,
              accepted: false,
            };
            if (alive.current) setPendingReply(target);
          }
          throw e;
        }
      }
      if (target) await verifyReply(target);
    } catch (e) {
      if (alive.current)
        setReplyError(
          `${target ? (target.accepted ? "The update was accepted, but verification is incomplete. " : "The update result is unknown. Check the saved reply before retrying. ") : ""}${errorMessage(e)}`,
        );
    } finally {
      if (alive.current) setReplyBusy(false);
    }
  }
  async function loadLatestReply() {
    if (mutationBusy || !item || !reply) return;
    setReplyBusy(true);
    setReplyError("");
    const id = item.id,
      retained = { ...reply };
    try {
      const latest = await api.feedbackGet(id, true);
      if (!alive.current) return;
      if (latest.id !== id)
        throw new Error("The latest feedback ID did not match.");
      setItem(latest);
      setPendingReply(null);
      setConflict(false);
      setReplies((previous) => ({
        ...previous,
        [id]: { ...retained, expected_revision: latest.revision },
      }));
      setNotice(
        "Latest revision loaded. Your draft reply is retained; compare it with the saved reply below before saving again.",
      );
    } catch (e) {
      if (alive.current) setReplyError(errorMessage(e));
    } finally {
      if (alive.current) setReplyBusy(false);
    }
  }
  return (
    <div className="page feedback-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow">AIcademiya · Settings</div>
          <h1>Feedback</h1>
          <p>
            Share a bug, an idea or general feedback with the administrator.
          </p>
        </div>
      </div>
      <nav className="feedback-tabs" aria-label="Feedback lists">
        <button
          className={scope === "mine" ? "primary" : "secondary"}
          aria-pressed={scope === "mine"}
          disabled={mutationBusy || !!pendingReply || listBusy}
          onClick={() => changeScope("mine")}
        >
          My feedback
        </button>
        {user.role === "admin" && (
          <button
            className={admin ? "primary" : "secondary"}
            aria-pressed={admin}
            disabled={mutationBusy || !!pendingReply || listBusy}
            onClick={() => changeScope("inbox")}
          >
            Administrator inbox
          </button>
        )}
      </nav>
      {notice && (
        <div role="status">
          <Notice>{notice}</Notice>
        </div>
      )}
      {!admin && (
        <section
          className="card form-card feedback-compose"
          aria-labelledby="feedback-send-title"
        >
          <h2 id="feedback-send-title">Send feedback</h2>
          <p>
            Only the text you enter is sent. No attachments, email notifications
            or automatic activity transcripts.
          </p>
          <ErrorBanner error={storageError} />
          <ErrorBanner error={submitError} />
          {draft.attempt && (
            <p className="feedback-pending" role="status">
              This submission is awaiting verification. Its text and request ID
              are kept for a safe retry.
            </p>
          )}
          <form onSubmit={(e) => void submit(e)}>
            <label>
              Category
              <select
                aria-label="Category"
                disabled={submitBusy || !!draft.attempt}
                value={draft.category}
                onChange={(e) =>
                  keepDraft({
                    ...draft,
                    category: e.target.value as FeedbackCategory,
                  })
                }
              >
                {categories.map((value) => (
                  <option key={value} value={value}>
                    {titleCase(value)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Subject
              <input
                required
                aria-invalid={length(draft.subject) > 160}
                aria-describedby="feedback-draft-bounds"
                disabled={submitBusy || !!draft.attempt}
                value={draft.subject}
                onChange={(e) =>
                  keepDraft({ ...draft, subject: e.target.value })
                }
              />
            </label>
            <label>
              Message
              <textarea
                aria-label="Message"
                required
                aria-invalid={length(draft.message) > 6000}
                aria-describedby="feedback-draft-bounds"
                rows={5}
                disabled={submitBusy || !!draft.attempt}
                value={draft.message}
                onChange={(e) =>
                  keepDraft({ ...draft, message: e.target.value })
                }
              />
            </label>
            <small id="feedback-draft-bounds">
              {length(draft.subject)} / 160 subject characters ·{" "}
              {length(draft.message)} / 6,000 message characters. Drafts are
              saved on this browser for this account.
            </small>
            {(length(draft.subject) > 160 || length(draft.message) > 6000) && (
              <p role="alert">
                Your text is kept in full. Shorten the subject to 160 characters
                and the message to 6,000 before sending.
              </p>
            )}
            <div className="feedback-actions">
              <button
                className="primary"
                disabled={
                  mutationBusy ||
                  !!pendingReply ||
                  !!feedbackValidation(draft.subject, draft.message)
                }
              >
                {submitBusy
                  ? "Checking submission…"
                  : draft.attempt
                    ? "Check saved submission / retry"
                    : "Send feedback"}
              </button>
              {!draft.attempt && (
                <button
                  className="secondary"
                  type="button"
                  disabled={submitBusy || (!draft.subject && !draft.message)}
                  onClick={() => {
                    if (
                      window.confirm(
                        "Discard this account's unsent feedback draft?",
                      )
                    ) {
                      keepDraft(emptyDraft());
                      setSubmitError("");
                    }
                  }}
                >
                  Discard draft
                </button>
              )}
            </div>
          </form>
        </section>
      )}
      <section
        className="card feedback-history"
        aria-labelledby="feedback-history-title"
      >
        <div className="feedback-section-heading">
          <div>
            <h2 id="feedback-history-title">
              {admin ? "Administrator inbox" : "My feedback history"}
            </h2>
            <p>
              {admin
                ? "All accounts. Author details come from the saved account, not the submission."
                : "Only feedback submitted by your account appears here."}
            </p>
          </div>
          <button
            className="secondary"
            disabled={listBusy || mutationBusy || !!pendingReply}
            onClick={() => setRefresh((n) => n + 1)}
          >
            Refresh list
          </button>
        </div>
        <div className="feedback-filters">
          <label>
            Filter category
            <select
              aria-label="Filter category"
              value={category}
              disabled={listBusy || mutationBusy || !!pendingReply}
              onChange={(e) => {
                setCategory(e.target.value as typeof category);
                setOffset(0);
              }}
            >
              <option value="">All categories</option>
              {categories.map((value) => (
                <option key={value} value={value}>
                  {titleCase(value)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Filter status
            <select
              aria-label="Filter status"
              value={status}
              disabled={listBusy || mutationBusy || !!pendingReply}
              onChange={(e) => {
                setStatus(e.target.value as typeof status);
                setOffset(0);
              }}
            >
              <option value="">All statuses</option>
              {statuses.map((value) => (
                <option key={value} value={value}>
                  {titleCase(value)}
                </option>
              ))}
            </select>
          </label>
        </div>
        <ErrorBanner error={listError} retry={() => setRefresh((n) => n + 1)} />
        {listBusy && <p role="status">Loading feedback…</p>}
        {page && (
          <>
            <p className="feedback-count" role="status">
              {page.total
                ? `${page.offset + 1}–${page.offset + page.items.length} of ${page.total}`
                : "0 feedback items"}
            </p>
            {!page.items.length && <p>No feedback matches this list.</p>}
            <ul className="feedback-list">
              {page.items.map((row) => (
                <li key={row.id}>
                  <button
                    className="feedback-list-item"
                    data-feedback-id={row.id}
                    aria-current={selected === row.id ? "true" : undefined}
                    disabled={mutationBusy || !!pendingReply}
                    onClick={() => void openDetail(row.id)}
                  >
                    <span className="feedback-list-title">{row.subject}</span>
                    <span className="feedback-list-meta">
                      <Badge status={row.status} />
                      <span>{titleCase(row.category)}</span>
                      <Time value={row.created_at} />
                      {admin && (
                        <span>
                          {row.author
                            ? `${row.author.name} · ${row.author.role}`
                            : "Deleted account"}
                        </span>
                      )}
                      {!!row.reply && <span>Has a reply</span>}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
            <nav
              className="feedback-pagination"
              aria-label="Feedback pagination"
            >
              <button
                className="secondary"
                disabled={
                  listBusy || mutationBusy || !!pendingReply || !page.offset
                }
                onClick={() => setOffset(Math.max(0, page.offset - page.limit))}
              >
                Previous page
              </button>
              <span>
                Page {Math.floor(page.offset / page.limit) + 1} of{" "}
                {Math.max(1, Math.ceil(page.total / page.limit))}
              </span>
              <button
                className="secondary"
                disabled={
                  listBusy ||
                  mutationBusy ||
                  !!pendingReply ||
                  page.offset + page.items.length >= page.total
                }
                onClick={() => setOffset(page.offset + page.limit)}
              >
                Next page
              </button>
            </nav>
          </>
        )}
      </section>
      {selected && (
        <section
          className="card form-card feedback-detail"
          aria-labelledby="feedback-detail-title"
        >
          <h2 id="feedback-detail-title" ref={detailHeading} tabIndex={-1}>
            Feedback detail
          </h2>
          {detailBusy && <p role="status">Loading selected feedback…</p>}
          <ErrorBanner
            error={detailError}
            retry={() => void openDetail(selected, true)}
          />
          {item && (
            <>
              <h3 className="feedback-subject">{item.subject}</h3>
              <div className="feedback-list-meta">
                <Badge status={item.status} />
                <span>{titleCase(item.category)}</span>
                <span>
                  Created <Time value={item.created_at} />
                </span>
                <span>
                  Updated <Time value={item.updated_at} />
                </span>
              </div>
              {admin && (
                <p className="feedback-author">
                  {item.author
                    ? `${item.author.name} · ${item.author.email} · ${item.author.role}`
                    : "Deleted account — author details are no longer available."}
                </p>
              )}
              <h4>Message</h4>
              <p className="feedback-literal">{item.message}</p>
              <h4>Administrator reply</h4>
              <p className="feedback-literal">
                {item.reply || "No reply yet."}
              </p>
              <p className="feedback-status-help">
                New means awaiting review. Reviewed means an administrator has
                reviewed it, not that the issue is resolved.
              </p>
              {admin && reply && (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    void saveReply();
                  }}
                >
                  <h3>Reply and review</h3>
                  <ErrorBanner error={replyError} />
                  {conflict && (
                    <p role="alert">
                      Another administrator changed this item. Your draft has
                      not been overwritten. Load the latest revision before
                      saving again.
                    </p>
                  )}
                  <label>
                    Review status
                    <select
                      aria-label="Review status"
                      value={reply.status}
                      disabled={replyBusy || !!pendingReply}
                      onChange={(e) =>
                        editReply({ status: e.target.value as FeedbackStatus })
                      }
                    >
                      {statuses.map((value) => (
                        <option key={value} value={value}>
                          {titleCase(value)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Your reply
                    <textarea
                      aria-label="Your reply"
                      aria-invalid={length(reply.reply) > 6000}
                      aria-describedby="feedback-reply-bounds"
                      rows={5}
                      value={reply.reply}
                      disabled={replyBusy || !!pendingReply}
                      onChange={(e) => editReply({ reply: e.target.value })}
                    />
                  </label>
                  <small id="feedback-reply-bounds">
                    {length(reply.reply)} / 6,000 characters · Editing revision{" "}
                    {reply.expected_revision}. Plain human reply only; no email
                    is sent.
                  </small>
                  {length(reply.reply) > 6000 && (
                    <p role="alert">
                      Your reply is kept in full. Shorten it to 6,000 characters
                      before saving.
                    </p>
                  )}
                  <div className="feedback-actions">
                    <button
                      className="primary"
                      disabled={
                        mutationBusy ||
                        !!pendingReply ||
                        conflict ||
                        !replyDirty ||
                        length(reply.reply) > 6000
                      }
                    >
                      Save reply and status
                    </button>
                    {pendingReply && (
                      <button
                        className="secondary"
                        type="button"
                        disabled={mutationBusy}
                        onClick={() => void saveReply(true)}
                      >
                        Check saved reply
                      </button>
                    )}
                    {(conflict || pendingReply) && (
                      <button
                        className="secondary"
                        type="button"
                        disabled={mutationBusy}
                        onClick={() => void loadLatestReply()}
                      >
                        Load latest revision, keep draft
                      </button>
                    )}
                    {!pendingReply && (
                      <button
                        className="secondary"
                        type="button"
                        disabled={mutationBusy || !replies[item.id]}
                        onClick={() => {
                          if (
                            window.confirm(
                              "Discard the unsaved reply for this item?",
                            )
                          ) {
                            setReplies((previous) => {
                              const copy = { ...previous };
                              delete copy[item.id];
                              return copy;
                            });
                            setConflict(false);
                            setReplyError("");
                          }
                        }}
                      >
                        Discard reply edits
                      </button>
                    )}
                  </div>
                </form>
              )}
            </>
          )}
        </section>
      )}
    </div>
  );
}
