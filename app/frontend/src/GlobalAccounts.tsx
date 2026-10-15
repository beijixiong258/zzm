import { useEffect, useState } from "react";
import type { Role, User } from "./types";
import type {
  AccountDetail,
  AccountFilters,
  AccountPage,
} from "./account-management-types";
import { accountApi } from "./account-management-api";
import {
  roleLabel,
  unknownWrite,
  useAccountLane,
} from "./account-management-state";
import {
  AccountImport,
  CreateAccount,
  RoleOptions,
} from "./GlobalAccountForms";
import { GlobalCourseAssignments } from "./CourseStaff";
import { confirmNavigation, useUnsavedChanges } from "./navigation-guard";
import { ErrorBanner, Loading } from "./ui";
import { AccountNotice as Notice } from "./account-management-ui";
import "./account-management.css";
type Edit = { kind: "role"; role: Role } | { kind: "status"; active: boolean };
function editMatches(a: AccountDetail, uid: string, edit: Edit) {
  return (
    a.user.id === uid &&
    (edit.kind === "role"
      ? a.user.role === edit.role
      : a.active === edit.active)
  );
}
function AccountEditor({
  actor,
  uid,
  onChanged,
  onCourse,
  onHold,
  assignmentsHeld,
}: {
  actor: User;
  uid: string;
  onChanged: () => void;
  onCourse: (cid: string) => void;
  onHold: (hold: boolean) => void;
  assignmentsHeld: boolean;
}) {
  const lane = useAccountLane(),
    [data, setData] = useState<AccountDetail | null>(null),
    [role, setRole] = useState<Role>("student"),
    [confirm, setConfirm] = useState<Edit | null>(null);
  const [recovery, setRecovery] = useState<{ edit: Edit; ack: boolean } | null>(
      null,
    ),
    [inspected, setInspected] = useState(false);
  const dirty = !!data && role !== data.user.role;
  useUnsavedChanges(dirty || !!confirm || lane.busy || !!recovery);
  useEffect(() => {
    onHold(lane.busy || !!recovery);
    return () => onHold(false);
  }, [lane.busy, recovery, onHold]);
  async function load(initial = false) {
    await lane.run(async (current) => {
      const a = await accountApi.get(uid);
      if (!current()) return;
      if (a.user.id !== uid)
        throw Error("Account detail returned another person.");
      setData(a);
      if (initial) setRole(a.user.role);
    });
  }
  useEffect(() => {
    void load(true);
  }, []);
  async function apply() {
    if (!confirm || recovery || actor.id === uid) return;
    await lane.run(async (current) => {
      let ack = false;
      try {
        const result = await (confirm.kind === "role"
          ? accountApi.role(uid, confirm.role)
          : accountApi.status(uid, confirm.active));
        if (!current()) return;
        const valid =
          result.user.id === uid &&
          (confirm.kind === "role"
            ? result.user.role === confirm.role
            : "active" in result && result.active === confirm.active);
        if (!valid)
          throw Error("Account mutation acknowledgement did not match.");
        ack = true;
        setRecovery({ edit: confirm, ack });
        const fresh = await accountApi.get(uid);
        if (!current()) return;
        if (!editMatches(fresh, uid, confirm))
          throw Error("Independent account readback did not match.");
        setData(fresh);
        if (confirm.kind === "role") setRole(fresh.user.role);
        setConfirm(null);
        setRecovery(null);
        lane.setNotice(
          "Account change acknowledged and independently verified.",
        );
        onChanged();
      } catch (e) {
        if (!current()) return;
        if (ack || unknownWrite(e)) {
          setRecovery({ edit: confirm, ack });
          setInspected(false);
          throw Error(
            `Account outcome needs inspection. Draft retained; no automatic retry. ${e instanceof Error ? e.message : ""}`,
          );
        }
        throw e;
      }
    });
  }
  async function inspect() {
    if (!recovery) return;
    await lane.run(async (current) => {
      const fresh = await accountApi.get(uid);
      if (!current()) return;
      if (fresh.user.id !== uid)
        throw Error("Inspection returned another person.");
      setData(fresh);
      if (recovery.ack && editMatches(fresh, uid, recovery.edit)) {
        if (recovery.edit.kind === "role") setRole(fresh.user.role);
        setConfirm(null);
        setRecovery(null);
        lane.setNotice("Account change independently verified.");
        onChanged();
      } else {
        setInspected(true);
        lane.setNotice(
          `${editMatches(fresh, uid, recovery.edit) ? "The requested state is visible." : "The requested state is not visible."} The original write is not verified. Review saved values before unlocking the retained action.`,
        );
      }
    });
  }
  const locked = lane.busy || !!recovery,
    self = actor.id === uid;
  return (
    <section className="card form-card am-account-detail" aria-busy={lane.busy}>
      <h3>Selected account</h3>
      <ErrorBanner error={lane.error} />
      {lane.notice && <Notice>{lane.notice}</Notice>}
      {!data ? (
        lane.busy ? (
          <Loading />
        ) : (
          <button className="secondary" onClick={() => void load(true)}>
            Retry account detail
          </button>
        )
      ) : (
        <>
          <h4>{data.user.name}</h4>
          <p>
            {data.user.email} · Saved role: {roleLabel(data.user.role)} ·{" "}
            {data.active ? "Active" : "Disabled"}
          </p>
          <p>
            {data.assigned_course_count} course assignments ·{" "}
            {data.owned_course_count} primary responsibilities
          </p>
          {data.purge_at && (
            <p className="notice">
              Existing retention deadline: {data.purge_at}. Global disabling
              adds no new purge deadline; explicit restoration cancels the
              applicable account deadline.
            </p>
          )}
          {self && (
            <p className="notice">
              You cannot change your own global role or disable your own
              account. Another active administrator must manage this account.
            </p>
          )}
          <label>
            New global role
            <select
              aria-label="New global role"
              disabled={locked || self}
              value={role}
              onChange={(e) => {
                setRole(e.target.value as Role);
                setConfirm(null);
              }}
            >
              <RoleOptions />
            </select>
          </label>
          <p>
            Changing role revokes this person's sessions. It does not reset
            passwords or transfer course ownership. Staff-to-Student requires
            explicit removal of all staff assignments after primary transfers.
            Student-to-staff still needs an explicit course assignment.
          </p>
          <div className="button-row">
            <button
              className="primary"
              disabled={locked || self || !dirty}
              onClick={() => setConfirm({ kind: "role", role })}
            >
              Change global role
            </button>
            <button
              className="secondary"
              disabled={locked || self}
              onClick={() =>
                setConfirm({ kind: "status", active: !data.active })
              }
            >
              {data.active ? "Disable account" : "Restore account"}
            </button>
            <button
              className="secondary"
              disabled={lane.busy}
              onClick={() => void load()}
            >
              Reload account, keep draft
            </button>
            {dirty && !locked && (
              <button
                className="text-button"
                onClick={() => {
                  setRole(data.user.role);
                  setConfirm(null);
                }}
              >
                Discard role draft
              </button>
            )}
          </div>
          <p>
            Disabling is reversible, revokes sessions and does not permanently
            delete the account. The last usable active administrator and every
            course's last active manager are protected by the server.
          </p>
          {confirm && (
            <div className="notice confirmation">
              <p>
                {confirm.kind === "role"
                  ? `Change ${data.user.email} to ${roleLabel(confirm.role)}?`
                  : confirm.active
                    ? `Restore ${data.user.email}?`
                    : `Disable ${data.user.email} globally? This affects sign-in, not just one course.`}
              </p>
              <div className="button-row">
                <button
                  className="primary"
                  disabled={locked || self}
                  onClick={() => void apply()}
                >
                  {confirm.kind === "role"
                    ? "Confirm role change"
                    : confirm.active
                      ? "Confirm account restore"
                      : "Confirm account disable"}
                </button>
                <button
                  className="secondary"
                  disabled={locked}
                  onClick={() => setConfirm(null)}
                >
                  Cancel account action
                </button>
              </div>
            </div>
          )}
          {recovery && (
            <div className="am-recovery">
              <button
                className="secondary"
                disabled={lane.busy}
                onClick={() => void inspect()}
              >
                Inspect account outcome (GET only)
              </button>
              {inspected && (
                <button
                  className="secondary"
                  disabled={lane.busy}
                  onClick={() => {
                    if (
                      window.confirm(
                        "Saved account values inspected. Unlock the retained action without retrying?",
                      )
                    ) {
                      setRecovery(null);
                      setInspected(false);
                    }
                  }}
                >
                  I reviewed the account — unlock action
                </button>
              )}
            </div>
          )}
          <h4>Manage assignments before role or status changes</h4>
          <p>
            For a primary/last-manager conflict: add another active Admin or
            Teacher, make that person primary, then explicitly remove this
            person's assignment if changing to Student. Refresh this account and
            confirm the retained role/status action.
          </p>
          <ul className="am-people">
            {data.staff_courses.map((c) => (
              <li key={c.id}>
                <span>
                  {c.code} · {c.title}
                  {c.trashed_at ? " (in trash)" : ""}
                  {c.owner_id === uid ? " · Primary manager" : ""}
                </span>
                <button
                  className="secondary"
                  disabled={assignmentsHeld}
                  onClick={() => onCourse(c.id)}
                >
                  Manage staff for {c.code}
                </button>
              </li>
            ))}
          </ul>
          <button
            className="secondary"
            disabled={assignmentsHeld}
            onClick={() => onCourse("")}
          >
            Open all-course staff assignments
          </button>
        </>
      )}
    </section>
  );
}
export default function GlobalAccounts({
  user,
  onChanged,
}: {
  user: User;
  onChanged?: () => void;
}) {
  if (user.role !== "admin")
    return <p>Global account administration requires an administrator.</p>;
  return (
    <AccountsPanel
      key={`${user.id}:${user.role}`}
      user={user}
      onChanged={onChanged}
    />
  );
}
function AccountsPanel({
  user,
  onChanged,
}: {
  user: User;
  onChanged?: () => void;
}) {
  const lane = useAccountLane(),
    [page, setPage] = useState<AccountPage | null>(null),
    [filters, setFilters] = useState<AccountFilters>({ offset: 0, limit: 50 }),
    [q, setQ] = useState(""),
    [selected, setSelected] = useState(""),
    [held, setHeld] = useState(false),
    [course, setCourse] = useState(""),
    [courseHeld, setCourseHeld] = useState(false);
  async function load() {
    await lane.run(async (current) => {
      setPage(null);
      const next = await accountApi.list(filters);
      if (!current()) return;
      if (
        next.offset !== (filters.offset ?? 0) ||
        next.limit !== (filters.limit ?? 50)
      )
        throw Error("Account page did not match the requested range.");
      if (next.total > 0 && !next.items.length && next.offset > 0) {
        setFilters({ ...filters, offset: 0 });
        return;
      }
      setPage(next);
    });
  }
  useEffect(() => {
    void load();
  }, [filters]);
  const changed = () => {
    void load();
    onChanged?.();
  };
  function changeFilters(patch: AccountFilters) {
    if (held || lane.busy || !confirmNavigation()) return;
    setSelected("");
    setPage(null);
    setFilters({ ...filters, ...patch });
  }
  function selectCourse(cid: string) {
    if (courseHeld) return;
    setCourse(cid);
    requestAnimationFrame(() =>
      document
        .getElementById("global-course-assignments")
        ?.scrollIntoView({ behavior: "smooth", block: "start" }),
    );
  }
  return (
    <div className="account-management">
      <section className="am-account-index">
        <h2>Global User Accounts</h2>
        <p>
          One platform account, one current global role. Account powers and
          course staff assignments are separate. Global imports create or skip
          accounts; they never bulk-change existing roles or passwords.
        </p>
        <div className="am-two-column">
          <CreateAccount onChanged={changed} />
          <AccountImport onChanged={changed} />
        </div>
        <form
          className="am-filter"
          onSubmit={(e) => {
            e.preventDefault();
            changeFilters({ q: q.trim(), offset: 0 });
          }}
        >
          <fieldset disabled={lane.busy || held}>
            <div className="am-fields">
              <label>
                Search global accounts
                <input
                  aria-label="Search global accounts"
                  placeholder="Name or email"
                  maxLength={200}
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                />
              </label>
              <label>
                Filter global role
                <select
                  aria-label="Filter global role"
                  value={filters.role ?? ""}
                  onChange={(e) =>
                    changeFilters({
                      role: (e.target.value || undefined) as Role | undefined,
                      offset: 0,
                    })
                  }
                >
                  <option value="">All roles</option>
                  <RoleOptions />
                </select>
              </label>
              <label>
                Filter account status
                <select
                  aria-label="Filter account status"
                  value={
                    filters.active === undefined ? "" : String(filters.active)
                  }
                  onChange={(e) =>
                    changeFilters({
                      active:
                        e.target.value === ""
                          ? undefined
                          : e.target.value === "true",
                      offset: 0,
                    })
                  }
                >
                  <option value="">All statuses</option>
                  <option value="true">Active</option>
                  <option value="false">Disabled</option>
                </select>
              </label>
              <label>
                Accounts per page
                <select
                  aria-label="Accounts per page"
                  value={filters.limit}
                  onChange={(e) =>
                    changeFilters({ limit: Number(e.target.value), offset: 0 })
                  }
                >
                  <option value="10">10</option>
                  <option value="50">50</option>
                  <option value="100">100</option>
                </select>
              </label>
            </div>
            <div className="button-row">
              <button className="primary">Search accounts</button>
              <button
                type="button"
                className="secondary"
                onClick={() => void load()}
              >
                Refresh global accounts
              </button>
            </div>
          </fieldset>
        </form>
        <ErrorBanner error={lane.error} />
        {lane.busy ? (
          <Loading />
        ) : (
          page && (
            <>
              <p role="status">
                {page.total
                  ? `${page.offset + 1}–${page.offset + page.items.length} of ${page.total} accounts`
                  : "0 accounts"}
              </p>
              <ul className="am-people am-account-list">
                {page.items.map((a) => (
                  <li key={a.user.id}>
                    <div>
                      <strong>{a.user.name}</strong>
                      <small className="block">
                        {a.user.email} · {roleLabel(a.user.role)} ·{" "}
                        {a.active ? "Active" : "Disabled"}
                      </small>
                      <small>
                        {a.assigned_course_count} staff assignments ·{" "}
                        {a.owned_course_count} primary responsibilities
                      </small>
                    </div>
                    <button
                      className="secondary"
                      aria-pressed={selected === a.user.id}
                      disabled={held}
                      onClick={() => {
                        if (selected !== a.user.id && confirmNavigation())
                          setSelected(a.user.id);
                      }}
                    >
                      Manage account: {a.user.name}
                    </button>
                  </li>
                ))}
              </ul>
              <div className="button-row">
                <button
                  className="secondary"
                  disabled={held || page.offset === 0}
                  onClick={() =>
                    changeFilters({
                      offset: Math.max(0, page.offset - page.limit),
                    })
                  }
                >
                  Previous accounts
                </button>
                <button
                  className="secondary"
                  disabled={
                    held || page.offset + page.items.length >= page.total
                  }
                  onClick={() =>
                    changeFilters({ offset: page.offset + page.limit })
                  }
                >
                  Next accounts
                </button>
              </div>
            </>
          )
        )}
        {selected && (
          <AccountEditor
            key={`${user.id}:${selected}`}
            actor={user}
            uid={selected}
            onChanged={changed}
            onCourse={selectCourse}
            onHold={setHeld}
            assignmentsHeld={courseHeld}
          />
        )}
      </section>
      <GlobalCourseAssignments
        user={user}
        selectedCourse={course}
        onHold={setCourseHeld}
        onSelect={(cid) => {
          if (confirmNavigation()) selectCourse(cid);
        }}
        onChanged={changed}
      />
    </div>
  );
}
