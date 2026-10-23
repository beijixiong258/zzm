<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue";
import { t } from "../../i18n";
import { call, key, type Material } from "../../classroom-api";
import { navigate } from "../classroom-state";
import FileUploader from "../components/FileUploader.vue";
import MaterialTree from "../components/MaterialTree.vue";
import CourseMaterialPreview from "../components/CourseMaterialPreview.vue";
const props = defineProps<{ courseId: string }>();
const materials = ref<Material[]>([]),
  selectedId = ref(""),
  showArchived = ref(false),
  busy = ref(false),
  error = ref("");
const title = ref(""),
  visibility = ref<"student" | "teacher">("student");
const uploadVisibility = ref<"student" | "teacher">("student");
const selected = computed(() =>
  materials.value.find((m) => m.id === selectedId.value),
);
let timer: ReturnType<typeof setTimeout> | undefined,
  disposed = false;
let materialLoadError = "";
async function load() {
  clearTimeout(timer);
  try {
    materials.value = await call<Material[]>(
      `/courses/${key(props.courseId)}/materials`,
    );
    if (
      !disposed &&
      materials.value.some(
        (m) => !m.archived && ["queued", "processing"].includes(m.status),
      )
    )
      timer = setTimeout(() => {
        void load();
      }, 3000);
    if (error.value === materialLoadError) error.value = "";
    materialLoadError = "";
  } catch (e) {
    materialLoadError = (e as Error).message;
    error.value = materialLoadError;
    if (!disposed) timer = setTimeout(() => void load(), 5000);
  }
}
function select(material: Material) {
  selectedId.value = material.id;
  title.value = material.title;
  visibility.value = material.visibility;
}
async function action(fn: () => Promise<void>) {
  busy.value = true;
  error.value = "";
  try {
    await fn();
    await load();
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
async function save() {
  await action(async () => {
    await call(`/materials/${key(selectedId.value)}`, "PUT", {
      title: title.value,
      visibility: visibility.value,
    });
  });
}
async function archive() {
  if (
    !selected.value ||
    !window.confirm(
      t(
        "Change the archive state of this material? Published versions keep their original references.",
      ),
    )
  )
    return;
  await action(async () => {
    await call(
      `/materials/${key(selectedId.value)}/archive?archived=${!selected.value!.archived}`,
      "POST",
    );
  });
}
async function retry() {
  await action(async () => {
    await call(`/materials/${key(selectedId.value)}/retry`, "POST");
  });
}
onBeforeUnmount(() => {
  disposed = true;
  clearTimeout(timer);
});
void load();
</script>
<template>
  <nav class="page-return-bar" :aria-label="t('Back')">
    <button @click="navigate({ page: 'course', courseId })">
      ← {{ t("Back to course") }}
    </button>
    <span class="muted">{{ t("Course materials") }}</span>
  </nav>
  <header class="page-heading compact-heading">
    <div>
      <p class="eyebrow">{{ t("COURSE LIBRARY") }}</p>
      <h1>{{ t("Course materials") }}</h1>
      <p class="muted">
        {{
          t("Organize materials once, then reuse them across learning tasks.")
        }}
      </p>
    </div>
  </header>
  <section class="panel library-upload">
    <div class="form-stack">
      <label
        >{{ t("Visibility for new uploads")
        }}<select v-model="uploadVisibility">
          <option value="student">{{ t("Students and teachers") }}</option>
          <option value="teacher">{{ t("Teachers and AI only") }}</option>
        </select></label
      >
      <FileUploader
        :endpoint="`/courses/${key(courseId)}/materials`"
        :visibility="uploadVisibility"
        @uploaded="select"
        @settled="load"
      />
    </div>
  </section>
  <p class="muted">
    {{
      t(
        "Supported: PDF, Word, PowerPoint, Excel, text and images. Up to 25 MiB per file.",
      )
    }}
  </p>
  <p v-if="error" class="error" role="alert">{{ error }}</p>
  <div class="library-layout">
    <aside class="panel">
      <label class="check-label"
        ><input v-model="showArchived" type="checkbox" />{{
          t("Show archived items")
        }}</label
      ><MaterialTree
        :materials="materials.filter((m) => showArchived || !m.archived)"
        :selected="selectedId"
        @select="select"
      />
      <p v-if="!materials.length" class="empty">
        {{ t("Upload course materials to begin.") }}
      </p>
    </aside>
    <section class="panel">
      <template v-if="selected"
        ><form class="row wrap material-edit" @submit.prevent="save">
          <label class="grow"
            >{{ t("Material title") }}<input v-model="title" required /></label
          ><label
            >{{ t("Visibility")
            }}<select v-model="visibility">
              <option value="student">{{ t("Students and teachers") }}</option>
              <option value="teacher">{{ t("Teachers and AI only") }}</option>
            </select></label
          ><button :disabled="busy">{{ t("Save") }}</button
          ><button
            type="button"
            :class="{ 'warning-action': !selected.archived }"
            :disabled="busy"
            @click="archive"
          >
            {{ t(selected.archived ? "Restore" : "Archive") }}</button
          ><button
            v-if="
              !['queued', 'processing'].includes(selected.status) &&
              !selected.archived
            "
            type="button"
            :disabled="busy"
            @click="retry"
          >
            {{ t("Reprocess material") }}
          </button>
        </form>
        <CourseMaterialPreview
          :key="selected.id + selected.status"
          :material="selected"
      /></template>
      <p v-else class="empty">
        {{ t("Select a material from the folder tree to preview it.") }}
      </p>
    </section>
  </div>
</template>
