<script setup lang="ts">
import { Input as TInput, Button as TButton } from "tdesign-vue-next";
import { computed, ref } from "vue";
import { t } from "../i18n";
import { call, key } from "../classroom-api";
import { courses, navigate, refreshCourses, tasks } from "../classroom-state";

const props = defineProps<{ courseId?: string }>();
const course = computed(() =>
  courses.value.find((item) => item.id === props.courseId),
);
const activeCourses = computed(() =>
  courses.value.filter((item) => !item.archived),
);
const courseTasks = computed(() =>
  (tasks.value[props.courseId || ""] || []).filter((task) => !task.archived),
);
const totalTasks = computed(
  () =>
    Object.values(tasks.value)
      .flat()
      .filter((task) => !task.archived).length,
);
const error = ref(""),
  busy = ref(false),
  joinCode = ref("");

async function join() {
  busy.value = true;
  error.value = "";
  try {
    await call("/courses/join?code=" + key(joinCode.value), "POST");
    joinCode.value = "";
    await refreshCourses();
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
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
  <p v-if="error" class="error" role="alert">{{ error }}</p>
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
  <form v-if="!course" class="panel row" @submit.prevent="join">
    <label class="grow"
      >{{ t("Course invitation code")
      }}<TInput v-control-attrs="{ required: true }" v-model="joinCode"
    /></label>
    <TButton theme="default" variant="outline" type="submit" :disabled="busy">{{
      t("Join course")
    }}</TButton>
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
          <span
            class="badge status-label"
            :data-status="task.publishedVersionId ? 'published' : 'draft'"
          >
            {{ t(task.publishedVersionId ? "Published" : "Draft") }}
          </span>
        </div>
        <p class="muted">{{ task.description }}</p>
        <small>{{
          t(task.sessionType === "tutor" ? "AI tutor" : "Assignment")
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
      {{ t("Your teacher has not published a task yet.") }}
    </p>
  </div>
</template>
