import { computed, ref } from "vue";
import {
  call,
  key,
  type Bootstrap,
  type Course,
  type TaskSummary,
  type User,
} from "../classroom-api";
import { savedLocale, setLocale, t } from "../i18n";

export const user = ref<User | null>(null);
export const courses = ref<Course[]>([]);
export const tasks = ref<Record<string, TaskSummary[]>>({});
export const bootstrap = ref<Bootstrap | null>(null);
export const dirty = ref(false);
export const staff = computed(() => user.value?.role !== "student");
export type Route = {
  page: string;
  courseId: string;
  taskId: string;
  versionId?: string;
  recordId?: string;
};
function readRoute(): Route {
  const query = new URLSearchParams(location.hash.slice(1));
  return {
    page: query.get("page") || "home",
    courseId: query.get("courseId") || "",
    taskId: query.get("taskId") || "",
    versionId: query.get("versionId") || undefined,
    recordId: query.get("recordId") || undefined,
  };
}
export const route = ref<Route>(readRoute());
export const routeKey = ref(0);
export function navigate(next: Partial<Route>) {
  if (dirty.value && !window.confirm(t("Leave without saving your changes?")))
    return false;
  dirty.value = false;
  const value: Route = { page: "home", courseId: "", taskId: "", ...next };
  route.value = value;
  routeKey.value++;
  const query = new URLSearchParams();
  Object.entries(value).forEach(([k, v]) => {
    if (v) query.set(k, v);
  });
  history.pushState(null, "", `#${query}`);
  window.scrollTo(0, 0);
  return true;
}
export function retainTaskAddress(taskId: string) {
  // Saving a new task must retain its address without remounting an active generation form.
  if (route.value.page !== "task" || route.value.taskId) return;
  route.value = { ...route.value, taskId };
  const query = new URLSearchParams(location.hash.slice(1));
  query.set("taskId", taskId);
  history.replaceState(null, "", `#${query}`);
}
window.addEventListener("popstate", () => {
  if (dirty.value && !window.confirm(t("Leave without saving your changes?"))) {
    history.go(1);
    return;
  }
  dirty.value = false;
  route.value = readRoute();
  routeKey.value++;
});
window.addEventListener("beforeunload", (event) => {
  if (dirty.value) {
    event.preventDefault();
    event.returnValue = "";
  }
});
export async function refreshCourses() {
  courses.value = await call<Course[]>("/courses");
  const entries = await Promise.all(
    courses.value
      .filter((c) => !c.archived)
      .map(
        async (course) =>
          [
            course.id,
            await call<TaskSummary[]>(`/courses/${key(course.id)}/sessions`),
          ] as const,
      ),
  );
  tasks.value = Object.fromEntries(entries);
}
export async function initialize() {
  setLocale(savedLocale() || "zh-CN");
  bootstrap.value = await call<Bootstrap>("/bootstrap");
  try {
    user.value = await call<User>("/auth/me");
  } catch (error) {
    if ((error as { status?: number }).status !== 401) throw error;
    user.value = null;
  }
  if (user.value && !user.value.mustChangePassword) await refreshCourses();
}
