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
  section?: "account" | "feedback" | "model" | "search" | "users";
};
export function readRoute(hash = location.hash): Route {
  const [path, query] = hash.replace(/^#\/?/, "").split("?");
  const [page, sid, uid] = path.split("/");
  if (
    ![
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
    if (page === "settings") {
      const section = ["account", "feedback", "model", "search", "users"].includes(sid) ? sid as Route["section"] : undefined;
      return { page: "settings", ...(section ? { section } : {}) };
    }
    return {
      page: page as Route["page"],
      sid: sid ? decodeURIComponent(sid) : undefined,
      uid: uid ? decodeURIComponent(uid) : undefined,
      version: new URLSearchParams(query).get("version_id") || undefined,
    };
  } catch {
    return { page: "home" };
  }
}
export function routeHash(r: Route) {
  if (r.page === "settings") return `/settings${r.section ? `/${r.section}` : ""}`;
  return `/${r.page}${r.sid ? `/${encodeURIComponent(r.sid)}` : ""}${r.uid ? `/${encodeURIComponent(r.uid)}` : ""}${r.version ? `?version_id=${encodeURIComponent(r.version)}` : ""}`;
}
export function canAccessRoute(role: Role, page: Route["page"]) {
  if (page === "accounts") return role !== "student";
  if (["teacher", "record", "roster", "versions", "course-materials", "course-trash"].includes(page))
    return role !== "student";
  return true;
}
