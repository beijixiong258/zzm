<script setup lang="ts">
import { confirmAction } from "../confirmAction";
import {
  Checkbox as TCheckbox,
  Button as TButton,
  Select as TSelect,
  Option as TOption,
  Input as TInput,
} from "tdesign-vue-next";
import { computed, ref } from "vue";
import { t } from "../i18n";
import { call, key, type Material } from "../classroom-api";
import { navigate } from "../classroom-state";
import { useCourseMaterials } from "../useCourseMaterials";
import FileUploader from "../components/FileUploader.vue";
import MaterialTree from "../components/MaterialTree.vue";
import CourseMaterialPreview from "../components/CourseMaterialPreview.vue";
const props = defineProps<{ courseId: string }>();
const {
  materials,
  error: materialError,
  load,
} = useCourseMaterials(() => props.courseId);
const selectedId = ref(""),
  showArchived = ref(false),
  busy = ref(false),
  error = ref("");
const title = ref(""),
  visibility = ref<"student" | "teacher">("student");
const uploadVisibility = ref<"student" | "teacher">("student");
const selected = computed(() =>
  materials.value.find((m) => m.id === selectedId.value),
);
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
    !(await confirmAction(
      t(
        "Change the archive state of this material? Published versions keep their original references.",
      ),
    ))
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
async function removeMaterial(material: Material) {
  if (
    busy.value ||
    !(await confirmAction(
      t(
        "Delete {0}? Unused uploaded files will be moved to the recycle folder.",
        [material.title],
      ),
    ))
  )
    return;
  await action(async () => {
    await call(`/materials/${key(material.id)}`, "DELETE");
    if (selectedId.value === material.id) selectedId.value = "";
  });
}
void load();
</script>
<template>
  <nav class="page-return-bar" :aria-label="t('Back')">
    <TButton
      theme="default"
      variant="outline"
      type="button"
      @click="navigate({ page: 'course', courseId })"
    >
      ← {{ t("Back to course") }}
    </TButton>
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
        }}<TSelect v-model="uploadVisibility">
          <TOption value="student" :label="t('Students and teachers')" />
          <TOption
            value="teacher"
            :label="t('Teachers and AI only')"
          /> </TSelect
      ></label>
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
  <p v-if="error || materialError" class="error" role="alert">
    {{ error || materialError }}
  </p>
  <div class="library-layout">
    <aside class="panel">
      <TCheckbox v-model="showArchived">{{
        t("Show archived items")
      }}</TCheckbox
      ><MaterialTree
        :materials="materials.filter((m) => showArchived || !m.archived)"
        :selected="selectedId"
        deletable
        :disabled="busy"
        @select="select"
        @remove="removeMaterial"
      />
      <p v-if="!materials.length" class="empty">
        {{ t("Upload course materials to begin.") }}
      </p>
    </aside>
    <section class="panel">
      <template v-if="selected"
        ><form class="row wrap material-edit" @submit.prevent="save">
          <label class="grow"
            >{{ t("Material title")
            }}<TInput
              v-control-attrs="{ required: true }"
              v-model="title" /></label
          ><label
            >{{ t("Visibility")
            }}<TSelect v-model="visibility">
              <TOption value="student" :label="t('Students and teachers')" />
              <TOption
                value="teacher"
                :label="t('Teachers and AI only')"
              /> </TSelect></label
          ><TButton
            theme="default"
            variant="outline"
            type="submit"
            :disabled="busy"
            >{{ t("Save") }}</TButton
          ><TButton
            theme="default"
            variant="outline"
            type="button"
            :class="{ 'warning-action': !selected.archived }"
            :disabled="busy"
            @click="archive"
          >
            {{ t(selected.archived ? "Restore" : "Archive") }}</TButton
          ><TButton
            theme="default"
            variant="outline"
            v-if="
              !['queued', 'processing'].includes(selected.status) &&
              !selected.archived
            "
            type="button"
            :disabled="busy"
            @click="retry"
          >
            {{ t("Reprocess material") }}
          </TButton>
        </form>
        <p class="muted">
          {{
            t(
              "Archive hides a material and preserves its file and published references. Show archived items to restore it.",
            )
          }}
        </p>
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
