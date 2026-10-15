import { useEffect, useRef, useState } from "react";
import { ApiError } from "./api";
import type {
  AccountCreate,
  AccountDetail,
  AccountImportPreview,
  AccountImportResult,
  StaffResponse,
} from "./account-management-types";
import type { User } from "./types";
export const roles = ["student", "teacher", "admin"] as const;
export const roleLabel = (role: string) =>
  ({ student: "Student", teacher: "Teacher", admin: "Admin" })[role] ?? role;
export function passwordValid(value: string) {
  const n = Array.from(value).length;
  return n >= 8 && n <= 512 && /[A-Za-z]/.test(value) && /[0-9]/.test(value);
}
export function importFileError(file: Pick<File, "name" | "size">) {
  if (!/\.(csv|xlsx)$/i.test(file.name)) return "Choose a CSV or XLSX file.";
  if (!file.size) return "The file is empty.";
  if (file.size > 2 * 1024 * 1024)
    return "CSV and XLSX account files are limited to 2 MiB.";
  return "";
}
export function createdMatches(user: User, draft: AccountCreate) {
  return (
    !!user.id &&
    user.name === draft.name.trim() &&
    user.email.toLowerCase() === draft.email.trim().toLowerCase() &&
    user.role === draft.role &&
    user.must_change_password === true
  );
}
export function importResultValid(
  result: AccountImportResult,
  preview: AccountImportPreview,
) {
  return (
    result.created ===
      preview.rows.filter((r) => r.action === "create").length &&
    result.skipped === preview.rows.filter((r) => r.action === "skip").length &&
    new Set(result.user_ids).size ===
      new Set(preview.rows.map((r) => r.email.toLowerCase())).size
  );
}
export function importPreviewMatches(
  a: AccountImportPreview,
  b: AccountImportPreview,
) {
  const normalized = (p: AccountImportPreview) => [
    p.import_id,
    p.valid_count,
    p.error_count,
    p.rows.map((r) => [
      r.row_number,
      r.name,
      r.email,
      r.role,
      r.action,
      r.errors,
      r.warnings,
    ]),
  ];
  return JSON.stringify(normalized(a)) === JSON.stringify(normalized(b));
}
export function importReadbackMatches(
  accounts: AccountDetail[],
  result: AccountImportResult,
  preview: AccountImportPreview,
) {
  return (
    accounts.length === result.user_ids.length &&
    accounts.every((a, i) => a.user.id === result.user_ids[i]) &&
    preview.rows.every((row) =>
      accounts.some(
        (a) =>
          a.user.email.toLowerCase() === row.email.toLowerCase() &&
          a.user.role === row.role &&
          (row.action !== "create" ||
            (a.active &&
              a.user.must_change_password === true &&
              a.user.name === row.name.trim())),
      ),
    )
  );
}
export type StaffAction = { kind: "add" | "remove" | "primary"; uid: string };
export function staffMatches(
  data: StaffResponse,
  cid: string,
  action: StaffAction,
) {
  if (data.course.id !== cid) return false;
  const row = data.staff.find((r) => r.user.id === action.uid);
  if (action.kind === "remove") return !row;
  if (!row?.active || !["admin", "teacher"].includes(row.user.role))
    return false;
  return (
    action.kind === "add" ||
    (row.is_primary &&
      data.course.owner_id === action.uid &&
      data.staff.filter((r) => r.is_primary).length === 1)
  );
}
export function unknownWrite(error: unknown) {
  return !(
    error instanceof ApiError &&
    error.status >= 400 &&
    error.status < 500
  );
}
// Components are keyed by authenticated account/course. Never install a late response
// after unmount. Synchronous lock also prevents rapid double-click duplicate writes.
export function useAccountLane() {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const alive = useRef(true),
    locked = useRef(false),
    generation = useRef(0);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      generation.current++;
      locked.current = false;
    };
  }, []);
  async function run(job: (current: () => boolean) => Promise<void>) {
    if (locked.current) return;
    locked.current = true;
    const n = ++generation.current;
    const current = () => alive.current && n === generation.current;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await job(current);
    } catch (e) {
      if (current())
        setError(e instanceof Error ? e.message : "Request failed.");
    } finally {
      if (current()) {
        locked.current = false;
        setBusy(false);
      }
    }
  }
  return { busy, error, notice, run, setError, setNotice, locked };
}
