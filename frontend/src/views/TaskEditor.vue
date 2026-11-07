<script setup lang="ts">
import { confirmAction } from "../confirmAction";
import {
  Button as TButton,
  Dropdown as TDropdown,
  Select as TSelect,
  Option as TOption,
  MessagePlugin,
  type DropdownOption,
} from "tdesign-vue-next";
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { t, systemText } from "../i18n";
import {
  blankTask,
  call,
  dateText,
  assessmentStatusText,
  fileUrl,
  key,
  statusText,
  studentTask,
  taskAvailability,
  type Job,
  type Material,
  type Task,
  type ContextUsage,
  type StudentRow,
  type Workspace,
  type LearningRecord,
  type ChatMessage,
  type TaskSchedule,
  type AssessmentSummary,
} from "../classroom-api";
import {
  dirty,
  navigate,
  refreshCourses,
  retainTaskAddress,
  taskTime,
} from "../classroom-state";
import FileUploader from "../components/FileUploader.vue";
import ContextMeter from "../components/ContextMeter.vue";
import StudentTask from "./StudentTask.vue";
import TaskContent from "../components/TaskContent.vue";
import ProgressStatus from "../components/ProgressStatus.vue";
import MaterialTree from "../components/MaterialTree.vue";
import CourseMaterialPreview from "../components/CourseMaterialPreview.vue";
import LessonEditor from "../components/LessonEditor.vue";
import RichText from "../components/RichText.vue";
import RecordHistory from "../components/RecordHistory.vue";
import AppDialog from "../components/AppDialog.vue";
import TaskScheduleDialog from "../components/TaskScheduleDialog.vue";
import FormativeAssessmentPanel from "../components/FormativeAssessmentPanel.vue";
import { useCourseMaterials } from "../useCourseMaterials";
const props = defineProps<{
  courseId: string;
  taskId: string;
}>();
const draft = ref<Task>(blankTask(props.courseId)),
  baseline = ref("");
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
  showGenerationState = ref(false),
  selectedMaterial = ref<Material | null>(null);
const pendingUploads = ref(0);
const taskActionsVisible = ref(false);
const checkingConnection = ref(false);
const choosingFiles = ref(false),
  showPreview = ref(false);
const previewMode = ref<"edit" | "student">("edit");
const scheduleDialog = ref<"publish" | "edit" | "reopen" | null>(null);
let uploadsChanged = false;
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
const studentProgressPanel = ref<HTMLElement | null>(null);
const usage = ref<ContextUsage | null>(null),
  checkingContext = ref(false),
  previewKey = ref(0);
let contextTimer: ReturnType<typeof setTimeout> | undefined,
  contextSequence = 0;
let timer: ReturnType<typeof setTimeout> | undefined;
let connectionRequest: AbortController | undefined;
let disposed = false;
let polling = false;
const active = computed(
  () => job.value && ["queued", "running"].includes(job.value.status),
);
const availability = computed(() =>
  taskAvailability(draft.value, taskTime.value),
);
const needsReopening = computed(() =>
  ["expired", "closed"].includes(availability.value),
);
const hasContent = computed(
  () =>
    !!draft.value.content.handout?.trim() ||
    draft.value.content.questions.length > 0,
);
const selected = computed(() =>
  materials.value.filter(
    (m) => !m.archived && draft.value.materialIds.includes(m.id),
  ),
);
const materialsReady = computed(
  () =>
    selected.value.length > 0 &&
    selected.value.every((material) =>
      ["ready", "needsReview"].includes(material.status),
    ),
);
const taskActions = computed<DropdownOption[]>(() => [
  {
    content: t("Edit task"),
    value: "edit",
    disabled: busy.value || !!active.value,
    onClick: () => {
      previewMode.value = "edit";
      showPreview.value = true;
    },
  },
  ...(draft.value.id
    ? [
        {
          content: t("Student progress"),
          value: "progress",
          disabled: busy.value,
          onClick: () => {
            void action(async () => {
              await viewProgress();
              await nextTick();
              studentProgressPanel.value?.scrollIntoView({
                block: "start",
                behavior: "smooth",
              });
            });
          },
        },
      ]
    : []),
  ...(draft.value.publishedVersionId && !needsReopening.value
    ? [
        {
          content: t("Change availability"),
          value: "availability",
          disabled: busy.value || !!active.value,
          onClick: openAvailabilityEditor,
        },
      ]
    : []),
  {
    content: t("File management"),
    value: "files",
    disabled: busy.value || !!active.value,
    onClick: () => {
      void openFileSelection();
    },
  },
  {
    content: t(
      checkingConnection.value ? "Checking connection…" : "Test AI connection",
    ),
    value: "connection",
    disabled: checkingConnection.value,
    onClick: () => {
      void checkAiConnection();
    },
  },
  ...(draft.value.id
    ? [
        {
          content: t("Archive task"),
          value: "archive",
          disabled: busy.value || !!active.value || pendingUploads.value > 0,
          onClick: () => {
            void archiveTask();
          },
        },
      ]
    : []),
]);
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
  if (
    selectionPreviewId.value &&
    !activeMaterials.value.some(
      (material) => material.id === selectionPreviewId.value,
    )
  )
    selectionPreviewId.value = "";
  void checkContext();
});
async function checkContext() {
  const sequence = ++contextSequence;
  if (
    (!draft.value.title.trim() && !draft.value.materialIds.length) ||
    disposed
  ) {
    checkingContext.value = false;
    usage.value = null;
    return;
  }
  checkingContext.value = true;
  try {
    const next = await call<ContextUsage>(
      `/courses/${key(props.courseId)}/context-budget`,
      "POST",
      { ...draft.value, title: draft.value.title || t("Untitled task") },
    );
    if (sequence === contextSequence) usage.value = next;
  } catch {
    if (sequence === contextSequence) usage.value = null;
  } finally {
    if (sequence === contextSequence) checkingContext.value = false;
  }
}
function showConnectionMessage(content: string, connected = false) {
  const showMessage = connected ? MessagePlugin.success : MessagePlugin.error;
  void showMessage({
    content,
    placement: "top",
    duration: 4000,
    closeBtn: true,
    style: { maxWidth: "calc(100vw - 32px)" },
  });
}
async function checkAiConnection() {
  if (disposed || checkingConnection.value) return;
  checkingConnection.value = true;
  taskActionsVisible.value = false;
  const controller = new AbortController();
  connectionRequest = controller;
  const timeout = setTimeout(() => controller.abort(), 18000);
  try {
    const result = await call<{
      connected: boolean;
      model: string;
      elapsedMs: number;
      detail?: string;
    }>("/ai/connection", "POST", undefined, controller.signal);
    if (disposed) return;
    const summary = `${t(result.connected ? "Connection successful" : "Connection failed")} · ${result.model} · ${result.elapsedMs} ms`;
    showConnectionMessage(
      summary + (result.detail ? ` — ${systemText(result.detail)}` : ""),
      result.connected,
    );
  } catch (e) {
    if (!disposed)
      showConnectionMessage(
        controller.signal.aborted
          ? t("The connection check did not finish in time. Try again shortly.")
          : systemText((e as Error).message),
      );
  } finally {
    clearTimeout(timeout);
    connectionRequest = undefined;
    if (!disposed) checkingConnection.value = false;
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
  if (disposed) return;
  if (!materials.value.some((item) => item.id === material.id))
    materials.value.push(material);
  if (!draft.value.materialIds.includes(material.id))
    draft.value.materialIds.push(material.id);
  uploadsChanged = true;
  void loadMaterials();
}
async function uploadsPending(count: number) {
  pendingUploads.value = count;
  if (count) return;
  // 上传组件先更新待处理数量，再发出最后一份材料的事件。
  await nextTick();
  if (pendingUploads.value || !uploadsChanged || disposed) return;
  await action(async () => {
    await saveDraft(false);
    uploadsChanged = false;
  });
}
async function retryMaterial(material = selectedMaterial.value) {
  if (!material) return;
  await action(async () => {
    await call(`/materials/${key(material.id)}/retry`, "POST");
    await loadMaterials();
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
      const jobs = await call<Job[]>(
        `/sessions/${key(props.taskId)}/generations`,
      );
      job.value = jobs[0] || null;
      showGenerationState.value =
        !!job.value &&
        ["queued", "running", "succeeded"].includes(job.value.status);
      if (showGenerationState.value) schedulePoll();
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
async function saveDraft(updatePublished = true) {
  if (!draft.value.title.trim()) draft.value.title = t("Untitled task");
  const path = draft.value.id
    ? `/sessions/${key(draft.value.id)}`
    : `/courses/${key(props.courseId)}/sessions`;
  const result = await call<Task>(path, draft.value.id ? "PUT" : "POST", {
    ...draft.value,
    updatePublished,
  });
  if (disposed) return result;
  accept(result);
  retainTaskAddress(result.id);
  await refreshCourses();
  return result;
}
async function archiveTask() {
  if (!draft.value.id || busy.value || active.value || pendingUploads.value)
    return;
  if (
    !(await confirmAction(
      t(
        "Archive {0}? Students will no longer see this task. You can restore it in Archived tasks. Unsaved changes will not be saved.",
        [draft.value.title],
      ),
    ))
  )
    return;
  await action(async () => {
    await call(
      `/sessions/${key(draft.value.id)}/archive?archived=true`,
      "POST",
    );
    dirty.value = false;
    await refreshCourses();
    await navigate({ page: "archives" });
  });
}
async function save() {
  await action(async () => {
    await saveDraft();
    success.value = t(
      draft.value.publishedVersionId ? "Task updated." : "Draft saved.",
    );
  });
}
async function generate() {
  if (pendingUploads.value || !materialsReady.value) return false;
  if (
    hasContent.value &&
    !(await confirmAction(
      t(
        "Generate a new lesson from these materials? The published version will remain available.",
      ),
    ))
  )
    return false;
  let started = false;
  await action(async () => {
    await saveDraft(false);
    if (disposed) return;
    job.value = await call<Job>(
      `/sessions/${key(draft.value.id)}/generations`,
      "POST",
      {
        revision: draft.value.revision,
        kind: "generate",
      },
    );
    showGenerationState.value = true;
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
      previewMode.value = "edit";
      showPreview.value = true;
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
function requestPublish() {
  if (draft.value.publishedVersionId) {
    void publish();
  } else {
    error.value = "";
    scheduleDialog.value = "publish";
  }
}
function openAvailabilityEditor() {
  error.value = "";
  scheduleDialog.value = needsReopening.value ? "reopen" : "edit";
}
async function publish(schedule?: TaskSchedule) {
  await action(async () => {
    if (dirty.value || !draft.value.id) await saveDraft(false);
    if (disposed) return;
    const updating = !!draft.value.publishedVersionId;
    await call(`/sessions/${key(draft.value.id)}/publish`, "POST", {
      revision: draft.value.revision,
      ...schedule,
    });
    scheduleDialog.value = null;
    accept(await call<Task>(`/sessions/${key(draft.value.id)}`));
    await refreshCourses();
    success.value = t(updating ? "Task updated." : "Task published.");
  });
}
async function saveAvailability(schedule: TaskSchedule) {
  if (scheduleDialog.value === "publish") {
    await publish(schedule);
    return;
  }
  const reopening = scheduleDialog.value === "reopen";
  await action(async () => {
    const { available, availabilityStatus, closesAt, revision, archived } =
      await call<Task>(`/sessions/${key(draft.value.id)}/availability`, "PUT", {
        revision: draft.value.revision,
        ...schedule,
      });
    if (disposed) return;
    // 开放时间单独保存，保留编辑器里尚未保存的讲义改动。
    const updated = {
      available,
      availabilityStatus,
      closesAt,
      revision,
      archived,
    };
    baseline.value = JSON.stringify({
      ...JSON.parse(baseline.value),
      ...updated,
    });
    draft.value = { ...draft.value, ...updated };
    scheduleDialog.value = null;
    await refreshCourses();
    success.value = t(
      reopening ? "Task re-enabled." : "Task availability saved.",
    );
  });
}
async function openFileSelection() {
  selectedMaterial.value = null;
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
  // 只有在文件管理中明确选择材料时，才更改任务附件。
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
  cancelSelection();
}
async function viewProgress() {
  if (!draft.value.id) throw Error(t("Save the task before viewing progress."));
  const rows = await call<StudentRow[]>(
    `/sessions/${key(draft.value.id)}/students`,
  );
  if (disposed) return;
  students.value = rows;
}
async function observe(recordId: string | null) {
  if (!recordId) return;
  await action(async () => {
    observed.value = await call<Workspace>(`/records/${key(recordId)}/observe`);
  });
}
function updateObservedAssessment(assessment: AssessmentSummary) {
  const record = observed.value?.record;
  if (record?.assessment?.id !== assessment.id) return;
  record.assessment = assessment;
  if (students.value) {
    students.value = students.value.map((student) =>
      student.recordId === record.id ? { ...student, assessment } : student,
    );
  }
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
onBeforeUnmount(() => {
  disposed = true;
  connectionRequest?.abort();
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
    <TButton theme="default" variant="outline" type="button" @click="load">{{
      t("Retry")
    }}</TButton>
  </div>
  <template v-else>
    <div v-show="!choosingFiles" class="teacher-chat-page task-chat">
      <header class="conversation-heading task-heading">
        <div class="task-heading-title">
          <p class="eyebrow">{{ t("Teaching task") }}</p>
          <strong>{{ draft.title || t("New lesson") }}</strong>
          <div v-if="draft.id" class="row wrap task-availability">
            <span class="badge status-label" :data-status="availability">{{
              statusText(availability)
            }}</span>
            <small v-if="draft.closesAt" class="muted">{{
              t("Closing time: {0}", [dateText(draft.closesAt)])
            }}</small>
          </div>
        </div>
        <div class="row wrap task-heading-actions">
          <TButton
            v-if="needsReopening"
            theme="primary"
            type="button"
            :disabled="busy || !!active"
            @click="openAvailabilityEditor"
            >{{ t("Re-enable task") }}</TButton
          >
          <TButton
            :variant="draft.content.handout ? 'outline' : 'base'"
            type="button"
            :theme="!draft.content.handout ? 'primary' : 'default'"
            :disabled="
              busy || !!active || pendingUploads > 0 || !materialsReady
            "
            @click="generate"
          >
            {{
              t(draft.content.handout ? "Regenerate lesson" : "Generate lesson")
            }}
          </TButton>
          <TButton
            theme="default"
            variant="outline"
            v-if="hasContent"
            type="button"
            :disabled="busy || !!active"
            @click="showPreview = true"
          >
            {{ t("Preview and edit lesson") }}
          </TButton>
          <TDropdown
            :options="taskActions"
            trigger="click"
            placement="bottom-right"
            :popup-props="{
              visible: taskActionsVisible,
              onVisibleChange: (visible) => (taskActionsVisible = visible),
            }"
          >
            <TButton
              theme="default"
              variant="outline"
              :aria-expanded="taskActionsVisible"
              @keydown.esc.stop="taskActionsVisible = false"
            >
              {{ t("More actions") }} <span aria-hidden="true">⌄</span>
            </TButton>
          </TDropdown>
        </div>
      </header>
      <p v-if="error || materialError" role="alert" class="error">
        {{ systemText(error || materialError) }}
      </p>
      <p v-if="success" role="status" class="success">
        {{ systemText(success) }}
      </p>
      <section
        v-if="showGenerationState && job"
        class="conversation-result generation-state"
      >
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
        <p v-if="job.elapsedSeconds != null" class="muted">
          {{
            t("Elapsed: {0} seconds, including queue time.", [
              job.elapsedSeconds,
            ])
          }}
        </p>
        <p v-if="active && (job.elapsedSeconds || 0) >= 120" class="notice">
          {{
            t(
              "Generation is taking longer than usual. You can leave this page and return later; avoid starting a duplicate request.",
            )
          }}
        </p>
        <p
          v-if="
            job.correctedQuestions &&
            ['succeeded', 'applied'].includes(job.status)
          "
          class="notice"
        >
          {{
            t(
              "{0} questions had no answer choices and were retained as open responses. Review them before publishing.",
              [job.correctedQuestions],
            )
          }}
        </p>
        <p v-if="job.errorMessage" class="error">
          {{ systemText(job.errorMessage) }}
        </p>
        <details v-if="job.diagnosticResponse">
          <summary>{{ t("Model response for diagnosis") }}</summary>
          <pre class="diagnostic-response">{{ job.diagnosticResponse }}</pre>
        </details>
        <details v-if="job.usage">
          <summary>{{ t("Provider usage") }}</summary>
          <ContextMeter :usage="job.usage" />
        </details>
        <details v-if="job.requestTiming">
          <summary>{{ t("Request timing") }}</summary>
          <p>
            {{
              t("Local queue: {0} s; AI request: {1} s.", [
                (job.requestTiming.queueWaitMs / 1000).toFixed(1),
                (job.requestTiming.requestMs / 1000).toFixed(1),
              ])
            }}
          </p>
          <p v-if="job.requestTiming.firstResponseMs != null">
            {{
              t(
                "First streamed response: {0} s; reconnects before answer output: {1}.",
                [
                  (job.requestTiming.firstResponseMs / 1000).toFixed(1),
                  job.requestTiming.streamRetries,
                ],
              )
            }}
          </p>
        </details>
        <TButton
          theme="default"
          variant="outline"
          type="button"
          v-if="['queued', 'running', 'succeeded'].includes(job.status)"
          :disabled="busy"
          @click="poll"
        >
          {{ t("Refresh generation status") }}
        </TButton>
      </section>
      <section class="conversation-result task-upload">
        <h2>{{ t("Upload your teaching materials") }}</h2>
        <p class="muted">
          {{
            t(
              "Upload all lesson materials, worksheets, answer keys and teaching instructions together. AI will organize them into a lesson for you to review and edit.",
            )
          }}
        </p>
        <FileUploader
          :endpoint="'/courses/' + key(courseId) + '/materials'"
          visibility="teacher"
          :disabled="busy || !!active"
          @pending="uploadsPending"
          @uploaded="uploaded"
          @settled="loadMaterials"
        />
        <div v-if="selected.length" class="selected-materials">
          <small>{{ t("Selected materials: {0}", [selected.length]) }}</small>
          <TSelect
            v-control-attrs="{
              'aria-label': t('Selected materials: {0}', [selected.length]),
            }"
            :value="selectedMaterial?.id || ''"
            :placeholder="t('Select a file to preview')"
            filterable
            @change="
              (value) =>
                (selectedMaterial =
                  selected.find((material) => material.id === value) || null)
            "
          >
            <TOption
              v-for="material in selected"
              :key="material.id"
              :value="material.id"
              :label="`${material.fileName} · ${statusText(material.status)}`"
              :title="material.relativePath || material.fileName"
            />
          </TSelect>
        </div>
        <p v-if="selected.length && !materialsReady" class="muted">
          {{
            t(
              "The lesson can be generated when all uploaded materials are ready.",
            )
          }}
        </p>
      </section>
      <details class="conversation-result">
        <summary>{{ t("Local token estimate") }}</summary>
        <p>
          <small class="muted">{{
            t(
              "Local estimates are advisory only. The provider determines capacity, actual usage and request acceptance.",
            )
          }}</small>
        </p>
        <ContextMeter :usage="usage" :loading="checkingContext" embedded />
      </details>
      <section v-if="hasContent" class="conversation-result lesson-result">
        <h2>{{ draft.title }}</h2>
        <p>{{ draft.description }}</p>
        <p class="muted">
          {{
            t("{0} questions · Review and edit the lesson in preview.", [
              draft.content.questions.length,
            ])
          }}
        </p>
        <p v-if="dirty" class="notice">
          {{ t("There are unsaved changes in the lesson preview.") }}
        </p>
        <TButton
          theme="primary"
          @click="showPreview = true"
          :disabled="busy || !!active"
        >
          {{ t("Preview and edit lesson") }}
        </TButton>
      </section>
      <section
        v-if="students"
        ref="studentProgressPanel"
        class="conversation-result"
      >
        <strong>{{ t("Student progress") }}</strong>
        <TButton
          theme="default"
          variant="outline"
          type="button"
          v-for="student in students"
          :key="student.userId"
          class="progress-row"
          :disabled="!student.recordId || busy"
          @click="observe(student.recordId)"
        >
          <span>{{ student.name }}</span
          ><span
            >{{ statusText(student.submissionStatus || student.status) }} ·
            {{ student.answered }}/{{ student.total }}</span
          >
          <small v-if="student.assessment" class="muted">{{
            assessmentStatusText(student.assessment.status)
          }}</small>
        </TButton>
        <p v-if="!students.length" class="muted">
          {{ t("No students have joined this course yet.") }}
        </p>
      </section>
    </div>
    <section
      v-if="choosingFiles"
      ref="selectionPanel"
      tabindex="-1"
      class="material-selection"
      @keydown.esc.prevent="cancelSelection"
    >
      <header class="conversation-heading">
        <TButton
          theme="default"
          variant="outline"
          type="button"
          @click="cancelSelection"
          >← {{ t("Back to task") }}</TButton
        >
        <h1>{{ t("File management") }}</h1>
        <div class="row">
          <TButton
            theme="default"
            variant="outline"
            type="button"
            @click="cancelSelection"
            >{{ t("Cancel") }}</TButton
          ><TButton
            theme="primary"
            variant="base"
            type="button"
            class="primary"
            @click="saveSelection"
          >
            {{ t("Save") }}
          </TButton>
        </div>
      </header>
      <p class="muted">
        {{
          t(
            "Select course files for this task, then save your selection. This does not save or create the task.",
          )
        }}
      </p>
      <p v-if="pendingUploads" class="notice">
        {{
          t(
            "Uploads continue in the background. Select completed uploads manually in File management.",
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
        <section class="panel material-selection-preview">
          <div class="material-preview-controls">
            <TSelect
              v-control-attrs="{
                'aria-label': t('Select a file to preview'),
                title: selectionPreview?.fileName || '',
              }"
              v-model="selectionPreviewId"
              class="material-preview-select"
              filterable
              clearable
              :disabled="!activeMaterials.length"
              :placeholder="t('Select a file to preview')"
              @keydown.esc.stop
            >
              <TOption
                v-for="material in activeMaterials"
                :key="material.id"
                :value="material.id"
                :label="material.fileName"
                :title="material.relativePath || material.fileName"
              />
            </TSelect>
            <TButton
              theme="default"
              variant="outline"
              type="button"
              class="material-preview-button"
              :disabled="!selectionPreview"
              @click="selectedMaterial = selectionPreview || null"
            >
              {{ t("Preview") }}
            </TButton>
          </div>
        </section>
      </div>
    </section>
  </template>
  <AppDialog
    v-if="selectedMaterial"
    :title="selectedMaterial.fileName || t('Material preview')"
    wide
    @close="selectedMaterial = null"
  >
    <CourseMaterialPreview :material="selectedMaterial" />
    <TButton
      theme="default"
      variant="outline"
      type="button"
      v-if="!['queued', 'processing'].includes(selectedMaterial.status)"
      :disabled="busy"
      @click="retryMaterial(selectedMaterial)"
    >
      {{ t("Reprocess material") }}
    </TButton>
  </AppDialog>
  <AppDialog
    v-if="showPreview"
    :title="t(hasContent ? 'Preview and edit lesson' : 'Edit task')"
    :busy="busy"
    wide
    @close="showPreview = false"
  >
    <div class="row wrap spread lesson-preview-toolbar">
      <div class="row">
        <TButton
          :theme="previewMode === 'edit' ? 'primary' : 'default'"
          :variant="previewMode === 'edit' ? 'base' : 'outline'"
          @click="previewMode = 'edit'"
        >
          {{ t("Edit task") }}
        </TButton>
        <TButton
          :theme="previewMode === 'student' ? 'primary' : 'default'"
          :variant="previewMode === 'student' ? 'base' : 'outline'"
          @click="previewMode = 'student'"
        >
          {{ t("Student preview") }}
        </TButton>
      </div>
      <div class="row">
        <TButton
          theme="primary"
          :disabled="busy || (!!draft.id && !dirty) || !!active"
          @click="save"
        >
          {{ t("Save changes") }}
        </TButton>
        <TButton
          theme="default"
          variant="outline"
          :disabled="busy || !!active || !hasContent"
          @click="requestPublish"
        >
          {{ t(draft.publishedVersionId ? "Update task" : "Publish task") }}
        </TButton>
      </div>
    </div>
    <p v-if="error" class="error" role="alert">{{ systemText(error) }}</p>
    <p v-if="success" class="success" role="status">
      {{ systemText(success) }}
    </p>
    <LessonEditor
      v-if="previewMode === 'edit'"
      v-model="draft"
      :disabled="busy || !!active"
    />
    <template v-else>
      <p v-if="dirty" class="muted">
        {{
          t("Save your changes to try the updated lesson with the AI tutor.")
        }}
      </p>
      <StudentTask
        v-if="draft.id && hasContent && !dirty"
        :key="draft.id + '-' + previewKey"
        :task-id="draft.id"
        preview
      />
      <TaskContent v-else :task="preview" preview readonly />
    </template>
  </AppDialog>
  <TaskScheduleDialog
    v-if="scheduleDialog"
    :title="
      t(
        scheduleDialog === 'publish'
          ? 'Publish task'
          : scheduleDialog === 'reopen'
            ? 'Re-enable task'
            : 'Change availability',
      )
    "
    :submit-label="
      t(
        scheduleDialog === 'publish'
          ? 'Publish task'
          : scheduleDialog === 'reopen'
            ? 'Re-enable task'
            : 'Save changes',
      )
    "
    :current="scheduleDialog === 'edit' ? draft : undefined"
    :busy="busy"
    :error="error"
    @close="scheduleDialog = null"
    @submit="saveAvailability"
  />
  <AppDialog
    v-if="observed"
    :title="t('Learning record')"
    wide
    :busy="busy"
    @close="observed = null"
  >
    <p v-if="error" role="alert" class="error">{{ systemText(error) }}</p>
    <FormativeAssessmentPanel
      v-if="observed.record?.assessment"
      :record-id="observed.record.id"
      :latest="observed.record.assessment"
      :can-grade="!observed.record.preview"
      @updated="updateObservedAssessment"
    />
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
      <TButton
        theme="default"
        variant="outline"
        type="button"
        v-if="message.pendingReview && message.requestId"
        :disabled="busy"
        @click="approveObserved(message)"
      >
        {{ t("Approve and release feedback") }}
      </TButton>
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
        <TButton
          theme="default"
          variant="outline"
          type="button"
          :disabled="
            busy ||
            !['submitted', 'confirmed', 'needsRevision'].includes(
              observed.record.status,
            )
          "
          @click="reviewObserved('needsRevision')"
        >
          {{ t("Request revision") }}
        </TButton>
        <TButton
          theme="default"
          variant="outline"
          type="button"
          :disabled="
            busy ||
            !['submitted', 'confirmed', 'needsRevision'].includes(
              observed.record.status,
            )
          "
          @click="reviewObserved('confirmed')"
        >
          {{ t("Confirm completion") }}
        </TButton>
      </div>
    </template>
  </AppDialog>
</template>
