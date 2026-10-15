import { useRef, useState, type FormEvent } from "react";
import { accountApi } from "./account-management-api";
import {
  createdMatches,
  importFileError,
  importResultValid,
  importReadbackMatches,
  importPreviewMatches,
  passwordValid,
  roleLabel,
  roles,
  unknownWrite,
  useAccountLane,
} from "./account-management-state";
import type {
  AccountCreate,
  AccountImportPreview,
  AccountImportResult,
} from "./account-management-types";
import type { Role } from "./types";
import { useUnsavedChanges } from "./navigation-guard";
import { ErrorBanner } from "./ui";
import { AccountNotice as Notice } from "./account-management-ui";
export const passwordHelp =
  "8–512 characters, including an ASCII letter and a digit. The person must change this temporary password at first sign-in.";
export function RoleOptions() {
  return (
    <>
      {roles.map((role) => (
        <option key={role} value={role}>
          {roleLabel(role)}
        </option>
      ))}
    </>
  );
}
export function CreateAccount({ onChanged }: { onChanged: () => void }) {
  const lane = useAccountLane();
  const [draft, setDraft] = useState<AccountCreate>({
    name: "",
    email: "",
    role: "student",
    temporary_password: "",
  });
  const [attempt, setAttempt] = useState<{
    id: string | null;
    acknowledged: boolean;
  } | null>(null);
  const [inspected, setInspected] = useState(false);
  useUnsavedChanges(
    !!draft.name ||
      !!draft.email ||
      !!draft.temporary_password ||
      draft.role !== "student" ||
      lane.busy ||
      !!attempt,
  );
  const blocked = lane.busy || !!attempt;
  const change = (patch: Partial<AccountCreate>) => {
    setDraft({ ...draft, ...patch });
    lane.setNotice("");
  };
  function complete() {
    setDraft({ name: "", email: "", role: "student", temporary_password: "" });
    setAttempt(null);
    lane.setNotice("Account created and independently verified.");
    onChanged();
  }
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (attempt || !passwordValid(draft.temporary_password)) return;
    await lane.run(async (current) => {
      let recovery = { id: null as string | null, acknowledged: false };
      try {
        const ack = await accountApi.create({
          ...draft,
          name: draft.name.trim(),
          email: draft.email.trim(),
        });
        if (!current()) return;
        recovery = {
          id: ack.user.id || null,
          acknowledged: createdMatches(ack.user, draft),
        };
        setAttempt(recovery);
        if (!recovery.acknowledged)
          throw Error(
            "Creation acknowledgement did not match the submitted account.",
          );
        const fresh = await accountApi.get(ack.user.id);
        if (!current()) return;
        if (
          fresh.user.id !== ack.user.id ||
          !createdMatches(fresh.user, draft) ||
          !fresh.active
        )
          throw Error("Account readback did not match the creation.");
        complete();
      } catch (e) {
        if (!current()) return;
        if (recovery.acknowledged || unknownWrite(e)) {
          setAttempt(recovery);
          setInspected(false);
          throw Error(
            `${recovery.acknowledged ? "Creation accepted, but readback is incomplete." : "Creation outcome is unknown."} Your draft is retained. Inspect before any new write. ${e instanceof Error ? e.message : ""}`,
          );
        }
        throw e;
      }
    });
  }
  async function inspect() {
    if (!attempt) return;
    await lane.run(async (current) => {
      if (attempt.id) {
        const fresh = await accountApi.get(attempt.id);
        if (!current()) return;
        if (fresh.user.id !== attempt.id)
          throw Error("Creation inspection returned another account.");
        if (!createdMatches(fresh.user, draft) || !fresh.active) {
          setInspected(true);
          lane.setNotice(
            `Inspection found ${fresh.user.email} (${roleLabel(fresh.user.role)}, ${fresh.active ? "active" : "disabled"}), which differs from the retained creation draft. The original write is not verified in the current state. Review this account in the global list before explicitly unlocking or discarding the draft.`,
          );
          onChanged();
          return;
        }
        if (attempt.acknowledged) {
          complete();
          return;
        }
      } else {
        const matches = await accountApi.list({
          q: draft.email.trim(),
          limit: 100,
        });
        if (!current()) return;
        const exact = matches.items.find(
          (a) =>
            a.user.email.toLowerCase() === draft.email.trim().toLowerCase(),
        );
        if (exact) {
          const fresh = await accountApi.get(exact.user.id);
          if (!current()) return;
          lane.setNotice(
            `Inspection found ${fresh.user.email} (${roleLabel(fresh.user.role)}, ${fresh.active ? "active" : "disabled"}). The original creation was not acknowledged; inspect this account before deciding to discard or retry.`,
          );
        } else
          lane.setNotice(
            "No exact email found in the current account index. This is not proof that the unknown write failed. Check again before an explicit retry.",
          );
      }
      setInspected(true);
      onChanged();
    });
  }
  return (
    <section className="card form-card am-create" aria-busy={lane.busy}>
      <h3>Create account</h3>
      <p>
        Global role grants no automatic course assignment. Share the temporary
        password privately; it is kept only in this form's memory.
      </p>
      <ErrorBanner error={lane.error} />
      {lane.notice && <Notice>{lane.notice}</Notice>}
      <form onSubmit={(e) => void submit(e)}>
        <fieldset disabled={blocked}>
          <div className="am-fields">
            <label>
              Account name
              <input
                aria-label="Account name"
                required
                maxLength={100}
                value={draft.name}
                onChange={(e) => change({ name: e.target.value })}
              />
            </label>
            <label>
              Account email
              <input
                aria-label="Account email"
                type="email"
                required
                maxLength={254}
                value={draft.email}
                onChange={(e) => change({ email: e.target.value })}
              />
            </label>
            <label>
              New account role
              <select
                aria-label="New account role"
                value={draft.role}
                onChange={(e) => change({ role: e.target.value as Role })}
              >
                <RoleOptions />
              </select>
            </label>
            <label>
              Temporary password
              <input
                aria-label="Temporary password"
                type="password"
                autoComplete="new-password"
                required
                value={draft.temporary_password}
                onChange={(e) => change({ temporary_password: e.target.value })}
              />
              <small>{passwordHelp}</small>
            </label>
          </div>
          <button
            className="primary"
            disabled={
              !draft.name.trim() ||
              !draft.email.trim() ||
              !passwordValid(draft.temporary_password)
            }
          >
            Create account
          </button>
        </fieldset>
      </form>
      {attempt && (
        <div className="am-recovery">
          <p>Writes are paused. No automatic retry will be made.</p>
          <button
            className="secondary"
            disabled={lane.busy}
            onClick={() => void inspect()}
          >
            Inspect creation outcome (GET only)
          </button>
          {inspected && (
            <button
              className="secondary"
              disabled={lane.busy}
              onClick={() => {
                if (
                  window.confirm(
                    "I have inspected the account index. Unlock the retained draft for a deliberate new attempt? This does not retry automatically.",
                  )
                ) {
                  setAttempt(null);
                  setInspected(false);
                }
              }}
            >
              I reviewed the outcome — unlock draft
            </button>
          )}
        </div>
      )}
      {!blocked &&
        (draft.name ||
          draft.email ||
          draft.temporary_password ||
          draft.role !== "student") && (
          <button
            className="text-button"
            onClick={() => {
              if (
                window.confirm(
                  "Discard the account draft and temporary password?",
                )
              )
                setDraft({
                  name: "",
                  email: "",
                  role: "student",
                  temporary_password: "",
                });
            }}
          >
            Discard account draft
          </button>
        )}
    </section>
  );
}
export function AccountImport({ onChanged }: { onChanged: () => void }) {
  const lane = useAccountLane(),
    fileInput = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null),
    [role, setRole] = useState<Role>("student"),
    [password, setPassword] = useState("");
  const [preview, setPreview] = useState<AccountImportPreview | null>(null),
    [unresolved, setUnresolved] = useState(false),
    [result, setResult] = useState<AccountImportResult | null>(null);
  useUnsavedChanges(
    !!file || !!password || !!preview || lane.busy || unresolved,
  );
  function reset() {
    setPreview(null);
    setFile(null);
    setPassword("");
    setUnresolved(false);
    if (fileInput.current) fileInput.current.value = "";
  }
  async function validate(e: FormEvent) {
    e.preventDefault();
    if (!file || unresolved) return;
    const error = importFileError(file);
    if (error) {
      lane.setError(error);
      return;
    }
    await lane.run(async (current) => {
      const p = await accountApi.preview(file, role, password);
      if (!current()) return;
      setPreview(p);
      setPassword("");
      setResult(null);
    });
  }
  async function verify(
    r: AccountImportResult,
    p: AccountImportPreview,
    current: () => boolean,
  ) {
    if (!importResultValid(r, p))
      throw Error(
        "Import acknowledgement counts or account IDs do not match the reviewed rows.",
      );
    const accounts: Awaited<ReturnType<typeof accountApi.get>>[] = [];
    for (let offset = 0; offset < r.user_ids.length; offset += 10) {
      accounts.push(
        ...(await Promise.all(
          r.user_ids
            .slice(offset, offset + 10)
            .map((uid) => accountApi.get(uid)),
        )),
      );
      if (!current()) return;
    }
    if (!importReadbackMatches(accounts, r, p))
      throw Error(
        "Imported accounts could not all be verified by independent GET.",
      );
    setResult(r);
    reset();
    lane.setNotice("Import committed atomically and independently verified.");
    onChanged();
  }
  async function commit() {
    if (!preview || preview.error_count || unresolved) return;
    await lane.run(async (current) => {
      let ack = false;
      try {
        const r = await accountApi.commit(preview.import_id);
        ack = true;
        if (!current()) return;
        setUnresolved(true);
        await verify(r, preview, current);
      } catch (e) {
        if (!current()) return;
        if (ack || unknownWrite(e)) {
          setUnresolved(true);
          throw Error(
            `Import outcome needs readback. The review is retained; do not upload or commit again. ${e instanceof Error ? e.message : ""}`,
          );
        }
        throw e;
      }
    });
  }
  async function recover() {
    if (!preview) return;
    await lane.run(async (current) => {
      const state = await accountApi.importState(preview.import_id);
      if (!current()) return;
      if (!importPreviewMatches(state.preview, preview))
        throw Error("Import recovery returned a different preview.");
      if (state.status === "committed" && state.result)
        await verify(state.result, preview, current);
      else {
        setUnresolved(false);
        lane.setNotice(
          "The server reports this preview is pending. Review it again; only an explicit Commit action will write.",
        );
      }
    });
  }
  return (
    <section className="card form-card am-import" aria-busy={lane.busy}>
      <h3>Import global accounts — CSV / XLSX</h3>
      <p>
        Columns: name,email; optional role,temporary_password. Each row's role
        overrides the default. Default role is Student. Existing same-role
        accounts are skipped without changing their names, roles or passwords. A
        differing role is an error: change it explicitly in the account list.
      </p>
      <p>
        CSV and XLSX: 2 MiB. Up to 1,000 rows; server checks expanded XLSX
        size. Any error blocks the entire commit. Passwords never appear in the
        review.
      </p>
      <ErrorBanner error={lane.error} />
      {lane.notice && <Notice>{lane.notice}</Notice>}
      {result && (
        <Notice>
          Created {result.created} · Skipped {result.skipped} · Verified
          accounts {result.user_ids.length}
        </Notice>
      )}
      <form onSubmit={(e) => void validate(e)}>
        <fieldset disabled={lane.busy || unresolved || !!preview}>
          <div className="am-fields">
            <label>
              Account import file
              <input
                aria-label="Account import file"
                ref={fileInput}
                type="file"
                required
                accept=".csv,.xlsx"
                onChange={(e) => {
                  setFile(e.target.files?.[0] ?? null);
                  setResult(null);
                }}
              />
            </label>
            <label>
              Default import role
              <select
                aria-label="Default import role"
                value={role}
                onChange={(e) => setRole(e.target.value as Role)}
              >
                <RoleOptions />
              </select>
            </label>
            <label>
              Default temporary password (optional)
              <input
                aria-label="Default temporary password (optional)"
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <small>{passwordHelp}</small>
            </label>
          </div>
          <button
            className="primary"
            disabled={!file || (!!password && !passwordValid(password))}
          >
            Validate account import
          </button>
        </fieldset>
      </form>
      {preview && (
        <>
          <h4>
            Account import review · {preview.valid_count} valid /{" "}
            {preview.error_count} errors
          </h4>
          <p className="settings-helper">
            On narrow screens, scroll this review horizontally to inspect every
            column before committing.
          </p>
          <div
            className="table-wrap"
            tabIndex={0}
            aria-label="Account import review table"
          >
            <table>
              <thead>
                <tr>
                  <th>Row</th>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Action</th>
                  <th>Validation</th>
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((r) => (
                  <tr key={r.row_number}>
                    <td>{r.row_number}</td>
                    <td>{r.name}</td>
                    <td>{r.email}</td>
                    <td>{roleLabel(r.role)}</td>
                    <td>{r.action}</td>
                    <td>
                      {r.errors.map((x, i) => (
                        <p className="field-error" key={`e${i}`}>
                          {x}
                        </p>
                      ))}
                      {r.warnings.map((x, i) => (
                        <p key={`w${i}`}>{x}</p>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="button-row">
            <button
              className="primary"
              disabled={
                lane.busy ||
                unresolved ||
                !!preview.error_count ||
                !preview.valid_count
              }
              onClick={() => void commit()}
            >
              Commit reviewed accounts
            </button>
            {!unresolved && (
              <button
                className="secondary"
                disabled={lane.busy}
                onClick={() => {
                  setPreview(null);
                  setResult(null);
                }}
              >
                Revise import file
              </button>
            )}
          </div>
        </>
      )}
      {unresolved && (
        <div className="am-recovery">
          <p>
            Commit may already have completed. This button only reads the exact
            saved import and its account IDs.
          </p>
          <button
            className="secondary"
            disabled={lane.busy}
            onClick={() => void recover()}
          >
            Check import outcome (GET only)
          </button>
        </div>
      )}
      {!lane.busy && !unresolved && (file || preview || password) && (
        <button
          className="text-button"
          onClick={() => {
            if (window.confirm("Discard this import draft?")) reset();
          }}
        >
          Discard account import
        </button>
      )}
    </section>
  );
}
