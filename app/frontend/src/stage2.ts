import type { Role, Availability, Question, Group } from "./types";
export const isStaff = (role: Role) => role === "teacher" || role === "admin";

export function effectiveAvailability(s: Availability, now = Date.now()) {
  if (s.starts_at || s.ends_at) {
    if (s.starts_at && now < Date.parse(s.starts_at))
      return { active: false, reason: "not_started" };
    if (s.ends_at && now >= Date.parse(s.ends_at))
      return { active: false, reason: "ended" };
    return { active: true, reason: "scheduled" };
  }
  return {
    active: s.active !== false,
    reason: s.active === false ? "manual_inactive" : "manual_active",
  };
}
export function localDateTime(iso: string | null | undefined) {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
export function schedulePayload(active: boolean, start: string, end: string) {
  const starts_at = start ? new Date(start).toISOString() : null;
  const ends_at = end ? new Date(end).toISOString() : null;
  if (starts_at && ends_at && starts_at >= ends_at)
    throw new Error("End must be after start");
  return { active, starts_at, ends_at };
}
export function moveItem<T>(items: T[], index: number, delta: number) {
  const target = index + delta;
  if (target < 0 || target >= items.length) return items;
  const out = [...items];
  [out[index], out[target]] = [out[target], out[index]];
  return out;
}
export function renumber(questions: Question[]) {
  return questions.map((q, i) => ({ ...q, ordinal: i + 1 }));
}
export function authoringErrors(groups: Group[], questions: Question[]) {
  const errors: string[] = [];
  if (new Set(groups.map((g) => g.id)).size !== groups.length)
    errors.push("Duplicate group IDs");
  if (groups.some((g) => !g.title.trim()))
    errors.push("Group titles are required");
  if (new Set(questions.map((q) => q.id)).size !== questions.length)
    errors.push("Duplicate question IDs");
  if (
    questions.some(
      (q) => !q.prompt.trim() || !groups.some((g) => g.id === q.group_id),
    )
  )
    errors.push("Each question needs a prompt and a valid group");
  return errors;
}
export function safeExternal(value: string | null | undefined) {
  if (!value) return null;
  try {
    const u = new URL(value);
    return ["http:", "https:"].includes(u.protocol) ? u.href : null;
  } catch {
    return null;
  }
}
export function withVersion(url: string, version?: string | null) {
  if (version == null) return url;
  const [path, hash] = url.split("#");
  const u = new URL(path, "http://local");
  u.searchParams.set("version_id", version);
  return `${u.pathname}${u.search}${hash ? `#${hash}` : ""}`;
}
export function retentionText(purge: string | null, now = Date.now()) {
  if (!purge) return "—";
  const remaining = Math.max(0, Date.parse(purge) - now);
  return `${Math.ceil(remaining / 86400000)}d · ${new Date(purge).toLocaleString("en-GB")}`;
}
