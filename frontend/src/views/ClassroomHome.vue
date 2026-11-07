<script setup lang="ts">
import {
  Input as TInput,
  Button as TButton,
  MessagePlugin,
} from "tdesign-vue-next";
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { systemText, t } from "../i18n";
import { call, dateText, key } from "../classroom-api";
import {
  courses,
  navigate,
  refreshCourses,
  refreshCourseTasks,
  visibleCourseTasks,
} from "../classroom-state";

const props = defineProps<{ courseId?: string }>();
const course = computed(() =>
  courses.value.find((item) => item.id === props.courseId),
);
const activeCourses = computed(() =>
  courses.value.filter((item) => !item.archived),
);
const courseTasks = computed(() => visibleCourseTasks(props.courseId || ""));
const totalTasks = computed(() =>
  activeCourses.value.reduce(
    (count, item) => count + visibleCourseTasks(item.id).length,
    0,
  ),
);
const error = ref(""),
  busy = ref(false),
  joinCode = ref("");
let disposed = false;
let taskRefresh: ReturnType<typeof setTimeout>;
async function refreshTaskList() {
  const courseId = props.courseId;
  if (!courseId || disposed) return;
  try {
    if (!document.hidden) await refreshCourseTasks(courseId);
  } catch {
    // 保留上一次可用列表，下一次刷新重试。
  }
  if (!disposed) taskRefresh = setTimeout(refreshTaskList, 30000);
}
onMounted(refreshTaskList);
onBeforeUnmount(() => {
  disposed = true;
  clearTimeout(taskRefresh);
});

async function join() {
  if (disposed || busy.value || !joinCode.value.trim()) return;
  busy.value = true;
  error.value = "";
  try {
    await call("/courses/join?code=" + key(joinCode.value.trim()), "POST");
    await refreshCourses();
    if (disposed) return;
    joinCode.value = "";
    void MessagePlugin.success({
      content: t("Course joined. Open it from My courses."),
      duration: 4000,
      closeBtn: true,
    });
  } catch (e) {
    if (!disposed) error.value = systemText((e as Error).message);
  } finally {
    if (!disposed) busy.value = false;
  }
}
</script>

<template>
  <header class="page-heading">
    <div>
      <p class="eyebrow">{{ t("YOUR LEARNING") }}</p>
      <h1>{{ course?.title || t("My learning") }}</h1>
      <p class="muted">
        {{
          course?.description ||
          t("A clear place for every course, task and learning conversation.")
        }}
      </p>
    </div>
  </header>
  <p v-if="error" class="error" role="alert">{{ systemText(error) }}</p>
  <div v-if="!course" class="overview-grid">
    <div class="panel stat">
      <span>{{ t("My courses") }}</span
      ><strong>{{ activeCourses.length }}</strong>
    </div>
    <div class="panel stat">
      <span>{{ t("Learning tasks") }}</span
      ><strong>{{ totalTasks }}</strong>
    </div>
  </div>
  <form v-if="!course" class="panel row wrap" @submit.prevent="join">
    <label class="grow">
      {{ t("Course invitation code") }}
      <TInput
        v-control-attrs="{
          required: true,
          'aria-label': t('Course invitation code'),
        }"
        v-model="joinCode"
        maxlength="32"
        :disabled="busy"
        :placeholder="
          t('Enter the course invitation code provided by your teacher.')
        "
      />
      <small class="muted">
        {{
          t(
            "Use the course invitation code to join. Course codes and personal sign-in codes do not work here.",
          )
        }}
      </small>
    </label>
    <TButton
      theme="default"
      variant="outline"
      type="submit"
      :loading="busy"
      :disabled="busy || !joinCode.trim()"
    >
      {{ t(busy ? "Joining…" : "Join course") }}
    </TButton>
  </form>
  <h2>{{ t(course ? "Learning tasks" : "My courses") }}</h2>
  <div v-if="!course" class="course-grid">
    <article
      v-for="item in activeCourses"
      :key="item.id"
      class="panel course-card"
    >
      <span class="course-code">{{ item.code }}</span>
      <h3>{{ item.title }}</h3>
      <p class="muted">{{ item.description }}</p>
      <TButton
        theme="default"
        variant="outline"
        type="button"
        @click="navigate({ page: 'course', courseId: item.id })"
      >
        {{ t("Open course") }} →
      </TButton>
    </article>
  </div>
  <div v-else class="task-list">
    <article v-for="task in courseTasks" :key="task.id" class="panel task-card">
      <div class="task-icon">
        {{ task.sessionType === "tutor" ? "✦" : "▤" }}
      </div>
      <div class="grow">
        <div class="row wrap">
          <h3>{{ task.title }}</h3>
          <span class="badge status-label" data-status="open">
            {{ t("Open for responses") }}
          </span>
        </div>
        <p class="muted">{{ task.description }}</p>
        <small>{{
          t(task.sessionType === "tutor" ? "AI tutor" : "Assignment")
        }}</small>
        <small v-if="task.closesAt" class="muted task-closing-time">{{
          t("Closing time: {0}", [dateText(task.closesAt)])
        }}</small>
      </div>
      <TButton
        theme="default"
        variant="outline"
        type="button"
        @click="
          navigate({ page: 'learn', courseId: course.id, taskId: task.id })
        "
      >
        {{ t("Open task") }}
      </TButton>
    </article>
    <p v-if="!courseTasks.length" class="panel empty">
      {{ t("No tasks are currently open.") }}
    </p>
  </div>
</template>
