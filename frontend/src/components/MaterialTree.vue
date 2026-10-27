<script setup lang="ts">
import { Button as TButton, Checkbox as TCheckbox } from "tdesign-vue-next";
import { computed } from "vue";
import MaterialProgress from "./MaterialProgress.vue";
import { t } from "../i18n";
import { statusText, type Material } from "../classroom-api";
const props = defineProps<{
  materials: Material[];
  prefix?: string;
  selected?: string;
  selectable?: boolean;
  checked?: string[];
  deletable?: boolean;
  disabled?: boolean;
}>();
const emit = defineEmits<{
  select: [material: Material];
  check: [id: string, checked: boolean];
  remove: [material: Material];
}>();
const prefix = computed(() => props.prefix || "");
const inputTokenLimit = 200000;
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
          :deletable="deletable"
          :disabled="disabled"
          @select="emit('select', $event)"
          @check="(id, value) => emit('check', id, value)"
          @remove="emit('remove', $event)"
        />
      </details>
    </li>
    <li
      v-for="{ material, inputTokens, exceedsInputLimit } in files"
      :key="material.id"
      class="tree-file"
      :class="{ selected: selected === material.id }"
    >
      <TCheckbox
        v-if="selectable"
        :checked="checked?.includes(material.id)"
        :disabled="disabled"
        v-control-attrs="{ 'aria-label': t('Select {0}', [material.title]) }"
        @change="emit('check', material.id, $event)"
      />
      <TButton
        theme="default"
        variant="outline"
        type="button"
        @click="emit('select', material)"
      >
        <span>{{ material.title }}</span>
        <span class="material-status-row">
          <small class="status-label" :data-status="material.status">{{
            statusText(material.status)
          }}</small>
          <small
            v-if="inputTokens != null"
            class="material-token-usage"
            :title="
              t(
                'Local estimates are advisory only. The provider determines capacity, actual usage and request acceptance.',
              )
            "
            >{{
              t("Local estimate: {0} tokens / reminder line: {1}", [
                inputTokens?.toLocaleString(),
                inputTokenLimit.toLocaleString(),
              ])
            }}</small
          >
          <small v-if="exceedsInputLimit" class="token-risk">{{
            t("High local estimate · reminder only")
          }}</small>
        </span>
        <MaterialProgress :material="material" />
      </TButton>
      <TButton
        theme="danger"
        variant="outline"
        v-if="deletable"
        type="button"
        class="danger material-delete"
        :disabled="disabled"
        :aria-label="t('Delete {0}', [material.title])"
        @click.stop="emit('remove', material)"
      >
        {{ t("Delete") }}
      </TButton>
    </li>
  </ul>
</template>
