<script setup lang="ts">
import { computed } from "vue";
import MaterialProgress from "./MaterialProgress.vue";
import { t } from "../../i18n";
import { statusText, type Material } from "../../classroom-api";
const props = defineProps<{
  materials: Material[];
  prefix?: string;
  selected?: string;
  selectable?: boolean;
  checked?: string[];
}>();
const emit = defineEmits<{
  select: [material: Material];
  check: [id: string, checked: boolean];
}>();
const prefix = computed(() => props.prefix || "");
const inputTokenLimit = 40000;
function materialInputTokens(material: Material): number | null {
  const report = material.extractionReport;
  if (
    !["ready", "needsReview"].includes(material.status) ||
    !report ||
    report.truncated ||
    !report.failedUnits ||
    report.failedUnits.length ||
    !(report.unitsTotal > 0) ||
    report.unitsProcessed !== report.unitsTotal
  )
    return null;
  const isPdf =
    material.mimeType === "application/pdf" ||
    material.fileName.toLowerCase().endsWith(".pdf");
  if (isPdf && !["text", "images"].includes(report.pdfInputMode || ""))
    return null;
  // Match the request gate: native/extracted text uses its conservative upper bound;
  // PDF page images use the prepared image estimate, without legacy OCR usage.
  const tokens =
    isPdf && report.pdfInputMode === "images"
      ? report.imageInputTokensEstimated
      : report.textTokensUpperBound;
  return typeof tokens === "number" && Number.isFinite(tokens) && tokens >= 0
    ? Math.ceil(tokens)
    : null;
}
const folders = computed(() =>
  [
    ...new Set(
      props.materials.flatMap((m) => {
        const remaining = (m.relativePath || m.fileName).slice(
          prefix.value.length,
        );
        return remaining.includes("/") ? [remaining.split("/")[0]] : [];
      }),
    ),
  ].sort(),
);
const files = computed(() =>
  props.materials
    .filter(
      (m) =>
        !(m.relativePath || m.fileName)
          .slice(prefix.value.length)
          .includes("/"),
    )
    .map((material) => {
      const inputTokens = materialInputTokens(material);
      return {
        material,
        inputTokens,
        exceedsInputLimit: inputTokens != null && inputTokens > inputTokenLimit,
      };
    }),
);
</script>
<template>
  <ul class="material-tree">
    <li v-for="folder in folders" :key="folder">
      <details open>
        <summary>{{ folder }}</summary>
        <MaterialTree
          :materials="
            materials.filter((m) =>
              (m.relativePath || m.fileName).startsWith(prefix + folder + '/'),
            )
          "
          :prefix="prefix + folder + '/'"
          :selected="selected"
          :selectable="selectable"
          :checked="checked"
          @select="emit('select', $event)"
          @check="(id, value) => emit('check', id, value)"
        />
      </details>
    </li>
    <li
      v-for="{ material, inputTokens, exceedsInputLimit } in files"
      :key="material.id"
      class="tree-file"
      :class="{ selected: selected === material.id }"
    >
      <input
        v-if="selectable"
        type="checkbox"
        :checked="checked?.includes(material.id)"
        :aria-label="t('Select {0}', [material.title])"
        @change="
          emit(
            'check',
            material.id,
            ($event.target as HTMLInputElement).checked,
          )
        "
      />
      <button type="button" @click="emit('select', material)">
        <span>{{ material.title }}</span>
        <span class="material-status-row">
          <small
            class="status-label"
            :data-status="
              exceedsInputLimit ? 'inputLimitExceeded' : material.status
            "
            >{{
              exceedsInputLimit
                ? t("Processing complete · AI input limit exceeded")
                : statusText(material.status)
            }}</small
          >
          <small
            v-if="exceedsInputLimit"
            class="material-token-usage"
            :title="
              t(
                'Material only. Text uses a conservative upper bound; PDF images use an estimate. Prompts and other selected materials use additional capacity.',
              )
            "
            >{{
              t("Estimated use: {0} tokens / limit: {1}", [
                inputTokens?.toLocaleString(),
                inputTokenLimit.toLocaleString(),
              ])
            }}</small
          >
        </span>
        <MaterialProgress :material="material" />
      </button>
    </li>
  </ul>
</template>
