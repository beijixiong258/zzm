<script setup lang="ts">
import { t } from "../../i18n";
const props = withDefaults(
  defineProps<{
    offset: number;
    total: number;
    limit?: number;
    busy?: boolean;
  }>(),
  { limit: 20 },
);
const emit = defineEmits<{ change: [number] }>();
</script>
<template>
  <nav v-if="total > limit" class="pagination" :aria-label="t('Pagination')">
    <button
      class="secondary"
      :disabled="busy || offset === 0"
      @click="emit('change', Math.max(0, offset - limit))"
    >
      {{ t("Previous") }}
    </button>
    <span>{{
      t("{0}–{1} of {2}", [offset + 1, Math.min(offset + limit, total), total])
    }}</span>
    <button
      class="secondary"
      :disabled="busy || offset + limit >= total"
      @click="emit('change', offset + limit)"
    >
      {{ t("Next") }}
    </button>
  </nav>
</template>
