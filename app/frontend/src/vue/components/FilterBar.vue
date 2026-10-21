<script setup lang="ts">
import { ref } from "vue";
import { t } from "../../i18n";
defineProps<{ active?: boolean }>();
const open = ref(false);
</script>
<template>
  <div class="filter-shell">
    <button
      type="button"
      class="secondary filter-toggle"
      :aria-expanded="open"
      @click="open = !open"
    >
      {{ open ? t("Hide filters") : t("Search & filters")
      }}<span v-if="active" class="badge">{{ t("Active") }}</span>
    </button>
    <div class="filter-bar" :class="{ 'filter-open': open }"><slot /></div>
  </div>
</template>
