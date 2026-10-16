import { t, locale, setLocale } from "../i18n";
import { computed, onBeforeUnmount, ref, watch, type Ref } from "vue";
import { api, ApiError } from "../api";
import { readRoute, routeHash, type Route } from "../routes";
import type { Bootstrap, Course, User } from "../types";

export const user = ref<User | null>(null);
export const bootstrap = ref<Bootstrap | null>(null);
export const courses = ref<Course[]>([]);
export const route = ref<Route>(readRoute());
export const staff = computed(
  () => !!user.value && user.value.role !== "student",
);
const guards = new Map<symbol, () => boolean>();
import { errorText, label } from "./utils";
export { errorText, clone, dateText, label } from "./utils";

export function useDirty(dirty: Ref<boolean>) {
  const token = Symbol();
  guards.set(token, () => dirty.value);
  const listener = (e: BeforeUnloadEvent) => {
    if (dirty.value) {
      e.preventDefault();
      e.returnValue = "";
    }
  };
  window.addEventListener("beforeunload", listener);
  onBeforeUnmount(() => {
    guards.delete(token);
    window.removeEventListener("beforeunload", listener);
  });
}
export const confirmation = ref<{
  message: string;
  resolve: (value: boolean) => void;
} | null>(null);
export function askConfirm(message: string): Promise<boolean> {
  if (confirmation.value) return Promise.resolve(false);
  return new Promise((resolve) => {
    confirmation.value = { message, resolve };
  });
}
export function resolveConfirm(value: boolean) {
  const pending = confirmation.value;
  confirmation.value = null;
  pending?.resolve(value);
}
export async function confirmLeave() {
  return (
    ![...guards.values()].some((check) => check()) ||
    (await askConfirm(
      t(
        "Leave this page with unsaved changes? Changes have not been saved to the server.",
      ),
    ))
  );
}
export async function navigate(next: Route) {
  if (routeHash(next) === routeHash(route.value)) return;
  if (!(await confirmLeave())) return;
  route.value = next;
  location.hash = routeHash(next);
  window.scrollTo(0, 0);
}
window.addEventListener("hashchange", async () => {
  const next = readRoute();
  if (routeHash(next) === routeHash(route.value)) return;
  if (!(await confirmLeave())) {
    history.replaceState(null, "", "#" + routeHash(route.value));
    return;
  }
  route.value = next;
  window.scrollTo(0, 0);
});
export async function refreshCourses() {
  courses.value = await api.courses();
}
export async function initialize() {
  bootstrap.value = await api.bootstrap();
  setLocale(bootstrap.value.default_locale);
  try {
    user.value = (await api.me()).user;
  } catch (e) {
    if (!(e instanceof ApiError && e.status === 401)) throw e;
    user.value = null;
  }
  if (user.value && !user.value.must_change_password) await refreshCourses();
}
export function useTask() {
  const busy = ref(false),
    error = ref(""),
    success = ref("");
  async function run(action: () => Promise<void>, message = "") {
    if (busy.value) return false;
    busy.value = true;
    error.value = "";
    success.value = "";
    try {
      await action();
      success.value = message;
      return true;
    } catch (e) {
      error.value = errorText(e);
      return false;
    } finally {
      busy.value = false;
    }
  }
  return { busy, error, success, run };
}
export function useDialogDraft<T>(value: Ref<T>) {
  const original = JSON.stringify(value.value);
  const dirty = computed(() => JSON.stringify(value.value) !== original);
  return dirty;
}
watch(
  [route, locale],
  () => {
    document.title = `AIcademiya · ${label(route.value.page)}`;
  },
  { immediate: true },
);
