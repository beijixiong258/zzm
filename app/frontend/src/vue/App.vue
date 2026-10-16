<script setup lang="ts">
import { computed, defineAsyncComponent, ref } from "vue";
import {
  BookOpen,
  Settings2,
  History,
  LogOut,
  Menu,
  X,
  GraduationCap,
  ArrowLeft,
} from "lucide-vue-next";
import { api } from "../api";
import { canAccessRoute } from "../routes";
import {
  user,
  bootstrap,
  courses,
  route,
  staff,
  initialize,
  navigate,
  useTask,
  confirmLeave,
  confirmation,
  resolveConfirm,
} from "./state";
import EditorDialog from "./components/EditorDialog.vue";
import FeedbackNotice from "./components/FeedbackNotice.vue";
import LoginView from "./views/LoginView.vue";
import HomeView from "./views/HomeView.vue";
const TeacherView = defineAsyncComponent(
  () => import("./views/TeacherView.vue"),
);
const LearningView = defineAsyncComponent(
  () => import("./views/LearningView.vue"),
);
const VersionsView = defineAsyncComponent(
  () => import("./views/VersionsView.vue"),
);
const PeopleView = defineAsyncComponent(() => import("./views/PeopleView.vue"));
const SettingsView = defineAsyncComponent(
  () => import("./views/SettingsView.vue"),
);
const LibraryView = defineAsyncComponent(
  () => import("./views/LibraryView.vue"),
);
const HistoryView = defineAsyncComponent(
  () => import("./views/HistoryView.vue"),
);
const { busy, error, run } = useTask();
const mobile = ref(false),
  ready = ref(false);
const active = computed(() =>
  ["settings", "profile", "accounts"].includes(route.value.page)
    ? "settings"
    : route.value.page === "history"
      ? "history"
      : "home",
);
async function boot() {
  await run(initialize);
  ready.value = true;
}
void boot();
async function logout() {
  if (!(await confirmLeave())) return;
  await run(async () => {
    await api.logout();
    mobile.value = false;
    user.value = null;
    courses.value = [];
    route.value = { page: "home" };
    location.hash = "/home";
  });
}
</script>
<template>
  <div v-if="!ready" class="boot-screen">
    <img src="/aicademiya-mark.svg" alt="" />
    <p>Opening your workspace…</p>
  </div>
  <LoginView v-else-if="!user" :bootstrap="bootstrap" @authenticated="boot" />
  <div v-else class="app-shell">
    <aside class="sidebar" :class="{ visible: mobile }">
      <a
        href="#/home"
        class="brand"
        @click.prevent="
          navigate({ page: 'home' });
          mobile = false;
        "
        ><img src="/aicademiya-mark.svg" alt="" /><span
          >AIcademiya<small>TEACHING & LEARNING</small></span
        ></a
      >
      <div class="nav-heading">
        <p class="nav-label">WORKSPACE</p>
        <button
          class="icon-button mobile-toggle"
          aria-label="Close menu"
          @click="mobile = false"
        >
          <X :size="20" />
        </button>
      </div>
      <nav aria-label="Main navigation">
        <button
          :class="{ active: active === 'home' }"
          @click="
            navigate({ page: 'home' });
            mobile = false;
          "
        >
          <BookOpen :size="19" /> Courses</button
        ><button
          v-if="!staff"
          :class="{ active: active === 'history' }"
          @click="
            navigate({ page: 'history' });
            mobile = false;
          "
        >
          <History :size="19" /> Learning history</button
        ><button
          :class="{ active: active === 'settings' }"
          @click="
            navigate({ page: 'settings', section: 'account' });
            mobile = false;
          "
        >
          <Settings2 :size="19" /> Settings
        </button>
      </nav>
      <div class="sidebar-bottom">
        <div class="user-summary">
          <span class="avatar"
            ><img
              v-if="user.avatar_url"
              :src="user.avatar_url"
              alt=""
            /><template v-else>{{ user.name.slice(0, 1) }}</template></span
          >
          <div>
            <strong>{{ user.name }}</strong
            ><small>{{
              user.role === "admin"
                ? "Administrator"
                : staff
                  ? "Teacher"
                  : "Student"
            }}</small>
          </div>
        </div>
        <button class="sidebar-logout" :disabled="busy" @click="logout">
          <LogOut :size="16" /> Sign out
        </button>
      </div>
    </aside>
    <button
      v-if="mobile"
      class="nav-overlay"
      aria-label="Close navigation"
      @click="mobile = false"
    />
    <div class="app-main">
      <header class="topbar">
        <button
          class="icon-button mobile-toggle"
          aria-label="Toggle navigation"
          :aria-expanded="mobile"
          @click="mobile = !mobile"
        >
          <X v-if="mobile" :size="21" /><Menu v-else :size="21" /></button
        ><span class="topbar-label"
          ><GraduationCap :size="18" />
          {{ staff ? "Teaching workspace" : "Learning workspace" }}</span
        ><span v-if="bootstrap?.demo_enabled" class="badge local"
          >Local demo</span
        ><span v-else class="badge">Local workspace</span>
      </header>
      <main>
        <FeedbackNotice :error="error" /><button
          v-if="route.page !== 'home' && active !== 'settings'"
          class="back-button"
          @click="navigate({ page: 'home' })"
        >
          <ArrowLeft :size="15" /> Back to courses
        </button>
        <SettingsView
          v-if="user.must_change_password"
          :key="user.id"
          force-password
        />
        <p
          v-else-if="!canAccessRoute(user.role, route.page)"
          class="notice error"
        >
          This page is not available to your role.
        </p>
        <HomeView
          v-else-if="route.page === 'home' || route.page === 'course-trash'"
          :key="route.page"
        />
        <TeacherView
          v-else-if="route.page === 'teacher' && route.sid"
          :key="route.sid"
          :sid="route.sid"
        />
        <LearningView
          v-else-if="['workspace', 'record'].includes(route.page) && route.sid"
          :key="`${route.sid}:${route.uid}:${route.version}`"
          :sid="route.sid"
          :uid="route.uid"
          :version="route.version"
        />
        <VersionsView
          v-else-if="route.page === 'versions' && route.sid"
          :key="route.sid"
          :course-id="route.sid"
        />
        <PeopleView
          v-else-if="route.page === 'roster' && route.sid"
          :key="route.sid"
          :course-id="route.sid"
        />
        <LibraryView
          v-else-if="route.page === 'course-materials' && route.sid"
          :key="route.sid"
          :course-id="route.sid"
        />
        <HistoryView v-else-if="route.page === 'history'" />
        <SettingsView v-else :key="`${route.section}:${route.page}`" />
      </main>
      <footer class="app-footer">
        AIcademiya <span>A considered space for learning.</span>
      </footer>
    </div>
  </div>
  <FeedbackNotice v-if="!user" :error="error" />
  <EditorDialog
    v-if="confirmation"
    title="Confirm action"
    compact
    @close="resolveConfirm(false)"
    ><p>{{ confirmation.message }}</p>
    <template #actions
      ><button class="primary" @click="resolveConfirm(true)">
        Confirm
      </button></template
    ></EditorDialog
  >
</template>
