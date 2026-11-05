<script setup lang="ts">
import { Button as TButton } from "tdesign-vue-next";
import { computed, ref } from "vue";
import { call, key, type TaskSummary } from "../classroom-api";
import { courses, refreshCourses, tasks } from "../classroom-state";
import { confirmAction } from "../confirmAction";
import { systemText, t } from "../i18n";

const busy = ref(false),
  error = ref("");
const archivedTasks = computed(() =>
  courses.value.flatMap((course) =>
    (tasks.value[course.id] || [])
      .filter((task) => task.archived)
      .map((task) => ({ ...task, courseTitle: course.title })),
  ),
);
async function refresh() {
  busy.value = true;
  error.value = "";
  try {
    await refreshCourses();
  } catch (e) {
    error.value = systemText((e as Error).message);
  } finally {
    busy.value = false;
  }
}
async function manage(task: TaskSummary, remove: boolean) {
  if (busy.value) return;
  if (
    remove &&
    !(await confirmAction(
      t(
        "Permanently delete {0}? This removes the task, published versions, generation records, student learning records and conversations. Course materials are kept; student attachments move to the recycle folder. This cannot be undone in the application.",
        [task.title],
      ),
    ))
  )
    return;
  busy.value = true;
  error.value = "";
  try {
    await call(
      `/sessions/${key(task.id)}${remove ? "" : "/archive?archived=false"}`,
      remove ? "DELETE" : "POST",
    );
    await refreshCourses();
  } catch (e) {
    error.value = systemText((e as Error).message);
  } finally {
    busy.value = false;
  }
}
void refresh();
</script>

<template>
  <header class="page-heading">
    <div>
      <h1>{{ t("Archived tasks") }}</h1>
      <p class="muted">
        {{
          t(
            "Archived tasks are hidden from students. Restore a task to make it available again, or permanently delete it.",
          )
        }}
      </p>
    </div>
    <TButton
      theme="default"
      variant="outline"
      :disabled="busy"
      @click="refresh"
      >{{ t("Refresh") }}</TButton
    >
  </header>
  <p v-if="error" class="error" role="alert">{{ error }}</p>
  <div class="task-list">
    <article
      v-for="task in archivedTasks"
      :key="task.id"
      class="panel task-card archived-task-card"
    >
      <div class="grow">
        <h2>{{ task.title }}</h2>
        <p class="muted">{{ task.courseTitle }}</p>
      </div>
      <div class="row wrap">
        <TButton
          theme="primary"
          :disabled="busy"
          @click="manage(task, false)"
          >{{ t("Restore task") }}</TButton
        >
        <TButton
          theme="danger"
          variant="outline"
          :disabled="busy"
          @click="manage(task, true)"
          >{{ t("Delete permanently") }}</TButton
        >
      </div>
    </article>
    <p v-if="!archivedTasks.length" class="panel empty">
      {{ t(busy ? "Loading…" : "No archived tasks.") }}
    </p>
  </div>
</template>
