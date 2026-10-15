import { useEffect, useRef, useState, type FormEvent } from "react";
import type { SessionDetail, Material, CourseMaterial } from "./types";
import { api } from "./api";
import { useUiText } from "./uiText";
import { ErrorBanner, errorMessage, Notice } from "./ui";
import Materials from "./Materials";
import HelpPopover from "./HelpPopover";
import { useUnsavedChanges } from "./navigation-guard";
import {
  materialReadbackMatches,
  selectMaterialFiles,
  uploadMaterialQueue,
  uploadSuccessMessage,
  type MaterialUpload,
} from "./material-upload";
import "./material-manager.css";
import { documentApi } from "./document-api";
import type { DocumentCapability } from "./document-types";

const FILE_KINDS = ["reading", "worksheet", "answer_key", "slides", "reference"];
export function fileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
}

export default function MaterialManager({
  session,
  onChanged,
  onBusyChange,
}: {
  session: SessionDetail;
  onChanged: (s: SessionDetail) => void;
  onBusyChange?: (busy: boolean) => void;
}) {
  const { t } = useUiText();
  const [capability, setCapability] = useState<DocumentCapability | null>(null);
  const [capabilityLoaded, setCapabilityLoaded] = useState(false);
  useEffect(() => {
    const control = new AbortController();
    setCapabilityLoaded(false);
    documentApi
      .capability(control.signal)
      .then(setCapability)
      .catch(() => {
        if (!control.signal.aborted) setCapability(null);
      })
      .finally(() => { if (!control.signal.aborted) setCapabilityLoaded(true); });
    return () => control.abort();
  }, [session.id]);
  const [queue, setQueue] = useState<MaterialUpload[]>([]),
    [visibility, setVisibility] = useState<"student" | "teacher">("student"),
    [linkVisibility, setLinkVisibility] = useState<"student" | "teacher">(
      "student",
    ),
    [kind, setKind] = useState("reading"),
    [url, setUrl] = useState(""),
    [title, setTitle] = useState(""),
    [library, setLibrary] = useState<CourseMaterial[]>([]),
    [libraryLoading, setLibraryLoading] = useState(true),
    [selected, setSelected] = useState(""),
    [editing, setEditing] = useState<Material | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [success, setSuccess] = useState("");
  const editedOriginal =
    editing && session.materials.find((m) => m.id === editing.id);
  useUnsavedChanges(
    busy ||
      !!url ||
      !!title ||
      queue.some((q) => q.status === "queued" || q.status === "failed") ||
      !!(
        editing &&
        editedOriginal &&
        (editing.title !== editedOriginal.title ||
          editing.kind !== editedOriginal.kind ||
          editing.visibility !== editedOriginal.visibility ||
          editing.url !== editedOriginal.url)
      ),
  );
  const epoch = useRef(0),
    inFlight = useRef(false);
  useEffect(() => {
    const current = ++epoch.current;
    setLibraryLoading(true);
    api
      .courseMaterials(session.course_id)
      .then((r) => {
        if (current === epoch.current) setLibrary(r.materials);
      })
      .catch((e) => {
        if (current === epoch.current) setError(errorMessage(e));
      })
      .finally(() => {
        if (current === epoch.current) setLibraryLoading(false);
      });
    return () => {
      epoch.current++;
      onBusyChange?.(false);
    };
  }, [session.course_id, session.id]);

  async function run(
    action: () => Promise<Material | void>,
    message: string | (() => string) = "Draft saved and verified. Publish a course edition to share changes with students.",
    verify?: (s: SessionDetail, library: CourseMaterial[]) => boolean,
  ) {
    if (inFlight.current) return false;
    const current = epoch.current;
    inFlight.current = true;
    setBusy(true);
    onBusyChange?.(true);
    setError("");
    setSuccess("");
    try {
      const result = await action();
      if (current !== epoch.current) return false;
      const [s, list] = await Promise.all([
        api.session(session.id),
        api.courseMaterials(session.course_id),
      ]);
      if (current !== epoch.current) return false;
      if (
        s.id !== session.id ||
        (result &&
          (!materialReadbackMatches(
            result,
            s.materials.find((m) => m.id === result.id),
          ) ||
            !list.materials.some(
              (m) => m.id === result.id && m.session_ids.includes(session.id),
            ))) ||
        (verify && !verify(s, list.materials))
      ) {
        throw new Error(
          "The update could not be confirmed in both the session and course library. Refresh before retrying.",
        );
      }
      setLibrary(list.materials);
      onChanged(s);
      setSuccess(typeof message === "function" ? message() : message);
      return true;
    } catch (e) {
      if (current === epoch.current) setError(errorMessage(e));
      return false;
    } finally {
      inFlight.current = false;
      if (current === epoch.current) {
        setBusy(false);
        setLibraryLoading(false);
        onBusyChange?.(false);
      }
    }
  }
  async function upload(items = queue.filter((q) => q.status === "queued")) {
    const current = epoch.current;
    let accepted: Material[] = [];
    await run(
      async () => {
        accepted = await uploadMaterialQueue(
          session.id,
          items,
          { visibility, kind },
          (item) =>
            setQueue((rows) =>
              rows.map((r) => (r.key === item.key ? item : r)),
            ),
          () => current === epoch.current,
        );
        if (!accepted.length && current === epoch.current)
          throw new Error(
            "No files were uploaded. Check the individual results below.",
          );
      },
      () => uploadSuccessMessage(accepted),
      (s, list) =>
        accepted.every(
          (m) =>
            materialReadbackMatches(
              m,
              s.materials.find((a) => a.id === m.id),
            ) &&
            list.some(
              (a) => a.id === m.id && a.session_ids.includes(session.id),
            ),
        ),
    );
  }
  async function link(e: FormEvent) {
    e.preventDefault();
    if (
      await run(() =>
        api.createLink(session.id, { url, title, visibility: linkVisibility }),
      )
    ) {
      setUrl("");
      setTitle("");
    }
  }
  const currentIds = new Set(session.materials.map((m) => m.id));
  const available = library.filter(
    (m) => !currentIds.has(m.id) && !m.session_ids.includes(session.id),
  );
  const failed = queue.filter((q) => q.status === "failed");
  return (
    <section className="materials-editor">
      <div className="section-heading">
        <div>
          <h2>Session materials</h2>
          <p>Files and links used by this session.</p>
        </div>
        <button
          className="secondary"
          disabled={busy}
          onClick={() => void run(async () => {}, "Materials refreshed.")}
        >
          {t("refresh")}
        </button>
      </div>
      <ErrorBanner error={error} />
      {success && <Notice>{success}</Notice>}
      <div className="material-create-grid">
        <form
          className="upload-card card"
          onSubmit={(e) => {
            e.preventDefault();
            void upload();
          }}
        >
          <h3>Upload materials</h3>
          <p>Files are saved once in the course library and linked here.</p>
          <p className="extraction-note">
            {capability?.available
              ? `${capability.formats.map((f) => f.toUpperCase()).join(", ")}: complete document processing in the background. Other formats: text/OCR preview only.`
              : "Text/OCR preview only. Complete document processing is unavailable or not yet confirmed."}
          </p>
          <fieldset className="material-form-fields" disabled={busy}>
            <label>
              Choose files
              <input
                type="file"
                multiple
                disabled={!capabilityLoaded}
                accept=".txt,.md,.pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.png,.jpg,.jpeg,.webp"
                onChange={(e) => {
                  setQueue(
                    selectMaterialFiles(
                      Array.from(e.target.files || []),
                      capability ?? false,
                    ),
                  );
                  setSuccess("");
                }}
              />
            </label>
            <label>
              Choose a folder
              <input type="file" multiple aria-label="Choose a folder" disabled={!capabilityLoaded}
                ref={(input) => { input?.setAttribute("webkitdirectory", ""); }}
                onChange={(e) => {
                  setQueue(selectMaterialFiles(Array.from(e.target.files || []), capability ?? false));
                  setSuccess("");
                }} />
            </label>
            <small>
              {capability?.available ? `${capability.max_upload_bytes / (1024 * 1024)} MiB for complete processing; 25 MiB for previews.` : "25 MiB per preview file."} Text, PDF, Word, PowerPoint and images.
              <HelpPopover label="material extraction">
                Complete processing retains source pages and uses the configured document worker.
                Other formats use a text/OCR preview. Review flagged source regions before publishing.
              </HelpPopover>
            </small>
            <label>
              Default material type
              <select
                aria-label={t("kind")}
                value={kind}
                onChange={(e) => {
                  setKind(e.target.value);
                  if (e.target.value === "answer_key") setVisibility("teacher");
                }}
              >
                {FILE_KINDS.map((k) => (
                  <option key={k} value={k}>
                    {t(`${k}Kind` as Parameters<typeof t>[0])}
                  </option>
                ))}
              </select>
            </label>
            <Visibility
              value={visibility}
              onChange={setVisibility}
              teacherOnly={kind === "answer_key"}
            />
            <button
              className="primary"
              disabled={!queue.some((q) => q.status === "queued")}
            >
              Upload selected files
            </button>
          </fieldset>
        </form>
        <form className="upload-card card" onSubmit={(e) => void link(e)}>
          <h3>Add a link</h3>
          <p>Public URL or DOI. Private-access restrictions still apply.</p>
          <fieldset className="material-form-fields" disabled={busy}>
            <label>
              URL / DOI
              <input
                required
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://… / 10.1234/example"
              />
            </label>
            <label>
              {t("title")}
              <input value={title} onChange={(e) => setTitle(e.target.value)} />
            </label>
            <Visibility value={linkVisibility} onChange={setLinkVisibility} />
            <button className="primary" disabled={!url.trim()}>
              Save link
            </button>
          </fieldset>
        </form>
      </div>
      {queue.length > 0 && (
        <section
          className="upload-results card"
          aria-label="Upload results"
          aria-live="polite"
        >
          <div className="section-heading">
            <h3>Selected files ({queue.length})</h3>
            <span>{fileSize(queue.reduce((total, item) => total + item.file.size, 0))}</span>
            {failed.length > 1 && (
              <button
                className="secondary"
                disabled={busy}
                onClick={() => void upload(failed)}
              >
                Retry failed files
              </button>
            )}
          </div>
          <small>
            Keep this page open while files upload. Completed files remain in
            the course library if you leave.
          </small>
          <ul>
            {queue.map((item) => (
              <li key={item.key} data-upload-state={item.status}>
                <div>
                  <strong>{item.relativePath || item.file.name}</strong>
                  <small>{fileSize(item.file.size)}</small>
                  {(item.status === "queued" || item.status === "failed") && <label>
                    Material type
                    <select aria-label={`Material type for ${item.relativePath || item.file.name}`} value={item.kind ?? kind} disabled={busy}
                      onChange={(e) => setQueue((rows) => rows.map((row) => row.key === item.key ? {...row, kind: e.target.value, visibility: e.target.value === "answer_key" ? "teacher" : row.visibility} : row))}>
                      {FILE_KINDS.map((value) => <option key={value} value={value}>{t(`${value}Kind` as Parameters<typeof t>[0])}</option>)}
                    </select>
                  </label>}
                  {item.status === "uploading" && <div className="material-upload-progress">
                    <progress aria-label={`Upload progress for ${item.relativePath || item.file.name}`} max={100}
                      value={item.progress?.complete ? 100 : item.progress?.total ? Math.min(100, item.progress.loaded / item.progress.total * 100) : undefined} />
                    <span>{item.progress?.complete ? "100% sent · waiting for server confirmation" : item.progress?.total ? `${Math.floor(item.progress.loaded / item.progress.total * 100)}% uploaded` : "Uploading…"}</span>
                  </div>}
                  <small>
                    {item.status === "uploading"
                      ? item.processing === "full_document"
                        ? "Saving original & queuing full document…"
                        : "Uploading & extracting preview…"
                      : item.status === "uploaded"
                        ? item.processing === "full_document"
                          ? "Original saved · inspect background processing separately"
                          : item.material?.status === "ready"
                            ? "Uploaded"
                            : "Uploaded · extraction needs review"
                        : item.status === "failed"
                          ? "Upload not confirmed"
                          : item.processing === "full_document"
                            ? "Queued · complete document"
                            : "Queued · preview only"}
                  </small>
                  {item.error && <p className="field-error">{item.error}</p>}
                </div>
                {(item.status === "queued" || item.status === "failed") && <button type="button" className="text-button danger" disabled={busy}
                  aria-label={`Remove selected ${item.relativePath || item.file.name}`} onClick={() => setQueue((rows) => rows.filter((row) => row.key !== item.key))}>Remove selected file</button>}
                {item.status === "failed" && (
                  <button
                    type="button"
                    className="secondary"
                    disabled={busy}
                    onClick={() => void upload([item])}
                    aria-label={`Retry ${item.file.name}`}
                  >
                    Retry
                  </button>
                )}
              </li>
            ))}
          </ul>
          {failed.length > 0 && (
            <small>
              Successful files will not be uploaded again. If a connection was
              lost, check the course library before retrying that file.
            </small>
          )}
        </section>
      )}
      <form
        className="course-material-picker card"
        onSubmit={async (e) => {
          e.preventDefault();
          if (
            selected &&
            (await run(() => api.attachMaterial(session.id, selected)))
          )
            setSelected("");
        }}
      >
        <div>
          <h3>Reuse a course material</h3>
          <p>Link an existing file without uploading it again.</p>
        </div>
        <label>
          Course Materials
          <select
            aria-label="Course Materials"
            value={selected}
            disabled={busy || libraryLoading}
            onChange={(e) => setSelected(e.target.value)}
          >
            <option value="">
              {libraryLoading
                ? "Loading course library…"
                : available.length
                  ? "Select an existing course material"
                  : "No unlinked course materials"}
            </option>
            {available.map((m) => (
              <option key={m.id} value={m.id}>
                {m.title}
                {m.visibility === "teacher" ? " · Teacher only" : ""}
              </option>
            ))}
          </select>
        </label>
        <button
          className="secondary"
          disabled={
            busy || !selected || !available.some((m) => m.id === selected)
          }
        >
          Add to this session
        </button>
      </form>
      {editing && (
        <form
          className="card form-card"
          onSubmit={async (e) => {
            e.preventDefault();
            const m = editing;
            if (
              await run(() =>
                api.updateMaterial(session.id, m.id, {
                  title: m.title,
                  visibility: m.visibility,
                  ...(m.kind !== "link" ? {kind: m.kind} : {}),
                  ...(m.kind === "link" ? { url: m.url || "" } : {}),
                }),
              )
            )
              setEditing(null);
          }}
        >
          <h3>Edit shared material</h3>
          <p>
            Title, visibility and source changes apply to all linked session
            drafts. Published editions stay unchanged.
          </p>
          <fieldset className="material-form-fields" disabled={busy}>
            <label>
              {t("title")}
              <input
                required
                value={editing.title}
                onChange={(e) =>
                  setEditing({ ...editing, title: e.target.value })
                }
              />
            </label>
            {editing.kind === "link" && (
              <label>
                URL / DOI
                <input
                  required
                  value={editing.url || ""}
                  onChange={(e) =>
                    setEditing({ ...editing, url: e.target.value })
                  }
                />
              </label>
            )}
            {editing.kind !== "link" && <label>Material type
              <select aria-label="Edit material type" value={editing.kind} onChange={(e) => setEditing({...editing, kind:e.target.value, visibility:e.target.value === "answer_key" ? "teacher" : editing.visibility})}>
                {FILE_KINDS.map((value) => <option key={value} value={value}>{t(`${value}Kind` as Parameters<typeof t>[0])}</option>)}
              </select>
            </label>}
            <Visibility
              value={editing.visibility}
              onChange={(v) => setEditing({ ...editing, visibility: v })}
              teacherOnly={editing.kind === "answer_key"}
            />
            <div className="button-row">
              <button className="primary">{t("save")}</button>
              <button
                type="button"
                className="secondary"
                onClick={() => setEditing(null)}
              >
                {t("cancel")}
              </button>
            </div>
          </fieldset>
        </form>
      )}
      <Materials
        materials={session.materials}
        teacher
        disabled={busy}
        onDocumentChanged={() =>
          void run(
            async () => {},
            "Document draft refreshed. Publication remains explicit.",
          )
        }
        onEdit={(m) => setEditing({ ...m })}
        onReprocess={async (m) => {
          await run(
            () => api.reprocessMaterial(session.id, m.id),
            "Extraction refreshed and verified. Review the result before publishing.",
          );
        }}
        onArchive={async (m) => {
          const ok = await run(
            async () => {
              await api.archiveMaterial(session.id, m.id);
            },
            "Removed from this session. The course file, other sessions and published editions are unchanged.",
            (s, list) =>
              !s.materials.some((x) => x.id === m.id) &&
              list.some(
                (x) => x.id === m.id && !x.session_ids.includes(session.id),
              ),
          );
          if (!ok) throw new Error("Session removal was not confirmed.");
        }}
      />
    </section>
  );
}
function Visibility({
  value,
  onChange,
  teacherOnly = false,
}: {
  value: "student" | "teacher";
  onChange: (v: "student" | "teacher") => void;
  teacherOnly?: boolean;
}) {
  const { t } = useUiText();
  return (
    <label>
      <span>
        {t("visibility")}{" "}
        <HelpPopover label="material visibility">
          Teacher-only material stays private. Answer keys must remain
          teacher-only. A saved draft becomes available to students only through
          a published edition.
        </HelpPopover>
      </span>
      <select
        aria-label={t("visibility")}
        value={value}
        onChange={(e) => onChange(e.target.value as typeof value)}
      >
        <option value="student" disabled={teacherOnly}>
          {t("studentMaterial")}
        </option>
        <option value="teacher">{t("teacherMaterial")}</option>
      </select>
    </label>
  );
}
