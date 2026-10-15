import type { Course, User } from "./types";
import type { Route } from "./routes";

export const platformTitle = (code?: string | null) => code ? `AIcademiya · ${code}` : "AIcademiya";
export function pageTitle(user: User | null, route: Route, homeCourse: Course | undefined, scopedCourse: Course | undefined) {
  if (!user || user.must_change_password) return platformTitle();
  if (route.page === "home") return platformTitle(homeCourse?.code);
  if (["teacher", "workspace", "record", "roster", "versions", "course-materials"].includes(route.page))
    return platformTitle(scopedCourse?.code);
  return platformTitle();
}
export function populationLabel(count: number, singular: "Session" | "Admin" | "Teacher" | "Student") {
  return count === 1 ? singular : `${singular}s`;
}
