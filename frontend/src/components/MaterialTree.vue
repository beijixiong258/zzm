<script setup lang="ts">
import { ChevronRight } from "lucide-vue-next";
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
defineSlots<{
  details?(props: { material: Material }): unknown;
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
  // 与请求校验规则一致：原生文本和提取文本采用保守上界；
  // PDF 页面图像使用处理后的图像估算值，不计入旧版文字识别用量。
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
        >
          <template v-if="$slots.details" #details="{ material }">
            <slot name="details" :material="material" />
          </template>
        </MaterialTree>
      </details>
    </li>
    <li
      v-for="{ material, inputTokens, exceedsInputLimit } in files"
      :key="material.id"
      :class="{ 'tree-file-card': $slots.details }"
    >
      <div class="tree-file" :class="{ selected: selected === material.id }">
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
          :class="{ 'tree-file-toggle': $slots.details }"
          :aria-expanded="$slots.details ? selected === material.id : undefined"
          @click="emit('select', material)"
        >
          <template v-if="$slots.details" #icon>
            <ChevronRight
              class="tree-file-chevron"
              :size="16"
              aria-hidden="true"
            />
          </template>
          <span class="tree-file-title">{{ material.title }}</span>
          <span class="material-status-row">
            <small class="status-label" :data-status="material.status">{{
              statusText(material.status)
            }}</small>
            <template v-if="!$slots.details || selected === material.id">
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
                    inputTokens.toLocaleString(),
                    inputTokenLimit.toLocaleString(),
                  ])
                }}</small
              >
              <small v-if="exceedsInputLimit" class="token-risk">{{
                t("High local estimate · reminder only")
              }}</small>
            </template>
          </span>
          <MaterialProgress v-if="!$slots.details" :material="material" />
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
      </div>
      <div
        v-if="$slots.details && selected === material.id"
        class="tree-file-details"
      >
        <slot name="details" :material="material" />
      </div>
    </li>
  </ul>
</template>
