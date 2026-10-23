<script setup lang="ts">
import { ref } from "vue";
import { t } from "../../i18n";
import { call, key, type Course, type TaskSummary } from "../../classroom-api";
import { courses, dirty, refreshCourses } from "../classroom-state";
import TaskEditor from "./TaskEditor.vue";
const workspace = ref<Course | null>(null),
  items = ref<TaskSummary[]>([]),
  error = ref(""),
  editing = ref(false),
  taskId = ref(""),
  mode = ref("tutor");
const copyTargets = ref<Record<string, string>>({});
const copying = ref("");
async function copyResource(id: string) {
  if (!copyTargets.value[id] || copying.value) return;
  copying.value = id;
  error.value = "";
  try {
    await call(
      "/sessions/" + key(id) + "/copy?courseId=" + key(copyTargets.value[id]),
      "POST",
    );
    await refreshCourses();
    copyTargets.value[id] = "";
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    copying.value = "";
  }
}
async function load() {
  try {
    workspace.value = await call<Course>("/workbench", "POST");
    items.value = await call<TaskSummary[]>(
      `/courses/${key(workspace.value.id)}/sessions`,
    );
  } catch (e) {
    error.value = (e as Error).message;
  }
}
function open(id = "", tool = "tutor") {
  taskId.value = id;
  mode.value = tool;
  editing.value = true;
}
async function back() {
  if (dirty.value && !window.confirm(t("Leave without saving your changes?")))
    return;
  dirty.value = false;
  editing.value = false;
  await load();
}
void load();
</script>
<template>
  <p v-if="error" class="error" role="alert">{{ error }}</p>
  <template v-if="workspace && editing"
    ><button class="workbench-back" @click="back">
      ← {{ t("Back to workbench") }}</button
    ><TaskEditor
      :key="`${taskId}-${mode}`"
      :course-id="workspace.id"
      :task-id="taskId"
      :initial-mode="mode"
      workbench
  /></template>
  <template v-else
    ><header class="page-heading">
      <div>
        <p class="eyebrow">{{ t("TEACHER TOOLS") }}</p>
        <h1>{{ t("Teacher workbench") }}</h1>
        <p class="muted">
          {{
            t(
              "Create and save reusable teaching resources before adding them to a course.",
            )
          }}
        </p>
      </div>
    </header>
    <div class="overview-grid">
      <button
        v-for="tool in ['tutor', 'reading', 'worksheet']"
        :key="tool"
        class="panel workbench-tool"
        :disabled="!workspace"
        @click="open('', tool)"
      >
        <strong>{{
          t(
            tool === "tutor"
              ? "Adaptive tutor"
              : tool === "reading"
                ? "Reading and rewriting"
                : "Worksheets and handouts",
          )
        }}</strong>
        <p>
          {{
            t(
              tool === "tutor"
                ? "Design instructions and rehearse a conversation with your tutor."
                : tool === "reading"
                  ? "Turn source materials into an accessible lesson and revise it with AI."
                  : "Create practice, extract existing questions and prepare editable learning resources.",
            )
          }}
        </p>
      </button>
    </div>
    <h2>{{ t("Saved resources and templates") }}</h2>
    <article
      v-for="item in items.filter((i) => !i.archived)"
      :key="item.id"
      class="panel task-card"
    >
      <div class="grow">
        <h3>{{ item.title }}</h3>
        <p>{{ item.description }}</p>
      </div>
      <div class="row wrap">
        <button @click="open(item.id)">{{ t("Open and edit") }}</button>
        <select
          v-model="copyTargets[item.id]"
          :aria-label="t('Destination course')"
        >
          <option value="">{{ t("Choose a course") }}</option>
          <option
            v-for="course in courses.filter((c) => !c.archived && !c.workspace)"
            :key="course.id"
            :value="course.id"
          >
            {{ course.title }}
          </option>
        </select>
        <button
          :disabled="!copyTargets[item.id] || !!copying"
          @click="copyResource(item.id)"
        >
          {{ t("Add to course") }}
        </button>
      </div>
    </article>
    <p v-if="!items.length" class="empty">
      {{ t("Your saved resources will appear here.") }}
    </p>
  </template>
</template>
