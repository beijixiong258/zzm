import { useEffect, useState, type FormEvent } from "react";
import { api } from "./api";
import { ErrorBanner } from "./ui";
import { AccountNotice as Notice } from "./account-management-ui";
import { useUnsavedChanges } from "./navigation-guard";
import {
  passwordValid,
  unknownWrite,
  useAccountLane,
} from "./account-management-state";
import { passwordHelp } from "./GlobalAccountForms";
export default function ProvisionStudent(props: {
  courseId: string;
  onCreated: () => Promise<void>;
  onHold?: (held: boolean) => void;
}) {
  return <ProvisionForm key={props.courseId} {...props} />;
}
function ProvisionForm({
  courseId,
  onCreated,
  onHold,
}: {
  courseId: string;
  onCreated: () => Promise<void>;
  onHold?: (held: boolean) => void;
}) {
  const lane = useAccountLane(),
    [open, setOpen] = useState(false),
    [name, setName] = useState(""),
    [email, setEmail] = useState(""),
    [temporary, setTemporary] = useState("");
  const [attempt, setAttempt] = useState<{
      uid: string | null;
      ack: boolean;
    } | null>(null),
    [inspected, setInspected] = useState(false);
  const dirty = !!name || !!email || !!temporary;
  useUnsavedChanges(dirty || lane.busy || !!attempt);
  useEffect(() => {
    onHold?.(lane.busy || !!attempt);
    return () => onHold?.(false);
  }, [lane.busy, attempt, onHold]);
  async function complete() {
    setName("");
    setEmail("");
    setTemporary("");
    setAttempt(null);
    setOpen(false);
    lane.setNotice(
      "Student account/enrollment acknowledged and independently verified.",
    );
    await onCreated();
  }
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (attempt || (temporary && !passwordValid(temporary))) return;
    await lane.run(async (current) => {
      let recovery = { uid: null as string | null, ack: false };
      try {
        const ack = await api.provisionStudent(courseId, {
          name: name.trim(),
          email: email.trim(),
          temporary_password: temporary,
        });
        if (!current()) return;
        if (
          ack.course_id !== courseId ||
          !ack.user.id ||
          ack.user.email.toLowerCase() !== email.trim().toLowerCase() ||
          ack.user.role !== "student"
        )
          throw Error("Student provision acknowledgement did not match.");
        recovery = { uid: ack.user.id, ack: true };
        setAttempt(recovery);
        const next = await api.roster(courseId, false);
        if (!current()) return;
        if (
          !next.some(
            (r) =>
              r.user.id === ack.user.id &&
              r.user.email.toLowerCase() === email.trim().toLowerCase() &&
              r.user.role === "student",
          )
        )
          throw Error("Student enrollment readback did not match.");
        await complete();
      } catch (e) {
        if (!current()) return;
        if (recovery.ack || unknownWrite(e)) {
          setAttempt(recovery);
          setInspected(false);
          throw Error(
            `Student creation/enrollment outcome needs inspection. Draft retained; no automatic retry. ${e instanceof Error ? e.message : ""}`,
          );
        }
        throw e;
      }
    });
  }
  async function inspect() {
    if (!attempt) return;
    await lane.run(async (current) => {
      const next = await api.roster(courseId, false);
      if (!current()) return;
      const exact = next.find(
        (r) =>
          r.user.email.toLowerCase() === email.trim().toLowerCase() &&
          r.user.role === "student",
      );
      if (attempt.ack && exact?.user.id === attempt.uid) {
        await complete();
        return;
      }
      setInspected(true);
      lane.setNotice(
        `${exact ? "This email is enrolled in the course." : "This email is not currently in the active roster."} The original write was not acknowledged; review before a deliberate new attempt.`,
      );
    });
  }
  const blocked = lane.busy || !!attempt;
  return (
    <section className="provision-student am-provision">
      <button
        className="secondary"
        disabled={blocked}
        onClick={() => {
          if (open && dirty && !window.confirm("Discard this student draft?"))
            return;
          setOpen(!open);
          if (open) {
            setName("");
            setEmail("");
            setTemporary("");
          }
        }}
      >
        Create or enroll student
      </button>
      <ErrorBanner error={lane.error} />
      {lane.notice && <Notice>{lane.notice}</Notice>}
      {open && (
        <form className="card provision-form" onSubmit={(e) => void submit(e)}>
          <h3>Create or enroll student</h3>
          <p>
            New accounts are Students and must change their temporary password
            at first sign-in. An existing Student email is enrolled without
            changing its name, role or password. Leave the password blank only
            when enrolling an existing Student.
          </p>
          <fieldset disabled={blocked}>
            <div className="am-fields">
              <label>
                Student name
                <input
                  aria-label="Student name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  maxLength={100}
                  autoComplete="off"
                />
              </label>
              <label>
                Student email
                <input
                  aria-label="Student email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  maxLength={254}
                  autoComplete="off"
                />
              </label>
              <label>
                Student temporary password
                <input
                  aria-label="Student temporary password"
                  type="password"
                  autoComplete="new-password"
                  value={temporary}
                  onChange={(e) => setTemporary(e.target.value)}
                />
                <small>
                  {passwordHelp} Leave blank for an existing Student.
                </small>
              </label>
            </div>
            <button
              className="primary"
              disabled={
                !name.trim() ||
                !email.trim() ||
                (!!temporary && !passwordValid(temporary))
              }
            >
              Create / enroll student
            </button>
          </fieldset>
        </form>
      )}
      {attempt && (
        <div className="am-recovery">
          <button
            className="secondary"
            disabled={lane.busy}
            onClick={() => void inspect()}
          >
            Inspect student outcome (GET only)
          </button>
          {inspected && (
            <button
              className="secondary"
              disabled={lane.busy}
              onClick={() => {
                if (
                  window.confirm(
                    "I inspected this course roster. Unlock retained student draft without retrying?",
                  )
                ) {
                  setAttempt(null);
                  setInspected(false);
                }
              }}
            >
              I reviewed the roster — unlock student draft
            </button>
          )}
        </div>
      )}
    </section>
  );
}
