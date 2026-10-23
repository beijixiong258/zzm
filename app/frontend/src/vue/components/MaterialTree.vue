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
  props.materials.filter(
    (m) =>
      !(m.relativePath || m.fileName).slice(prefix.value.length).includes("/"),
  ),
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
      v-for="material in files"
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
        <span>{{ material.title }}</span
        ><small class="status-label" :data-status="material.status">{{
          statusText(material.status)
        }}</small>
        <MaterialProgress :material="material" />
      </button>
    </li>
  </ul>
</template>
