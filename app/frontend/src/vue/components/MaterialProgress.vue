<script setup lang="ts">
import { computed } from "vue";
import { t, systemText } from "../../i18n";
import { type Material, statusText } from "../../classroom-api";
import ProgressStatus from "./ProgressStatus.vue";
const props = defineProps<{ material: Material }>();
const report = computed(() => props.material.extractionReport);
const percent = computed(() =>
  report.value?.unitsTotal
    ? Math.min(
        100,
        report.value.pdfInputMode
          ? (report.value.pdfInputMode === "inspecting"
              ? ((report.value.unitsInspected || 0) / report.value.unitsTotal) * 50
              : 50 + (report.value.unitsProcessed / report.value.unitsTotal) * 50)
          : (report.value.unitsProcessed / report.value.unitsTotal) * 100,
      )
    : null,
);
</script>
<template>
  <ProgressStatus
    v-if="['queued', 'processing'].includes(material.status)"
    :label="
      report?.currentUnit
        ? t(report.pdfInputMode ? 'Preparing {0}' : 'Reading {0}', [systemText(report.currentUnit)])
        : statusText(material.status)
    "
    :value="percent"
    :detail="
      report?.unitsTotal
        ? t(report.pdfInputMode === 'inspecting'
            ? 'Checked {0} of {1} PDF pages.'
            : 'Prepared {0} of {1} pages or sections.', [
            report.pdfInputMode === 'inspecting' ? (report.unitsInspected || 0) : report.unitsProcessed,
            report.unitsTotal,
          ])
        : t('Preparing document…')
    "
  />
</template>
