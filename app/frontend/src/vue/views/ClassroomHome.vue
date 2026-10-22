<script setup lang="ts">
import { computed, ref } from "vue";
import { t } from "../../i18n";
import { call, key, type ChatMessage, type Course } from "../../classroom-api";
import {
  courses,
  navigate,
  refreshCourses,
  staff,
  tasks,
} from "../classroom-state";
import RichText from "../components/RichText.vue";
const props = defineProps<{ courseId?: string }>();
const course = computed(() =>
  courses.value.find((c) => c.id === props.courseId),
);
const courseTasks = computed(() => tasks.value[props.courseId || ""] || []);
const error = ref(""),
  busy = ref(false),
  showCourse = ref(false),
  editing = ref("");
const form = ref({
  title: "",
  code: "",
  description: "",
  systemInstructions: "",
});
const prompt = ref(""),
  messages = ref<ChatMessage[]>([]),
  assistantBusy = ref(false),
  showArchived = ref(false),
  joinCode = ref("");
const totalTasks = computed(
  () =>
    Object.values(tasks.value)
      .flat()
      .filter((s) => !s.archived).length,
);
function edit(value?: Course) {
  editing.value = value?.id || "";
  form.value = {
    title: value?.title || "",
    code: value?.code || "",
    description: value?.description || "",
    systemInstructions: value?.systemInstructions || "",
  };
  showCourse.value = true;
}
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
async function saveCourse() {
  await action(async () => {
    const saved = await call<Course>(
      editing.value ? `/courses/${key(editing.value)}` : "/courses",
      editing.value ? "PUT" : "POST",
      form.value,
    );
    await refreshCourses();
    showCourse.value = false;
    navigate({ page: "course", courseId: saved.id });
  });
}
async function archiveCourse(value: Course) {
  if (
    !window.confirm(
      t(
        value.archived
          ? "Restore this course?"
          : "Archive this course and hide it from students?",
      ),
    )
  )
    return;
  await action(async () => {
    await call(
      `/courses/${key(value.id)}/archive?archived=${!value.archived}`,
      "POST",
    );
    await refreshCourses();
  });
}
async function archiveTask(id: string, archived: boolean) {
  if (
    !window.confirm(
      t(
        archived
          ? "Restore this task?"
          : "Archive this task? Learning records will be retained.",
      ),
    )
  )
    return;
  await action(async () => {
    await call(`/sessions/${key(id)}/archive?archived=${!archived}`, "POST");
    await refreshCourses();
  });
}
async function ask() {
  if (!prompt.value.trim() || assistantBusy.value) return;
  const message = prompt.value.trim();
  assistantBusy.value = true;
  error.value = "";
  try {
    const reply = await call<{ message: string }>(
      "/teacher/assistant",
      "POST",
      {
        message,
        requestId: crypto.randomUUID(),
        history: messages.value.slice(-30),
        courseId: course.value?.id || null,
      },
    );
    messages.value.push(
      { role: "user", content: message },
      { role: "assistant", content: reply.message },
    );
    prompt.value = "";
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    assistantBusy.value = false;
  }
}
async function join() {
  await action(async () => {
    await call(`/courses/join?code=${key(joinCode.value)}`, "POST");
    joinCode.value = "";
    await refreshCourses();
  });
}
</script>
<template>
  <header class="page-heading">
    <div>
      <p class="eyebrow">
        {{ t(staff ? "TEACH & ORGANIZE" : "YOUR LEARNING") }}
      </p>
      <h1>{{ course?.title || t(staff ? "Teaching home" : "My learning") }}</h1>
      <p class="muted">
        {{
          course?.description ||
          t("A clear place for every course, task and learning conversation.")
        }}
      </p>
    </div>
    <button v-if="staff && !course" class="primary" @click="edit()">
      ＋ {{ t("Create course") }}
    </button>
  </header>
  <p v-if="error" class="error" role="alert">{{ error }}</p>
  <section v-if="staff && !course" class="panel assistant-panel">
    <div class="row spread">
      <div>
        <h2>{{ t("Teaching assistant") }}</h2>
        <p class="muted">
          {{ t("Discuss a lesson idea, learning goal or classroom activity.") }}
        </p>
      </div>
      <span class="ai-mark">✦</span>
    </div>
    <div v-if="messages.length" class="chat-messages">
      <article
        v-for="(message, index) in messages"
        :key="index"
        :class="['message', message.role]"
      >
        <small>{{ t(message.role === "user" ? "You" : "AI assistant") }}</small
        ><RichText :text="message.content" />
      </article>
    </div>
    <form class="assistant-compose" @submit.prevent="ask">
      <textarea
        v-model="prompt"
        :disabled="assistantBusy"
        :aria-label="t('Message to the teaching assistant')"
        :placeholder="t('What would you like to prepare for your students?')"
        rows="3"
      /><button class="primary" :disabled="assistantBusy || !prompt.trim()">
        {{ t(assistantBusy ? "Thinking…" : "Send") }}
      </button>
    </form>
  </section>
  <div v-if="!course" class="overview-grid">
    <div class="panel stat">
      <span>{{ t("My courses") }}</span
      ><strong>{{ courses.filter((c) => !c.archived).length }}</strong>
    </div>
    <div class="panel stat">
      <span>{{ t("Learning tasks") }}</span
      ><strong>{{ totalTasks }}</strong>
    </div>
    <div v-if="staff" class="panel coming-soon">
      <strong>{{ t("Classroom insights") }}</strong>
      <p class="muted">
        {{ t("More teaching overview panels will be added here.") }}
      </p>
    </div>
  </div>
  <form v-if="!staff && !course" class="panel row" @submit.prevent="join">
    <label class="grow"
      >{{ t("Course invitation code")
      }}<input v-model="joinCode" required /></label
    ><button :disabled="busy">{{ t("Join course") }}</button>
  </form>
  <div v-if="course" class="course-toolbar panel row wrap">
    <button
      v-if="staff"
      class="primary"
      :disabled="course.archived"
      @click="navigate({ page: 'task', courseId: course.id })"
    >
      ＋ {{ t("Create task") }}</button
    ><button
      v-if="staff"
      @click="navigate({ page: 'materials', courseId: course.id })"
    >
      {{ t("Course materials") }}</button
    ><button
      v-if="staff"
      @click="navigate({ page: 'people', courseId: course.id })"
    >
      {{ t("Manage class") }}</button
    ><button v-if="staff" @click="edit(course)">
      {{ t("Course settings") }}</button
    ><span v-if="staff" class="muted"
      >{{ t("Invitation code") }}: <strong>{{ course.joinCode }}</strong></span
    ><button
      v-if="staff"
      class="text-button"
      :disabled="busy"
      @click="archiveCourse(course)"
    >
      {{ t(course.archived ? "Restore" : "Archive") }}
    </button>
  </div>
  <div class="row spread">
    <h2>{{ t(course ? "Learning tasks" : "My courses") }}</h2>
    <label v-if="staff" class="check-label"
      ><input v-model="showArchived" type="checkbox" />{{
        t("Show archived items")
      }}</label
    >
  </div>
  <div v-if="!course" class="course-grid">
    <article
      v-for="item in courses.filter((c) => showArchived || !c.archived)"
      :key="item.id"
      class="panel course-card"
    >
      <div class="row spread">
        <span class="course-code">{{ item.code }}</span
        ><span v-if="item.archived" class="badge">{{ t("Archived") }}</span>
      </div>
      <h3>{{ item.title }}</h3>
      <p class="muted">{{ item.description }}</p>
      <button
        v-if="!item.archived"
        @click="navigate({ page: 'course', courseId: item.id })"
      >
        {{ t("Open course") }} →</button
      ><button v-else :disabled="busy" @click="archiveCourse(item)">
        {{ t("Restore") }}
      </button>
    </article>
  </div>
  <div v-else class="task-list">
    <article
      v-for="task in courseTasks.filter((s) => showArchived || !s.archived)"
      :key="task.id"
      class="panel task-card"
    >
      <div class="task-icon">
        {{ task.sessionType === "tutor" ? "✦" : "▤" }}
      </div>
      <div class="grow">
        <div class="row wrap">
          <h3>{{ task.title }}</h3>
          <span class="badge">{{
            t(
              task.archived
                ? "Archived"
                : task.publishedVersionId
                  ? "Published"
                  : "Draft",
            )
          }}</span>
        </div>
        <p class="muted">{{ task.description }}</p>
        <small>{{
          t(task.sessionType === "tutor" ? "AI tutor" : "Assignment")
        }}</small>
      </div>
      <div class="row wrap">
        <button
          v-if="!task.archived"
          @click="
            navigate({
              page: staff ? 'task' : 'learn',
              courseId: course.id,
              taskId: task.id,
            })
          "
        >
          {{ t(staff ? "Edit task" : "Open task") }}</button
        ><button
          v-if="staff"
          @click="
            navigate({ page: 'monitor', courseId: course.id, taskId: task.id })
          "
        >
          {{ t("Student progress") }}</button
        ><button
          v-if="staff"
          class="text-button"
          :disabled="busy"
          @click="archiveTask(task.id, task.archived)"
        >
          {{ t(task.archived ? "Restore" : "Archive") }}
        </button>
      </div>
    </article>
    <p v-if="!courseTasks.length" class="panel empty">
      {{
        t(
          staff
            ? "Create the first learning task for this course."
            : "Your teacher has not published a task yet.",
        )
      }}
    </p>
  </div>
  <div
    v-if="showCourse"
    class="modal-backdrop"
    @click.self="showCourse = false"
  >
    <form
      class="modal form-stack"
      role="dialog"
      aria-modal="true"
      :aria-label="t('Course settings')"
      @submit.prevent="saveCourse"
    >
      <h2>{{ t(editing ? "Course settings" : "Create course") }}</h2>
      <label
        >{{ t("Course name")
        }}<input v-model="form.title" required maxlength="300" /></label
      ><label
        >{{ t("Course code")
        }}<input v-model="form.code" required maxlength="100" /></label
      ><label
        >{{ t("Description")
        }}<textarea v-model="form.description" rows="3" /></label
      ><label
        >{{ t("Course-wide teaching instructions")
        }}<textarea
          v-model="form.systemInstructions"
          rows="5"
          :placeholder="
            t(
              'Set common teaching principles, student context and boundaries for all tasks in this course.',
            )
          "
        /><small>{{
          t("Inherited by the AI tutor; not shown to students.")
        }}</small></label
      >
      <div class="row end">
        <button type="button" @click="showCourse = false">
          {{ t("Cancel") }}</button
        ><button class="primary" :disabled="busy">{{ t("Save") }}</button>
      </div>
    </form>
  </div>
</template>
