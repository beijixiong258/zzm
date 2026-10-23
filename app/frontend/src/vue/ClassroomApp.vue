<script setup lang="ts">
import { computed, defineAsyncComponent, ref, watch } from "vue";
import { ArrowRight, Compass, MessageSquare } from "lucide-vue-next";
import { locale, setLocale, t } from "../i18n";
import {
  call,
  dateText,
  statusText,
  type LearningRecordSummary,
  type User,
} from "../classroom-api";
import {
  bootstrap,
  courses,
  initialize,
  navigate,
  refreshCourses,
  route,
  routeKey,
  staff,
  tasks,
  user,
} from "./classroom-state";
import ClassroomHome from "./views/ClassroomHome.vue";
import BrandLogo from "./components/BrandLogo.vue";
const TeacherWorkbench = defineAsyncComponent(
  () => import("./views/TeacherWorkbench.vue"),
);
const TaskEditor = defineAsyncComponent(() => import("./views/TaskEditor.vue"));
const StudentTask = defineAsyncComponent(
  () => import("./views/StudentTask.vue"),
);
const TaskMonitor = defineAsyncComponent(
  () => import("./views/TaskMonitor.vue"),
);
const CourseLibrary = defineAsyncComponent(
  () => import("./views/CourseLibrary.vue"),
);
const CoursePeople = defineAsyncComponent(
  () => import("./views/CoursePeople.vue"),
);
const ready = ref(false),
  busy = ref(false),
  error = ref(""),
  menuOpen = ref(false);
const loginRoles = [
  { value: "teacher", label: "Teacher" },
  { value: "student", label: "Student" },
  { value: "admin", label: "Admin" },
] as const;
const loginRole = ref<User["role"]>("teacher");
const studentEmail = ref(false);
const studentSignIn = computed(
  () => loginRole.value === "student" && !studentEmail.value,
);
const creatingAdmin = computed(
  () => loginRole.value === "admin" && bootstrap.value?.needsSetup === true,
);
const studentCredentials = ref({ username: "", invitationCode: "" });
const demoAccounts = computed(() =>
  ["teacher", "student"].flatMap(
    (role) =>
      bootstrap.value?.demoAccounts.filter(
        (account) => account.role === role,
      ) || [],
  ),
);
watch(loginRole, () => {
  error.value = "";
  loginForm.value.password = "";
  studentCredentials.value.invitationCode = "";
  studentEmail.value = false;
});
const loginForm = ref({ name: "", email: "", password: "" }),
  passwordForm = ref({ currentPassword: "", newPassword: "" });
const historyRows = ref<LearningRecordSummary[]>([]),
  accountRows = ref<User[]>([]),
  showAccount = ref(false);
const accountForm = ref({ name: "", email: "", password: "", role: "student" });
const course = computed(() =>
  courses.value.find((c) => c.id === route.value.courseId),
);
const pageKey = routeKey;
async function action(fn: () => Promise<void>) {
  busy.value = true;
  error.value = "";
  try {
    await fn();
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
async function boot() {
  ready.value = false;
  error.value = "";
  try {
    await initialize();
    if (user.value?.mustChangePassword) navigate({ page: "settings" });
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    ready.value = true;
  }
}
async function signIn() {
  await action(async () => {
    if (creatingAdmin.value) {
      await call("/auth/setup", "POST", { ...loginForm.value, role: "admin" });
      if (bootstrap.value) bootstrap.value.needsSetup = false;
    }
    user.value = studentSignIn.value
      ? await call<User>(
          "/auth/student-login",
          "POST",
          studentCredentials.value,
        )
      : await call<User>("/auth/login", "POST", {
          ...loginForm.value,
          role: loginRole.value,
        });
    studentCredentials.value.invitationCode = "";
    loginForm.value.password = "";
    if (user.value.mustChangePassword) navigate({ page: "settings" });
    else {
      await refreshCourses();
      navigate({ page: "home" });
    }
  });
}
async function demo(id: string) {
  await action(async () => {
    user.value = await call<User>(
      `/auth/demo/${encodeURIComponent(id)}`,
      "POST",
    );
    await refreshCourses();
    navigate({ page: "home" });
  });
}
async function signOut() {
  if (!navigate({ page: "home" })) return;
  await action(async () => {
    await call("/auth/logout", "POST");
    user.value = null;
    courses.value = [];
    tasks.value = {};
  });
}
async function open(page: string) {
  if (!navigate({ page })) return;
  menuOpen.value = false;
}
watch(
  () => [user.value?.id, route.value.page],
  async () => {
    if (!user.value || user.value.mustChangePassword) return;
    await action(async () => {
      if (route.value.page === "history")
        historyRows.value = await call<LearningRecordSummary[]>("/history");
      if (route.value.page === "accounts" && user.value?.role === "admin")
        accountRows.value = await call<User[]>("/accounts");
    });
  },
);
async function changePassword() {
  await action(async () => {
    await call("/auth/password", "POST", passwordForm.value);
    passwordForm.value = { currentPassword: "", newPassword: "" };
    user.value = await call<User>("/auth/me");
    await refreshCourses();
    navigate({ page: "home" });
  });
}
async function createAccount() {
  await action(async () => {
    await call("/accounts", "POST", accountForm.value);
    accountRows.value = await call<User[]>("/accounts");
    showAccount.value = false;
    accountForm.value = { name: "", email: "", password: "", role: "student" };
  });
}
function taskTitle(id: string) {
  return (
    Object.values(tasks.value)
      .flat()
      .find((task) => task.id === id)?.title || id
  );
}
void boot();
</script>
<template>
  <div v-if="!ready" class="startup">
    <BrandLogo :wordmark="false" />
    <p>{{ t("Opening your workspace…") }}</p>
  </div>
  <main v-else-if="!user" class="login-page" :lang="locale">
    <div class="login-toolbar">
      <select
        :value="locale"
        :aria-label="t('Interface language')"
        @change="setLocale(($event.target as HTMLSelectElement).value)"
      >
        <option value="zh-CN">中文</option>
        <option value="en">English</option>
      </select>
    </div>
    <div class="login-layout">
      <section class="login-story" aria-labelledby="login-story-title">
        <p class="login-eyebrow">{{ t("A space for deeper learning") }}</p>
        <h1 id="login-story-title">
          {{ t("A little curiosity.\nA deeper understanding.") }}
        </h1>
        <p class="login-introduction">
          {{
            t(
              "A focused space for questions, reflection and thoughtful feedback.",
            )
          }}
        </p>
        <div class="login-illustration" aria-hidden="true">
          <div class="login-orbit"></div>
          <div class="login-note login-note-explore">
            <Compass :size="25" :stroke-width="1.4" />
            <span>{{ t("Explore the idea.") }}</span>
            <i></i><i></i>
          </div>
          <div class="login-note login-note-discuss">
            <MessageSquare :size="25" :stroke-width="1.4" />
            <span>{{ t("Find your voice.") }}</span>
            <i></i><i></i>
          </div>
        </div>
        <ol class="login-principles">
          <li><span>01</span> / {{ t("Think") }}</li>
          <li><span>02</span> / {{ t("Discuss") }}</li>
          <li><span>03</span> / {{ t("Reflect") }}</li>
        </ol>
      </section>
      <section class="login-card" aria-labelledby="login-form-title">
        <div class="login-brand">
          <span class="login-brand-mark" aria-hidden="true"></span>
          <div class="login-brand-copy">
            <span class="login-wordmark">AIcademiya</span>
            <span class="login-tagline">{{ t("Learn with intention") }}</span>
          </div>
        </div>
        <h2 id="login-form-title">
          {{
            t(
              creatingAdmin
                ? "Create the first administrator account"
                : "Your learning starts here.",
            )
          }}
        </h2>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <div
          class="sign-in-tabs login-role-tabs"
          role="group"
          :aria-label="t('Sign in as')"
        >
          <button
            v-for="role in loginRoles"
            :key="role.value"
            type="button"
            :class="{ primary: loginRole === role.value }"
            :aria-pressed="loginRole === role.value"
            :disabled="busy"
            @click="loginRole = role.value"
          >
            {{ t(role.label) }}
          </button>
        </div>
        <button
          v-if="loginRole === 'student'"
          type="button"
          class="login-method"
          :disabled="busy"
          @click="
            studentEmail = !studentEmail;
            error = '';
          "
        >
          {{
            t(
              studentEmail
                ? "Use a personal invitation code"
                : "Use email and password",
            )
          }}
        </button>
        <form class="form-stack" @submit.prevent="signIn">
          <label v-if="creatingAdmin">
            {{ t("Name") }}
            <input v-model="loginForm.name" required autocomplete="name" />
          </label>
          <template v-if="studentSignIn">
            <label>
              {{ t("Username") }}
              <input
                v-model="studentCredentials.username"
                required
                autocomplete="username"
                autocapitalize="none"
                :spellcheck="false"
                maxlength="64"
              />
            </label>
            <label>
              {{ t("Invitation code") }}
              <input
                v-model="studentCredentials.invitationCode"
                type="password"
                required
                autocomplete="current-password"
                maxlength="128"
              />
            </label>
          </template>
          <template v-else>
            <label>
              {{ t("Email address") }}
              <input
                v-model="loginForm.email"
                type="email"
                required
                autocomplete="username"
                autocapitalize="none"
                :spellcheck="false"
                placeholder="you@example.edu"
              />
            </label>
            <label>
              {{ t("Password") }}
              <input
                v-model="loginForm.password"
                type="password"
                required
                :minlength="creatingAdmin ? 8 : 1"
                :autocomplete="
                  creatingAdmin ? 'new-password' : 'current-password'
                "
              />
            </label>
          </template>
          <div
            v-if="
              bootstrap?.demoEnabled && demoAccounts.length && !creatingAdmin
            "
            class="login-demo-panel"
          >
            <small>{{ t("Try a demo — no password needed") }}</small>
            <div class="login-demo-options">
              <button
                v-for="account in demoAccounts"
                :key="account.id"
                type="button"
                :disabled="busy"
                @click="demo(account.id)"
              >
                {{
                  t(
                    account.role === "teacher"
                      ? "Demo teacher sign-in"
                      : "Demo student sign-in",
                  )
                }}
              </button>
            </div>
          </div>
          <small v-if="studentSignIn" class="login-help">
            {{
              t(
                "Use the personal invitation code your teacher gave you. A course join code cannot be used to sign in.",
              )
            }}
          </small>
          <button class="primary login-submit" :disabled="busy || !bootstrap">
            <ArrowRight :size="18" aria-hidden="true" />
            {{ t(creatingAdmin ? "Create account and sign in" : "Sign in") }}
          </button>
        </form>
        <p v-if="creatingAdmin" class="login-help login-access-note">
          {{
            t(
              "Create your administrator account to manage users. Demo accounts do not need a password.",
            )
          }}
        </p>
        <button v-if="!bootstrap" :disabled="busy" @click="boot">
          {{ t("Retry connection") }}
        </button>
      </section>
    </div>
  </main>
  <div v-else class="classroom-shell">
    <button
      class="mobile-menu"
      :aria-label="t('Toggle navigation')"
      @click="menuOpen = !menuOpen"
    >
      ☰
    </button>
    <aside :class="['classroom-sidebar', { open: menuOpen }]">
      <button class="brand" @click="open('home')">
        <BrandLogo /></button
      ><button
        class="nav-home"
        :class="{ active: route.page === 'home' }"
        @click="open('home')"
      >
        ⌂ {{ t("Home") }}
      </button>
      <button
        v-if="staff"
        :class="{ active: route.page === 'workbench' }"
        @click="open('workbench')"
      >
        ✦ {{ t("Teacher workbench") }}
      </button>
      <p class="nav-caption">{{ t("MY COURSES") }}</p>
      <div class="course-navigation">
        <details
          v-for="item in courses.filter((c) => !c.archived)"
          :key="item.id"
          :open="item.id === route.courseId"
        >
          <summary>{{ item.title }}</summary>
          <button
            @click="
              navigate({ page: 'course', courseId: item.id });
              menuOpen = false;
            "
          >
            {{ t("Course overview") }}</button
          ><template v-if="staff"
            ><button
              @click="
                navigate({ page: 'task', courseId: item.id });
                menuOpen = false;
              "
            >
              ＋ {{ t("Create task") }}</button
            ><button
              @click="
                navigate({ page: 'people', courseId: item.id });
                menuOpen = false;
              "
            >
              {{ t("Manage class") }}</button
            ><button
              @click="
                navigate({ page: 'materials', courseId: item.id });
                menuOpen = false;
              "
            >
              {{ t("Materials") }}
            </button></template
          ><button
            v-for="task in (tasks[item.id] || []).filter((s) => !s.archived)"
            :key="task.id"
            :class="{ active: route.taskId === task.id }"
            @click="
              navigate({
                page: staff ? 'task' : 'learn',
                courseId: item.id,
                taskId: task.id,
              });
              menuOpen = false;
            "
          >
            <span>{{ task.sessionType === "tutor" ? "✦" : "▤" }}</span
            >{{ task.title }}
          </button>
        </details>
        <p v-if="!courses.length" class="muted small">
          {{ t("Your courses will appear here.") }}
        </p>
      </div>
      <nav class="secondary-nav">
        <button v-if="!staff" @click="open('history')">
          {{ t("Learning history") }}</button
        ><button v-if="user.role === 'admin'" @click="open('accounts')">
          {{ t("Account management") }}</button
        ><button @click="open('settings')">{{ t("Account settings") }}</button>
      </nav>
      <div class="sidebar-user">
        <strong>{{ user.name }}</strong
        ><small>{{
          t(
            user.role === "student"
              ? "Student"
              : user.role === "admin"
                ? "Administrator"
                : "Teacher",
          )
        }}</small
        ><button @click="signOut">{{ t("Sign out") }}</button>
      </div>
    </aside>
    <div v-if="menuOpen" class="sidebar-shade" @click="menuOpen = false" />
    <div class="classroom-main">
      <header class="topbar">
        <div>
          <span>{{
            t(staff ? "Teaching workspace" : "Learning workspace")
          }}</span
          ><span v-if="course" class="muted"> / {{ course.code }}</span>
        </div>
        <select
          :value="locale"
          :aria-label="t('Interface language')"
          @change="setLocale(($event.target as HTMLSelectElement).value)"
        >
          <option value="zh-CN">中文</option>
          <option value="en">English</option>
        </select>
      </header>
      <main class="page-body">
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <template v-if="user.mustChangePassword || route.page === 'settings'"
          ><header class="page-heading">
            <div>
              <h1>{{ t("Account settings") }}</h1>
              <p v-if="user.mustChangePassword" class="notice">
                {{ t("Change your temporary password before continuing.") }}
              </p>
            </div>
          </header>
          <p v-if="user.demo" class="panel">
            {{
              t(
                "This is a demo account. Use the demo sign-in buttons; no password is required.",
              )
            }}
          </p>
          <p v-else-if="user.username && !user.email" class="panel">
            {{
              t(
                "Your account uses a personal invitation code. Ask your teacher to reset it when needed.",
              )
            }}
          </p>
          <form
            v-else
            class="panel form-stack settings-form"
            @submit.prevent="changePassword"
          >
            <h2>{{ t("Change password") }}</h2>
            <label
              >{{ t("Current password")
              }}<input
                v-model="passwordForm.currentPassword"
                type="password"
                required
                autocomplete="current-password" /></label
            ><label
              >{{ t("New password")
              }}<input
                v-model="passwordForm.newPassword"
                type="password"
                minlength="8"
                required
                autocomplete="new-password" /></label
            ><button class="primary" :disabled="busy">
              {{ t("Save password") }}
            </button>
          </form></template
        >
        <ClassroomHome
          v-else-if="['home', 'course'].includes(route.page)"
          :key="pageKey"
          :course-id="route.courseId"
        />
        <TeacherWorkbench
          v-else-if="staff && route.page === 'workbench'"
          :key="pageKey"
        />
        <TaskEditor
          v-else-if="staff && route.page === 'task'"
          :key="pageKey"
          :course-id="route.courseId"
          :task-id="route.taskId"
        />
        <CourseLibrary
          v-else-if="staff && route.page === 'materials'"
          :key="pageKey"
          :course-id="route.courseId"
        />
        <CoursePeople
          v-else-if="staff && route.page === 'people'"
          :key="pageKey"
          :course-id="route.courseId"
        />
        <TaskMonitor
          v-else-if="staff && route.page === 'monitor'"
          :key="pageKey"
          :task-id="route.taskId"
        />
        <StudentTask
          v-else-if="!staff && route.page === 'learn'"
          :key="pageKey"
          :task-id="route.taskId"
          :version-id="route.versionId"
        />
        <section v-else-if="route.page === 'history'">
          <h1>{{ t("Learning history") }}</h1>
          <article
            v-for="record in historyRows"
            :key="record.id"
            class="panel task-card"
          >
            <div class="grow">
              <h3>{{ taskTitle(record.sessionId) }}</h3>
              <p>{{ dateText(record.updatedAt) }}</p>
              <small>{{ t("Version") }}: {{ record.versionId }}</small>
              <div>
                <span class="badge status-label" :data-status="record.status">{{
                  statusText(record.status)
                }}</span>
              </div>
            </div>
            <button
              @click="
                navigate({
                  page: 'learn',
                  taskId: record.sessionId,
                  versionId: record.versionId,
                })
              "
            >
              {{ t("View learning record") }}
            </button>
          </article>
          <p v-if="!historyRows.length" class="empty">
            {{ t("Your learning history will appear here.") }}
          </p>
        </section>
        <section v-else-if="user.role === 'admin' && route.page === 'accounts'">
          <div class="page-heading">
            <h1>{{ t("Account management") }}</h1>
            <button class="primary" @click="showAccount = true">
              ＋ {{ t("Create account") }}
            </button>
          </div>
          <div class="panel table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{{ t("Name") }}</th>
                  <th>{{ t("Email") }}</th>
                  <th>{{ t("Role") }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="account in accountRows" :key="account.id">
                  <td>{{ account.name }}</td>
                  <td>{{ account.email }}</td>
                  <td>
                    {{
                      t(
                        account.role === "admin"
                          ? "Administrator"
                          : account.role === "teacher"
                            ? "Teacher"
                            : "Student",
                      )
                    }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
        <p v-else class="empty">
          {{ t("This page is not available to your role.") }}
        </p>
      </main>
      <footer>AIcademiya · {{ t("A considered space for learning.") }}</footer>
    </div>
    <div
      v-if="showAccount"
      class="modal-backdrop"
      @click.self="showAccount = false"
    >
      <form
        class="modal form-stack"
        role="dialog"
        aria-modal="true"
        :aria-label="t('Create account')"
        @submit.prevent="createAccount"
      >
        <h2>{{ t("Create account") }}</h2>
        <label
          >{{ t("Name") }}<input v-model="accountForm.name" required /></label
        ><label
          >{{ t("Email")
          }}<input v-model="accountForm.email" type="email" required /></label
        ><label
          >{{ t("Password")
          }}<input
            v-model="accountForm.password"
            type="password"
            minlength="8"
            required /></label
        ><label
          >{{ t("Role")
          }}<select v-model="accountForm.role">
            <option value="student">{{ t("Student") }}</option>
            <option value="teacher">{{ t("Teacher") }}</option>
            <option value="admin">{{ t("Administrator") }}</option>
          </select></label
        >
        <div class="row end">
          <button type="button" @click="showAccount = false">
            {{ t("Cancel") }}</button
          ><button class="primary" :disabled="busy">
            {{ t("Create account") }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>
