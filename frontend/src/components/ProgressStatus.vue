<script setup lang="ts">
import { Loading as TLoading, Progress as TProgress } from "tdesign-vue-next";
defineProps<{ label: string; detail?: string; value?: number | null }>();
</script>
<template>
  <div class="progress-status" role="status">
    <div class="row spread">
      <span><TLoading v-if="value == null" size="small" />{{ label }}</span>
      <small v-if="value != null">{{ Math.round(value) }}%</small>
    </div>
    <TProgress
      v-if="value != null"
      :aria-label="label"
      :percentage="value"
      :label="false"
    />
    <small v-if="detail" class="muted">{{ detail }}</small>
  </div>
</template>
