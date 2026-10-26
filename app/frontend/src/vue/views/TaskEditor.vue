<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { t, systemText } from "../../i18n";
import {
  blankTask,
  call,
  key,
  statusText,
  studentTask,
  type Job,
  type Material,
  type Task,
  type Version,
  type ContextUsage,
} from "../../classroom-api";
import {
  dirty,
  navigate,
  refreshCourses,
  retainTaskAddress,
} from "../classroom-state";
import FileUploader from "../components/FileUploader.vue";
import AiConnection from "../components/AiConnection.vue";
import ContextMeter from "../components/ContextMeter.vue";
import StudentTask from "./StudentTask.vue";
import TaskContent from "../components/TaskContent.vue";
import ProgressStatus from "../components/ProgressStatus.vue";
import MaterialTree from "../components/MaterialTree.vue";
import CourseMaterialPreview from "../components/CourseMaterialPreview.vue";
const props = defineProps<{
  courseId: string;
  taskId: string;
  workbench?: boolean;
  initialMode?: string;
}>();
const draft = ref<Task>(blankTask(props.courseId)),
  baseline = ref(""),
  materials = ref<Material[]>([]),
  versions = ref<Version[]>([]);
const busy = ref(false),
  error = ref(""),
  success = ref(""),
  loading = ref(true),
  ready = ref(false),
  job = ref<Job | null>(null),
  selectedMaterial = ref<Material | null>(null);
const importSources = ref<string[]>([]);
const pendingUploads = ref(0);
const uploadVisibility = ref<"student" | "teacher">("student");
const usage = ref<ContextUsage | null>(null),
  checkingContext = ref(false),
  previewKey = ref(0);
let materialTimer: ReturnType<typeof setTimeout> | undefined,
  contextTimer: ReturnType<typeof setTimeout> | undefined,
  contextSequence = 0;
let timer: ReturnType<typeof setTimeout> | undefined;
let disposed = false;
let polling = false;
let materialLoadError = "";
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
async function loadMaterials() {
  clearTimeout(materialTimer);
  try {
    const loaded = await call<Material[]>(
      `/courses/${key(props.courseId)}/materials`,
    );
    if (disposed) return;
    materials.value = loaded;
    if (error.value === materialLoadError) error.value = "";
    materialLoadError = "";
  } catch (e) {
    materialLoadError = (e as Error).message;
    if (!disposed)
      materialTimer = setTimeout(
        () => void loadMaterials().catch(() => {}),
        5000,
      );
    throw e;
  }
  if (
    !disposed &&
    materials.value.some(
      (m) => !m.archived && ["queued", "processing"].includes(m.status),
    )
  )
    materialTimer = setTimeout(
      () => void loadMaterials().catch((e) => (error.value = e.message)),
      2500,
    );
  if (selectedMaterial.value)
    selectedMaterial.value =
      materials.value.find((m) => m.id === selectedMaterial.value?.id) || null;
  void checkContext();
}
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
  materials.value.push(material);
  chooseMaterial(material.id, true);
  void loadMaterials().catch((e) => (error.value = e.message));
}
async function retryMaterial() {
  if (!selectedMaterial.value) return;
  await action(async () => {
    await call(`/materials/${key(selectedMaterial.value!.id)}/retry`, "POST");
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
    await loadMaterials();
    if (disposed) return;
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
      const task = blankTask(props.courseId);
      if (props.initialMode === "tutor")
        task.content.teachingMode = "autonomous";
      if (props.initialMode === "worksheet") task.sessionType = "assignment";
      if (props.initialMode === "reading")
        task.additionalInstructions = t(
          "Create a guided reading resource with key concepts, examples and reflection questions.",
        );
      accept(task);
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
async function generate(kind = "generate") {
  if (pendingUploads.value) return;
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
    return;
  await action(async () => {
    await saveDraft();
    job.value = await call<Job>(
      `/sessions/${key(draft.value.id)}/generations`,
      "POST",
      {
        revision: draft.value.revision,
        kind,
        sourceMaterialIds: importSources.value,
        instruction: draft.value.additionalInstructions,
      },
    );
    accept(await call<Task>(`/sessions/${key(draft.value.id)}`));
    schedulePoll();
  });
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
onBeforeUnmount(() => {
  disposed = true;
  clearTimeout(timer);
  clearTimeout(materialTimer);
  clearTimeout(contextTimer);
  contextSequence++;
  dirty.value = false;
});
void load();
</script>
<template>
  <nav v-if="!workbench" class="page-return-bar" :aria-label="t('Back')">
    <button @click="navigate({ page: 'course', courseId })">
      ← {{ t("Back to course") }}
    </button>
    <span class="muted">{{ t("Create and preview") }}</span>
  </nav>
  <header class="page-heading compact-heading">
    <div>
      <h1>{{ taskId || draft.id ? t("Edit task") : t("Create task") }}</h1>
      <p class="muted">
        {{
          t(
            "Choose materials, add instructions, and let AI prepare the lesson. Try it as a student on the right.",
          )
        }}
      </p>
    </div>
    <div class="row wrap">
      <button
        v-if="draft.id && !workbench"
        @click="navigate({ page: 'monitor', courseId, taskId: draft.id })"
      >
        {{ t("Student progress") }}
      </button>
      <button :disabled="busy || active || loading || !ready" @click="save">
        {{ t("Save draft") }}
      </button>
      <button
        v-if="!workbench"
        class="primary"
        :disabled="
          busy || active || loading || !ready || !draft.content.handout
        "
        @click="publish"
      >
        {{ t("Publish task") }}
      </button>
    </div>
  </header>
  <p v-if="error" role="alert" class="error">{{ systemText(error) }}</p>
  <p v-if="success" role="status" class="success">{{ systemText(success) }}</p>
  <ProgressStatus v-if="loading" :label="t('Loading…')" />
  <div v-else-if="!ready" class="panel">
    <button @click="load">{{ t("Retry") }}</button>
  </div>
  <div v-else class="authoring-layout">
    <div class="authoring-form">
      <fieldset :disabled="busy || !!active" class="panel form-stack">
        <h2>{{ t("Task setup") }}</h2>
        <label
          >{{ t("Task name")
          }}<input v-model="draft.title" maxlength="300" required
        /></label>
        <div class="form-grid">
          <label
            >{{ t("Task type")
            }}<select v-model="draft.sessionType">
              <option value="tutor">{{ t("AI tutor") }}</option>
              <option value="assignment">{{ t("Assignment") }}</option>
            </select></label
          >
          <label
            >{{ t("Teaching language")
            }}<select v-model="draft.teachingLanguage">
              <option value="zh-CN">中文</option>
              <option value="en">English</option>
            </select></label
          >
        </div>
        <details class="additional-fields">
          <summary>{{ t("Tutoring settings") }}</summary>
          <div class="form-grid">
            <label
              >{{ t("Teaching mode")
              }}<select v-model="draft.content.teachingMode">
                <option value="guided">{{ t("Guided learning") }}</option>
                <option value="autonomous">{{ t("Adaptive tutor") }}</option>
              </select></label
            >
            <label
              >{{ t("AI feedback")
              }}<select v-model="draft.content.feedbackMode">
                <option value="immediate">{{ t("Show immediately") }}</option>
                <option value="teacherReview">
                  {{ t("Teacher review before release") }}
                </option>
              </select></label
            >
          </div>
        </details>
      </fieldset>
      <fieldset :disabled="busy || !!active" class="panel form-stack">
        <div class="row spread">
          <h2>{{ t("Task materials") }}</h2>
          <button
            type="button"
            @click="loadMaterials().catch((e) => (error = e.message))"
          >
            {{ t("Refresh status") }}
          </button>
        </div>
        <label
          >{{ t("Visibility for new uploads")
          }}<select v-model="uploadVisibility">
            <option value="student">{{ t("Students and teachers") }}</option>
            <option value="teacher">{{ t("Teachers and AI only") }}</option>
          </select></label
        >
        <FileUploader
          :endpoint="'/courses/' + key(courseId) + '/materials'"
          :visibility="uploadVisibility"
          :disabled="busy || !!active"
          @pending="pendingUploads = $event"
          @uploaded="uploaded"
          @settled="loadMaterials().catch((e) => (error = e.message))"
        />
        <MaterialTree
          :materials="materials.filter((m) => !m.archived)"
          selectable
          :checked="draft.materialIds"
          @check="chooseMaterial"
          @select="selectedMaterial = $event"
        />
        <p v-if="!materials.length" class="empty">
          {{ t("Upload course materials to begin.") }}
        </p>
        <details>
          <summary>{{ t("How documents are read") }}</summary>
          <p class="muted">
            {{
              t(
                "PDFs with a complete usable text layer are extracted locally. Otherwise, the entire PDF is sent as page images in order, without OCR. Each AI request is limited to 40,000 input tokens, including materials, prompts and chat history.",
              )
            }}
          </p>
        </details>
        <details class="additional-fields">
          <summary>{{ t("Import existing worksheet") }}</summary>
          <div class="inset form-stack">
            <strong>{{ t("Worksheet source materials") }}</strong>
            <label
              v-for="material in selected"
              :key="material.id"
              class="check-label"
            >
              <input
                v-model="importSources"
                type="checkbox"
                :value="material.id"
                :disabled="!['ready', 'needsReview'].includes(material.status)"
              />{{ material.title }}
            </label>
            <button
              type="button"
              :disabled="
                pendingUploads > 0 ||
                !importSources.length ||
                usage?.allowed === false ||
                !!usage?.pendingMaterials?.length ||
                !!usage?.incompleteMaterials?.length
              "
              @click="generate('import')"
            >
              {{ t("Extract worksheet questions") }}
            </button>
          </div>
        </details>
      </fieldset>
      <fieldset :disabled="busy || !!active" class="panel form-stack">
        <h2>{{ t("Additional instructions for AI") }}</h2>
        <label class="prompt-label">
          <span class="muted">{{
            t(
              "Tell AI what to teach or what to change. This is the only place you need to write instructions for this task.",
            )
          }}</span>
          <textarea
            v-model="draft.additionalInstructions"
            rows="6"
            maxlength="10000"
            :aria-label="t('Additional instructions for AI')"
            :placeholder="
              t(
                'For example: explain formative assessment for first-year students, include a classroom example, and finish with three reflection questions. To revise, describe what should change.',
              )
            "
          />
          <small>{{
            t(
              "Course instructions are inherited automatically. These notes are not shown to students.",
            )
          }}</small>
        </label>
        <ContextMeter :usage="usage" :loading="checkingContext" />
        <p v-if="usage?.revisionBudget?.allowed === false" class="notice">
          {{
            t(
              "The revision is not ready to send: check that all materials are processed and that the current lesson, materials and instructions fit within the 40,000-token input limit.",
            )
          }}
        </p>
        <div class="row wrap">
          <button
            class="primary"
            type="button"
            :disabled="
              pendingUploads > 0 ||
              !draft.title.trim() ||
              usage?.allowed === false ||
              !!usage?.pendingMaterials?.length ||
              !!usage?.incompleteMaterials?.length
            "
            @click="generate()"
          >
            {{
              t(draft.content.handout ? "Regenerate lesson" : "Generate lesson")
            }}
          </button>
          <button
            v-if="draft.content.handout"
            type="button"
            :disabled="
              pendingUploads > 0 ||
              !draft.additionalInstructions?.trim() ||
              usage?.revisionBudget?.allowed === false ||
              !!usage?.pendingMaterials?.length ||
              !!usage?.incompleteMaterials?.length
            "
            @click="generate('revise')"
          >
            {{ t("Revise with these instructions") }}
          </button>
        </div>
        <details>
          <summary>{{ t("AI connection and context") }}</summary>
          <AiConnection />
        </details>
      </fieldset>
      <details v-if="versions.length" class="panel">
        <summary>{{ t("Published versions") }}</summary>
        <div
          v-for="version in versions"
          :key="version.id"
          class="row spread version-row"
        >
          <span>{{ version.label }}</span
          ><button :disabled="busy || !!active" @click="restore(version.id)">
            {{ t("Restore to draft") }}
          </button>
        </div>
      </details>
    </div>
    <aside class="student-preview panel">
      <div class="preview-heading">
        <strong>{{ t("Student preview") }}</strong
        ><span class="badge">{{ t("AI-generated lesson") }}</span>
      </div>
      <div
        v-if="job && job.status !== 'applied'"
        class="preview-controls generation-state"
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
        <strong v-else class="status-label" :data-status="job.status">{{
          statusText(job.status)
        }}</strong>
        <p v-if="job.errorMessage" class="error">
          {{ systemText(job.errorMessage) }}
        </p>
        <button
          v-if="['queued', 'running', 'succeeded'].includes(job.status)"
          :disabled="busy"
          @click="poll"
        >
          {{ t("Refresh generation status") }}
        </button>
      </div>
      <div v-if="draft.content.handout && dirty" class="preview-controls">
        <button :disabled="busy || !!active" @click="simulate">
          {{ t("Save and refresh preview") }}
        </button>
        <p class="notice">
          {{
            t(
              "The simulation uses the saved draft. Save your changes to refresh it.",
            )
          }}
        </p>
      </div>
      <StudentTask
        v-if="draft.id && draft.content.handout"
        :key="draft.id + '-' + previewKey"
        :task-id="draft.id"
        preview
      />
      <TaskContent
        v-else-if="draft.content.handout"
        :task="preview"
        preview
        readonly
      />
      <div v-else class="preview-placeholder">
        <h2>{{ t("Your lesson will appear here") }}</h2>
        <p>
          {{
            t(
              "Add materials and generate a lesson. AI will prepare the welcome message, explanations, examples and practice for your students.",
            )
          }}
        </p>
      </div>
    </aside>
  </div>
  <div
    v-if="selectedMaterial"
    class="modal-backdrop"
    @click.self="selectedMaterial = null"
  >
    <section
      role="dialog"
      aria-modal="true"
      :aria-label="t('Material preview')"
      class="modal wide"
    >
      <header class="page-return-bar">
        <button @click="selectedMaterial = null">
          ← {{ t("Back to task") }}
        </button>
        <button :aria-label="t('Close')" @click="selectedMaterial = null">
          ×
        </button>
      </header>
      <CourseMaterialPreview :material="selectedMaterial" />
      <button
        v-if="!['queued', 'processing'].includes(selectedMaterial.status)"
        :disabled="busy"
        @click="retryMaterial"
      >
        {{ t("Reprocess material") }}
      </button>
    </section>
  </div>
</template>
