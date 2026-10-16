<script setup lang="ts">
import { ref } from "vue";
import { api } from "../../api";
import type { CourseMaterial } from "../../types";
import { courses, useTask } from "../state";
import PageHeader from "../components/PageHeader.vue";
import MaterialsPane from "../components/MaterialsPane.vue";
import FeedbackNotice from "../components/FeedbackNotice.vue";
const props = defineProps<{ courseId: string }>();
const materials = ref<CourseMaterial[]>([]);
const { busy, error, run } = useTask();
async function load() {
  await run(async () => {
    materials.value = (await api.courseMaterials(props.courseId)).materials;
  });
}
void load();
</script>
<template>
  <PageHeader
    title="Course library"
    :eyebrow="courses.find((c) => c.id === courseId)?.code"
    description="All files and links saved in this course. Add or edit them from a session’s Materials tab."
    ><button class="secondary" :disabled="busy" @click="load">
      Refresh
    </button></PageHeader
  ><FeedbackNotice :error="error" :busy="busy" /><MaterialsPane
    :materials="materials"
  />
</template>
