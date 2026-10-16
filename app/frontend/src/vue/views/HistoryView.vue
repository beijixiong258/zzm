<script setup lang="ts">
import { ref } from "vue";
import { api } from "../../api";
import type { LearningRun } from "../../types";
import { useTask, dateText, navigate, label } from "../state";
import PageHeader from "../components/PageHeader.vue";
import ItemRow from "../components/ItemRow.vue";
import FeedbackNotice from "../components/FeedbackNotice.vue";
const rows = ref<LearningRun[]>([]);
const { busy, error, run } = useTask();
void run(async () => {
  rows.value = await api.history();
});
</script>
<template>
  <PageHeader
    title="Learning history"
    description="Return to your work in its original course version."
  /><FeedbackNotice :error="error" :busy="busy" />
  <div class="item-list">
    <ItemRow
      v-for="r in rows"
      :key="r.session.id + ':' + r.version.id"
      :title="r.session.title"
      :description="r.course.title"
      :number="r.session.number"
      ><template #meta
        ><span class="badge">{{ label(r.status) }}</span
        ><span>Version {{ r.version.number }}</span
        ><span>{{ dateText(r.last_active) }}</span></template
      ><template #actions
        ><button
          class="secondary"
          @click="
            navigate({
              page: 'workspace',
              sid: r.session.id,
              version: r.version.id,
            })
          "
        >
          Open saved work
        </button></template
      ></ItemRow
    >
    <div v-if="!rows.length && !busy" class="empty-state">
      Your learning history will appear here.
    </div>
  </div>
</template>
