<script setup lang="ts">
import { computed, ref } from "vue";
import { t } from "../../i18n";
import {
  call,
  dateText,
  key,
  statusText,
  versionParam,
  type LearningRecord,
  type StudentRow,
  type Task,
  type Version,
  type Workspace,
} from "../../classroom-api";
import TaskContent from "../components/TaskContent.vue";
import RichText from "../components/RichText.vue";
const props = defineProps<{ taskId: string }>();
const task = ref<Task | null>(null),
  versions = ref<Version[]>([]),
  versionId = ref(""),
  students = ref<StudentRow[]>([]),
  selected = ref<Workspace | null>(null);
const error = ref(""),
  busy = ref(false),
  filter = ref(""),
  note = ref("");
const visible = computed(() =>
  students.value.filter(
    (s) =>
      !filter.value ||
      `${s.name} ${s.email}`.toLowerCase().includes(filter.value.toLowerCase()),
  ),
);
const counters = computed(() => ({
  notStarted: students.value.filter((s) => s.status === "notStarted").length,
  inProgress: students.value.filter((s) => s.status === "inProgress").length,
  completed: students.value.filter((s) => s.status === "completed").length,
}));
async function refresh() {
  error.value = "";
  try {
    students.value = await call<StudentRow[]>(
      `/sessions/${key(props.taskId)}/students${versionParam(versionId.value)}`,
    );
    selected.value = null;
  } catch (e) {
    error.value = (e as Error).message;
  }
}
async function load() {
  try {
    task.value = await call<Task>(`/sessions/${key(props.taskId)}`);
    versions.value = await call<Version[]>(
      `/sessions/${key(props.taskId)}/versions`,
    );
    versionId.value = task.value.publishedVersionId || "";
    await refresh();
  } catch (e) {
    error.value = (e as Error).message;
  }
}
async function inspect(id: string) {
  error.value = "";
  try {
    selected.value = await call<Workspace>(`/records/${key(id)}/observe`);
    note.value = selected.value.record?.teacherNote || "";
  } catch (e) {
    error.value = (e as Error).message;
  }
}
async function review(status: string) {
  const record = selected.value?.record;
  if (!record) return;
  busy.value = true;
  error.value = "";
  try {
    const saved = await call<LearningRecord>(
      `/records/${key(record.id)}/review`,
      "POST",
      { revision: record.revision, status, teacherNote: note.value },
    );
    if (selected.value) selected.value.record = saved;
    students.value = await call<StudentRow[]>(
      `/sessions/${key(props.taskId)}/students${versionParam(versionId.value)}`,
    );
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
void load();
</script>
<template>
  <header class="page-heading">
    <div>
      <p class="eyebrow">{{ t("LEARNING PROGRESS") }}</p>
      <h1>{{ t("Student progress") }}</h1>
      <p class="muted">{{ task?.title }}</p>
    </div>
    <div class="row">
      <label
        >{{ t("Task version")
        }}<select v-model="versionId" @change="refresh">
          <option v-if="!versions.length" value="">
            {{ t("Not published") }}
          </option>
          <option
            v-for="version in versions"
            :key="version.id"
            :value="version.id"
          >
            {{ version.label
            }}{{
              version.id === task?.publishedVersionId
                ? ` · ${t("Current published version")}`
                : ""
            }}
          </option>
        </select></label
      ><button @click="refresh">{{ t("Refresh") }}</button>
    </div>
  </header>
  <p v-if="error" class="error" role="alert">{{ error }}</p>
  <div class="overview-grid">
    <div v-for="(count, status) in counters" :key="status" class="panel stat">
      <span>{{ statusText(status) }}</span
      ><strong>{{ count }}</strong>
    </div>
  </div>
  <section class="panel">
    <div class="row spread">
      <h2>
        {{ t("All students") }} <span class="muted">{{ students.length }}</span>
      </h2>
      <input
        v-model="filter"
        :placeholder="t('Search by name or email')"
        :aria-label="t('Search students')"
      />
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>{{ t("Student") }}</th>
            <th>{{ t("Participation") }}</th>
            <th>{{ t("Answers") }}</th>
            <th>{{ t("Last active") }}</th>
            <th>{{ t("Learning record") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="student in visible" :key="student.userId">
            <td>
              <strong>{{ student.name }}</strong
              ><small>{{ student.email }}</small>
            </td>
            <td>
              <span class="badge" :class="student.status">{{
                statusText(student.status)
              }}</span
              ><small
                v-if="
                  ['submitted', 'needsRevision'].includes(
                    student.submissionStatus,
                  )
                "
                >{{ statusText(student.submissionStatus) }}</small
              >
            </td>
            <td>{{ student.answered }} / {{ student.total }}</td>
            <td>{{ dateText(student.lastActive) }}</td>
            <td>
              <button
                :disabled="!student.recordId"
                @click="inspect(student.recordId!)"
              >
                {{ t("View answers and conversation") }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="!students.length" class="empty">
      {{ t("Add students to this course to see their participation.") }}
    </p>
  </section>
  <section v-if="selected?.record" class="review-section">
    <div class="page-heading">
      <h2>{{ t("Learning record") }}</h2>
      <button @click="selected = null">{{ t("Close record") }}</button>
    </div>
    <div class="learning-layout">
      <div class="panel">
        <TaskContent
          :task="selected.task"
          :answers="selected.record.answers"
          readonly
        />
        <details class="reference-review">
          <summary>{{ t("Teacher reference answers") }}</summary>
          <div
            v-for="(question, index) in selected.task.content.questions"
            :key="question.id"
          >
            <h4>{{ t("Question {0}", [index + 1]) }}</h4>
            <RichText :text="question.referenceAnswer || ''" /><RichText
              :text="question.explanation || ''"
            />
          </div>
        </details>
      </div>
      <aside class="panel">
        <h3>{{ t("Complete conversation history") }}</h3>
        <p v-if="!selected.record.messages.length" class="muted">
          {{ t("No conversation yet.") }}
        </p>
        <article
          v-for="(message, index) in selected.record.messages"
          :key="index"
          :class="['message', message.role]"
        >
          <small
            >{{ t(message.role === "user" ? "Student" : "AI tutor") }} ·
            {{ dateText(message.createdAt) }}</small
          ><RichText :text="message.content" />
        </article>
        <div class="form-stack teacher-feedback">
          <label
            >{{ t("Teacher feedback") }}<textarea v-model="note" rows="4" />
          </label>
          <div class="row wrap">
            <button
              :disabled="
                busy ||
                !['submitted', 'confirmed', 'needsRevision'].includes(
                  selected.record.status,
                )
              "
              @click="review('needsRevision')"
            >
              {{ t("Request revision") }}</button
            ><button
              class="primary"
              :disabled="
                busy ||
                !['submitted', 'confirmed', 'needsRevision'].includes(
                  selected.record.status,
                )
              "
              @click="review('confirmed')"
            >
              {{ t("Confirm completion") }}
            </button>
          </div>
        </div>
      </aside>
    </div>
  </section>
</template>
