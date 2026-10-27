<script setup lang="ts">
import { confirmAction } from "../confirmAction";
import {
  Button as TButton,
  Select as TSelect,
  Option as TOption,
  Input as TInput,
  Textarea as TTextarea,
  Dropdown as TDropdown,
  Checkbox as TCheckbox,
  CheckboxGroup as TCheckboxGroup,
  type DropdownOption,
} from "tdesign-vue-next";
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { t, systemText } from "../i18n";
import {
  blankTask,
  answerText,
  questionTypes,
  call,
  fileUrl,
  key,
  statusText,
  studentTask,
  versionParam,
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
const taskActionsVisible = ref(false);
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
const progressVersionId = ref("");
const studentProgressPanel = ref<HTMLElement | null>(null);
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
const taskActions = computed<DropdownOption[]>(() => [
  ...(hasContent.value
    ? [
        {
          content: t("Revise with these instructions"),
          value: "revise",
          disabled:
            busy.value ||
            chatBusy.value ||
            !!active.value ||
            pendingUploads.value > 0 ||
            !draft.value.additionalInstructions?.trim() ||
            usage.value?.materialsReady === false,
          onClick: () => {
            void generate("revise");
          },
        },
      ]
    : []),
  ...(draft.value.id
    ? [
        {
          content: t("Student progress"),
          value: "progress",
          disabled: busy.value || chatBusy.value,
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
  {
    content: t("File management"),
    value: "files",
    disabled: busy.value || chatBusy.value || !!active.value,
    onClick: () => {
      void openFileSelection();
    },
  },
  {
    content: t("Course conversation"),
    value: "course",
    disabled: busy.value || chatBusy.value || !!active.value,
    onClick: () => navigate({ page: "course", courseId: props.courseId }),
  },
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
  const result = await call<Task>(
    path,
    draft.value.id ? "PUT" : "POST",
    draft.value,
  );
  if (disposed) return result;
  accept(result);
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
    !(await confirmAction(
      t(
        "Generate a new lesson from these materials? The published version will remain available.",
      ),
    ))
  )
    return false;
  let started = false;
  await action(async () => {
    await saveDraft();
    if (disposed) return;
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
    if (disposed) return;
    if (!(await confirmAction(t("Publish this task to students?")))) return;
    if (disposed) return;
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
    !(await confirmAction(
      t("Restore this version into the draft? Unsaved edits will be replaced."),
    ))
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
  // Only explicit choices in file management change the task's attachments.
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
async function viewProgress(versionId = progressVersionId.value) {
  if (!draft.value.id) throw Error(t("Save the task before viewing progress."));
  const selectedVersion = versionId || draft.value.publishedVersionId || "";
  const rows = await call<StudentRow[]>(
    `/sessions/${key(draft.value.id)}/students${versionParam(selectedVersion)}`,
  );
  if (disposed) return;
  progressVersionId.value = selectedVersion;
  students.value = rows;
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
  if (disposed) return;
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
      if (disposed) return;
      outcome = t("Task configuration saved to the draft.");
    } else
      outcome = t(
        "The task draft is retained here. Tell AI a task name to save it.",
      );
  }
  if (["selectFiles", "files"].includes(reply.action))
    await openFileSelection();
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
        "Review the preview, then use Publish task beside the task title to confirm publication.",
      );
  else if (reply.action === "progress") await viewProgress();
  else if (["members", "inviteStudent", "newTask"].includes(reply.action))
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
    <TButton theme="default" variant="outline" type="button" @click="load">{{
      t("Retry")
    }}</TButton>
  </div>
  <template v-else>
    <div v-show="!choosingFiles" class="teacher-chat-page task-chat">
      <header class="conversation-heading task-heading">
        <div class="task-heading-title">
          <p class="eyebrow">{{ t("Task conversation") }}</p>
          <strong>{{ draft.title || t("New task conversation") }}</strong>
        </div>
        <div class="row wrap task-heading-actions">
          <TButton
            :variant="draft.content.handout ? 'outline' : 'base'"
            type="button"
            :theme="!draft.content.handout ? 'primary' : 'default'"
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
              t(draft.content.handout ? "Regenerate lesson" : "Generate lesson")
            }}
          </TButton>
          <TButton
            theme="default"
            variant="outline"
            type="button"
            :disabled="busy || chatBusy || !!active || !selected.length"
            @click="showImportSources = true"
          >
            {{ t("Import existing worksheet") }}
          </TButton>
          <TButton
            theme="default"
            variant="outline"
            v-if="hasContent"
            type="button"
            :disabled="busy || chatBusy || !!active"
            @click="showPreview = true"
          >
            {{ t("Student preview") }}
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
          <TButton
            theme="primary"
            variant="base"
            v-if="hasContent"
            type="button"
            class="primary"
            :disabled="busy || chatBusy || !!active"
            @click="publish"
          >
            {{ t("Publish task") }}
          </TButton>
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
        <template #results>
          <details class="conversation-result" open>
            <summary>{{ t("Current task configuration") }}</summary>
            <div class="task-attachment-tools">
              <strong>{{ t("Task attachments") }}</strong>
              <p class="muted">
                {{
                  t(
                    "Uploads are added to the course library. Open File management to choose the attachments for this task.",
                  )
                }}
              </p>
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
                  }}<TSelect
                    v-model="uploadVisibility"
                    :disabled="busy || chatBusy || !!active"
                  >
                    <TOption
                      value="student"
                      :label="t('Students and teachers')"
                    />
                    <TOption
                      value="teacher"
                      :label="t('Teachers and AI only')"
                    /> </TSelect
                ></label>
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
                  ><TButton
                    theme="default"
                    variant="outline"
                    type="button"
                    :disabled="busy || chatBusy || !!active"
                    @click="openFileSelection"
                  >
                    {{ t("File management") }}
                  </TButton></template
                >
              </FileUploader>
              <div v-if="selected.length" class="selected-materials">
                <small>{{
                  t("Selected materials: {0}", [selected.length])
                }}</small>
                <TButton
                  theme="default"
                  variant="outline"
                  v-for="material in selected"
                  :key="material.id"
                  type="button"
                  @click="selectedMaterial = material"
                >
                  {{ material.title }}
                  <small>{{ statusText(material.status) }}</small>
                </TButton>
              </div>
              <p v-else class="empty selected-empty">
                {{
                  t(
                    "No task attachments selected. Open File management to select course files.",
                  )
                }}
              </p>
            </div>
            <p class="muted">
              {{
                t(
                  "Edit these fields directly, or describe changes in the conversation.",
                )
              }}
            </p>
            <form @submit.prevent="save">
              <fieldset :disabled="busy || chatBusy || !!active">
                <dl class="configuration-summary">
                  <dt>
                    <label for="task-title">{{ t("Task name") }}</label>
                  </dt>
                  <dd>
                    <TInput
                      :disabled="busy || chatBusy || !!active"
                      v-control-attrs="{ id: 'task-title', required: true }"
                      v-model="draft.title"
                      @blur="draft.title = draft.title.trim()"
                      maxlength="300"
                    />
                  </dd>
                  <dt>
                    <label for="task-type">{{ t("Task type") }}</label>
                  </dt>
                  <dd>
                    <TSelect
                      :disabled="busy || chatBusy || !!active"
                      v-control-attrs="{ id: 'task-type' }"
                      v-model="draft.sessionType"
                    >
                      <TOption value="tutor" :label="t('AI tutor')" />
                      <TOption value="assignment" :label="t('Assignment')" />
                    </TSelect>
                  </dd>
                  <dt>
                    <label for="task-language">{{
                      t("Teaching language")
                    }}</label>
                  </dt>
                  <dd>
                    <TSelect
                      :disabled="busy || chatBusy || !!active"
                      v-control-attrs="{ id: 'task-language' }"
                      v-model="draft.teachingLanguage"
                    >
                      <TOption value="zh-CN" label="中文" />
                      <TOption value="en" label="English" />
                    </TSelect>
                  </dd>
                  <dt>
                    <label for="task-learning-goals">{{
                      t("Learning goals")
                    }}</label>
                  </dt>
                  <dd>
                    <TTextarea
                      :disabled="busy || chatBusy || !!active"
                      v-control-attrs="{ id: 'task-learning-goals', rows: '3' }"
                      :autosize="{ minRows: 3, maxRows: 10 }"
                      v-model="draft.learningGoals"
                      maxlength="20000"
                    />
                  </dd>
                  <dt>
                    <label for="task-instructions">{{
                      t("Additional instructions for AI")
                    }}</label>
                  </dt>
                  <dd>
                    <TTextarea
                      :disabled="busy || chatBusy || !!active"
                      v-control-attrs="{ id: 'task-instructions', rows: '3' }"
                      :autosize="{ minRows: 3, maxRows: 10 }"
                      v-model="draft.additionalInstructions"
                      maxlength="20000"
                    />
                  </dd>
                </dl>
                <div class="row wrap end configuration-actions">
                  <TButton
                    :disabled="busy || chatBusy || !!active"
                    theme="primary"
                    variant="base"
                    class="primary"
                    type="submit"
                  >
                    {{ t("Save draft") }}
                  </TButton>
                </div>
              </fieldset>
            </form>
          </details>
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
          <section v-if="hasContent" class="conversation-result lesson-result">
            <h2>{{ draft.title }}</h2>
            <RichText
              v-if="draft.content.handout"
              :text="draft.content.handout"
            />
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
                  :text="answerText(question, question.referenceAnswer)"
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
          <section
            v-if="students"
            ref="studentProgressPanel"
            class="conversation-result"
          >
            <strong>{{ t("Student progress") }}</strong>
            <label v-if="versions.length" class="form-stack">
              {{ t("Version") }}
              <TSelect
                :value="progressVersionId"
                :disabled="busy || chatBusy"
                @change="
                  (value) =>
                    action(async () => {
                      await viewProgress(String(value));
                      observed = null;
                    })
                "
              >
                <TOption
                  v-for="version in versions"
                  :key="version.id"
                  :value="version.id"
                  :label="version.label"
                />
              </TSelect>
            </label>
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
                >{{ statusText(student.status) }} · {{ student.answered }}/{{
                  student.total
                }}</span
              >
            </TButton>
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
              ><TButton
                theme="default"
                variant="outline"
                type="button"
                :disabled="busy || chatBusy || !!active"
                @click="restore(version.id)"
              >
                {{ t("Restore to draft") }}
              </TButton>
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
        <section class="panel">
          <template v-if="selectionPreview"
            ><CourseMaterialPreview :material="selectionPreview" />
            <TButton
              theme="default"
              variant="outline"
              type="button"
              v-if="!['queued', 'processing'].includes(selectionPreview.status)"
              :disabled="busy"
              @click="retryMaterial(selectionPreview)"
            >
              {{ t("Reprocess material") }}
            </TButton>
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
      <TCheckboxGroup v-model="importSources" class="import-sources">
        <TCheckbox
          v-for="material in selected"
          :key="material.id"
          :value="material.id"
          :disabled="!['ready', 'needsReview'].includes(material.status)"
          >{{ material.title }}</TCheckbox
        >
      </TCheckboxGroup>
      <p v-if="!selected.length" class="empty">
        {{
          t(
            "No task attachments selected. Open File management to select course files.",
          )
        }}
      </p>
      <div class="row end">
        <TButton
          theme="default"
          variant="outline"
          type="button"
          @click="showImportSources = false"
          >{{ t("Cancel") }}</TButton
        ><TButton
          theme="primary"
          variant="base"
          type="button"
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
        </TButton>
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
    :title="t('Student preview')"
    wide
    @close="showPreview = false"
  >
    <TButton
      theme="default"
      variant="outline"
      type="button"
      v-if="dirty"
      :disabled="busy"
      @click="simulate"
    >
      {{ t("Save and refresh preview") }}
    </TButton>
    <StudentTask
      v-if="draft.id && hasContent && !dirty"
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
