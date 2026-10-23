<script setup lang="ts">
defineProps<{ label: string; detail?: string; value?: number | null }>();
</script>
<template>
  <div class="progress-status" role="status">
    <div class="row spread">
      <span
        ><span
          v-if="value == null"
          class="activity-spinner"
          aria-hidden="true"
        />{{ label }}</span
      >
      <small v-if="value != null">{{ Math.round(value) }}%</small>
    </div>
    <progress
      :aria-label="label"
      max="100"
      :value="value == null ? undefined : value"
    />
    <small v-if="detail" class="muted">{{ detail }}</small>
  </div>
</template>
