<script setup lang="ts">
import {
  Select as TSelect,
  Option as TOption,
  Button as TButton,
  Input as TInput,
  ConfigProvider as TConfigProvider,
  RadioGroup as TRadioGroup,
  Table as TTable,
  type GlobalConfigProvider,
} from "tdesign-vue-next";
import { computed, defineAsyncComponent, ref, watch } from "vue";
import zhCN from "tdesign-vue-next/es/locale/zh_CN";
import enUS from "tdesign-vue-next/es/locale/en_US";
import { ArrowRight, Compass, MessageSquare } from "lucide-vue-next";
import { locale, setLocale, t } from "./i18n";
import {
  call,
  dateText,
  statusText,
  type LearningRecordSummary,
  type User,
} from "./classroom-api";
import {
  bootstrap,
  courses,
  dirty,
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
import AppDialog from "./components/AppDialog.vue";
const TeacherChat = defineAsyncComponent(
  () => import("./views/TeacherChat.vue"),
);
const TaskEditor = defineAsyncComponent(() => import("./views/TaskEditor.vue"));
const StudentTask = defineAsyncComponent(
  () => import("./views/StudentTask.vue"),
);
const CourseLibrary = defineAsyncComponent(
  () => import("./views/CourseLibrary.vue"),
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
const componentLocale = computed(
  () =>
    (locale.value === "en" ? enUS : zhCN) as unknown as GlobalConfigProvider,
);
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
  if (!(await navigate({ page: "home" }))) return;
  await action(async () => {
    await call("/auth/logout", "POST");
    user.value = null;
    courses.value = [];
    tasks.value = {};
  });
}
async function open(page: string) {
  if (!(await navigate({ page }))) return;
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
  <TConfigProvider :global-config="componentLocale">
    <div v-if="!ready" class="startup">
      <BrandLogo :wordmark="false" />
      <p>{{ t("Opening your workspace…") }}</p>
    </div>
    <main v-else-if="!user" class="login-page" :lang="locale">
      <div class="login-toolbar">
        <TSelect
          v-control-attrs="{ 'aria-label': t('Interface language') }"
          :value="locale"
          @change="setLocale(String($event))"
        >
          <TOption value="zh-CN" label="中文" />
          <TOption value="en" label="English" />
        </TSelect>
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
          <TRadioGroup
            v-model="loginRole"
            class="login-role-tabs"
            theme="button"
            variant="primary-filled"
            :disabled="busy"
            :options="
              loginRoles.map((role) => ({
                value: role.value,
                label: t(role.label),
              }))
            "
            :aria-label="t('Sign in as')"
          />
          <TButton
            theme="default"
            variant="outline"
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
          </TButton>
          <form class="form-stack" @submit.prevent="signIn">
            <label v-if="creatingAdmin">
              {{ t("Name") }}
              <TInput
                v-control-attrs="{ required: true }"
                v-model="loginForm.name"
                autocomplete="name"
              />
            </label>
            <template v-if="studentSignIn">
              <label>
                {{ t("Username") }}
                <TInput
                  v-control-attrs="{ required: true, autocapitalize: 'none' }"
                  v-model="studentCredentials.username"
                  autocomplete="username"
                  :spell-check="false"
                  maxlength="64"
                />
              </label>
              <label>
                {{ t("Invitation code") }}
                <TInput
                  v-control-attrs="{ required: true }"
                  v-model="studentCredentials.invitationCode"
                  type="password"
                  autocomplete="current-password"
                  maxlength="128"
                />
              </label>
            </template>
            <template v-else>
              <label>
                {{ t("Email address") }}
                <TInput
                  v-control-attrs="{
                    type: 'email',
                    required: true,
                    autocapitalize: 'none',
                  }"
                  v-model="loginForm.email"
                  autocomplete="username"
                  :spell-check="false"
                  placeholder="you@example.edu"
                />
              </label>
              <label>
                {{ t("Password") }}
                <TInput
                  v-control-attrs="{
                    required: true,
                    minlength: creatingAdmin ? 8 : 1,
                  }"
                  v-model="loginForm.password"
                  type="password"
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
                <TButton
                  theme="default"
                  variant="outline"
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
                </TButton>
              </div>
            </div>
            <small v-if="studentSignIn" class="login-help">
              {{
                t(
                  "Use the personal invitation code your teacher gave you. A course join code cannot be used to sign in.",
                )
              }}
            </small>
            <TButton
              theme="primary"
              variant="base"
              type="submit"
              class="primary login-submit"
              :disabled="busy || !bootstrap"
            >
              <ArrowRight :size="18" aria-hidden="true" />
              {{ t(creatingAdmin ? "Create account and sign in" : "Sign in") }}
            </TButton>
          </form>
          <p v-if="creatingAdmin" class="login-help login-access-note">
            {{
              t(
                "Create your administrator account to start a fresh teaching workspace.",
              )
            }}
          </p>
          <TButton
            theme="default"
            variant="outline"
            type="button"
            v-if="!bootstrap"
            :disabled="busy"
            @click="boot"
          >
            {{ t("Retry connection") }}
          </TButton>
        </section>
      </div>
    </main>
    <div v-else :class="['classroom-shell', { 'teacher-shell': staff }]">
      <TButton
        theme="default"
        variant="outline"
        type="button"
        class="mobile-menu"
        :aria-label="t('Toggle navigation')"
        @click="menuOpen = !menuOpen"
      >
        ☰
      </TButton>
      <aside :class="['classroom-sidebar', { open: menuOpen }]">
        <TButton
          theme="default"
          variant="outline"
          type="button"
          class="brand"
          @click="open('home')"
        >
          <BrandLogo /></TButton
        ><TButton
          theme="default"
          variant="outline"
          type="button"
          class="nav-home"
          :class="{ active: route.page === 'home' }"
          @click="open('home')"
        >
          {{ staff ? "＋" : "⌂" }}
          {{ t(staff ? "New course conversation" : "Home") }}
        </TButton>
        <p class="nav-caption">{{ t("MY COURSES") }}</p>
        <div class="course-navigation">
          <details
            v-for="item in courses.filter((c) => !c.archived)"
            :key="item.id"
            :open="item.id === route.courseId"
          >
            <summary>{{ item.title }}</summary>
            <TButton
              theme="default"
              variant="outline"
              type="button"
              @click="
                navigate({ page: 'course', courseId: item.id });
                menuOpen = false;
              "
            >
              {{
                t(staff ? "Course conversation" : "Course overview")
              }}</TButton
            ><template v-if="staff"
              ><TButton
                theme="default"
                variant="outline"
                type="button"
                :disabled="
                  route.page === 'course' && route.courseId === item.id && dirty
                "
                @click="
                  navigate({ page: 'task', courseId: item.id });
                  menuOpen = false;
                "
              >
                ＋ {{ t("Create task") }}</TButton
              ><TButton
                theme="default"
                variant="outline"
                type="button"
                @click="
                  navigate({ page: 'materials', courseId: item.id });
                  menuOpen = false;
                "
              >
                {{ t("Materials") }}
              </TButton></template
            ><TButton
              theme="default"
              variant="outline"
              type="button"
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
            </TButton>
          </details>
          <p v-if="!courses.length" class="muted small">
            {{ t("Your courses will appear here.") }}
          </p>
        </div>
        <nav class="secondary-nav">
          <TButton
            theme="default"
            variant="outline"
            type="button"
            v-if="!staff"
            @click="open('history')"
          >
            {{ t("Learning history") }}</TButton
          ><TButton
            theme="default"
            variant="outline"
            type="button"
            v-if="user.role === 'admin'"
            @click="open('accounts')"
          >
            {{ t("Account management") }}</TButton
          ><TButton
            theme="default"
            variant="outline"
            type="button"
            @click="open('settings')"
            >{{ t("Account settings") }}</TButton
          >
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
          ><TButton
            theme="default"
            variant="outline"
            type="button"
            @click="signOut"
            >{{ t("Sign out") }}</TButton
          >
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
          <TSelect
            v-control-attrs="{ 'aria-label': t('Interface language') }"
            :value="locale"
            @change="setLocale(String($event))"
          >
            <TOption value="zh-CN" label="中文" />
            <TOption value="en" label="English" />
          </TSelect>
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
                }}<TInput
                  v-control-attrs="{ required: true }"
                  v-model="passwordForm.currentPassword"
                  type="password"
                  autocomplete="current-password" /></label
              ><label
                >{{ t("New password")
                }}<TInput
                  v-control-attrs="{ minlength: '8', required: true }"
                  v-model="passwordForm.newPassword"
                  type="password"
                  autocomplete="new-password" /></label
              ><TButton
                theme="primary"
                variant="base"
                type="submit"
                class="primary"
                :disabled="busy"
              >
                {{ t("Save password") }}
              </TButton>
            </form></template
          >
          <TeacherChat
            v-else-if="staff && ['home', 'course'].includes(route.page)"
            :key="pageKey"
            :course-id="route.courseId"
          />
          <ClassroomHome
            v-else-if="!staff && ['home', 'course'].includes(route.page)"
            :key="pageKey"
            :course-id="route.courseId"
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
                  <span
                    class="badge status-label"
                    :data-status="record.status"
                    >{{ statusText(record.status) }}</span
                  >
                </div>
              </div>
              <TButton
                theme="default"
                variant="outline"
                type="button"
                @click="
                  navigate({
                    page: 'learn',
                    taskId: record.sessionId,
                    versionId: record.versionId,
                  })
                "
              >
                {{ t("View learning record") }}
              </TButton>
            </article>
            <p v-if="!historyRows.length" class="empty">
              {{ t("Your learning history will appear here.") }}
            </p>
          </section>
          <section
            v-else-if="user.role === 'admin' && route.page === 'accounts'"
          >
            <div class="page-heading">
              <h1>{{ t("Account management") }}</h1>
              <TButton
                theme="primary"
                variant="base"
                type="button"
                class="primary"
                @click="showAccount = true"
              >
                ＋ {{ t("Create account") }}
              </TButton>
            </div>
            <div class="panel table-wrap">
              <TTable
                row-key="id"
                :data="accountRows"
                :columns="[
                  { colKey: 'name', title: t('Name') },
                  { colKey: 'email', title: t('Email') },
                  { colKey: 'role', title: t('Role') },
                ]"
              >
                <template #role="{ row }">
                  {{
                    t(
                      row.role === "admin"
                        ? "Administrator"
                        : row.role === "teacher"
                          ? "Teacher"
                          : "Student",
                    )
                  }}
                </template>
              </TTable>
            </div>
          </section>
          <p v-else class="empty">
            {{ t("This page is not available to your role.") }}
          </p>
        </main>
        <footer>
          AIcademiya · {{ t("A considered space for learning.") }}
        </footer>
      </div>
      <AppDialog
        v-if="showAccount"
        :title="t('Create account')"
        @close="showAccount = false"
      >
        <form class="form-stack" @submit.prevent="createAccount">
          <label
            >{{ t("Name")
            }}<TInput
              v-control-attrs="{ required: true }"
              v-model="accountForm.name" /></label
          ><label
            >{{ t("Email")
            }}<TInput
              v-control-attrs="{ type: 'email', required: true }"
              v-model="accountForm.email" /></label
          ><label
            >{{ t("Password")
            }}<TInput
              v-control-attrs="{ minlength: '8', required: true }"
              v-model="accountForm.password"
              type="password" /></label
          ><label
            >{{ t("Role")
            }}<TSelect v-model="accountForm.role">
              <TOption value="student" :label="t('Student')" />
              <TOption value="teacher" :label="t('Teacher')" />
              <TOption value="admin" :label="t('Administrator')" /> </TSelect
          ></label>
          <div class="row end">
            <TButton
              theme="default"
              variant="outline"
              type="button"
              @click="showAccount = false"
            >
              {{ t("Cancel") }}</TButton
            ><TButton
              theme="primary"
              variant="base"
              type="submit"
              class="primary"
              :disabled="busy"
            >
              {{ t("Create account") }}
            </TButton>
          </div>
        </form>
      </AppDialog>
    </div>
  </TConfigProvider>
</template>
