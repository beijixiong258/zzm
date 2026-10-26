<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { t, systemText } from "../i18n";
import {
  blankTask,
  questionTypes,
  call,
  fileUrl,
  key,
  statusText,
  studentTask,
  type Job,
  type Material,
  type Task,
  type Version,
  type ContextUsage,
  type TeacherReply,
  type StudentRow,
  type Workspace,
  type LearningRecord,
  type ChatMessage,
} from "../classroom-api";
import {
  dirty,
  navigate,
  refreshCourses,
  retainTaskAddress,
  user,
} from "../classroom-state";
import FileUploader from "../components/FileUploader.vue";
import AiConnection from "../components/AiConnection.vue";
import ContextMeter from "../components/ContextMeter.vue";
import StudentTask from "./StudentTask.vue";
import TaskContent from "../components/TaskContent.vue";
import ProgressStatus from "../components/ProgressStatus.vue";
import MaterialTree from "../components/MaterialTree.vue";
import CourseMaterialPreview from "../components/CourseMaterialPreview.vue";
import TeacherConversation from "../components/TeacherConversation.vue";
import RichText from "../components/RichText.vue";
import RecordHistory from "../components/RecordHistory.vue";
import AppDialog from "../components/AppDialog.vue";
import { useCourseMaterials } from "../useCourseMaterials";
const props = defineProps<{
  courseId: string;
  taskId: string;
}>();
const draft = ref<Task>(blankTask(props.courseId)),
  baseline = ref(""),
  versions = ref<Version[]>([]);
const {
  materials,
  error: materialError,
  load: loadMaterials,
} = useCourseMaterials(() => props.courseId);
const busy = ref(false),
  error = ref(""),
  success = ref(""),
  loading = ref(true),
  ready = ref(false),
  job = ref<Job | null>(null),
  selectedMaterial = ref<Material | null>(null);
const importSources = ref<string[]>([]);
const pendingUploads = ref(0);
const chatBusy = ref(false),
  choosingFiles = ref(false),
  showImportSources = ref(false),
  showPreview = ref(false);
const selectionIds = ref<string[]>([]),
  selectionPreviewId = ref(""),
  selectionError = ref("");
const selectionPanel = ref<HTMLElement | null>(null);
const selectionChanges = new Map<string, boolean>();
const selectionPreview = computed(() =>
  materials.value.find((m) => m.id === selectionPreviewId.value),
);
const activeMaterials = computed(() =>
  materials.value.filter((m) => !m.archived),
);
const students = ref<StudentRow[] | null>(null),
  observed = ref<Workspace | null>(null);
const conversationKey = computed(
  () =>
    `${user.value?.id}:task:${draft.value.id || props.taskId || props.courseId + ":new"}`,
);
const uploadVisibility = ref<"student" | "teacher">("student");
const usage = ref<ContextUsage | null>(null),
  checkingContext = ref(false),
  previewKey = ref(0);
let contextTimer: ReturnType<typeof setTimeout> | undefined,
  contextSequence = 0;
let timer: ReturnType<typeof setTimeout> | undefined;
let disposed = false;
let polling = false;
const active = computed(
  () => job.value && ["queued", "running"].includes(job.value.status),
);
const selected = computed(() =>
  materials.value.filter(
    (m) => !m.archived && draft.value.materialIds.includes(m.id),
  ),
);
const preview = computed(() =>
  studentTask({ ...draft.value, materials: selected.value }),
);
watch(
  draft,
  () => {
    dirty.value =
      !!baseline.value && JSON.stringify(draft.value) !== baseline.value;
  },
  { deep: true, flush: "sync" },
);
function accept(value: Task) {
  if (disposed) return;
  previewKey.value++;
  draft.value = value;
  baseline.value = JSON.stringify(value);
  dirty.value = false;
}
watch(materials, () => {
  if (selectedMaterial.value)
    selectedMaterial.value =
      materials.value.find(
        (material) => material.id === selectedMaterial.value?.id,
      ) || null;
  void checkContext();
});
async function checkContext() {
  const sequence = ++contextSequence;
  if (!draft.value.title.trim() || disposed) {
    checkingContext.value = false;
    usage.value = null;
    return;
  }
  checkingContext.value = true;
  try {
    const next = await call<ContextUsage>(
      `/courses/${key(props.courseId)}/context-budget`,
      "POST",
      draft.value,
    );
    if (sequence === contextSequence) usage.value = next;
  } catch {
    if (sequence === contextSequence) usage.value = null;
  } finally {
    if (sequence === contextSequence) checkingContext.value = false;
  }
}
watch(
  draft,
  () => {
    clearTimeout(contextTimer);
    contextSequence++;
    checkingContext.value = false;
    usage.value = null;
    contextTimer = setTimeout(() => void checkContext(), 700);
  },
  { deep: true },
);
function uploaded(material: Material) {
  if (!materials.value.some((item) => item.id === material.id))
    materials.value.push(material);
  chooseMaterial(material.id, true);
  if (choosingFiles.value && !selectionIds.value.includes(material.id))
    selectionIds.value.push(material.id);
  void loadMaterials();
}
async function retryMaterial(material = selectedMaterial.value) {
  if (!material) return;
  await action(async () => {
    await call(`/materials/${key(material.id)}/retry`, "POST");
    await loadMaterials();
  });
}
async function simulate() {
  await action(async () => {
    await saveDraft();
  });
}
async function load() {
  if (disposed) return;
  loading.value = true;
  ready.value = false;
  error.value = "";
  try {
    if (!(await loadMaterials()) || disposed) return;
    if (props.taskId) {
      accept(await call<Task>(`/sessions/${key(props.taskId)}`));
      versions.value = await call<Version[]>(
        `/sessions/${key(props.taskId)}/versions`,
      );
      const jobs = await call<Job[]>(
        `/sessions/${key(props.taskId)}/generations`,
      );
      job.value = jobs[0] || null;
      if (
        job.value &&
        ["queued", "running", "succeeded"].includes(job.value.status)
      )
        schedulePoll();
    } else {
      accept(blankTask(props.courseId));
    }
    if (!disposed) ready.value = true;
  } catch (e) {
    if (!disposed) error.value = (e as Error).message;
  } finally {
    if (!disposed) loading.value = false;
  }
}
async function action(fn: () => Promise<void>) {
  if (busy.value || !ready.value || disposed) return;
  busy.value = true;
  error.value = "";
  success.value = "";
  try {
    await fn();
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
async function saveDraft() {
  if (!draft.value.title.trim()) throw Error(t("Enter a task name first."));
  const path = draft.value.id
    ? `/sessions/${key(draft.value.id)}`
    : `/courses/${key(props.courseId)}/sessions`;
  const sentIds = new Set(draft.value.materialIds);
  const result = await call<Task>(
    path,
    draft.value.id ? "PUT" : "POST",
    draft.value,
  );
  const uploadedDuringSave = draft.value.materialIds.filter(
    (id) => !sentIds.has(id),
  );
  accept(result);
  uploadedDuringSave.forEach((id) => chooseMaterial(id, true));
  retainTaskAddress(result.id);
  await refreshCourses();
  return result;
}
async function save() {
  await action(async () => {
    await saveDraft();
    success.value = t("Draft saved.");
  });
}
async function generate(
  kind = "generate",
  instruction = draft.value.additionalInstructions,
) {
  if (pendingUploads.value) return false;
  importSources.value = importSources.value.filter((id) =>
    draft.value.materialIds.includes(id),
  );
  if (
    kind === "generate" &&
    draft.value.content.questions.length &&
    !window.confirm(
      t(
        "Generate a new lesson from these materials? The published version will remain available.",
      ),
    )
  )
    return false;
  let started = false;
  await action(async () => {
    await saveDraft();
    job.value = await call<Job>(
      `/sessions/${key(draft.value.id)}/generations`,
      "POST",
      {
        revision: draft.value.revision,
        kind,
        sourceMaterialIds: importSources.value,
        instruction,
      },
    );
    accept(await call<Task>(`/sessions/${key(draft.value.id)}`));
    schedulePoll();
    started = true;
  });
  return started;
}
function schedulePoll() {
  clearTimeout(timer);
  if (!disposed)
    timer = setTimeout(() => {
      void poll();
    }, 2000);
}
async function poll() {
  if (!job.value || disposed || polling) return;
  clearTimeout(timer);
  polling = true;
  try {
    const next = await call<Job>(`/generations/${key(job.value.id)}`);
    if (disposed) return;
    job.value = next;
    if (next.status === "succeeded") {
      if (dirty.value) {
        error.value = t(
          "The draft changed during generation. Save your changes before trying again.",
        );
        return;
      }
      accept(await call<Task>(`/generations/${key(next.id)}/apply`, "POST"));
      job.value.status = "applied";
      success.value = t(
        "AI content is ready. Review the student preview before publishing.",
      );
      await refreshCourses();
    } else if (["queued", "running"].includes(next.status)) schedulePoll();
  } catch (e) {
    if (!disposed) {
      error.value = (e as Error).message;
      schedulePoll();
    }
  } finally {
    polling = false;
  }
}
async function publish() {
  await action(async () => {
    if (dirty.value || !draft.value.id) await saveDraft();
    if (!window.confirm(t("Publish this task to students?"))) return;
    await call(`/sessions/${key(draft.value.id)}/publish`, "POST", {
      revision: draft.value.revision,
    });
    accept(await call<Task>(`/sessions/${key(draft.value.id)}`));
    versions.value = await call<Version[]>(
      `/sessions/${key(draft.value.id)}/versions`,
    );
    await refreshCourses();
    success.value = t("Task published.");
  });
}
async function restore(versionId: string) {
  if (
    !window.confirm(
      t("Restore this version into the draft? Unsaved edits will be replaced."),
    )
  )
    return;
  await action(async () => {
    await call(
      `/sessions/${key(draft.value.id)}/versions/${key(versionId)}/restore`,
      "POST",
      { revision: draft.value.revision },
    );
    accept(await call<Task>(`/sessions/${key(draft.value.id)}`));
    success.value = t("Version restored into the draft.");
  });
}
function chooseMaterial(id: string, checked: boolean) {
  if (checked && !draft.value.materialIds.includes(id))
    draft.value.materialIds.push(id);
  if (!checked)
    draft.value.materialIds = draft.value.materialIds.filter(
      (value) => value !== id,
    );
}
async function openFileSelection() {
  selectionIds.value = [...draft.value.materialIds];
  selectionChanges.clear();
  selectionPreviewId.value = "";
  selectionError.value = "";
  choosingFiles.value = true;
  await nextTick();
  selectionPanel.value?.focus();
  void loadMaterials();
}
function changeSelection(id: string, checked: boolean) {
  selectionChanges.set(id, checked);
  selectionIds.value = checked
    ? [...new Set([...selectionIds.value, id])]
    : selectionIds.value.filter((value) => value !== id);
}
function cancelSelection() {
  choosingFiles.value = false;
  selectionChanges.clear();
  selectionError.value = "";
}
function saveSelection() {
  const chosen = new Set(draft.value.materialIds);
  // Apply only the user's changes, so uploads completing after opening are retained.
  for (const [id, checked] of selectionChanges) {
    if (checked) chosen.add(id);
    else chosen.delete(id);
  }
  const activeIds = new Set(activeMaterials.value.map((m) => m.id));
  const nextIds = [...chosen].filter((id) => activeIds.has(id));
  const references = [
    ...(draft.value.content.illustrationMaterialIds || []),
    ...draft.value.content.questions.flatMap((q) => [
      ...(q.sourceMaterialIds || []),
      ...(q.imageMaterialIds || []),
    ]),
  ];
  if (references.some((id) => !nextIds.includes(id))) {
    selectionError.value = t(
      "Some materials are referenced by existing questions or illustrations. Keep them selected or revise those references first. No questions were removed.",
    );
    return;
  }
  draft.value.materialIds = nextIds;
  importSources.value = importSources.value.filter((id) =>
    nextIds.includes(id),
  );
  cancelSelection();
}
async function viewProgress() {
  if (!draft.value.id) throw Error(t("Save the task before viewing progress."));
  students.value = await call<StudentRow[]>(
    `/sessions/${key(draft.value.id)}/students`,
  );
}
async function observe(recordId: string | null) {
  if (!recordId) return;
  await action(async () => {
    observed.value = await call<Workspace>(`/records/${key(recordId)}/observe`);
  });
}
async function reviewObserved(status: "confirmed" | "needsRevision") {
  const workspace = observed.value;
  const record = workspace?.record;
  if (!workspace || !record) return;
  await action(async () => {
    const saved = await call<LearningRecord>(
      `/records/${key(record.id)}/review`,
      "POST",
      {
        revision: record.revision,
        status,
        teacherNote: record.teacherNote,
      },
    );
    if (observed.value === workspace) workspace.record = saved;
    await viewProgress();
  });
}
async function approveObserved(message: ChatMessage) {
  const workspace = observed.value;
  const record = workspace?.record;
  if (!workspace || !record || !message.requestId) return;
  await action(async () => {
    const saved = await call<LearningRecord>(
      `/records/${key(record.id)}/feedback/${key(message.requestId!)}/approve`,
      "POST",
      { text: message.content },
    );
    if (observed.value === workspace) workspace.record = saved;
  });
}
async function configure(reply: TeacherReply, message: string) {
  const fields = [
    "title",
    "description",
    "sessionType",
    "topic",
    "learningGoals",
    "additionalInstructions",
    "teachingLanguage",
  ] as const;
  let changed = false;
  for (const field of fields)
    if (Object.hasOwn(reply.fields, field)) {
      (draft.value as unknown as Record<string, unknown>)[field] =
        reply.fields[field];
      changed = true;
    }
  if (Object.hasOwn(reply.fields, "teachingMode")) {
    if (!["guided", "autonomous"].includes(reply.fields.teachingMode))
      throw Error(t("Invalid teaching or feedback mode"));
    draft.value.content.teachingMode = reply.fields.teachingMode as
      "guided" | "autonomous";
    changed = true;
  }
  if (Object.hasOwn(reply.fields, "feedbackMode")) {
    if (!["immediate", "teacherReview"].includes(reply.fields.feedbackMode))
      throw Error(t("Invalid teaching or feedback mode"));
    draft.value.content.feedbackMode = reply.fields.feedbackMode as
      "immediate" | "teacherReview";
    changed = true;
  }
  let outcome = "";
  if (changed) {
    if (draft.value.title.trim()) {
      await saveDraft();
      outcome = t("Task configuration saved to the draft.");
    } else
      outcome = t(
        "The task draft is retained here. Tell AI a task name to save it.",
      );
  }
  if (reply.action === "selectFiles") await openFileSelection();
  else if (reply.action === "import") showImportSources.value = true;
  else if (["generate", "revise"].includes(reply.action)) {
    if (pendingUploads.value)
      return (
        outcome +
        "\n" +
        t("Wait for the current uploads to finish before generating.")
      );
    const started = await generate(reply.action, message);
    if (error.value) throw Error(error.value);
    if (started)
      outcome += "\n" + t("Generation started. Progress is shown below.");
  } else if (reply.action === "preview") showPreview.value = true;
  else if (reply.action === "publish")
    outcome +=
      "\n" +
      t(
        "Review the preview, then use Publish task below to confirm publication.",
      );
  else if (reply.action === "progress") await viewProgress();
  else if (
    ["files", "members", "inviteStudent", "newTask"].includes(reply.action)
  )
    outcome +=
      "\n" +
      t(
        "Use the course conversation for course-level changes and student invitations.",
      );
  return outcome.trim();
}
onBeforeUnmount(() => {
  disposed = true;
  clearTimeout(timer);
  clearTimeout(contextTimer);
  contextSequence++;
  dirty.value = false;
});
void load();
</script>
<template>
  <ProgressStatus v-if="loading" :label="t('Loading…')" />
  <div v-else-if="!ready" class="panel">
    <p class="error">{{ systemText(error || materialError) }}</p>
    <button @click="load">{{ t("Retry") }}</button>
  </div>
  <template v-else>
    <div v-show="!choosingFiles" class="teacher-chat-page task-chat">
      <header class="conversation-heading">
        <div>
          <p class="eyebrow">{{ t("Task conversation") }}</p>
          <strong>{{ draft.title || t("New task conversation") }}</strong>
        </div>
        <div class="row wrap">
          <button
            :disabled="busy || chatBusy || !!active"
            @click="navigate({ page: 'course', courseId })"
          >
            {{ t("Course conversation") }}
          </button>
          <button
            :disabled="busy || chatBusy || !!active"
            @click="navigate({ page: 'materials', courseId })"
          >
            {{ t("File management") }}
          </button>
        </div>
      </header>
      <p v-if="error || materialError" role="alert" class="error">
        {{ systemText(error || materialError) }}
      </p>
      <p v-if="success" role="status" class="success">
        {{ systemText(success) }}
      </p>
      <TeacherConversation
        :conversation-key="conversationKey"
        :context="{
          scope: 'task',
          courseId,
          taskId: draft.id || null,
          taskDraft: draft,
        }"
        :apply-reply="configure"
        :disabled="busy || !!active"
        @pending="chatBusy = $event"
        :welcome="
          t(
            'Tell me the task name, teaching language and learning goal. Attach materials, then ask me to generate, import or revise the lesson.',
          )
        "
      >
        <template #attachments>
          <div class="task-attachment-tools">
            <details class="upload-visibility">
              <summary>
                {{ t("Visibility for new uploads") }} ·
                {{
                  t(
                    uploadVisibility === "student"
                      ? "Students and teachers"
                      : "Teachers and AI only",
                  )
                }}
              </summary>
              <label
                >{{ t("Visibility")
                }}<select
                  v-model="uploadVisibility"
                  :disabled="busy || chatBusy || !!active"
                >
                  <option value="student">
                    {{ t("Students and teachers") }}
                  </option>
                  <option value="teacher">
                    {{ t("Teachers and AI only") }}
                  </option>
                </select></label
              >
            </details>
            <FileUploader
              :endpoint="'/courses/' + key(courseId) + '/materials'"
              :visibility="uploadVisibility"
              :disabled="busy || chatBusy || !!active"
              @pending="pendingUploads = $event"
              @uploaded="uploaded"
              @settled="loadMaterials"
            >
              <template #actions
                ><button
                  type="button"
                  :disabled="busy || chatBusy || !!active"
                  @click="openFileSelection"
                >
                  {{ t("Select files") }}
                </button></template
              >
            </FileUploader>
            <div v-if="selected.length" class="selected-materials">
              <small>{{
                t("Selected materials: {0}", [selected.length])
              }}</small>
              <button
                v-for="material in selected"
                :key="material.id"
                type="button"
                @click="selectedMaterial = material"
              >
                {{ material.title }}
                <small>{{ statusText(material.status) }}</small>
              </button>
            </div>
            <p v-else class="empty selected-empty">
              {{
                t(
                  "No task materials selected. Upload files or choose existing course files.",
                )
              }}
            </p>
          </div>
        </template>
        <template #results>
          <details v-if="draft.title" class="conversation-result">
            <summary>{{ t("Current task configuration") }}</summary>
            <dl class="configuration-summary">
              <dt>{{ t("Task name") }}</dt>
              <dd>{{ draft.title }}</dd>
              <dt>{{ t("Task type") }}</dt>
              <dd>
                {{
                  t(
                    draft.sessionType === "assignment"
                      ? "Assignment"
                      : "AI tutor",
                  )
                }}
              </dd>
              <dt>{{ t("Teaching language") }}</dt>
              <dd>
                {{ draft.teachingLanguage === "zh-CN" ? "中文" : "English" }}
              </dd>
              <dt>{{ t("Learning goals") }}</dt>
              <dd>{{ draft.learningGoals || "—" }}</dd>
              <dt>{{ t("Additional instructions for AI") }}</dt>
              <dd>{{ draft.additionalInstructions || "—" }}</dd>
            </dl>
          </details>
          <div class="conversation-actions row wrap">
            <button :disabled="busy || chatBusy || !!active" @click="save">
              {{ t("Save draft") }}
            </button>
            <button
              :disabled="
                busy ||
                chatBusy ||
                !!active ||
                pendingUploads > 0 ||
                usage?.materialsReady === false
              "
              @click="generate('generate')"
            >
              {{
                t(
                  draft.content.handout
                    ? "Regenerate lesson"
                    : "Generate lesson",
                )
              }}
            </button>
            <button
              :disabled="busy || chatBusy || !!active || !selected.length"
              @click="showImportSources = true"
            >
              {{ t("Import existing worksheet") }}
            </button>
            <button
              v-if="draft.content.handout"
              :disabled="
                busy ||
                chatBusy ||
                !!active ||
                pendingUploads > 0 ||
                !draft.additionalInstructions?.trim() ||
                usage?.materialsReady === false
              "
              @click="generate('revise')"
            >
              {{ t("Revise with these instructions") }}
            </button>
            <button
              v-if="draft.content.handout"
              :disabled="busy || chatBusy || !!active"
              @click="showPreview = true"
            >
              {{ t("Student preview") }}
            </button>
            <button
              v-if="draft.content.handout"
              class="primary"
              :disabled="busy || chatBusy || !!active"
              @click="publish"
            >
              {{ t("Publish task") }}
            </button>
            <button
              v-if="draft.id"
              :disabled="busy || chatBusy"
              @click="action(viewProgress)"
            >
              {{ t("Student progress") }}
            </button>
          </div>
          <details class="conversation-result">
            <summary>{{ t("Local token estimate") }}</summary>
            <ContextMeter
              :usage="usage"
              :loading="checkingContext"
            /><AiConnection />
          </details>
          <section v-if="job" class="conversation-result generation-state">
            <ProgressStatus
              v-if="active || job.status === 'succeeded'"
              :label="statusText(job.stage)"
              :detail="
                job.progressCharacters
                  ? t(
                      'Received {0} characters. The complete lesson will appear after validation.',
                      [job.progressCharacters],
                    )
                  : t(
                      'Waiting for AI output. Progress updates automatically; you can leave this page and return later.',
                    )
              "
            />
            <strong v-else>{{ statusText(job.status) }}</strong>
            <p v-if="job.errorMessage" class="error">
              {{ systemText(job.errorMessage) }}
            </p>
            <details v-if="job.diagnosticResponse">
              <summary>{{ t("Model response for diagnosis") }}</summary>
              <pre class="diagnostic-response">{{
                job.diagnosticResponse
              }}</pre>
            </details>
            <details v-if="job.usage">
              <summary>{{ t("Provider usage") }}</summary>
              <ContextMeter :usage="job.usage" />
            </details>
            <button
              v-if="['queued', 'running', 'succeeded'].includes(job.status)"
              :disabled="busy"
              @click="poll"
            >
              {{ t("Refresh generation status") }}
            </button>
          </section>
          <section
            v-if="draft.content.handout"
            class="conversation-result lesson-result"
          >
            <h2>{{ draft.title }}</h2>
            <RichText :text="draft.content.handout" />
            <details v-if="draft.content.questions.length">
              <summary>
                {{ t("Questions and reference answers") }} ·
                {{ draft.content.questions.length }}
              </summary>
              <article
                v-for="(question, index) in draft.content.questions"
                :key="question.id"
                class="question-review"
              >
                <strong
                  >{{ index + 1 }}.
                  {{
                    t(
                      questionTypes[
                        question.type as keyof typeof questionTypes
                      ] || question.type,
                    )
                  }}</strong
                ><RichText :text="question.prompt" />
                <ul v-if="question.options?.length">
                  <li v-for="option in question.options" :key="option">
                    {{ option }}
                  </li>
                </ul>
                <p>
                  <strong>{{ t("Reference answer") }}</strong>
                </p>
                <RichText
                  v-if="question.referenceAnswer"
                  :text="question.referenceAnswer"
                />
                <p v-else class="muted">
                  {{
                    t(
                      "No source reference answer. AI will give qualitative feedback on the student's response.",
                    )
                  }}
                </p>
              </article>
            </details>
          </section>
          <section v-if="students" class="conversation-result">
            <strong>{{ t("Student progress") }}</strong>
            <button
              v-for="student in students"
              :key="student.userId"
              class="progress-row"
              :disabled="!student.recordId || busy"
              @click="observe(student.recordId)"
            >
              <span>{{ student.name }}</span
              ><span
                >{{ statusText(student.status) }} · {{ student.answered }}/{{
                  student.total
                }}</span
              >
            </button>
            <p v-if="!students.length" class="muted">
              {{ t("No students have joined this course yet.") }}
            </p>
          </section>
          <details v-if="versions.length" class="conversation-result">
            <summary>{{ t("Published versions") }}</summary>
            <div
              v-for="version in versions"
              :key="version.id"
              class="row spread"
            >
              <span>{{ version.label }}</span
              ><button
                :disabled="busy || chatBusy || !!active"
                @click="restore(version.id)"
              >
                {{ t("Restore to draft") }}
              </button>
            </div>
          </details>
        </template>
      </TeacherConversation>
    </div>
    <section
      v-if="choosingFiles"
      ref="selectionPanel"
      tabindex="-1"
      class="material-selection"
      @keydown.esc.prevent="cancelSelection"
    >
      <header class="conversation-heading">
        <button @click="cancelSelection">← {{ t("Back to task") }}</button>
        <h1>{{ t("Select files") }}</h1>
        <div class="row">
          <button @click="cancelSelection">{{ t("Cancel") }}</button
          ><button class="primary" @click="saveSelection">
            {{ t("Save") }}
          </button>
        </div>
      </header>
      <p class="muted">
        {{
          t(
            "Save confirms only this material selection. It does not save or create the task.",
          )
        }}
      </p>
      <p v-if="pendingUploads" class="notice">
        {{
          t(
            "Uploads continue in the background. Newly uploaded materials stay selected.",
          )
        }}
        · {{ pendingUploads }}
      </p>
      <p v-if="selectionError || materialError" class="error" role="alert">
        {{ systemText(selectionError || materialError) }}
      </p>
      <div class="material-selection-layout">
        <aside class="panel">
          <MaterialTree
            :materials="activeMaterials"
            selectable
            :checked="selectionIds"
            :selected="selectionPreviewId"
            @check="changeSelection"
            @select="selectionPreviewId = $event.id"
          />
          <p v-if="!activeMaterials.length" class="empty">
            {{
              t(
                "No active course materials are available. Return to the task to upload files.",
              )
            }}
          </p>
        </aside>
        <section class="panel">
          <template v-if="selectionPreview"
            ><CourseMaterialPreview :material="selectionPreview" />
            <button
              v-if="!['queued', 'processing'].includes(selectionPreview.status)"
              :disabled="busy"
              @click="retryMaterial(selectionPreview)"
            >
              {{ t("Reprocess material") }}
            </button>
          </template>
          <p v-else class="empty">
            {{ t("Select a material from the folder tree to preview it.") }}
          </p>
        </section>
      </div>
    </section>
  </template>
  <AppDialog
    v-if="showImportSources"
    :title="t('Worksheet source materials')"
    @close="showImportSources = false"
  >
    <div class="form-stack">
      <p class="muted">
        {{
          t(
            "Choose which selected task materials contain the original questions. This does not change task materials.",
          )
        }}
      </p>
      <label v-for="material in selected" :key="material.id" class="check-label"
        ><input
          v-model="importSources"
          type="checkbox"
          :value="material.id"
          :disabled="!['ready', 'needsReview'].includes(material.status)"
        />{{ material.title }}</label
      >
      <p v-if="!selected.length" class="empty">
        {{
          t(
            "No task materials selected. Upload files or choose existing course files.",
          )
        }}
      </p>
      <div class="row end">
        <button @click="showImportSources = false">{{ t("Cancel") }}</button
        ><button
          class="primary"
          :disabled="
            busy ||
            !!active ||
            pendingUploads > 0 ||
            !importSources.length ||
            usage?.materialsReady === false
          "
          @click="
            showImportSources = false;
            generate('import');
          "
        >
          {{ t("Extract worksheet questions") }}
        </button>
      </div>
    </div>
  </AppDialog>
  <AppDialog
    v-if="selectedMaterial && !choosingFiles"
    :title="t('Material preview')"
    wide
    @close="selectedMaterial = null"
  >
    <CourseMaterialPreview :material="selectedMaterial" />
    <button
      v-if="!['queued', 'processing'].includes(selectedMaterial.status)"
      :disabled="busy"
      @click="retryMaterial(selectedMaterial)"
    >
      {{ t("Reprocess material") }}
    </button>
  </AppDialog>
  <AppDialog
    v-if="showPreview"
    :title="t('Student preview')"
    wide
    @close="showPreview = false"
  >
    <button v-if="dirty" :disabled="busy" @click="simulate">
      {{ t("Save and refresh preview") }}
    </button>
    <StudentTask
      v-if="draft.id && draft.content.handout && !dirty"
      :key="draft.id + '-' + previewKey"
      :task-id="draft.id"
      preview
    />
    <TaskContent v-else :task="preview" preview readonly />
  </AppDialog>
  <AppDialog
    v-if="observed"
    :title="t('Learning record')"
    wide
    :busy="busy"
    @close="observed = null"
  >
    <p v-if="error" role="alert" class="error">{{ systemText(error) }}</p>
    <TaskContent
      :task="observed.task"
      :answers="observed.record?.answers"
      readonly
    />
    <article
      v-for="(message, index) in observed.record?.messages || []"
      :key="index"
      class="message"
    >
      <small>{{
        t(message.role === "user" ? "Student" : "AI assistant")
      }}</small
      ><RichText :text="message.content" />
      <button
        v-if="message.pendingReview && message.requestId"
        :disabled="busy"
        @click="approveObserved(message)"
      >
        {{ t("Approve and release feedback") }}
      </button>
    </article>
    <template v-if="observed.record">
      <RecordHistory
        v-for="kind in ['answer', 'conversation', 'attachment'] as const"
        :key="kind"
        :record="observed.record"
        :questions="observed.task.content.questions"
        :kind="kind"
      />
      <RecordHistory
        v-if="observed.record.messagesTruncated"
        :record="observed.record"
        :questions="observed.task.content.questions"
        kind="current"
      />
      <p v-for="attachment in observed.attachments || []" :key="attachment.id">
        <a :href="fileUrl(attachment.id)" target="_blank" rel="noopener">{{
          attachment.title
        }}</a>
        · {{ statusText(attachment.status) }}
      </p>
      <p v-if="observed.record.teacherNote">
        {{ t("Teacher feedback:") }} {{ observed.record.teacherNote }}
      </p>
      <div class="row wrap">
        <button
          :disabled="
            busy ||
            !['submitted', 'confirmed', 'needsRevision'].includes(
              observed.record.status,
            )
          "
          @click="reviewObserved('needsRevision')"
        >
          {{ t("Request revision") }}
        </button>
        <button
          :disabled="
            busy ||
            !['submitted', 'confirmed', 'needsRevision'].includes(
              observed.record.status,
            )
          "
          @click="reviewObserved('confirmed')"
        >
          {{ t("Confirm completion") }}
        </button>
      </div>
    </template>
  </AppDialog>
</template>
