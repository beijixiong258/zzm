import type { Role } from "./types";
export type Route = {
  page:
    | "home"
    | "history"
    | "workspace"
    | "teacher"
    | "record"
    | "settings"
    | "profile"
    | "accounts"
    | "roster"
    | "versions"
    | "course-materials"
    | "course-trash";
  sid?: string;
  uid?: string;
  version?: string;
  course?: string;
  tab?: string;
  section?: "account" | "feedback" | "model" | "search" | "users";
};
export function readRoute(hash = location.hash): Route {
  const [path, query] = hash.replace(/^#\/?/, "").split("?");
  const [page, sid, uid] = path.split("/");
  if (
    ![
      "home",
      "history",
      "workspace",
      "teacher",
      "record",
      "settings",
      "profile",
      "accounts",
      "roster",
      "versions",
      "course-materials",
      "course-trash",
    ].includes(page)
  )
    return { page: "home" };
  try {
    const params = new URLSearchParams(query);
    const context = {
      course: params.get("course") || undefined,
      tab: params.get("tab") || undefined,
    };
    if (page === "settings") {
      const section = [
        "account",
        "feedback",
        "model",
        "search",
        "users",
      ].includes(sid)
        ? (sid as Route["section"])
        : undefined;
      return { page: "settings", ...context, ...(section ? { section } : {}) };
    }
    return {
      page: page as Route["page"],
      sid: sid ? decodeURIComponent(sid) : undefined,
      uid: uid ? decodeURIComponent(uid) : undefined,
      version: params.get("version_id") || undefined,
      ...context,
    };
  } catch {
    return { page: "home" };
  }
}
export function routeHash(r: Route) {
  const params = new URLSearchParams();
  if (r.version) params.set("version_id", r.version);
  if (r.course) params.set("course", r.course);
  if (r.tab) params.set("tab", r.tab);
  const path =
    r.page === "settings"
      ? `/settings${r.section ? `/${r.section}` : ""}`
      : `/${r.page}${r.sid ? `/${encodeURIComponent(r.sid)}` : ""}${r.uid ? `/${encodeURIComponent(r.uid)}` : ""}`;
  return path + (params.size ? `?${params}` : "");
}
export function canAccessRoute(role: Role, page: Route["page"]) {
  if (
    [
      "accounts",
      "teacher",
      "record",
      "roster",
      "versions",
      "course-materials",
      "course-trash",
    ].includes(page)
  )
    return role !== "student";
  return true;
}
