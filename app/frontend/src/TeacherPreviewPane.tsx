import { useCallback, useEffect, useRef, useState } from "react";
import { Play, RotateCcw, Send, X } from "lucide-react";
import { api } from "./api";
import type { PreviewInfo, SessionDetail, TutorTurn, Workspace } from "./types";
import { clientId } from "./ids";
import { teachingPreviewKey } from "./teaching-profile";
import { draftKey, readDraft, writeDraft } from "./drafts";
import {
  acknowledgePending,
  composerEnterAction,
  conversationScope,
  pendingKey,
  phaseLabels,
  readPending,
  sameTurn,
  storePending,
  type PendingTutorTurn,
} from "./guided-study";
import { QuestionPrompt, TutorMessage } from "./TutorMessage";
import { AiBadge, ErrorBanner, errorMessage, connectionLabel } from "./ui";
import "./teacher-workbench.css";
import HelpPopover from "./HelpPopover";

export default function TeacherPreviewPane({
  saved,
  unsaved,
  viewerId,
  onBusyChange,
  onClose,
  onFullPreview,
}: {
  saved: SessionDetail;
  unsaved: boolean;
  viewerId?: string;
  onBusyChange: (busy: boolean) => void;
  onClose: () => void;
  onFullPreview: () => void;
}) {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [info, setInfo] = useState<PreviewInfo | null>(null);
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState<PendingTutorTurn | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  const [loading, setLoading] = useState(true);
  const [storageWarning, setStorageWarning] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const [optionsOpen, setOptionsOpen] = useState(false);
  const [technicalOpen, setTechnicalOpen] = useState(false);
  const generation = useRef(0),
    inFlight = useRef(false),
    composing = useRef(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const savedKey = JSON.stringify([
    teachingPreviewKey(saved),
    saved.title,
    saved.subtitle,
    saved.status,
    saved.groups,
    saved.questions,
    saved.reference_answers,
    saved.materials,
  ]);
  const state = useRef({ workspace, info, message, pending });
  state.current = { workspace, info, message, pending };
  const composer = useRef<HTMLTextAreaElement>(null),
    stream = useRef<HTMLDivElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const startIdentity = useRef({ key: "", id: "" });
  const viewer = viewerId || workspace?.user.id || "";
  const working =
    !!busy || !!info?.pending || !!workspace?.tutor?.pending_request_id;
  const stale = !!info?.stale || !!info?.reset_required;
  const owned =
    !!workspace &&
    workspace.user.id === viewer &&
    workspace.user.role !== "student" &&
    !!workspace.version?.is_draft;
  const locked =
    !ready ||
    loading ||
    stale ||
    working ||
    !owned ||
    !info?.id ||
    workspace?.tutor?.phase === "not_started" ||
    !!workspace?.read_only;

  function adopt(next: Workspace, preview: PreviewInfo) {
    const uid = viewerId || next.user.id;
    const nextScope = conversationScope({ ...next, preview }, uid);
    const previous = state.current;
    const oldScope = previous.workspace
      ? conversationScope(previous.workspace, uid)
      : null;
    const ack = acknowledgePending(
      nextScope,
      next.tutor?.last_completed_request_id,
      localStorage,
      previous.pending,
    );
    const sameScope = oldScope && draftKey(oldScope) === draftKey(nextScope);
    setMessage(
      readDraft(nextScope) ??
        (sameScope &&
        (!ack?.clear_draft || previous.message !== ack.turn.message)
          ? previous.message
          : ""),
    );
    setPending(
      readPending(nextScope) ||
        (previous.pending &&
        pendingKey(previous.pending.scope) === pendingKey(nextScope) &&
        !ack
          ? previous.pending
          : null),
    );
    setWorkspace({ ...next, preview });
    setInfo(preview);
  }
  const fetchState = useCallback(async () => {
    const [w, p] = await Promise.all([
      api.workspace(saved.id),
      api.previewInfo(saved.id),
    ]);
    if (
      w.preview &&
      (w.preview.id !== p.id ||
        w.preview.revision !== p.revision ||
        w.preview.current_revision !== p.current_revision)
    )
      throw new Error(
        "Preview changed while loading. Refresh the saved preview; your raw input is kept.",
      );
    return { w, p };
  }, [saved.id]);
  const load = useCallback(async () => {
    const token = ++generation.current;
    setLoading(true);
    setError("");
    try {
      const { w, p } = await fetchState();
      if (token !== generation.current) return;
      adopt(w, p);
    } catch (e) {
      if (token === generation.current) {
        setError(errorMessage(e));
        setReady(false);
        setInfo(null);
      }
    } finally {
      if (token === generation.current) setLoading(false);
    }
  }, [fetchState, savedKey, viewerId]);
  useEffect(() => {
    void load();
    return () => {
      generation.current++;
    };
  }, [load]);
  useEffect(() => {
    onBusyChange(working || loading);
    return () => onBusyChange(false);
  }, [working, loading, onBusyChange]);
  useEffect(() => {
    if (!working || busy) return;
    const token = generation.current;
    const timer = setInterval(() => {
      void fetchState()
        .then(({ w, p }) => {
          if (token === generation.current) adopt(w, p);
        })
        .catch((e) => {
          if (token === generation.current) setError(errorMessage(e));
        });
    }, 2500);
    return () => clearInterval(timer);
  }, [working, busy, fetchState]);
  useEffect(() => {
    if (resetOpen) dialog.current?.showModal();
  }, [resetOpen]);
  useEffect(() => {
    if (stream.current) stream.current.scrollTop = stream.current.scrollHeight;
  }, [workspace?.messages.length, busy]);

  async function run(name: string, operation: () => Promise<unknown>) {
    if (inFlight.current || working) return;
    const token = generation.current;
    inFlight.current = true;
    setBusy(name);
    setError("");
    try {
      await operation();
      const { w, p } = await fetchState();
      if (token === generation.current) adopt(w, p);
    } catch (e) {
      if (token === generation.current) {
        setError(errorMessage(e));
        try {
          const { w, p } = await fetchState();
          if (token === generation.current) adopt(w, p);
        } catch {
          /* Retain raw input and retry ID. */
        }
      }
    } finally {
      inFlight.current = false;
      if (mounted.current) setBusy("");
    }
  }
  async function start() {
    if (!workspace || !info || stale || !owned) return;
    if (!info.id && priorWork) {
      setResetOpen(true);
      return;
    }
    setReady(true);
    if (workspace.tutor?.phase && workspace.tutor.phase !== "not_started")
      return;
    await run("start", async () => {
      let w = workspace;
      if (!info.id) w = await api.resetPreview(saved.id, info.current_revision);
      const scope = conversationScope(w, viewer);
      const key = `${pendingKey(scope)}:start`;
      let requestId =
        startIdentity.current.key === key ? startIdentity.current.id : "";
      try {
        requestId = localStorage.getItem(key) || requestId;
      } catch {
        setStorageWarning(true);
      }
      if (!requestId) requestId = clientId();
      startIdentity.current = { key, id: requestId };
      try {
        localStorage.setItem(key, requestId);
      } catch {
        setStorageWarning(true);
      }
      await api.tutorStart(
        saved.id,
        requestId,
        undefined,
        w.preview?.id || undefined,
      );
      startIdentity.current = { key: "", id: "" };
      try {
        localStorage.removeItem(key);
      } catch {
        /* Harmless completed identity. */
      }
    });
  }
  async function reset() {
    if (!info || working) return;
    setResetOpen(false);
    setReady(false);
    await run("reset", () => api.resetPreview(saved.id, info.current_revision));
  }
  function edit(value: string) {
    setMessage(value);
    if (workspace && !writeDraft(conversationScope(workspace, viewer), value))
      setStorageWarning(true);
  }
  async function transmit(value: PendingTutorTurn) {
    if (
      !workspace ||
      locked ||
      inFlight.current ||
      value.turn.preview_id !== info?.id ||
      pendingKey(value.scope) !==
        pendingKey(conversationScope(workspace, viewer))
    )
      return;
    setPending(value);
    if (!storePending(value)) setStorageWarning(true);
    await run("turn", () => api.tutorTurn(saved.id, value.turn));
  }
  async function send(text = message, action: TutorTurn["action"] = "message") {
    if (!workspace || locked || composing.current || !text.trim()) return;
    const candidate: Omit<TutorTurn, "request_id"> = {
      message: text,
      action,
      web_search: false,
      preview_id: info?.id || undefined,
    };
    await transmit({
      scope: conversationScope(workspace, viewer),
      clear_draft: text === message,
      turn: {
        ...candidate,
        request_id:
          pending && sameTurn(pending.turn, candidate)
            ? pending.turn.request_id
            : clientId(),
      },
    });
  }
  const current = workspace?.session.questions.find(
    (q) => q.id === workspace.tutor?.current_question_id,
  );
  const lastAssistant = workspace
    ? [...workspace.messages].reverse().find((m) => m.role === "assistant")
    : undefined;
  const priorWork =
    !!workspace &&
    (!!workspace.messages.length ||
      !!Object.keys(workspace.attempts).length ||
      !!message ||
      !!pending ||
      (workspace.tutor?.phase !== undefined &&
        workspace.tutor.phase !== "not_started"));
  return (
    <aside
      className="tw-preview"
      aria-label="Tutor preview"
      aria-busy={working}
    >
      <header className="tw-pane-heading">
        <div>
          <span className="tw-kicker">Private</span>
          <h2>Tutor preview</h2>
        </div>
        <button
          className="icon-button"
          aria-label="Close tutor preview"
          disabled={working}
          onClick={onClose}
        >
          <X size={18} />
        </button>
      </header>
      <p className="tw-muted">Using saved draft</p>
      {workspace &&
        ["not_configured", "error"].includes(
          connectionLabel(workspace.ai).status,
        ) && (
          <p className="tw-warning" role="status">
            AI Model: {connectionLabel(workspace.ai).text}. An administrator can
            check it in Settings.
          </p>
        )}
      {unsaved && (
        <p className="tw-warning" role="status">
          Unsaved changes are not used here. Save, then reset to test them.
        </p>
      )}
      {stale && (
        <p className="tw-warning" role="alert">
          Preview outdated · this conversation uses an older saved draft. Reset
          to continue; the old conversation stays readable until then.
        </p>
      )}
      {storageWarning && (
        <p role="status">
          Local storage is unavailable. Keep a copy of your unsent text.
        </p>
      )}
      <ErrorBanner
        error={error}
        retry={loading ? undefined : () => void load()}
      />
      {loading ? (
        <p role="status">Loading your saved preview…</p>
      ) : (
        <>
          <div className="tw-preview-actions">
            <button
              className="primary"
              disabled={working || !owned || !info}
              onClick={() => (stale ? setResetOpen(true) : void start())}
            >
              <Play size={15} />
              {stale
                ? "Reset outdated preview"
                : workspace?.tutor?.phase &&
                    workspace.tutor.phase !== "not_started"
                  ? "Resume preview"
                  : "Start preview"}
            </button>
            <HelpPopover label="Help with tutor preview">
              Start requests a tutor response from your saved draft. Resume
              opens your existing preview without a new request. Student records
              are separate.
            </HelpPopover>
          </div>
          {workspace && (
            <>
              <div
                className="tw-phase"
                hidden={workspace.tutor?.phase === "not_started"}
              >
                {phaseLabels[workspace.tutor?.phase || "not_started"]}
              </div>
              <div
                className="tw-chat-stream"
                ref={stream}
                tabIndex={0}
                aria-label="Preview messages"
              >
                {!workspace.messages.length && (
                  <div className="tw-preview-empty">
                    <h3>Test your teaching design</h3>
                    <p>Try your teaching setup before publishing.</p>
                  </div>
                )}
                {workspace.messages.map((item) => (
                  <TutorMessage
                    key={item.id}
                    message={item}
                    workspace={workspace}
                    latest={lastAssistant?.id === item.id}
                    paced={workspace.tutor?.presentation === "paced" && !locked}
                    onQuestion={(id) =>
                      stream.current
                        ?.querySelector<HTMLElement>(
                          `[data-question-id="${CSS.escape(id)}"]`,
                        )
                        ?.scrollIntoView({ block: "nearest" })
                    }
                    onOption={
                      !locked
                        ? (text) => {
                            edit(text);
                            composer.current?.focus();
                          }
                        : undefined
                    }
                  />
                ))}
                {current &&
                  workspace.tutor?.phase === "worksheet" &&
                  lastAssistant?.presented_question_id !== current.id && (
                    <QuestionPrompt
                      question={current}
                      workspace={workspace}
                      disabled={locked}
                      onOption={(text) => {
                        edit(text);
                        composer.current?.focus();
                      }}
                    />
                  )}
                {working && (
                  <p role="status">
                    {busy === "reset"
                      ? "Resetting your preview…"
                      : "Waiting for the guided response…"}
                  </p>
                )}
              </div>
              <form
                className="tw-composer"
                hidden={!ready && !priorWork}
                onSubmit={(e) => {
                  e.preventDefault();
                  void send();
                }}
              >
                {pending && !working && (
                  <div className="tw-warning">
                    <span>
                      Message not confirmed. Your text is kept for retry.
                    </span>
                    <button
                      type="button"
                      className="text-button"
                      disabled={locked}
                      onClick={() => void transmit(pending)}
                    >
                      Retry previous message
                    </button>
                  </div>
                )}
                <label>
                  Test response
                  <textarea
                    ref={composer}
                    aria-label="Test response"
                    rows={3}
                    value={message}
                    disabled={locked}
                    onChange={(e) => edit(e.target.value)}
                    onCompositionStart={() => {
                      composing.current = true;
                    }}
                    onCompositionEnd={() => {
                      composing.current = false;
                    }}
                    onKeyDown={(e) => {
                      const action = composerEnterAction(
                        e.nativeEvent,
                        composing.current,
                      );
                      if (action === "native") return;
                      e.preventDefault();
                      if (action === "send") void send();
                    }}
                  />
                </label>
                <div className="tw-composer-row">
                  <small>
                    Enter to send · Shift + Enter for a new line
                    <br />
                    {message
                      ? "Unsent text saved for this preview"
                      : "Use Start / Resume to begin"}
                  </small>
                  <button
                    type="submit"
                    className="primary"
                    disabled={locked || !message.trim()}
                  >
                    <Send size={15} />
                    Send
                  </button>
                </div>
                {workspace.tutor?.phase === "quiz_offer" && (
                  <button
                    type="button"
                    className="text-button"
                    disabled={locked}
                    onClick={() =>
                      void send(
                        "No, let us skip the optional quiz.",
                        "skip_quiz",
                      )
                    }
                  >
                    Skip optional quiz
                  </button>
                )}
              </form>
            </>
          )}
          <details
            className="tw-preview-options"
            open={optionsOpen}
            onToggle={(e) => setOptionsOpen(e.currentTarget.open)}
          >
            <summary>Preview options</summary>
            <button
              className="secondary"
              disabled={working || !info || !owned}
              onClick={() => (priorWork ? setResetOpen(true) : void reset())}
            >
              <RotateCcw size={15} />
              Reset my preview
            </button>
            <a href={api.exportUrl(saved.id)} download>
              Download preview record
            </a>
            <details
              open={technicalOpen}
              onToggle={(e) => setTechnicalOpen(e.currentTarget.open)}
            >
              <summary>Technical details</summary>
              {info && (
                <div className="tw-identity">
                  <span>
                    Preview: <code>{info.id || "Not started"}</code>
                  </span>
                  <span>
                    Tested revision:{" "}
                    <code>{info.revision || "Not bound yet"}</code>
                  </span>
                  <span>
                    Current saved revision: <code>{info.current_revision}</code>
                  </span>
                </div>
              )}
              {workspace && <AiBadge ai={workspace.ai} />}
            </details>
          </details>
          <div className="tw-preview-links">
            <a href="#teacher-draft-editor">Back to teaching setup</a>
            <button
              className="text-button"
              disabled={working}
              onClick={onFullPreview}
            >
              Open full preview
            </button>
          </div>
        </>
      )}
      {resetOpen && (
        <dialog
          ref={dialog}
          className="tw-dialog"
          aria-labelledby="tw-reset-title"
          onCancel={() => setResetOpen(false)}
        >
          <h2 id="tw-reset-title">Reset your preview?</h2>
          <p>
            Your current preview conversation and saved test responses will be
            cleared. Unsent text from the old preview will not be sent in the
            new one. Student, published and other teachers' records stay
            unchanged.
          </p>
          <p>
            Download the current record before resetting if you need a copy.
          </p>
          <div className="button-row">
            <a href={api.exportUrl(saved.id)} download>
              Download current test record
            </a>
            <button className="secondary" onClick={() => setResetOpen(false)}>
              Keep current preview
            </button>
            <button
              className="primary"
              disabled={working}
              onClick={() => void reset()}
            >
              Confirm reset my preview
            </button>
          </div>
        </dialog>
      )}
    </aside>
  );
}
