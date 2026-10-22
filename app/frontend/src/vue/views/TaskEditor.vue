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
} from "../../classroom-api";
import {
  dirty,
  navigate,
  refreshCourses,
  retainTaskAddress,
} from "../classroom-state";
import TaskContent from "../components/TaskContent.vue";
import TaskQuestionEditor from "../components/TaskQuestionEditor.vue";
import MaterialTree from "../components/MaterialTree.vue";
import CourseMaterialPreview from "../components/CourseMaterialPreview.vue";
const props = defineProps<{ courseId: string; taskId: string }>();
const draft = ref<Task>(blankTask(props.courseId)),
  baseline = ref(""),
  materials = ref<Material[]>([]),
  versions = ref<Version[]>([]);
const busy = ref(false),
  error = ref(""),
  success = ref(""),
  loading = ref(true),
  job = ref<Job | null>(null),
  selectedMaterial = ref<Material | null>(null);
const importSource = ref(""),
  showImport = ref(false),
  uploaded = ref("");
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
  draft.value = value;
  baseline.value = JSON.stringify(value);
  dirty.value = false;
}
async function loadMaterials() {
  materials.value = await call<Material[]>(
    `/courses/${key(props.courseId)}/materials`,
  );
}
async function load() {
  try {
    await loadMaterials();
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
    } else accept(blankTask(props.courseId));
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    loading.value = false;
  }
}
async function action(fn: () => Promise<void>) {
  if (busy.value) return;
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
  if (
    kind === "generate" &&
    draft.value.content.questions.length &&
    !window.confirm(
      t(
        "Regenerate the learning plan and questions? The saved published version will remain available.",
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
        sourceMaterialId: importSource.value || null,
      },
    );
    accept(await call<Task>(`/sessions/${key(draft.value.id)}`));
    showImport.value = false;
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
    if (!disposed) error.value = (e as Error).message;
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
async function upload(event: Event) {
  const input = event.target as HTMLInputElement;
  const files = [...(input.files || [])];
  await action(async () => {
    for (const file of files) {
      uploaded.value = file.name;
      const body = new FormData();
      body.set("file", file);
      body.set("relativePath", file.webkitRelativePath || file.name);
      body.set("visibility", "student");
      const material = await call<Material>(
        `/courses/${key(props.courseId)}/materials`,
        "POST",
        body,
      );
      draft.value.materialIds.push(material.id);
    }
    await loadMaterials();
    success.value = t(
      "Materials uploaded. Refresh their status after processing.",
    );
  });
  uploaded.value = "";
  input.value = "";
}
onBeforeUnmount(() => {
  disposed = true;
  clearTimeout(timer);
  dirty.value = false;
});
void load();
</script>
<template>
  <div class="page-heading">
    <div>
      <p class="eyebrow">{{ t("CREATE A LEARNING EXPERIENCE") }}</p>
      <h1>{{ draft.id ? t("Edit task") : t("Create task") }}</h1>
      <p class="muted">
        {{
          t(
            "Choose materials and describe what matters. AI prepares the teaching plan and questions.",
          )
        }}
      </p>
    </div>
    <div class="row">
      <button
        v-if="draft.id"
        @click="navigate({ page: 'monitor', courseId, taskId: draft.id })"
      >
        {{ t("Student progress") }}</button
      ><button :disabled="busy || active || loading" @click="save">
        {{ t("Save draft") }}</button
      ><button
        class="primary"
        :disabled="busy || active || loading"
        @click="publish"
      >
        {{ t("Publish task") }}
      </button>
    </div>
  </div>
  <p v-if="error" role="alert" class="error">{{ error }}</p>
  <p v-if="success" role="status" class="success">{{ success }}</p>
  <p v-if="loading" class="empty">{{ t("Loading…") }}</p>
  <div v-else class="authoring-layout">
    <div class="authoring-form">
      <fieldset :disabled="busy || !!active" class="panel form-stack">
        <div class="form-grid">
          <label
            >{{ t("Task name")
            }}<input v-model="draft.title" maxlength="300" required /></label
          ><label
            >{{ t("Task type")
            }}<select v-model="draft.sessionType">
              <option value="tutor">{{ t("AI tutor") }}</option>
              <option value="assignment">{{ t("Assignment") }}</option>
            </select></label
          >
        </div>
        <label
          >{{ t("Task description")
          }}<textarea
            v-model="draft.description"
            rows="2"
            :placeholder="
              t('Optional — AI can draft this from your materials.')
            "
          />
        </label>
        <label
          >{{ t("Teaching language")
          }}<select v-model="draft.teachingLanguage">
            <option value="zh-CN">中文</option>
            <option value="en">English</option>
          </select></label
        >
        <label
          >{{ t("Topic or tutoring scope")
          }}<textarea
            v-model="draft.topic"
            rows="3"
            :placeholder="
              t(
                'For example: understand formative assessment and apply it to a classroom activity. Leave blank for AI to infer the topic.',
              )
            "
          />
        </label>
        <div class="row spread">
          <h3>{{ t("Task materials") }}</h3>
          <button
            type="button"
            @click="loadMaterials().catch((e) => (error = e.message))"
          >
            {{ t("Refresh status") }}
          </button>
        </div>
        <div class="upload-actions">
          <label class="button"
            >＋ {{ t("Upload files")
            }}<input type="file" multiple hidden @change="upload" /></label
          ><label class="button"
            >＋ {{ t("Upload folder")
            }}<input
              type="file"
              multiple
              webkitdirectory
              hidden
              @change="upload"
          /></label>
        </div>
        <p v-if="uploaded" class="muted">
          {{ t("Uploading {0}", [uploaded]) }}
        </p>
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
        <details class="additional-fields">
          <summary>{{ t("Additional requirements (optional)") }}</summary>
          <label
            >{{ t("Learning goals")
            }}<textarea
              v-model="draft.learningGoals"
              rows="4"
              :placeholder="
                t(
                  'What should students understand or be able to do? AI fills this in when left blank.',
                )
              "
            /><small>{{
              t("Visible to students and used by the AI tutor.")
            }}</small></label
          >
          <label
            >{{ t("Additional teaching instructions")
            }}<textarea
              v-model="draft.additionalInstructions"
              rows="4"
              :placeholder="
                t(
                  'Add any requirements specific to this task. Course-wide teaching instructions are inherited automatically.',
                )
              "
            /><small>{{
              t(
                "For the AI tutor only; students will not see these instructions.",
              )
            }}</small></label
          >
        </details>
        <div class="row wrap">
          <button
            type="button"
            class="primary"
            :disabled="!selected.length"
            @click="generate()"
          >
            ✦ {{ t("Generate with AI") }}</button
          ><button
            type="button"
            :disabled="!selected.length"
            @click="showImport = !showImport"
          >
            {{ t("Import existing worksheet") }}
          </button>
        </div>
        <div v-if="showImport" class="inset form-stack">
          <label
            >{{ t("Worksheet material")
            }}<select v-model="importSource">
              <option value="">{{ t("Choose a material") }}</option>
              <option
                v-for="material in selected"
                :key="material.id"
                :value="material.id"
              >
                {{ material.title }}
              </option>
            </select></label
          >
          <p class="muted">
            {{
              t(
                "Extracts existing questions and supplied answers, then appends them to the draft. Missing answers can be edited before publishing.",
              )
            }}
          </p>
          <button
            type="button"
            :disabled="!importSource"
            @click="generate('import')"
          >
            {{ t("Extract worksheet questions") }}
          </button>
        </div>
      </fieldset>
      <div v-if="job" class="panel generation-state" role="status">
        <strong>{{ statusText(job.status) }}</strong
        ><span>{{ statusText(job.stage) }}</span>
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
      <div class="panel">
        <TaskQuestionEditor
          :questions="draft.content.questions"
          :materials="selected"
          :teaching-language="draft.teachingLanguage"
          :disabled="busy || !!active"
        />
      </div>
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
        ><span class="badge">{{ t("Task content") }}</span>
      </div>
      <TaskContent :task="preview" preview readonly />
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
      <button
        class="modal-close"
        :aria-label="t('Close')"
        @click="selectedMaterial = null"
      >
        ×</button
      ><CourseMaterialPreview :material="selectedMaterial" />
    </section>
  </div>
</template>
