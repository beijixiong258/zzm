<script setup lang="ts">
withDefaults(defineProps<{ large?: boolean; wordmark?: boolean }>(), {
  wordmark: true,
});
</script>
<template>
  <span :class="['brand-lockup', { large }]">
    <span class="brand-mark"
      ><img src="/aicademiya-mark-light.svg" alt=""
    /></span>
    <span v-if="wordmark">AIcademiya</span>
  </span>
</template>
