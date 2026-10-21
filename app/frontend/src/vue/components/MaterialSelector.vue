<script setup lang="ts">
import { computed, ref } from "vue";
import { t } from "../../i18n";
import { label } from "../utils";
import type { Material } from "../../types";
import FilterBar from "./FilterBar.vue";
const props = defineProps<{
  materials: Material[];
  modelValue: string[];
  disabled?: boolean;
}>();
const emit = defineEmits<{
  "update:modelValue": [string[]];
  preview: [Material];
}>();
const query = ref("");
const matches = computed(() =>
  props.materials.filter((m) =>
    `${m.title} ${m.source_label} ${m.source_relative_path || ""}`
      .toLowerCase()
      .includes(query.value.trim().toLowerCase()),
  ),
);
function toggle(id: string, checked: boolean) {
  emit(
    "update:modelValue",
    checked
      ? [...props.modelValue, id]
      : props.modelValue.filter((value) => value !== id),
  );
}
</script>
<template>
  <FilterBar :active="!!query"
    ><label class="grow"
      >{{ t("Search materials")
      }}<input
        v-model="query"
        type="search"
        :placeholder="t('Search title or source path…')" /></label
  ></FilterBar>
  <p class="list-caption">{{ t("{0} selected", [modelValue.length]) }}</p>
  <div class="material-selector">
    <div v-for="m in matches" :key="m.id" class="selection-row">
      <label class="check"
        ><input
          type="checkbox"
          :checked="modelValue.includes(m.id)"
          :disabled="disabled"
          @change="toggle(m.id, ($event.target as HTMLInputElement).checked)"
        /><span
          >{{ m.title
          }}<small
            >{{ label(m.kind) }} ·
            {{ m.source_relative_path || m.source_label }} ·
            {{
              m.visibility === "teacher"
                ? t("Teacher only")
                : t("Student visible")
            }}</small
          ></span
        ></label
      ><button type="button" class="secondary" @click="emit('preview', m)">
        {{ t("Preview") }}
      </button>
    </div>
  </div>
  <p v-if="!matches.length" class="muted">{{ t("No matching materials") }}</p>
</template>
