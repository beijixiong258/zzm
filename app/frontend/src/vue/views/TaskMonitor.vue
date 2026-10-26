<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { t } from "../../i18n";
import {
  call,
  fileUrl,
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
import { dirty } from "../classroom-state";
import TaskContent from "../components/TaskContent.vue";
import RichText from "../components/RichText.vue";
import RecordHistory from "../components/RecordHistory.vue";
const props = defineProps<{ taskId: string }>();
const task = ref<Task | null>(null),
  versions = ref<Version[]>([]),
  versionId = ref(""),
  students = ref<StudentRow[]>([]),
  selected = ref<Workspace | null>(null);
const error = ref(""),
  busy = ref(false),
  loading = ref(true),
  inspecting = ref(false),
  filter = ref(""),
  note = ref(""),
  feedbackDrafts = ref<Record<string, string>>({});
let rosterSequence = 0,
  recordSequence = 0,
  disposed = false;
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
const edited = computed(() => {
  const record = selected.value?.record;
  return (
    !!record &&
    (note.value !== (record.teacherNote || "") ||
      record.messages.some(
        (message) =>
          message.pendingReview &&
          message.requestId &&
          feedbackDrafts.value[message.requestId] !== undefined &&
          feedbackDrafts.value[message.requestId] !== message.content,
      ))
  );
});
watch(edited, (value) => (dirty.value = value), { flush: "sync" });
function closeRecord() {
  if (
    busy.value ||
    (edited.value && !window.confirm(t("Discard unsaved changes?")))
  )
    return false;
  recordSequence++;
  inspecting.value = false;
  selected.value = null;
  note.value = "";
  feedbackDrafts.value = {};
  return true;
}
function changeVersion(event: Event) {
  const input = event.target as HTMLSelectElement;
  const nextVersion = input.value;
  input.value = versionId.value;
  if (!closeRecord()) return;
  versionId.value = nextVersion;
  void refresh();
}
function updateRecord(workspace: Workspace, record: LearningRecord) {
  const pending = new Set(
    record.messages
      .filter((message) => message.pendingReview)
      .map((message) => message.requestId),
  );
  for (const requestId of Object.keys(feedbackDrafts.value))
    if (!pending.has(requestId)) delete feedbackDrafts.value[requestId];
  workspace.record = record;
}
function isCurrentRecord(
  workspace: Workspace,
  recordId: string,
  sequence: number,
) {
  return (
    !disposed &&
    sequence === recordSequence &&
    selected.value === workspace &&
    workspace.record?.id === recordId
  );
}
async function refresh() {
  if (!closeRecord()) return;
  const sequence = ++rosterSequence;
  const requestedVersion = versionId.value;
  students.value = [];
  loading.value = true;
  error.value = "";
  try {
    const rows = await call<StudentRow[]>(
      `/sessions/${key(props.taskId)}/students${versionParam(requestedVersion)}`,
    );
    if (!disposed && sequence === rosterSequence) students.value = rows;
  } catch (e) {
    if (!disposed && sequence === rosterSequence)
      error.value = (e as Error).message;
  } finally {
    if (!disposed && sequence === rosterSequence) loading.value = false;
  }
}
async function load() {
  try {
    const [loadedTask, loadedVersions] = await Promise.all([
      call<Task>(`/sessions/${key(props.taskId)}`),
      call<Version[]>(`/sessions/${key(props.taskId)}/versions`),
    ]);
    if (disposed) return;
    task.value = loadedTask;
    versions.value = loadedVersions;
    versionId.value = loadedTask.publishedVersionId || "";
    await refresh();
  } catch (e) {
    if (!disposed) error.value = (e as Error).message;
  } finally {
    if (!disposed) loading.value = false;
  }
}
async function inspect(id: string) {
  if (busy.value || loading.value || !closeRecord()) return;
  const sequence = ++recordSequence;
  selected.value = null;
  note.value = "";
  inspecting.value = true;
  error.value = "";
  try {
    const workspace = await call<Workspace>(`/records/${key(id)}/observe`);
    if (disposed || sequence !== recordSequence) return;
    selected.value = workspace;
    note.value = workspace.record?.teacherNote || "";
  } catch (e) {
    if (!disposed && sequence === recordSequence)
      error.value = (e as Error).message;
  } finally {
    if (!disposed && sequence === recordSequence) inspecting.value = false;
  }
}
async function review(status: string) {
  const workspace = selected.value;
  const record = workspace?.record;
  if (busy.value || loading.value || inspecting.value || !workspace || !record)
    return;
  const sequence = recordSequence;
  const requestedVersion = versionId.value;
  busy.value = true;
  error.value = "";
  try {
    const saved = await call<LearningRecord>(
      `/records/${key(record.id)}/review`,
      "POST",
      { revision: record.revision, status, teacherNote: note.value },
    );
    if (!isCurrentRecord(workspace, record.id, sequence)) return;
    updateRecord(workspace, saved);
    const rows = await call<StudentRow[]>(
      `/sessions/${key(props.taskId)}/students${versionParam(requestedVersion)}`,
    );
    if (isCurrentRecord(workspace, record.id, sequence)) students.value = rows;
  } catch (e) {
    if (isCurrentRecord(workspace, record.id, sequence))
      error.value = (e as Error).message;
  } finally {
    if (!disposed) busy.value = false;
  }
}
async function approve(requestId: string, text: string) {
  const workspace = selected.value;
  const record = workspace?.record;
  if (busy.value || loading.value || inspecting.value || !workspace || !record)
    return;
  const sequence = recordSequence;
  busy.value = true;
  error.value = "";
  try {
    const saved = await call<LearningRecord>(
      `/records/${key(record.id)}/feedback/${key(requestId)}/approve`,
      "POST",
      { text },
    );
    if (isCurrentRecord(workspace, record.id, sequence))
      updateRecord(workspace, saved);
  } catch (e) {
    if (isCurrentRecord(workspace, record.id, sequence))
      error.value = (e as Error).message;
  } finally {
    if (!disposed) busy.value = false;
  }
}
onBeforeUnmount(() => {
  disposed = true;
  rosterSequence++;
  recordSequence++;
  dirty.value = false;
});
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
        }}<select
          :value="versionId"
          :disabled="busy || loading"
          @change="changeVersion"
        >
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
      ><button :disabled="busy || loading" @click="refresh">
        {{ t("Refresh") }}
      </button>
    </div>
  </header>
  <p v-if="error" class="error" role="alert">{{ error }}</p>
  <p v-if="loading" class="muted" role="status">{{ t("Loading…") }}</p>
  <div class="overview-grid progress-overview">
    <div
      v-for="(count, status) in counters"
      :key="status"
      class="panel stat"
      :data-status="status"
    >
      <span class="status-label" :data-status="status">{{
        statusText(status)
      }}</span
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
              <span class="badge status-label" :data-status="student.status">{{
                statusText(student.status)
              }}</span
              ><small
                class="status-label"
                :data-status="student.submissionStatus"
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
                :disabled="busy || loading || !student.recordId"
                @click="inspect(student.recordId!)"
              >
                {{ t("View answers and conversation") }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="!loading && !students.length" class="empty">
      {{ t("Add students to this course to see their participation.") }}
    </p>
  </section>
  <section v-if="selected?.record || inspecting" class="review-section">
    <div class="page-heading">
      <h2>{{ t("Learning record") }}</h2>
      <button :disabled="busy" @click="closeRecord">
        {{ t("Close record") }}
      </button>
    </div>
    <p v-if="inspecting" class="muted" role="status">{{ t("Loading…") }}</p>
    <div v-if="selected?.record" class="learning-layout">
      <div class="panel">
        <TaskContent
          :task="selected.task"
          :answers="selected.record.answers"
          readonly
        />
        <RecordHistory
          :record="selected.record"
          :questions="selected.task.content.questions"
          kind="answer"
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
          ><template v-if="message.pendingReview"
            ><p class="notice">
              {{ t("AI feedback is awaiting teacher review.") }}
            </p>
            <textarea
              :value="feedbackDrafts[message.requestId!] ?? message.content"
              @input="
                feedbackDrafts[message.requestId!] = (
                  $event.target as HTMLTextAreaElement
                ).value
              "
              :disabled="busy"
              rows="6"
              :aria-label="t('Review AI feedback')"
            /><button
              :disabled="busy"
              @click="
                approve(
                  message.requestId!,
                  feedbackDrafts[message.requestId!] ?? message.content,
                )
              "
            >
              {{ t("Approve and release feedback") }}
            </button></template
          ><RichText v-else :text="message.content" />
          <div v-for="id in message.attachmentIds || []" :key="id">
            <span
              v-if="selected.record.removedAttachments?.[id]"
              class="muted"
              >{{
                t("Removed attachment: {0}", [
                  selected.record.removedAttachments[id],
                ])
              }}</span
            >
            <a v-else :href="fileUrl(id)" target="_blank" rel="noopener">{{
              selected.attachments?.find((a) => a.id === id)?.title ||
              t("Attachment")
            }}</a>
          </div>
        </article>
        <RecordHistory
          :record="selected.record"
          :questions="selected.task.content.questions"
          kind="conversation"
        />
        <RecordHistory
          v-if="selected.record.messagesTruncated"
          :record="selected.record"
          :questions="selected.task.content.questions"
          kind="current"
        />
        <RecordHistory
          :record="selected.record"
          :questions="selected.task.content.questions"
          kind="attachment"
        />
        <section v-if="selected.attachments?.length">
          <h3>{{ t("Student attachments") }}</h3>
          <div v-for="file in selected.attachments" :key="file.id">
            <a :href="fileUrl(file.id)" target="_blank" rel="noopener">{{
              file.title
            }}</a>
            · {{ statusText(file.status)
            }}<small v-if="file.questionId">
              · {{ t("Question attachment") }}</small
            >
          </div>
        </section>
        <div class="form-stack teacher-feedback">
          <label
            >{{ t("Teacher feedback")
            }}<textarea v-model="note" rows="4" :disabled="busy" />
          </label>
          <div class="row wrap">
            <button
              class="warning-action"
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
              class="success-action"
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
