import { useCallback, useEffect, useRef, useState } from "react";
import { Eye, Save } from "lucide-react";
import { api } from "./api";
import type {
  SessionDetail,
  WorksheetDraft,
  StudentRow,
  VersionList,
} from "./types";
import { useUiText } from "./uiText";
import { authoringErrors } from "./stage2";
import { dateLabel } from "./study";
import {
  Loading,
  ErrorBanner,
  Notice,
  Status,
  Empty,
  errorMessage,
} from "./ui";
import Authoring from "./Authoring";
import MaterialManager from "./MaterialManager";
import Availability, { AvailabilityBadge } from "./Availability";
import WorksheetImport from "./WorksheetImport";
import TeachingFramework from "./TeachingFramework";
import { saveTeachingDraft } from "./teaching-profile";
import TeacherPreviewPane from "./TeacherPreviewPane";
import TeachingSourceReview from "./TeachingSourceReview";
import InstructionImport from "./InstructionImport";
import HelpPopover from "./HelpPopover";
import "./teacher-workbench.css";
import { useUnsavedChanges } from "./navigation-guard";
export default function TeacherSession({
  sid,
  onPreview,
  onRecord,
  onSaved,
  viewerId,
  onVersions,
}: {
  sid: string;
  onPreview: (sid?: string, vid?: string) => void;
  onRecord: (uid: string, vid?: string) => void;
  onSaved: () => void;
  viewerId?: string;
  onVersions?: (courseId: string) => void;
}) {
  const { t } = useUiText();
  const [session, setSession] = useState<SessionDetail | null>(null),
    [draft, setDraft] = useState<SessionDetail | null>(null),
    [tab, setTab] = useState("configuration"),
    [dirty, setDirty] = useState(false),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [success, setSuccess] = useState(""),
    [students, setStudents] = useState<StudentRow[]>([]),
    [versions, setVersions] = useState<VersionList | null>(null),
    [recordVersion, setRecordVersion] = useState<string | undefined>();
  useUnsavedChanges(dirty);
  const [availabilityDirty, setAvailabilityDirty] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(true);
  const [previewBusy, setPreviewBusy] = useState(false);
  const currentSid = useRef(sid);
  currentSid.current = sid;
  const loadGeneration = useRef(0);
  const fill = useCallback((s: SessionDetail) => {
    setSession(s);
    setDraft(s);
    setDirty(false);
  }, []);
  const load = useCallback(async () => {
    const token = ++loadGeneration.current;
    setLoading(true);
    try {
      const next = await api.session(sid);
      if (token === loadGeneration.current && currentSid.current === sid)
        fill(next);
    } catch (e) {
      if (token === loadGeneration.current) setError(errorMessage(e));
    } finally {
      if (token === loadGeneration.current) setLoading(false);
    }
  }, [sid, fill]);
  useEffect(() => {
    setPreviewBusy(false);
    setBusy(false);
    setError("");
    setSuccess("");
    void load();
    return () => {
      loadGeneration.current++;
    };
  }, [load]);
  useEffect(() => {
    if (tab !== "records") return;
    let alive = true;
    Promise.all([
      api.students(sid, recordVersion),
      api.versions(session!.course_id),
    ])
      .then(([rows, v]) => {
        if (alive) {
          setStudents(rows);
          setVersions(v);
        }
      })
      .catch((e) => {
        if (alive) setError(errorMessage(e));
      });
    return () => {
      alive = false;
    };
  }, [tab, sid, recordVersion, session?.course_id]);
  useEffect(() => {
    if (!session?.materials.some((m) => m.status === "processing")) return;
    let alive = true;
    const timer = setInterval(() => {
      api
        .session(sid)
        .then((s) => {
          if (!alive || currentSid.current !== sid) return;
          setSession((old) => (old ? { ...old, materials: s.materials } : s));
          setDraft((old) => (old ? { ...old, materials: s.materials } : s));
        })
        .catch((e) => {
          if (alive) setError(errorMessage(e));
        });
    }, 3000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [sid, session?.materials]);
  function update(p: Partial<SessionDetail>) {
    setDraft((d) => (d ? { ...d, ...p } : d));
    setDirty(true);
    setSuccess("");
  }
  async function save() {
    if (!draft || busy || previewBusy) return false;
    const token = loadGeneration.current;
    const errors = authoringErrors(draft.groups, draft.questions);
    if (errors.length) {
      setError(errors.join("; "));
      return false;
    }
    setBusy(true);
    setError("");
    try {
      const verified = await saveTeachingDraft(sid, draft);
      if (currentSid.current !== sid || token !== loadGeneration.current)
        return false;
      fill(verified);
      setSuccess("Draft saved. Publication is separate.");
      onSaved();
      return true;
    } catch (e) {
      if (currentSid.current === sid && token === loadGeneration.current)
        setError(errorMessage(e));
      return false;
    } finally {
      if (currentSid.current === sid && token === loadGeneration.current)
        setBusy(false);
    }
  }
  if (loading) return <Loading />;
  if (!session || !draft)
    return (
      <div className="page">
        <ErrorBanner error={error} retry={load} />
      </div>
    );
  const authoring: WorksheetDraft = {
    title: draft.title,
    groups: draft.groups,
    questions: draft.questions,
    reference_answers: draft.reference_answers || {},
  };
  return (
    <div className="page teacher-page">
      <div className="page-heading">
        <div>
          <div className="eyebrow">
            {t("session")} {session.number}
          </div>
          <h1>{session.title}</h1>
          <p>{session.subtitle}</p>
        </div>
        <div className="button-row">
          <button
            className="secondary"
            disabled={busy}
            aria-expanded={previewOpen}
            aria-controls="teacher-same-screen-preview"
            onClick={() => {
              setPreviewOpen(true);
              requestAnimationFrame(() => {
                if (window.innerWidth <= 1100)
                  document
                    .getElementById("teacher-same-screen-preview")
                    ?.scrollIntoView({ block: "start" });
                document
                  .getElementById("teacher-same-screen-preview")
                  ?.focus({ preventScroll: true });
              });
            }}
          >
            <Eye size={16} />
            {"Preview tutor"}
          </button>
          <button
            className="primary"
            disabled={busy || previewBusy || !dirty || !draft.title.trim()}
            onClick={() => void save()}
          >
            <Save size={16} />
            {"Save draft"}
          </button>
        </div>
      </div>
      <div className="teacher-status-line">
        <span className="small-tag">Editing draft</span>
        <AvailabilityBadge session={session} />
        <a
          href="#teacher-availability"
          onClick={(e) => {
            e.preventDefault();
            setTab("configuration");
            requestAnimationFrame(() => {
              const section = document.getElementById("teacher-availability");
              const details = section?.querySelector("details");
              if (details) details.open = true;
              section?.scrollIntoView({ block: "start" });
              section?.querySelector("summary")?.focus();
            });
          }}
        >
          Availability &amp; schedule
        </a>
        {dirty && <span className="unsaved">{t("unsaved")}</span>}
        <span>
          {draft.questions.length} {draft.questions.length === 1 ? "question" : t("questions")}
        </span>
        {onVersions && (
          <button
            className="text-button"
            disabled={busy || previewBusy}
            onClick={() => onVersions(session.course_id)}
          >
            Publish &amp; version history
          </button>
        )}
      </div>
      <ErrorBanner error={error} onClose={() => setError("")} />
      {success && <Notice>{success}</Notice>}
      {dirty && (
        <p className="tw-unsaved-banner" role="status">
          Unsaved changes · tutor preview uses the saved draft, not these edits.
        </p>
      )}
      <div className={`tw-workbench ${previewOpen ? "tw-with-preview" : ""}`}>
        <div
          className="tw-editor"
          id="teacher-draft-editor"
          tabIndex={-1}
          aria-label="Teaching draft editor"
        >
          <nav className="tabs" aria-label="Teaching session sections">
            {[
              ["configuration", t("configuration")],
              ["materials", t("materials")],
              ["tasks", t("tasks")],
              ["records", t("records")],
            ].map(([key, label]) => (
              <button
                key={key}
                className={tab === key ? "active" : ""}
                aria-current={tab === key ? "page" : undefined}
                disabled={busy}
                onClick={() => {
                  if (
                    tab === "configuration" &&
                    availabilityDirty &&
                    !window.confirm("Discard unapplied availability changes?")
                  )
                    return;
                  setTab(key);
                }}
              >
                {label}
              </button>
            ))}
          </nav>
          {tab === "configuration" && (
            <>
              <section className="card form-card tw-goals">
                <div className="tw-section-heading">
                  <h2>Learning goals</h2>
                  <HelpPopover label="Help with learning goals">
                    One objective per line. These goals guide the tutor; saving
                    does not change the published edition.
                  </HelpPopover>
                </div>
                <fieldset className="teacher-config-fields" disabled={busy}>
                  <div className="form-grid">
                    <label className="span-two">
                      Objectives
                      <textarea
                        rows={4}
                        value={draft.learning_objectives.join("\n")}
                        onChange={(e) =>
                          update({
                            learning_objectives: e.target.value.split("\n"),
                          })
                        }
                      />
                    </label>
                    <label>
                      Teaching language
                      <select
                        value={draft.teaching_language}
                        onChange={(e) =>
                          update({ teaching_language: e.target.value })
                        }
                      >
                        <option value="en">English</option>
                        <option value="zh">Chinese</option>
                      </select>
                    </label>
                  </div>
                  <details className="tw-session-details">
                    <summary>Session details &amp; publication</summary>
                    <div className="form-grid">
                      <label>
                        {t("title")}
                        <input
                          value={draft.title}
                          onChange={(e) => update({ title: e.target.value })}
                        />
                      </label>
                      <label>
                        {t("subtitle")}
                        <input
                          value={draft.subtitle}
                          onChange={(e) => update({ subtitle: e.target.value })}
                        />
                      </label>
                      <label className="span-two">
                        Include in next published edition
                        <select
                          value={draft.status}
                          onChange={(e) =>
                            update({
                              status: e.target.value as SessionDetail["status"],
                            })
                          }
                        >
                          <option value="published">Included</option>
                          <option value="draft">Not yet included</option>
                        </select>
                        <small>
                          This flag does not publish a version or open the
                          classroom.
                        </small>
                      </label>
                    </div>
                  </details>
                </fieldset>
              </section>
              <TeachingFramework
                session={draft}
                disabled={busy}
                onChange={update}
                instructionImport={
                  <InstructionImport
                    key={`import:${sid}`}
                    sid={sid}
                    instructions={draft.instructions}
                    disabled={busy}
                    onApply={(text) => update({ instructions: text })}
                  />
                }
              />
              <TeachingSourceReview
                key={`sources:${sid}`}
                saved={session}
                draft={draft}
                disabled={busy}
              />
              <Availability
                key={`availability:${sid}`}
                session={session}
                onDirtyChange={setAvailabilityDirty}
                onBusyChange={setBusy}
                onSaved={(s) => {
                  if (s.id !== currentSid.current) return;
                  setSession(s);
                  setDraft((d) =>
                    d
                      ? {
                          ...d,
                          active: s.active,
                          starts_at: s.starts_at,
                          ends_at: s.ends_at,
                          effective_active: s.effective_active,
                          availability_reason: s.availability_reason,
                        }
                      : d,
                  );
                  onSaved();
                }}
              />
            </>
          )}
          {tab === "materials" && (
            <MaterialManager
              key={session.id}
              session={session}
              onBusyChange={setBusy}
              onChanged={(s) => {
                if (s.id !== currentSid.current) return;
                setSession(s);
                setDraft((d) => (d ? { ...d, materials: s.materials } : d));
                onSaved();
              }}
            />
          )}
          {tab === "tasks" && (
            <>
              <p className="section-intro">{t("questionEditorHelp")}</p>
              {dirty ? (
                <Notice>
                  {"Save or discard local edits before importing a worksheet."}
                </Notice>
              ) : (
                <WorksheetImport
                  key={`worksheet:${sid}`}
                  session={session}
                  onCommitted={(s) => {
                    if (s.id !== currentSid.current) return;
                    fill(s);
                    onSaved();
                  }}
                />
              )}
              <Authoring
                value={authoring}
                materials={session.materials}
                disabled={busy}
                onChange={(d) =>
                  update({
                    groups: d.groups,
                    questions: d.questions,
                    reference_answers: d.reference_answers,
                  })
                }
              />
            </>
          )}
          {tab === "records" && (
            <section className="records-panel">
              <div className="section-heading">
                <h2>{t("records")}</h2>
                <label>
                  {"Content edition"}
                  <select
                    aria-label={"Content edition"}
                    value={recordVersion || ""}
                    onChange={(e) =>
                      setRecordVersion(e.target.value || undefined)
                    }
                  >
                    <option value="">{"Current published edition"}</option>
                    {versions?.versions.map((v) => (
                      <option key={v.id} value={v.id}>
                        v{v.number} · {v.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <p>
                {
                  "Select the original edition to review its submissions. Observation is read-only; it is not your draft preview."
                }
              </p>
              <div className="table-wrap card">
                <table>
                  <thead>
                    <tr>
                      <th>{t("student")}</th>
                      <th>{t("progress")}</th>
                      <th>{t("lastActive")}</th>
                      <th>{t("review")}</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {students.map((row) => (
                      <tr key={row.user.id}>
                        <td>
                          <strong>{row.user.name}</strong>
                          <small className="block">{row.user.email}</small>
                        </td>
                        <td>
                          {row.answered} / {row.total}
                        </td>
                        <td>{dateLabel(row.last_active)}</td>
                        <td>
                          <Status status={row.status} />
                        </td>
                        <td>
                          <button
                            className="text-button"
                            onClick={() =>
                              onRecord(
                                row.user.id,
                                recordVersion || row.version?.id || undefined,
                              )
                            }
                          >
                            {t("viewRecord")}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!students.length && <Empty title={t("noStudents")} />}
              </div>
            </section>
          )}
          {(tab === "configuration" || tab === "tasks") && (
            <div className="save-bar">
              <span>
                {dirty ? t("unsaved") : "Draft saved · publication is separate"}
              </span>
              <div className="button-row">
                {dirty && (
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() => {
                      if (
                        window.confirm("Discard local unsaved content edits?")
                      )
                        fill(session);
                    }}
                  >
                    {"Discard edits"}
                  </button>
                )}
                <button
                  className="primary"
                  disabled={
                    busy || previewBusy || !dirty || !draft.title.trim()
                  }
                  onClick={() => void save()}
                >
                  {"Save draft"}
                </button>
              </div>
            </div>
          )}
        </div>
        <div
          id="teacher-same-screen-preview"
          tabIndex={-1}
          className="tw-preview-column"
          hidden={!previewOpen}
        >
          <TeacherPreviewPane
            key={`preview:${sid}:${viewerId || "current-owner"}`}
            saved={session}
            unsaved={dirty}
            viewerId={viewerId}
            onBusyChange={setPreviewBusy}
            onClose={() => setPreviewOpen(false)}
            onFullPreview={() => onPreview()}
          />
        </div>
      </div>
    </div>
  );
}
