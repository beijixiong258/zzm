import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import {
  ArrowLeft,
  ArrowDown,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  Download,
  FileText,
  Lightbulb,
  LoaderCircle,
  Send,
  ShieldCheck,
  Sparkles,
  X,
  RotateCcw,
  History as HistoryIcon,
} from "lucide-react";
import { api } from "./api";
import { useUnsavedChanges } from "./navigation-guard";
import { clientId } from "./ids";
import type { Workspace, Question, Reference, TutorTurn } from "./types";
import {
  readDraft,
  writeDraft,
  clearDraft,
  draftKey,
  type DraftScope,
} from "./drafts";
import { effectiveAvailability } from "./stage2";
import { AvailabilityBadge } from "./Availability";
import { activeQuestions, canSubmit, dateLabel, isLocked } from "./study";
import {
  Loading,
  ErrorBanner,
  Status,
  AiBadge,
  Notice,
  errorMessage,
} from "./ui";
import Materials from "./Materials";
import SearchToggle, { webSearchAvailable } from "./SearchToggle";
import { QuestionPrompt, TutorMessage } from "./TutorMessage";
import SavedResponses from "./SavedResponses";
import TeacherProcessOverview from "./TeacherProcessOverview";
import {
  phaseLabels,
  recordedSpan,
  conversationScope,
  readPending,
  storePending,
  acknowledgePending,
  pendingKey,
  sameTurn,
  composerEnterAction,
  type PendingTutorTurn,
} from "./guided-study";
import "./guided-workspace.css";

type Panel = "materials" | "responses" | "review" | "process" | null;
export default function GuidedLearningWorkspace({
  sid,
  studentId,
  preview = false,
  onBack,
  onChanged,
  versionId,
  viewerId,
  onVersion,
}: {
  sid: string;
  versionId?: string;
  viewerId: string;
  onVersion: (version?: string) => void;
  studentId?: string;
  preview?: boolean;
  onBack: () => void;
  onChanged: () => void;
}) {
  const pinnedVersion = useRef<string | null | undefined>(versionId);
  const alive = useRef(true),
    inFlight = useRef(false),
    startAttempted = useRef(false);
  const startRequest = useRef("");
  const stream = useRef<HTMLDivElement>(null),
    composer = useRef<HTMLTextAreaElement>(null);
  const composing = useRef(false);
  const submitModal = useRef<HTMLDialogElement>(null);
  const resetModal = useRef<HTMLDialogElement>(null),
    previousPreview = useRef<string | null | undefined>(undefined);
  const followBottom = useRef(true),
    oldDraft = useRef<DraftScope | null>(null);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [loading, setLoading] = useState(true),
    [busy, setBusy] = useState("");
  const [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [resetDialog, setResetDialog] = useState(false),
    [highlightedMessage, setHighlightedMessage] = useState<string | null>(null);
  const [panel, setPanel] = useState<Panel>(studentId ? "process" : null),
    [selected, setSelected] = useState("");
  const [message, setMessage] = useState(""),
    [useWebSearch, setUseWebSearch] = useState(false);
  const [references, setReferences] = useState<Record<string, Reference>>({});
  const [pending, setPending] = useState<PendingTutorTurn | null>(null);
  const [storageWarning, setStorageWarning] = useState(false),
    [submitDialog, setSubmitDialog] = useState(false);
  const [teacherNote, setTeacherNote] = useState("");
  const [clock, setClock] = useState(Date.now()),
    [lastInteraction, setLastInteraction] = useState(Date.now());
  const [showLatest, setShowLatest] = useState(false);
  useUnsavedChanges(
    !!studentId &&
      !!workspace &&
      teacherNote !== workspace.submission.teacher_note,
  );
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  useEffect(() => {
    const timer = setInterval(() => setClock(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const fetchWorkspace = useCallback(
    () =>
      studentId
        ? api.studentWorkspace(sid, studentId, pinnedVersion.current)
        : api.workspace(sid, pinnedVersion.current),
    [sid, studentId],
  );
  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const w = await fetchWorkspace();
      if (!alive.current) return;
      pinnedVersion.current = w.version?.id ?? versionId;
      setWorkspace(w);
      setSelected(
        w.tutor?.current_question_id ||
          w.progress.current_question_id ||
          w.progress.active_question_ids[0] ||
          "",
      );
      setTeacherNote(w.submission.teacher_note);
      if (!studentId) setPending(readPending(conversationScope(w, viewerId)));
    } catch (e) {
      if (alive.current) setError(errorMessage(e));
    } finally {
      if (alive.current) setLoading(false);
    }
  }, [fetchWorkspace, studentId, viewerId, versionId]);
  useEffect(() => {
    void load();
  }, [load]);
  const scope = workspace ? conversationScope(workspace, viewerId) : null;
  const scopeId = scope ? draftKey(scope) : "";
  useEffect(() => {
    if (scope && !studentId) {
      setMessage(readDraft(scope) ?? "");
      setLastInteraction(Date.now());
    }
  }, [scopeId, studentId]);
  useEffect(() => {
    if (!workspace || !scope || studentId) return;
    const acknowledged = acknowledgePending(
      scope,
      workspace.tutor?.last_completed_request_id,
      localStorage,
      pending,
    );
    setPending(
      acknowledged
        ? null
        : readPending(scope) ||
            (pending && pendingKey(pending.scope) === pendingKey(scope)
              ? pending
              : null),
    );
    if (!acknowledged) return;
    if (acknowledged.clear_draft) {
      if (
        oldDraft.current &&
        readDraft(oldDraft.current) === acknowledged.turn.message
      ) {
        clearDraft(oldDraft.current);
        oldDraft.current = null;
      }
      setMessage(
        (current) =>
          readDraft(scope) ??
          (draftKey(scope) !== draftKey(acknowledged.scope) ||
          current === acknowledged.turn.message
            ? ""
            : current),
      );
    }
  }, [workspace, scopeId, studentId]);
  useEffect(() => {
    if (!workspace?.user.id) return;
    try {
      setUseWebSearch(
        localStorage.getItem(
          `aicademiya-search:${workspace.user.id}:${sid}`,
        ) === "true",
      );
    } catch {
      setUseWebSearch(false);
    }
  }, [workspace?.user.id, sid]);
  const locked =
    !!workspace &&
    (!!studentId ||
      isLocked(workspace) ||
      (preview &&
        !!(workspace.preview?.stale || workspace.preview?.reset_required)) ||
      (!preview && !effectiveAvailability(workspace.session, clock).active));
  async function run(
    name: string,
    operation: () => Promise<unknown>,
  ): Promise<Workspace | null> {
    if (inFlight.current) return null;
    inFlight.current = true;
    setBusy(name);
    setError("");
    setNotice("");
    try {
      await operation();
      const next = await fetchWorkspace();
      if (alive.current) {
        setWorkspace(next);
        onChanged();
        setLastInteraction(Date.now());
      }
      return next;
    } catch (e) {
      if (alive.current) setError(errorMessage(e));
      if (name === "turn" || name === "start") {
        try {
          const next = await fetchWorkspace();
          if (alive.current) setWorkspace(next);
        } catch {
          /* Keep the original error and persisted retry. */
        }
      }
      return null;
    } finally {
      inFlight.current = false;
      if (alive.current) setBusy("");
    }
  }
  useEffect(() => {
    const id = workspace?.preview?.id;
    if (!preview || !id) return;
    if (
      previousPreview.current !== undefined &&
      previousPreview.current !== id
    ) {
      startAttempted.current = true;
      startRequest.current = "";
      oldDraft.current = null;
      setPending(null);
      setReferences({});
    }
    previousPreview.current = id;
  }, [preview, workspace?.preview?.id]);
  useEffect(() => {
    if (resetDialog && resetModal.current && !resetModal.current.open)
      resetModal.current.showModal();
  }, [resetDialog]);
  async function resetOwnPreview() {
    if (
      !workspace?.preview ||
      !preview ||
      studentId ||
      inFlight.current ||
      workspace.preview.pending
    )
      return;
    const expected = workspace.preview.current_revision;
    const next = await run("preview-reset", () =>
      api.resetPreview(sid, expected),
    );
    if (next) {
      startAttempted.current = true;
      startRequest.current = "";
      oldDraft.current = null;
      setPending(null);
      setReferences({});
      setResetDialog(false);
      setNotice(
        "Your draft test was reset. Student records and published editions are unchanged. Begin the session when ready.",
      );
    }
  }
  async function begin() {
    if (!workspace || locked || inFlight.current) return;
    startAttempted.current = true;
    if (!startRequest.current) startRequest.current = clientId();
    followBottom.current = true;
    await run("start", () =>
      api.tutorStart(
        sid,
        startRequest.current,
        pinnedVersion.current,
        workspace.preview?.id || undefined,
      ),
    );
  }
  useEffect(() => {
    if (
      workspace?.tutor?.phase === "not_started" &&
      !locked &&
      !startAttempted.current &&
      !workspace.tutor.pending_request_id
    )
      void begin();
  }, [workspace?.tutor?.phase, locked]);
  useEffect(() => {
    if (!workspace?.tutor?.pending_request_id || busy) return;
    let stopped = false;
    const timer = setInterval(() => {
      void fetchWorkspace()
        .then((next) => {
          if (!stopped && alive.current) setWorkspace(next);
        })
        .catch((e) => {
          if (!stopped) setError(errorMessage(e));
        });
    }, 2500);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [workspace?.tutor?.pending_request_id, busy, fetchWorkspace]);
  useEffect(() => {
    const element = stream.current;
    if (element) {
      if (followBottom.current)
        requestAnimationFrame(() => {
          element.scrollTop = element.scrollHeight;
        });
      else setShowLatest(true);
    }
  }, [workspace?.messages.length, busy, workspace?.tutor?.current_question_id]);
  useEffect(() => {
    if (!panel && !submitDialog) return;
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setPanel(null);
        if (!inFlight.current) setSubmitDialog(false);
      }
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [panel, submitDialog]);
  useEffect(() => {
    if (submitDialog && submitModal.current && !submitModal.current.open)
      submitModal.current.showModal();
  }, [submitDialog]);
  function editMessage(value: string) {
    setMessage(value);
    setLastInteraction(Date.now());
    if (scope && !writeDraft(scope, value)) setStorageWarning(true);
  }
  function changeSearch(value: boolean) {
    setUseWebSearch(value);
    if (workspace)
      try {
        localStorage.setItem(
          `aicademiya-search:${workspace.user.id}:${sid}`,
          String(value),
        );
      } catch {
        /* Current switch still works. */
      }
  }
  async function transmit(value: PendingTutorTurn) {
    if (locked || inFlight.current || workspace?.tutor?.pending_request_id)
      return;
    followBottom.current = true;
    setPending(value);
    if (!storePending(value)) setStorageWarning(true);
    await run("turn", () =>
      api.tutorTurn(sid, value.turn, pinnedVersion.current),
    );
  }
  async function send(
    event?: FormEvent,
    text?: string,
    action: TutorTurn["action"] = "message",
    questionId?: string,
  ) {
    event?.preventDefault();
    if (
      !workspace ||
      !scope ||
      locked ||
      inFlight.current ||
      workspace.tutor?.pending_request_id ||
      composing.current
    )
      return;
    const content = text ?? message;
    if (!content.trim()) return;
    const candidate: Omit<TutorTurn, "request_id"> = {
      message: content,
      action,
      web_search: useWebSearch && webSearchAvailable(workspace.ai),
      ...(workspace.preview?.id ? { preview_id: workspace.preview.id } : {}),
      ...(questionId ? { question_id: questionId } : {}),
    };
    await transmit({
      turn: {
        ...candidate,
        request_id:
          pending && sameTurn(pending.turn, candidate)
            ? pending.turn.request_id
            : clientId(),
      },
      scope,
      clear_draft: text === undefined,
    });
  }
  async function reveal(question: Question) {
    if (!workspace) return;
    let ref: Reference | undefined;
    const next = await run("reference", async () => {
      ref = workspace.attempts[question.id]?.reference_revealed
        ? await api.readReference(sid, question.id, pinnedVersion.current)
        : await api.reference(
            sid,
            question.id,
            pinnedVersion.current,
            workspace.preview?.id || undefined,
          );
    });
    if (next && ref)
      setReferences((prev) => ({ ...prev, [question.id]: ref! }));
  }
  async function submit() {
    if (
      await run("submit", () =>
        api.submit(
          sid,
          pinnedVersion.current,
          workspace?.preview?.id || undefined,
        ),
      )
    ) {
      setSubmitDialog(false);
      setNotice("Submitted for your teacher to review.");
    }
  }
  async function review(status: "confirmed" | "needs_revision") {
    if (
      studentId &&
      (await run("review", () =>
        api.review(sid, studentId, status, teacherNote, pinnedVersion.current),
      ))
    )
      setNotice(
        status === "confirmed"
          ? "Teacher confirmation saved."
          : "Revision request saved.",
      );
  }
  function openQuestion(id: string) {
    setSelected(id);
    setPanel("responses");
  }
  function togglePanel(next: Panel) {
    if (
      next === "responses" &&
      panel !== next &&
      workspace?.tutor?.current_question_id
    )
      setSelected(workspace.tutor.current_question_id);
    setPanel((old) => (old === next ? null : next));
  }
  function locateMessage(messageId: string) {
    if (!workspace?.messages.some((m) => m.id === messageId)) return;
    followBottom.current = false;
    setPanel(null);
    setHighlightedMessage(messageId);
    requestAnimationFrame(() => {
      const elements =
        stream.current?.querySelectorAll<HTMLElement>("[data-message-id]");
      const element = Array.from(elements || []).find(
        (e) => e.dataset.messageId === messageId,
      );
      if (element) {
        element.scrollIntoView({ block: "center", behavior: "smooth" });
        element.focus({ preventScroll: true });
      }
    });
  }
  function scrollLatest() {
    const element = stream.current;
    if (element) element.scrollTop = element.scrollHeight;
    followBottom.current = true;
    setShowLatest(false);
  }
  if (loading) return <Loading />;
  if (!workspace)
    return (
      <div className="page">
        <ErrorBanner error={error} retry={load} />
      </div>
    );
  const tutor = workspace.tutor,
    phase = tutor?.phase || "not_started";
  const questions = activeQuestions(workspace),
    currentQuestion = questions.find(
      (q) => q.id === tutor?.current_question_id,
    );
  const lastAssistant = [...workspace.messages]
    .reverse()
    .find((m) => m.role === "assistant");
  const questionAlreadyShown =
    !!currentQuestion &&
    lastAssistant?.presented_question_id === currentQuestion.id;
  const readingGroups = workspace.session.groups.filter(
    (g) => g.kind === "reading",
  );
  const working = !!busy || !!tutor?.pending_request_id;
  const showIdleHelp =
    !locked &&
    !working &&
    phase === "worksheet" &&
    (tutor?.idle_hint_seconds || 0) > 0 &&
    clock - lastInteraction >= (tutor?.idle_hint_seconds || 0) * 1000 &&
    !document.hidden;
  const reviewAllowed = ["submitted", "confirmed", "needs_revision"].includes(
    workspace.submission.status,
  );
  const blockedReason = studentId
    ? "Read-only student record"
    : preview && (workspace.preview?.stale || workspace.preview?.reset_required)
      ? "The saved draft changed. Restart your preview to continue; this conversation remains readable."
      : workspace.read_only_reason
        ? "This edition is read-only. Your saved record remains available."
        : !preview && !effectiveAvailability(workspace.session, clock).active
          ? "This session is currently closed. You can still read your record."
          : workspace.submission.status === "confirmed"
            ? "Your teacher has confirmed this work."
            : "Submitted for teacher review. Your conversation and responses are saved.";
  return (
    <div className="guided-workspace" data-ai-mode={workspace.ai.mode}>
      <header className="guided-heading">
        <div>
          <button className="text-button guided-back" onClick={onBack}>
            <ArrowLeft size={14} /> Back
          </button>
          <div className="guided-eyebrow">
            SESSION {workspace.session.number}
            {preview
              ? " · TEACHER PREVIEW"
              : studentId
                ? " · LEARNING RECORD"
                : " · YOUR LEARNING SPACE"}
          </div>
          <h1>{workspace.session.title}</h1>
          <p>{workspace.session.subtitle}</p>
        </div>
        <div className="guided-heading-status">
          <Status status={workspace.submission.status} />
          {!studentId && <AiBadge ai={workspace.ai} />}
        </div>
      </header>
      <div className="guided-edition-row">
        <AvailabilityBadge session={workspace.session} />
        <label>
          Content edition{" "}
          <select
            aria-label="Content edition"
            value={
              workspace.version?.is_draft
                ? "draft"
                : workspace.version?.id || ""
            }
            disabled={working}
            onChange={(event) =>
              onVersion(
                event.target.value === "draft"
                  ? undefined
                  : event.target.value || undefined,
              )
            }
          >
            {preview && !studentId && (
              <option value="draft">Teacher content draft</option>
            )}
            {(workspace.available_versions || []).map((version) => (
              <option value={version.id} key={version.id}>
                v{version.number} · {version.label}
                {workspace.version?.id === version.id &&
                workspace.version.is_current
                  ? " · Current"
                  : ""}
              </option>
            ))}
            {!workspace.available_versions?.length &&
              !workspace.version?.is_draft && (
                <option value={workspace.version?.id || ""}>
                  Current published edition
                </option>
              )}
          </select>
        </label>
        {tutor?.started_at && (
          <details className="guided-record-details">
            <summary>Record details</summary>
            <span
              className="guided-time"
              title="Time span between recorded session activity, not a measure of active study."
            >
              Recorded span · {recordedSpan(tutor.elapsed_seconds)}
              <small>
                Time between recorded activity, not active study time.
              </small>
            </span>
          </details>
        )}
        {workspace.version &&
          !workspace.version.is_current &&
          !workspace.version.is_draft && (
            <span className="small-tag">Historical · read-only</span>
          )}
      </div>
      {preview && (
        <p className="guided-context">
          <BookOpen size={14} /> Your own draft preview. Student learning
          records are separate.
        </p>
      )}
      {preview &&
        !studentId &&
        workspace.version?.is_draft &&
        workspace.preview && (
          <div
            className={`preview-run-banner ${workspace.preview.stale || workspace.preview.reset_required ? "stale" : ""}`}
          >
            <p>
              {workspace.preview.stale || workspace.preview.reset_required
                ? "This conversation is not a test of the latest saved draft. Reset your own preview before continuing."
                : workspace.preview.bound_at
                  ? `Saved draft preview started ${dateLabel(workspace.preview.bound_at)}`
                  : "Preview not started yet."}
            </p>
            <button
              className="secondary"
              disabled={working || workspace.preview.pending}
              onClick={() => setResetDialog(true)}
            >
              Reset my preview
            </button>
          </div>
        )}
      {studentId && (
        <p className="guided-context">
          <ShieldCheck size={14} />
          <strong>{workspace.user.name}</strong> · {workspace.user.email} ·
          read-only observation
        </p>
      )}
      {storageWarning && (
        <Notice>
          Local storage is unavailable. Keep a copy of unsent text before
          leaving this page.
        </Notice>
      )}
      <ErrorBanner
        error={error || workspace.ai.last_error || ""}
        onClose={() => setError("")}
      />
      {notice && <Notice>{notice}</Notice>}
      <section className={`guided-shell ${panel ? "has-drawer" : ""}`}>
        <nav className="guided-toolbar" aria-label="Learning tools">
          <div className="guided-phase">
            <Sparkles size={17} />
            <span>{phaseLabels[phase]}</span>
            {phase === "worksheet" && (
              <small>
                {tutor?.completed_question_ids.length || 0} /{" "}
                {workspace.progress.total} discussed
              </small>
            )}
          </div>
          <div className="guided-tool-buttons">
            {studentId && (
              <button
                className={panel === "process" ? "active" : ""}
                aria-expanded={panel === "process"}
                aria-controls="learning-drawer"
                onClick={() => togglePanel("process")}
              >
                <HistoryIcon size={16} />
                <span>Process overview</span>
              </button>
            )}
            <button
              className={panel === "materials" ? "active" : ""}
              aria-expanded={panel === "materials"}
              aria-controls="learning-drawer"
              onClick={() => togglePanel("materials")}
            >
              <FileText size={16} />
              <span>Materials</span>
            </button>
            <button
              className={panel === "responses" ? "active" : ""}
              aria-expanded={panel === "responses"}
              aria-controls="learning-drawer"
              onClick={() => togglePanel("responses")}
            >
              <BookOpen size={16} />
              <span>Saved responses</span>
            </button>
            {studentId && (
              <button
                className={panel === "review" ? "active" : ""}
                onClick={() => togglePanel("review")}
              >
                <ShieldCheck size={16} />
                <span>Teacher review</span>
              </button>
            )}
            <details className="guided-export">
              <summary aria-label="Download conversation">
                <Download size={16} />
                <span>Download</span>
                <ChevronDown size={12} />
              </summary>
              <div>
                {!studentId && (
                  <>
                    <a
                      href={api.transcriptUrl(
                        sid,
                        "html",
                        workspace.version?.id,
                      )}
                      download
                    >
                      Conversation · HTML
                    </a>
                    <a
                      href={api.transcriptUrl(
                        sid,
                        "txt",
                        workspace.version?.id,
                      )}
                      download
                    >
                      Conversation · text
                    </a>
                  </>
                )}
                <a
                  href={api.exportUrl(sid, studentId, workspace.version?.id)}
                  download
                >
                  Full learning record · JSON
                </a>
              </div>
            </details>
          </div>
        </nav>
        <div className="guided-body">
          <main
            className="guided-conversation"
            aria-label="Conversation with your tutor"
          >
            <div
              className="guided-stream"
              ref={stream}
              onScroll={() => {
                const e = stream.current;
                if (e) {
                  followBottom.current =
                    e.scrollHeight - e.scrollTop - e.clientHeight < 90;
                  if (followBottom.current) setShowLatest(false);
                }
              }}
            >
              {!workspace.messages.length && (
                <div className="guided-welcome">
                  <span>
                    <Sparkles size={27} />
                  </span>
                  <h2>
                    {studentId
                      ? "No conversation recorded yet"
                      : "Start with your own thinking"}
                  </h2>
                  <p>
                    {studentId
                      ? "Submitted responses are available in Saved responses."
                      : "Try a response or ask your tutor a question."}
                  </p>
                  {!!workspace.session.learning_objectives.length && (
                    <ul>
                      {workspace.session.learning_objectives
                        .filter(Boolean)
                        .map((goal, i) => (
                          <li key={i}>{goal}</li>
                        ))}
                    </ul>
                  )}
                  {!locked && !working && (
                    <button className="primary" onClick={() => void begin()}>
                      <Sparkles size={16} />
                      {error
                        ? "Try opening the session again"
                        : "Begin session"}
                    </button>
                  )}
                </div>
              )}
              {workspace.messages.map((item) => (
                <TutorMessage
                  key={item.id}
                  message={item}
                  highlighted={highlightedMessage === item.id}
                  workspace={workspace}
                  latest={lastAssistant?.id === item.id}
                  paced={tutor?.presentation === "paced" && !locked}
                  onQuestion={openQuestion}
                  onOption={
                    !locked && !working
                      ? (text) => {
                          editMessage(text);
                          composer.current?.focus();
                        }
                      : undefined
                  }
                />
              ))}
              {phase === "worksheet" &&
                currentQuestion &&
                !questionAlreadyShown && (
                  <div className="guided-current-prompt">
                    <QuestionPrompt
                      question={currentQuestion}
                      workspace={workspace}
                      disabled={locked || working}
                      onOption={(text) => {
                        editMessage(text);
                        composer.current?.focus();
                      }}
                    />
                  </div>
                )}
              {readingGroups.length > 0 &&
                !workspace.selected_reading &&
                !locked &&
                phase === "worksheet" &&
                !currentQuestion && (
                  <section className="guided-reading-choice">
                    <h3>Choose a reading path</h3>
                    <p>
                      Your core questions are shared; choose one article for the
                      reading questions.
                    </p>
                    {readingGroups.map((group) => (
                      <button
                        className="secondary"
                        key={group.id}
                        disabled={working}
                        onClick={() =>
                          void run("reading", () =>
                            api.reading(
                              sid,
                              group.id,
                              pinnedVersion.current,
                              workspace.preview?.id || undefined,
                            ),
                          )
                        }
                      >
                        <span>
                          <strong>{group.title}</strong>
                          {group.description && (
                            <small>{group.description}</small>
                          )}
                        </span>
                      </button>
                    ))}
                  </section>
                )}
              {phase === "quiz_offer" && !locked && (
                <div className="guided-choice-row">
                  <button
                    className="primary"
                    disabled={working}
                    onClick={() => void send(undefined, "Yes")}
                  >
                    Try the practice quiz
                  </button>
                  <button
                    className="secondary"
                    disabled={working}
                    onClick={() =>
                      void send(
                        undefined,
                        "No, let us skip the optional quiz.",
                        "skip_quiz",
                      )
                    }
                  >
                    Skip the quiz
                  </button>
                </div>
              )}
              {phase === "complete" && !studentId && (
                <div className="guided-wrap-card">
                  <CheckCircle2 size={21} />
                  <div>
                    <h3>Your conversation is saved</h3>
                    <p>
                      You can revisit your responses, download the actual
                      conversation, or ask another question.
                    </p>
                    {!locked && (
                      <button
                        className="primary"
                        disabled={working || !canSubmit(workspace)}
                        onClick={() => setSubmitDialog(true)}
                      >
                        Submit for teacher review
                      </button>
                    )}
                  </div>
                </div>
              )}
              {working && (
                <div className="guided-thinking" role="status">
                  <LoaderCircle className="spin" size={18} />
                  <span>
                    {busy === "start"
                      ? "Preparing your session…"
                      : "Your tutor is responding…"}
                  </span>
                </div>
              )}
            </div>
            {showLatest && (
              <button
                className="guided-latest secondary"
                onClick={scrollLatest}
              >
                <ArrowDown size={14} /> Latest message
              </button>
            )}
            {!locked ? (
              <form
                className="guided-composer"
                onSubmit={(event) => void send(event)}
              >
                {pending && !working && (
                  <div className="guided-retry">
                    <span>
                      Request not completed. Your text is retained for retry.
                    </span>
                    <button
                      type="button"
                      className="text-button"
                      onClick={() => void transmit(pending)}
                    >
                      <RotateCcw size={13} /> Retry previous message
                    </button>
                  </div>
                )}
                {showIdleHelp && (
                  <div className="guided-idle-help">
                    <span>Need a nudge?</span>
                    <button
                      type="button"
                      className="text-button"
                      onClick={() =>
                        void send(
                          undefined,
                          "Could you give me a hint without revealing the answer?",
                          "hint",
                          tutor?.current_question_id || undefined,
                        )
                      }
                    >
                      Ask for a hint
                    </button>
                    <button
                      className="icon-button"
                      aria-label="Dismiss hint invitation"
                      type="button"
                      onClick={() => setLastInteraction(Date.now())}
                    >
                      <X size={13} />
                    </button>
                  </div>
                )}
                <label
                  className="guided-composer-label"
                  htmlFor="guided-message-input"
                >
                  {currentQuestion && phase === "worksheet"
                    ? `Your response · Question ${currentQuestion.ordinal}`
                    : "Message your tutor"}
                </label>
                <textarea
                  id="guided-message-input"
                  ref={composer}
                  aria-label="Message your tutor"
                  placeholder="Share your thinking, ask a question, or try again…"
                  rows={3}
                  aria-describedby="guided-composer-keyboard-help"
                  value={message}
                  disabled={working}
                  onChange={(event) => editMessage(event.target.value)}
                  onCompositionStart={() => {
                    composing.current = true;
                  }}
                  onCompositionEnd={() => {
                    composing.current = false;
                  }}
                  onKeyDown={(event) => {
                    const action = composerEnterAction(
                      event.nativeEvent,
                      composing.current,
                    );
                    if (action === "native") return;
                    event.preventDefault();
                    if (action === "send") void send();
                  }}
                />
                <div className="guided-composer-tools">
                  <div>
                    <SearchToggle
                      ai={workspace.ai}
                      value={useWebSearch}
                      disabled={working}
                      onChange={changeSearch}
                    />
                    {phase === "worksheet" && (
                      <button
                        type="button"
                        className="text-button"
                        disabled={working}
                        onClick={() =>
                          void send(
                            undefined,
                            "Could you give me a hint without revealing the answer?",
                            "hint",
                            tutor?.current_question_id || undefined,
                          )
                        }
                      >
                        <Lightbulb size={14} /> Hint
                      </button>
                    )}
                  </div>
                  <button
                    type="submit"
                    className="primary"
                    disabled={working || !message.trim()}
                  >
                    <Send size={15} /> Send
                  </button>
                </div>
                <div className="guided-composer-caption">
                  <small>
                    {message
                      ? "Unsent draft saved on this device"
                      : "Your conversation is saved as you go."}
                  </small>
                  <small id="guided-composer-keyboard-help">
                    Enter to send · Shift + Enter for a new line
                  </small>
                </div>
              </form>
            ) : (
              <div className="guided-locked">
                <ShieldCheck size={16} />
                <span>{blockedReason}</span>
              </div>
            )}
            {workspace.submission.teacher_note && (
              <div className="guided-teacher-note">
                <strong>Teacher note</strong>
                <p className="preserve-text">
                  {workspace.submission.teacher_note}
                </p>
              </div>
            )}
          </main>
          {panel && (
            <aside
              className="guided-drawer"
              id="learning-drawer"
              aria-label={
                panel === "materials"
                  ? "Session materials"
                  : panel === "responses"
                    ? "Saved responses"
                    : panel === "process"
                      ? "Learning process overview"
                      : "Teacher review"
              }
            >
              <div className="guided-drawer-heading">
                <h2>
                  {panel === "materials"
                    ? "Session materials"
                    : panel === "responses"
                      ? "Saved responses"
                      : panel === "process"
                        ? "Process overview"
                        : "Teacher review"}
                </h2>
                <button
                  className="icon-button"
                  aria-label="Close learning panel"
                  onClick={() => setPanel(null)}
                >
                  <X size={18} />
                </button>
              </div>
              <div className="guided-drawer-content" key={panel}>
                {panel === "process" && studentId && (
                  <TeacherProcessOverview
                    workspace={workspace}
                    onMessage={locateMessage}
                    onResponse={(qid) => {
                      setSelected(qid);
                      setPanel("responses");
                    }}
                  />
                )}
                {panel === "materials" && (
                  <Materials
                    materials={workspace.session.materials}
                    teacher={!!studentId || preview}
                    versionId={workspace.version?.id}
                  />
                )}
                {panel === "responses" && (
                  <>
                    {readingGroups.length > 0 && (
                      <details className="guided-reading-manage">
                        <summary>
                          Reading path
                          {workspace.selected_reading
                            ? " · selected"
                            : " · choose one"}
                        </summary>
                        {readingGroups.map((group) => (
                          <button
                            className={`secondary ${workspace.selected_reading === group.id ? "selected" : ""}`}
                            key={group.id}
                            disabled={locked || working}
                            onClick={() =>
                              void run("reading", () =>
                                api.reading(
                                  sid,
                                  group.id,
                                  pinnedVersion.current,
                                  workspace.preview?.id || undefined,
                                ),
                              )
                            }
                          >
                            {group.title}
                          </button>
                        ))}
                      </details>
                    )}
                    <SavedResponses
                      workspace={workspace}
                      selected={selected}
                      viewerId={viewerId}
                      locked={locked}
                      busy={working}
                      teacherRecord={!!studentId}
                      references={references}
                      onSelect={setSelected}
                      onDiscuss={(question) => {
                        setPanel(null);
                        void send(
                          undefined,
                          `Could we revisit question ${question.ordinal}: ${question.prompt}`,
                          "review_question",
                          question.id,
                        );
                      }}
                      onSave={async (question, answer) =>
                        !!(await run("answer", () =>
                          api.answer(
                            sid,
                            question.id,
                            answer,
                            pinnedVersion.current,
                            workspace.preview?.id || undefined,
                          ),
                        ))
                      }
                      onReveal={(question) => void reveal(question)}
                      onUseDraft={(text, source) => {
                        oldDraft.current = source;
                        editMessage(text);
                        setPanel(null);
                      }}
                      onStorageWarning={() => setStorageWarning(true)}
                    />
                    {!locked && (
                      <section className="guided-submission">
                        <button
                          className="primary full"
                          disabled={working || !canSubmit(workspace)}
                          onClick={() => setSubmitDialog(true)}
                        >
                          Submit for teacher review
                        </button>
                        <small>
                          Save a response for each required question. Optional
                          practice is not a submission requirement.
                        </small>
                      </section>
                    )}
                  </>
                )}
                {panel === "review" && studentId && (
                  <section className="guided-review">
                    <Status status={workspace.submission.status} />
                    <label>
                      Teacher note
                      <textarea
                        rows={6}
                        value={teacherNote}
                        onChange={(event) => setTeacherNote(event.target.value)}
                      />
                    </label>
                    {!reviewAllowed && (
                      <p>
                        Review becomes available once the student has submitted
                        their work.
                      </p>
                    )}
                    <button
                      className="primary full"
                      disabled={working || !reviewAllowed}
                      onClick={() => void review("confirmed")}
                    >
                      Confirm completion
                    </button>
                    <button
                      className="secondary full"
                      disabled={working || !reviewAllowed}
                      onClick={() => void review("needs_revision")}
                    >
                      Request revision
                    </button>
                    <a
                      href={api.exportUrl(
                        sid,
                        studentId,
                        workspace.version?.id,
                      )}
                      download
                    >
                      Download full learning record
                    </a>
                    {workspace.submission.reviewed_at && (
                      <small>
                        Reviewed {dateLabel(workspace.submission.reviewed_at)}
                      </small>
                    )}
                  </section>
                )}
              </div>
            </aside>
          )}
        </div>
      </section>
      {resetDialog && preview && !studentId && (
        <dialog
          ref={resetModal}
          className="guided-submit-dialog"
          aria-labelledby="reset-preview-title"
          onCancel={(event) => {
            if (inFlight.current) event.preventDefault();
            else setResetDialog(false);
          }}
        >
          <RotateCcw size={24} />
          <h2 id="reset-preview-title">Reset only your draft test?</h2>
          <p>
            Your own preview conversation and test responses will be cleared.
            Other accounts, student records and published editions stay
            unchanged. Download the current test record first if you need a
            copy.
          </p>
          <div className="button-row">
            <button
              className="secondary"
              disabled={working}
              onClick={() => setResetDialog(false)}
            >
              Keep this preview
            </button>
            <button
              className="primary"
              disabled={working || !!workspace.preview?.pending}
              onClick={() => void resetOwnPreview()}
            >
              Reset my preview
            </button>
          </div>
        </dialog>
      )}
      {submitDialog && (
        <dialog
          ref={submitModal}
          className="guided-submit-dialog"
          aria-labelledby="submit-title"
          onCancel={(event) => {
            if (inFlight.current) event.preventDefault();
            else setSubmitDialog(false);
          }}
        >
          <CheckCircle2 size={24} />
          <h2 id="submit-title">Ready for your teacher to review?</h2>
          <p>
            Your saved responses and conversation will be submitted together.
            Editing pauses until your teacher requests a revision.
          </p>
          <div className="button-row">
            <button
              className="secondary"
              disabled={working}
              onClick={() => setSubmitDialog(false)}
            >
              Keep working
            </button>
            <button
              className="primary"
              disabled={working}
              onClick={() => void submit()}
            >
              Submit worksheet
            </button>
          </div>
        </dialog>
      )}
    </div>
  );
}
