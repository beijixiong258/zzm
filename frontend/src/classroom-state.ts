import { computed, ref } from "vue";
import {
  call,
  key,
  taskAvailability,
  type Bootstrap,
  type Course,
  type TaskSummary,
  type User,
} from "./classroom-api";
import { savedLocale, setLocale, t } from "./i18n";
import { confirmAction } from "./confirmAction";
import { useTaskTime } from "./useTaskTime";

export const user = ref<User | null>(null);
export const courses = ref<Course[]>([]);
export const tasks = ref<Record<string, TaskSummary[]>>({});
export const bootstrap = ref<Bootstrap | null>(null);
export const dirty = ref(false);
export const staff = computed(() => user.value?.role !== "student");
export const taskTime = useTaskTime(() =>
  Object.values(tasks.value).flatMap((courseTasks) =>
    courseTasks.map((task) => task.closesAt),
  ),
);

export function visibleCourseTasks(courseId: string) {
  return (tasks.value[courseId] || []).filter(
    (task) =>
      !task.archived &&
      (staff.value || taskAvailability(task, taskTime.value) === "open"),
  );
}
function loadCourseTasks(courseId: string) {
  return call<TaskSummary[]>(`/courses/${key(courseId)}/sessions`);
}
export async function refreshCourseTasks(courseId: string) {
  const account = user.value?.id;
  const updated = await loadCourseTasks(courseId);
  if (user.value?.id === account)
    tasks.value = { ...tasks.value, [courseId]: updated };
}
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
function courseRoute(value: Route): Route {
  if (
    !user.value ||
    !staff.value ||
    !["course", "task", "materials"].includes(value.page) ||
    (value.page === "course" && !value.courseId)
  )
    return value;
  if (
    courses.value.some(
      (course) => course.id === value.courseId && !course.workspace,
    )
  )
    return tasks.value[value.courseId]?.some(
      (task) => task.id === value.taskId && task.archived,
    )
      ? { page: "archives", courseId: "", taskId: "" }
      : value;
  return { page: "home", courseId: "", taskId: "" };
}
export async function navigate(next: Partial<Route>) {
  if (
    dirty.value &&
    !(await confirmAction(t("Leave without saving your changes?")))
  )
    return false;
  dirty.value = false;
  const value = courseRoute({
    page: "home",
    courseId: "",
    taskId: "",
    ...next,
  });
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
  // 保存新任务时保留当前地址，避免重新挂载正在生成内容的表单。
  if (route.value.page !== "task" || route.value.taskId) return;
  route.value = { ...route.value, taskId };
  const query = new URLSearchParams(location.hash.slice(1));
  query.set("taskId", taskId);
  history.replaceState(null, "", `#${query}`);
}
export function retainCourseAddress(courseId: string) {
  route.value = { ...route.value, page: "course", courseId };
  const query = new URLSearchParams(location.hash.slice(1));
  query.set("page", "course");
  query.set("courseId", courseId);
  history.replaceState(null, "", `#${query}`);
}
window.addEventListener("popstate", async () => {
  const requested = readRoute();
  const next = courseRoute(requested);
  if (next !== requested) history.replaceState(null, "", `#page=${next.page}`);
  // 取消浏览器后退时恢复当前地址，这会再次触发 popstate 事件。
  if (
    Object.entries(next).every(
      ([key, value]) => route.value[key as keyof Route] === value,
    )
  )
    return;
  if (
    dirty.value &&
    !(await confirmAction(t("Leave without saving your changes?")))
  ) {
    history.go(1);
    return;
  }
  dirty.value = false;
  route.value = next;
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
      .filter((c) => staff.value || !c.archived)
      .map(
        async (course) =>
          [course.id, await loadCourseTasks(course.id)] as const,
      ),
  );
  tasks.value = Object.fromEntries(entries);
  const resolved = courseRoute(route.value);
  if (resolved !== route.value) await navigate(resolved);
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
