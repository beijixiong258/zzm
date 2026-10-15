import { useEffect, useState } from "react";
import type { Role, User } from "./types";
import type {
  AccountPage,
  CourseBrief,
  StaffResponse,
} from "./account-management-types";
import { accountApi } from "./account-management-api";
import {
  roleLabel,
  staffMatches,
  unknownWrite,
  useAccountLane,
  type StaffAction,
} from "./account-management-state";
import { useUnsavedChanges } from "./navigation-guard";
import { ErrorBanner, Loading } from "./ui";
import { AccountNotice as Notice } from "./account-management-ui";
export default function CourseStaff({
  user,
  courseId,
  onChanged,
  onHold,
}: {
  user: User;
  courseId: string;
  onChanged?: () => void;
  onHold?: (held: boolean) => void;
}) {
  if (user.role === "student")
    return <p>Course staff metadata is available only to assigned staff.</p>;
  return (
    <StaffPanel
      key={`${user.id}:${user.role}:${courseId}`}
      {...{ user, courseId, onChanged, onHold }}
    />
  );
}
function StaffPanel({
  user,
  courseId,
  onChanged,
  onHold,
}: {
  user: User;
  courseId: string;
  onChanged?: () => void;
  onHold?: (held: boolean) => void;
}) {
  const lane = useAccountLane();
  const [data, setData] = useState<StaffResponse | null>(null),
    [action, setAction] = useState<StaffAction | null>(null);
  const [recovery, setRecovery] = useState<{
      action: StaffAction;
      ack: boolean;
    } | null>(null),
    [inspected, setInspected] = useState(false);
  const [q, setQ] = useState(""),
    [candidateRole, setCandidateRole] = useState<Role>("teacher"),
    [candidates, setCandidates] = useState<AccountPage | null>(null);
  const admin = user.role === "admin";
  useUnsavedChanges(lane.busy || !!action || !!recovery);
  useEffect(() => {
    onHold?.(lane.busy || !!recovery);
    return () => onHold?.(false);
  }, [lane.busy, recovery, onHold]);
  const load = () =>
    lane.run(async (current) => {
      const fresh = await accountApi.staff(courseId);
      if (!current()) return;
      if (fresh.course.id !== courseId)
        throw Error("Staff readback returned another course.");
      setData(fresh);
    });
  useEffect(() => {
    void load();
  }, []);
  async function search(offset = 0) {
    await lane.run(async (current) => {
      setCandidates(null);
      const p = await accountApi.list({
        q: q.trim(),
        role: candidateRole,
        active: true,
        offset,
        limit: 10,
      });
      if (current()) setCandidates(p);
    });
  }
  async function mutate() {
    if (!admin || !action || recovery) return;
    await lane.run(async (current) => {
      let ack = false;
      try {
        const result = await (action.kind === "add"
          ? accountApi.addStaff(courseId, action.uid)
          : action.kind === "remove"
            ? accountApi.removeStaff(courseId, action.uid)
            : accountApi.primary(courseId, action.uid));
        if (!current()) return;
        if (!staffMatches(result, courseId, action))
          throw Error("Staff mutation acknowledgement did not match.");
        ack = true;
        setRecovery({ action, ack });
        const fresh = await accountApi.staff(courseId);
        if (!current()) return;
        if (!staffMatches(fresh, courseId, action))
          throw Error("Independent staff readback did not match.");
        setData(fresh);
        setAction(null);
        setRecovery(null);
        setCandidates(null);
        lane.setNotice(
          "Course staff change acknowledged and independently verified.",
        );
        onChanged?.();
      } catch (e) {
        if (!current()) return;
        if (ack || unknownWrite(e)) {
          setRecovery({ action, ack });
          setInspected(false);
          throw Error(
            `Staff outcome needs inspection. Action retained; no automatic retry. ${e instanceof Error ? e.message : ""}`,
          );
        }
        throw e;
      }
    });
  }
  async function inspect() {
    if (!recovery) return;
    await lane.run(async (current) => {
      const fresh = await accountApi.staff(courseId);
      if (!current()) return;
      if (fresh.course.id !== courseId)
        throw Error("Staff inspection returned another course.");
      setData(fresh);
      if (recovery.ack && staffMatches(fresh, courseId, recovery.action)) {
        setRecovery(null);
        setAction(null);
        setCandidates(null);
        lane.setNotice("Course staff change independently verified.");
        onChanged?.();
      } else {
        setInspected(true);
        lane.setNotice(
          `${staffMatches(fresh, courseId, recovery.action) ? "The requested state is visible." : "The requested state is not visible."} The original write is not verified. Review current staff before unlocking the retained action.`,
        );
      }
    });
  }
  const locked = lane.busy || !!recovery;
  const activeStaff =
    data?.staff.filter(
      (m) => m.active && ["admin", "teacher"].includes(m.user.role),
    ) ?? [];
  return (
    <section className="card form-card am-staff" aria-busy={lane.busy}>
      <div className="section-heading">
        <h3>Course staff</h3>
        <button
          className="secondary"
          disabled={lane.busy}
          onClick={() => void load()}
        >
          Refresh course staff
        </button>
      </div>
      <p>
        {admin
          ? "Assignments are explicit. Global account administration alone does not grant teaching access. Transfer the primary manager before removing, disabling or changing that person's role to Student."
          : "Your assigned course colleagues are shown here. Staff assignments and global account roles can only be changed by an administrator."}
      </p>
      <ErrorBanner error={lane.error} />
      {lane.notice && <Notice>{lane.notice}</Notice>}
      {!data ? (
        lane.busy ? (
          <Loading />
        ) : (
          <p>Course staff could not be loaded. Refresh to try again.</p>
        )
      ) : (
        <>
          <p>
            <strong>
              {data.course.code} · {data.course.title}
            </strong>
            {data.course.trashed_at && " · Course in trash"}
          </p>
          <ul className="am-people">
            {data.staff.map((member) => (
              <li key={member.user.id}>
                <div>
                  <strong>{member.user.name}</strong>
                  <small className="block">
                    {member.user.email} · {roleLabel(member.user.role)} ·{" "}
                    {member.active ? "Active" : "Disabled"}
                  </small>
                  {member.is_primary && (
                    <span className="am-tag">Primary manager</span>
                  )}
                </div>
                {admin && (
                  <div className="button-row">
                    {!member.is_primary &&
                      member.active &&
                      ["admin", "teacher"].includes(member.user.role) && (
                        <button
                          className="secondary"
                          disabled={locked}
                          onClick={() =>
                            setAction({ kind: "primary", uid: member.user.id })
                          }
                        >
                          Make primary manager: {member.user.name}
                        </button>
                      )}
                    <button
                      className="secondary"
                      disabled={
                        locked ||
                        member.is_primary ||
                        (member.active && activeStaff.length <= 1)
                      }
                      onClick={() =>
                        setAction({ kind: "remove", uid: member.user.id })
                      }
                    >
                      Remove staff: {member.user.name}
                    </button>
                    {member.is_primary && (
                      <small>Transfer primary management first.</small>
                    )}
                    {!member.is_primary &&
                      member.active &&
                      activeStaff.length <= 1 && (
                        <small>Add another active manager first.</small>
                      )}
                  </div>
                )}
              </li>
            ))}
          </ul>
          {admin && (
            <>
              <form
                className="am-candidate-search"
                onSubmit={(e) => {
                  e.preventDefault();
                  void search();
                }}
              >
                <fieldset disabled={locked}>
                  <div className="am-fields">
                    <label>
                      Search active staff candidates
                      <input
                        aria-label="Search active staff candidates"
                        value={q}
                        maxLength={200}
                        onChange={(e) => {
                          setQ(e.target.value);
                          setCandidates(null);
                        }}
                        placeholder="Name or email"
                      />
                    </label>
                    <label>
                      Candidate role
                      <select
                        aria-label="Candidate role"
                        value={candidateRole}
                        onChange={(e) => {
                          setCandidateRole(e.target.value as Role);
                          setCandidates(null);
                        }}
                      >
                        <option value="teacher">Teacher</option>
                        <option value="admin">Admin</option>
                      </select>
                    </label>
                  </div>
                  <button className="secondary">Search staff candidates</button>
                </fieldset>
              </form>
              {candidates && (
                <>
                  <p>
                    {candidates.total} active {roleLabel(candidateRole)}{" "}
                    candidates
                  </p>
                  <ul className="am-people">
                    {candidates.items.map((a) => (
                      <li key={a.user.id}>
                        <div>
                          <strong>{a.user.name}</strong>
                          <small className="block">{a.user.email}</small>
                        </div>
                        <button
                          className="secondary"
                          disabled={
                            locked ||
                            data.staff.some((m) => m.user.id === a.user.id)
                          }
                          onClick={() =>
                            setAction({ kind: "add", uid: a.user.id })
                          }
                        >
                          Add staff: {a.user.name}
                        </button>
                      </li>
                    ))}
                  </ul>
                  <div className="button-row">
                    <button
                      className="secondary"
                      disabled={locked || candidates.offset === 0}
                      onClick={() =>
                        void search(Math.max(0, candidates.offset - 10))
                      }
                    >
                      Previous candidates
                    </button>
                    <button
                      className="secondary"
                      disabled={
                        locked ||
                        candidates.offset + candidates.items.length >=
                          candidates.total
                      }
                      onClick={() => void search(candidates.offset + 10)}
                    >
                      Next candidates
                    </button>
                  </div>
                </>
              )}
              {action && (
                <div className="notice confirmation">
                  <p>
                    {action.kind === "add"
                      ? "Assign this active account to the course?"
                      : action.kind === "remove"
                        ? "Remove this staff assignment only? Teaching history and other course assignments are retained."
                        : "Transfer primary management to this already-assigned active staff member? The previous primary remains assigned."}{" "}
                    <strong>
                      {data.staff.find((m) => m.user.id === action.uid)?.user
                        .email ??
                        candidates?.items.find((a) => a.user.id === action.uid)
                          ?.user.email ??
                        action.uid}
                    </strong>
                  </p>
                  <p>
                    If a safety conflict is returned, keep this action, refresh
                    staff, add another manager and transfer primary management
                    explicitly. Course role changes never silently transfer
                    ownership.
                  </p>
                  <div className="button-row">
                    <button
                      className="primary"
                      disabled={locked}
                      onClick={() => void mutate()}
                    >
                      Confirm staff {action.kind}
                    </button>
                    <button
                      className="secondary"
                      disabled={locked}
                      onClick={() => setAction(null)}
                    >
                      Cancel staff action
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
                    Inspect staff outcome (GET only)
                  </button>
                  {inspected && (
                    <button
                      className="secondary"
                      disabled={lane.busy}
                      onClick={() => {
                        if (
                          window.confirm(
                            "Current staff have been inspected. Unlock the retained action without retrying?",
                          )
                        ) {
                          setRecovery(null);
                          setInspected(false);
                        }
                      }}
                    >
                      I reviewed staff — unlock action
                    </button>
                  )}
                </div>
              )}
            </>
          )}
        </>
      )}
    </section>
  );
}
export function GlobalCourseAssignments({
  user,
  selectedCourse,
  onSelect,
  onChanged,
  onHold,
}: {
  user: User;
  selectedCourse: string;
  onSelect: (id: string) => void;
  onChanged?: () => void;
  onHold?: (held: boolean) => void;
}) {
  const lane = useAccountLane(),
    [courses, setCourses] = useState<CourseBrief[]>([]),
    [held, setHeld] = useState(false);
  useEffect(() => {
    onHold?.(lane.busy || held);
    return () => onHold?.(false);
  }, [lane.busy, held, onHold]);
  const load = () =>
    lane.run(async (current) => {
      const result = await accountApi.courses();
      if (current()) setCourses(result.courses);
    });
  useEffect(() => {
    void load();
  }, []);
  return (
    <section className="am-assignments" id="global-course-assignments">
      <h2>Course staff assignments</h2>
      <p>
        Choose any course, even if you are not assigned to it. This index
        contains administrative metadata only; it does not grant access to
        course content.
      </p>
      <ErrorBanner error={lane.error} />
      <div className="am-fields">
        <label>
          Course for staff assignments
          <select
            aria-label="Course for staff assignments"
            value={selectedCourse}
            disabled={lane.busy || held}
            onChange={(e) => onSelect(e.target.value)}
          >
            <option value="">Choose a course</option>
            {courses.map((c) => (
              <option key={c.id} value={c.id}>
                {c.code} · {c.title}
                {c.trashed_at ? " (in trash)" : ""}
              </option>
            ))}
          </select>
        </label>
        <button
          className="secondary"
          disabled={lane.busy || held}
          onClick={() => void load()}
        >
          Refresh course index
        </button>
      </div>
      {selectedCourse && courses.some((c) => c.id === selectedCourse) && (
        <CourseStaff
          user={user}
          courseId={selectedCourse}
          onChanged={onChanged}
          onHold={setHeld}
        />
      )}
      {!lane.busy && !courses.length && (
        <p>No courses are available in the administrative index.</p>
      )}
    </section>
  );
}
