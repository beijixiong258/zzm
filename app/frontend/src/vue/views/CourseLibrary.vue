<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue";
import { t } from "../../i18n";
import { call, key, type Material } from "../../classroom-api";
import MaterialTree from "../components/MaterialTree.vue";
import CourseMaterialPreview from "../components/CourseMaterialPreview.vue";
const props = defineProps<{ courseId: string }>();
const materials = ref<Material[]>([]),
  selectedId = ref(""),
  showArchived = ref(false),
  busy = ref(false),
  error = ref(""),
  progress = ref("");
const title = ref(""),
  visibility = ref<"student" | "teacher">("student");
const selected = computed(() =>
  materials.value.find((m) => m.id === selectedId.value),
);
let timer: ReturnType<typeof setTimeout> | undefined,
  disposed = false;
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
  } catch (e) {
    error.value = (e as Error).message;
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
async function upload(event: Event) {
  const input = event.target as HTMLInputElement;
  const files = [...(input.files || [])];
  await action(async () => {
    for (let index = 0; index < files.length; index++) {
      const file = files[index];
      progress.value = `${index + 1}/${files.length} · ${file.name}`;
      const body = new FormData();
      body.set("file", file);
      body.set("relativePath", file.webkitRelativePath || file.name);
      body.set("visibility", "student");
      const created = await call<Material>(
        `/courses/${key(props.courseId)}/materials`,
        "POST",
        body,
      );
      select(created);
    }
  });
  progress.value = "";
  input.value = "";
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
  <header class="page-heading">
    <div>
      <p class="eyebrow">{{ t("COURSE LIBRARY") }}</p>
      <h1>{{ t("Course materials") }}</h1>
      <p class="muted">
        {{
          t("Organize materials once, then reuse them across learning tasks.")
        }}
      </p>
    </div>
    <div class="row">
      <label class="button primary"
        >＋ {{ t("Upload files")
        }}<input
          type="file"
          accept=".pdf,.docx,.doc,.pptx,.ppt,.xlsx,.xls,.txt,.md,.png,.jpg,.jpeg,.webp"
          multiple
          hidden
          :disabled="busy"
          @change="upload" /></label
      ><label class="button"
        >＋ {{ t("Upload folder")
        }}<input
          type="file"
          accept=".pdf,.docx,.doc,.pptx,.ppt,.xlsx,.xls,.txt,.md,.png,.jpg,.jpeg,.webp"
          multiple
          webkitdirectory
          hidden
          :disabled="busy"
          @change="upload"
      /></label>
    </div>
  </header>
  <p class="muted">
    {{
      t(
        "Supported: PDF, Word, PowerPoint, Excel, text and images. Up to 25 MiB per file.",
      )
    }}
  </p>
  <p v-if="error" class="error" role="alert">{{ error }}</p>
  <p v-if="progress" role="status">{{ t("Uploading {0}", [progress]) }}</p>
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
          ><button type="button" :disabled="busy" @click="archive">
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
