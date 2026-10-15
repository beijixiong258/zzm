import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { useUnsavedChanges } from "./navigation-guard";
import {
  importFileError,
  passwordValid,
  unknownWrite,
} from "./account-management-state";
import { api } from "./api";
import type { RosterEntry, RosterPreview, RosterResult } from "./types";
import { useUiText } from "./uiText";
import { retentionText } from "./stage2";
import { Loading, ErrorBanner, Empty, errorMessage } from "./ui";
import { AccountNotice as Notice } from "./account-management-ui";
import ProvisionStudent from "./ProvisionStudent";
type RosterProps = {
  courseId?: string;
  onChanged?: () => void;
  onHold?: (held: boolean) => void;
};
export default function Roster(props: RosterProps) {
  if (!props.courseId)
    return <p>Choose an assigned course to manage Course Students.</p>;
  return (
    <CourseRoster key={props.courseId} {...props} courseId={props.courseId} />
  );
}
function CourseRoster({
  courseId,
  onChanged,
  onHold,
}: RosterProps & { courseId: string }) {
  const { t } = useUiText();
  const [rows, setRows] = useState<RosterEntry[]>([]),
    [archived, setArchived] = useState(false),
    [selected, setSelected] = useState<string[]>([]),
    [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [success, setSuccess] = useState("");
  const [file, setFile] = useState<File | null>(null),
    [password, setPassword] = useState(""),
    [preview, setPreview] = useState<RosterPreview | null>(null),
    [result, setResult] = useState<RosterResult | null>(null),
    [confirm, setConfirm] = useState(false);
  const [now, setNow] = useState(Date.now());
  const alive = useRef(true),
    pending = useRef(false),
    generation = useRef(0);
  const fileInput = useRef<HTMLInputElement>(null);
  const [provisionHeld, setProvisionHeld] = useState(false);
  const [recovery, setRecovery] = useState<
    | { kind: "action"; ids: string[]; fromArchived: boolean; ack: boolean }
    | { kind: "import"; ackResult: RosterResult | null }
    | null
  >(null);
  const [inspected, setInspected] = useState(false);
  useUnsavedChanges(
    !!file || !!password || !!preview || confirm || busy || !!recovery,
  );
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      generation.current++;
      pending.current = false;
    };
  }, []);
  useEffect(() => {
    onHold?.(busy || loading || !!recovery || provisionHeld);
    return () => onHold?.(false);
  }, [busy, loading, recovery, provisionHeld, onHold]);
  const load = useCallback(async () => {
    if (pending.current) return;
    pending.current = true;
    const token = ++generation.current;
    setLoading(true);
    setError("");
    try {
      const next = await api.roster(courseId, archived);
      if (!alive.current || token !== generation.current) return;
      setRows(next);
      setNow(Date.now());
      setSelected([]);
      setConfirm(false);
    } catch (e) {
      if (alive.current && token === generation.current)
        setError(errorMessage(e));
    } finally {
      if (alive.current && token === generation.current) {
        pending.current = false;
        setLoading(false);
      }
    }
  }, [courseId, archived]);
  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 60000);
    return () => clearInterval(timer);
  }, []);
  async function act() {
    if (pending.current || recovery || !selected.length) return;
    pending.current = true;
    const token = ++generation.current,
      expected = [...selected],
      fromArchived = archived;
    setBusy(true);
    setError("");
    setSuccess("");
    let ack = false;
    try {
      const result = await api.rosterAction(
        fromArchived ? "restore" : "archive",
        expected,
        courseId,
      );
      if (!alive.current || token !== generation.current) return;
      if (expected.some((x) => !result.affected_ids.includes(x)))
        throw new Error("Not all selected changes were acknowledged.");
      ack = true;
      setRecovery({ kind: "action", ids: expected, fromArchived, ack });
      const [source, target] = await Promise.all([
        api.roster(courseId, fromArchived),
        api.roster(courseId, !fromArchived),
      ]);
      if (!alive.current || token !== generation.current) return;
      if (
        source.some((r) => expected.includes(r.user.id)) ||
        expected.some((uid) => !target.some((r) => r.user.id === uid))
      )
        throw new Error(
          "Roster changes could not be independently verified in both lists.",
        );
      setRows(source);
      setNow(Date.now());
      setSelected([]);
      setConfirm(false);
      setRecovery(null);
      setSuccess(
        "Course enrollment change acknowledged and independently verified.",
      );
      onChanged?.();
    } catch (e) {
      if (!alive.current || token !== generation.current) return;
      if (ack || unknownWrite(e)) {
        setRecovery({ kind: "action", ids: expected, fromArchived, ack });
        setInspected(false);
        setError(
          `Roster outcome needs inspection; selection retained. No automatic retry. ${errorMessage(e)}`,
        );
      } else setError(errorMessage(e));
    } finally {
      if (alive.current && token === generation.current) {
        pending.current = false;
        setBusy(false);
      }
    }
  }
  async function importPreview(e: FormEvent) {
    e.preventDefault();
    if (!file || pending.current || recovery) return;
    const invalid = importFileError(file);
    if (invalid) {
      setError(invalid);
      return;
    }
    pending.current = true;
    const token = ++generation.current;
    setBusy(true);
    setError("");
    setResult(null);
    setSuccess("");
    try {
      const next = await api.rosterPreview(courseId, file, password);
      if (!alive.current || token !== generation.current) return;
      setPreview(next);
      setPassword("");
    } catch (e) {
      if (alive.current && token === generation.current)
        setError(errorMessage(e));
    } finally {
      if (alive.current && token === generation.current) {
        pending.current = false;
        setBusy(false);
      }
    }
  }
  function importMatches(next: RosterEntry[], p: RosterPreview) {
    return p.rows
      .filter((x) => ["create", "enroll", "restore", "skip"].includes(x.action))
      .every((x) =>
        next.some(
          (row) =>
            row.user.email.toLowerCase() === x.email.toLowerCase() &&
            row.user.role === "student",
        ),
      );
  }
  function finishImport(r: RosterResult, next: RosterEntry[]) {
    setResult(r);
    setPreview(null);
    setFile(null);
    setPassword("");
    if (fileInput.current) fileInput.current.value = "";
    setRecovery(null);
    setRows(next);
    setArchived(false);
    setSelected([]);
    setSuccess("Roster import acknowledged and independently verified.");
    onChanged?.();
  }
  async function commit() {
    if (!preview || preview.error_count || pending.current || recovery) return;
    pending.current = true;
    const token = ++generation.current;
    setBusy(true);
    setError("");
    setSuccess("");
    let ackResult: RosterResult | null = null;
    try {
      const r = await api.rosterCommit(courseId, preview.import_id);
      if (!alive.current || token !== generation.current) return;
      const counts = {
        create: r.created,
        enroll: r.enrolled,
        restore: r.restored,
        skip: r.skipped,
      };
      if (
        Object.entries(counts).some(
          ([action, n]) =>
            n !== preview.rows.filter((row) => row.action === action).length,
        )
      )
        throw Error(
          "Roster import acknowledgement did not match review counts.",
        );
      ackResult = r;
      setRecovery({ kind: "import", ackResult });
      const next = await api.roster(courseId, false);
      if (!alive.current || token !== generation.current) return;
      if (!importMatches(next, preview))
        throw Error(
          "Roster import readback did not match all reviewed emails.",
        );
      finishImport(r, next);
    } catch (e) {
      if (!alive.current || token !== generation.current) return;
      if (ackResult || unknownWrite(e)) {
        setRecovery({ kind: "import", ackResult });
        setInspected(false);
        setError(
          `Import outcome needs inspection; review retained. Do not commit again blindly. ${errorMessage(e)}`,
        );
      } else setError(errorMessage(e));
    } finally {
      if (alive.current && token === generation.current) {
        pending.current = false;
        setBusy(false);
      }
    }
  }
  async function inspect() {
    if (!recovery || pending.current) return;
    pending.current = true;
    const token = ++generation.current;
    setBusy(true);
    setError("");
    try {
      if (recovery.kind === "action") {
        const [source, target] = await Promise.all([
          api.roster(courseId, recovery.fromArchived),
          api.roster(courseId, !recovery.fromArchived),
        ]);
        if (!alive.current || token !== generation.current) return;
        const matches =
          !source.some((r) => recovery.ids.includes(r.user.id)) &&
          recovery.ids.every((uid) => target.some((r) => r.user.id === uid));
        if (recovery.ack && matches) {
          setRecovery(null);
          setRows(source);
          setSelected([]);
          setConfirm(false);
          setSuccess("Roster change independently verified.");
          onChanged?.();
        } else {
          setInspected(true);
          setSuccess(
            `${matches ? "Requested roster state is visible." : "Requested roster state is not visible."} The original write is not verified. Review before unlocking the selection.`,
          );
        }
      } else if (preview) {
        const next = await api.roster(courseId, false);
        if (!alive.current || token !== generation.current) return;
        if (recovery.ackResult && importMatches(next, preview))
          finishImport(recovery.ackResult, next);
        else {
          setInspected(true);
          setSuccess(
            `${importMatches(next, preview) ? "All reviewed emails are currently enrolled." : "Some reviewed emails are not enrolled."} The roster API has no import-outcome GET. Original commit is not acknowledged; inspect before deliberately unlocking or discarding this review.`,
          );
        }
      }
    } catch (e) {
      if (alive.current && token === generation.current)
        setError(errorMessage(e));
    } finally {
      if (alive.current && token === generation.current) {
        pending.current = false;
        setBusy(false);
      }
    }
  }
  const locked = busy || loading || !!recovery || provisionHeld;
  return (
    <section className="roster-panel">
      <div className="section-heading">
        <h2>Course Students roster</h2>
        <button
          className="secondary"
          onClick={() => void load()}
          disabled={locked}
        >
          {t("refresh")}
        </button>
      </div>
      <p className="section-intro">
        {courseId
          ? "Course removal affects only this enrollment and its learning records; shared accounts remain active in other courses."
          : "Global archive immediately disables login and revokes sessions. Only student accounts can be selected."}{" "}
        {
          "Archived records can be restored for 30 days, then are purged in the authorized scope."
        }
      </p>
      <ErrorBanner error={error} />
      {success && <Notice>{success}</Notice>}
      {recovery && (
        <div className="am-recovery">
          <button
            className="secondary"
            disabled={busy}
            onClick={() => void inspect()}
          >
            Inspect roster outcome (GET only)
          </button>
          {inspected && (
            <button
              className="secondary"
              disabled={busy}
              onClick={() => {
                if (
                  window.confirm(
                    "Roster inspected. Unlock retained action without automatically retrying?",
                  )
                ) {
                  setRecovery(null);
                  setInspected(false);
                }
              }}
            >
              I reviewed roster — unlock action
            </button>
          )}
        </div>
      )}
      {result && (
        <Notice>
          {"Import committed"} · {"Created"} {result.created} · {"Enrolled"}{" "}
          {result.enrolled} · {"Restored"} {result.restored} · {"Skipped"}{" "}
          {result.skipped}
        </Notice>
      )}
      {courseId && (
        <>
          <fieldset disabled={busy || loading || !!recovery}>
            <ProvisionStudent
              courseId={courseId}
              onHold={setProvisionHeld}
              onCreated={async () => {
                await load();
                onChanged?.();
              }}
            />
          </fieldset>
          <details className="card form-card">
            <summary>{"Import CSV / XLSX roster"}</summary>
            <p>
              {
                "Required columns: name,email; temporary_password is optional if a default is supplied. Existing accounts are enrolled without resetting their names or passwords. Preview never displays passwords."
              }
            </p>
            <a className="text-button" href="/roster-template.csv" download>
              {"Download synthetic CSV template"}
            </a>
            <form onSubmit={(e) => void importPreview(e)}>
              <div className="form-grid">
                <label>
                  {t("chooseFile")}
                  <input
                    type="file"
                    ref={fileInput}
                    disabled={locked || !!preview}
                    aria-label="Roster import file"
                    accept=".csv,.xlsx"
                    required
                    onChange={(e) => {
                      setFile(e.target.files?.[0] || null);
                      setPreview(null);
                    }}
                  />
                </label>
                <label>
                  {"Default temporary password (optional)"}
                  <input
                    type="password"
                    disabled={locked || !!preview}
                    aria-label="Roster default temporary password"
                    autoComplete="new-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </label>
              </div>
              <button
                className="primary"
                disabled={
                  locked ||
                  !!preview ||
                  !file ||
                  (!!password && !passwordValid(password))
                }
              >
                {"Validate and preview"}
              </button>
            </form>
          </details>
        </>
      )}
      {preview && (
        <section className="card form-card">
          <h3>
            {"Import review"} · {preview.valid_count} {"valid"} /{" "}
            {preview.error_count} {"errors"}
          </h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>{t("name")}</th>
                  <th>{t("email")}</th>
                  <th>{"Action"}</th>
                  <th>{"Validation"}</th>
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((r) => (
                  <tr key={r.row_number}>
                    <td>{r.row_number}</td>
                    <td>{r.name}</td>
                    <td>{r.email}</td>
                    <td>
                      {
                        {
                          create: "Create",
                          enroll: "Enroll",
                          restore: "Restore",
                          skip: "Skip",
                          error: "Error",
                        }[r.action]
                      }
                    </td>
                    <td>
                      {r.errors.map((x, i) => (
                        <p className="field-error" key={i}>
                          {x}
                        </p>
                      ))}
                      {r.warnings.map((x, i) => (
                        <p key={i}>{x}</p>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p>
            {
              "Any error blocks the entire commit. Fix the spreadsheet and upload again."
            }
          </p>
          <div className="button-row">
            <button
              className="primary"
              disabled={
                locked || preview.error_count > 0 || preview.valid_count === 0
              }
              onClick={() => void commit()}
            >
              {"Commit reviewed import"}
            </button>
            <button
              className="secondary"
              disabled={locked}
              onClick={() => {
                setPreview(null);
                setFile(null);
                setPassword("");
                if (fileInput.current) fileInput.current.value = "";
              }}
            >
              {t("cancel")}
            </button>
          </div>
        </section>
      )}
      <nav className="tabs">
        <button
          className={!archived ? "active" : ""}
          disabled={locked}
          onClick={() => {
            if (!archived) return;
            setLoading(true);
            setRows([]);
            setSelected([]);
            setArchived(false);
            setConfirm(false);
          }}
        >
          {"Active roster"}
        </button>
        <button
          className={archived ? "active" : ""}
          disabled={locked}
          onClick={() => {
            if (archived) return;
            setLoading(true);
            setRows([]);
            setSelected([]);
            setArchived(true);
            setConfirm(false);
          }}
        >
          {"Recycle bin"}
        </button>
      </nav>
      <div className="section-heading">
        <label className="inline-check">
          <input
            type="checkbox"
            checked={rows.length > 0 && selected.length === rows.length}
            disabled={locked}
            onChange={(e) =>
              setSelected(e.target.checked ? rows.map((r) => r.user.id) : [])
            }
          />
          {"Select all"}
        </label>
        <button
          className="secondary"
          disabled={locked || !selected.length}
          onClick={() => setConfirm(true)}
        >
          {archived ? "Restore selected" : "Archive selected"} (
          {selected.length})
        </button>
      </div>
      {confirm && (
        <div className="notice confirmation">
          <p>
            {archived
              ? "Restore the selected students and cancel their purge deadlines?"
              : courseId
                ? "Remove these students only from this course, retaining records for 30 days?"
                : "Disable these student accounts globally and retain their records for 30 days?"}
          </p>
          <button
            className="primary"
            disabled={locked}
            onClick={() => void act()}
          >
            {archived ? "Confirm restore" : "Confirm archive"}
          </button>
          <button
            className="secondary"
            disabled={locked}
            onClick={() => setConfirm(false)}
          >
            {t("cancel")}
          </button>
        </div>
      )}
      {loading ? (
        <Loading />
      ) : !rows.length ? (
        <Empty title={"No students in this list"} />
      ) : (
        <div className="table-wrap card">
          <table>
            <thead>
              <tr>
                <th />
                <th>{t("student")}</th>
                <th>{"Learning records"}</th>
                {archived && <th>{"Time until purge"}</th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.user.id}>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={r.user.email}
                      disabled={locked}
                      checked={selected.includes(r.user.id)}
                      onChange={(e) =>
                        setSelected((s) =>
                          e.target.checked
                            ? [...s, r.user.id]
                            : s.filter((x) => x !== r.user.id),
                        )
                      }
                    />
                  </td>
                  <td>
                    <strong>{r.user.name}</strong>
                    <small className="block">{r.user.email}</small>
                    {r.user.must_change_password && (
                      <small>{t("firstPasswordPending")}</small>
                    )}
                  </td>
                  <td>
                    {r.has_work ? "Saved work retained" : "No saved work"}
                  </td>
                  {archived && (
                    <td>
                      <span className="retention-countdown">
                        {retentionText(r.purge_at, now).replace("d ·", "d ·")}
                      </span>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
