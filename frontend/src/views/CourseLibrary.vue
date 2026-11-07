<script setup lang="ts">
import { confirmAction } from "../confirmAction";
import {
  Checkbox as TCheckbox,
  Button as TButton,
  Select as TSelect,
  Option as TOption,
  Input as TInput,
} from "tdesign-vue-next";
import { computed, ref, watch } from "vue";
import { systemText, t } from "../i18n";
import { call, key, type Material } from "../classroom-api";
import { courses, navigate } from "../classroom-state";
import { useCourseMaterials } from "../useCourseMaterials";
import FileUploader from "../components/FileUploader.vue";
import MaterialTree from "../components/MaterialTree.vue";
import CourseMaterialPreview from "../components/CourseMaterialPreview.vue";
const props = defineProps<{ courseId: string }>();
const course = computed(() =>
  courses.value.find((item) => item.id === props.courseId),
);
const {
  materials,
  error: materialError,
  load,
} = useCourseMaterials(() => props.courseId);
const expandedId = ref(""),
  showArchived = ref(false),
  busy = ref(false),
  error = ref("");
const title = ref(""),
  visibility = ref<"student" | "teacher">("student");
const visibleMaterials = computed(() =>
  materials.value.filter(
    (material) => showArchived.value || !material.archived,
  ),
);
watch(visibleMaterials, (visible) => {
  if (!visible.some((material) => material.id === expandedId.value)) {
    expandedId.value = "";
  }
});
function toggleMaterial(material: Material) {
  if (expandedId.value === material.id) {
    expandedId.value = "";
    return;
  }
  expandedId.value = material.id;
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
async function saveMaterial(material: Material) {
  await action(async () => {
    await call(`/materials/${key(material.id)}`, "PUT", {
      title: title.value,
      visibility: visibility.value,
    });
  });
}
async function archiveMaterial(material: Material) {
  if (
    !(await confirmAction(
      t(
        material.archived
          ? "Restore this material to course materials? Existing task references will be kept."
          : "Change the archive state of this material? Published versions keep their original references.",
      ),
    ))
  )
    return;
  await action(async () => {
    await call(
      `/materials/${key(material.id)}/archive?archived=${!material.archived}`,
      "POST",
    );
  });
}
async function retryMaterial(material: Material) {
  await action(async () => {
    await call(`/materials/${key(material.id)}/retry`, "POST");
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
    if (expandedId.value === material.id) expandedId.value = "";
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
      <p class="eyebrow">{{ course?.title }}</p>
      <h1>{{ t("Course materials") }}</h1>
      <p class="muted">
        {{
          t("Organize materials once, then reuse them across learning tasks.")
        }}
      </p>
    </div>
  </header>
  <section class="panel library-upload">
    <FileUploader
      :endpoint="`/courses/${key(courseId)}/materials`"
      @settled="load"
    />
  </section>
  <p class="muted">
    {{
      t(
        "Supported: PDF, Word, PowerPoint, Excel, text and images. Up to 25 MiB per file.",
      )
    }}
  </p>
  <p v-if="error || materialError" class="error" role="alert">
    {{ systemText(error || materialError) }}
  </p>
  <section class="panel">
    <TCheckbox v-model="showArchived">{{ t("Show archived items") }}</TCheckbox>
    <div v-if="visibleMaterials.length" class="course-materials-scroll">
      <MaterialTree
        :materials="visibleMaterials"
        :selected="expandedId"
        deletable
        :disabled="busy"
        @select="toggleMaterial"
        @remove="removeMaterial"
      >
        <template #details="{ material }">
          <form
            class="row wrap material-edit"
            @submit.prevent="saveMaterial(material)"
          >
            <label class="grow">
              {{ t("Material title") }}
              <TInput v-control-attrs="{ required: true }" v-model="title" />
            </label>
            <label>
              {{ t("Visibility") }}
              <TSelect v-model="visibility">
                <TOption value="student" :label="t('Students and teachers')" />
                <TOption value="teacher" :label="t('Teachers and AI only')" />
              </TSelect>
            </label>
            <div class="row wrap material-edit-actions">
              <TButton
                theme="default"
                variant="outline"
                type="submit"
                :disabled="busy"
              >
                {{ t("Save") }}
              </TButton>
              <TButton
                theme="default"
                variant="outline"
                type="button"
                :class="{ 'warning-action': !material.archived }"
                :disabled="busy"
                @click="archiveMaterial(material)"
              >
                {{ t(material.archived ? "Restore" : "Archive") }}
              </TButton>
              <TButton
                v-if="
                  !['queued', 'processing'].includes(material.status) &&
                  !material.archived
                "
                theme="default"
                variant="outline"
                type="button"
                :disabled="busy"
                @click="retryMaterial(material)"
              >
                {{ t("Reprocess material") }}
              </TButton>
            </div>
          </form>
          <p class="muted">
            {{
              t(
                "Archive hides a material and preserves its file and published references. Show archived items to restore it.",
              )
            }}
          </p>
          <CourseMaterialPreview
            :key="material.status"
            :material="material"
            inline
          />
        </template>
      </MaterialTree>
    </div>
    <p v-else class="empty">
      {{
        t(
          materials.length
            ? "No matching materials"
            : "Upload course materials to begin.",
        )
      }}
    </p>
  </section>
</template>
