<script setup lang="ts">
import { computed } from "vue";
import { t } from "../../i18n";
const props = defineProps<{
  modelValue?: "student" | "teacher";
  kind: string;
  disabled?: boolean;
  allowDefault?: boolean;
  defaultVisibility?: "student" | "teacher";
}>();
const emit = defineEmits<{
  "update:modelValue": ["student" | "teacher" | undefined];
}>();
const effective = computed({
  get: () => (props.kind === "answer_key" ? "teacher" : props.modelValue),
  set: (value) => {
    if (props.kind !== "answer_key") emit("update:modelValue", value);
  },
});
</script>
<template>
  <select v-model="effective" :disabled="disabled || kind === 'answer_key'">
    <option v-if="allowDefault" :value="undefined">
      {{ t("Use default visibility") }} ·
      {{
        defaultVisibility === "teacher"
          ? t("Teachers only")
          : t("Students and teachers")
      }}
    </option>
    <option value="student">{{ t("Students and teachers") }}</option>
    <option value="teacher">{{ t("Teachers only") }}</option>
  </select>
</template>
