<script setup lang="ts">
defineProps<{ error?: string; success?: string; busy?: boolean }>();
</script>
<template>
  <p v-if="error" role="alert" class="notice error">{{ error }}</p>
  <p v-if="success" role="status" class="notice success">{{ success }}</p>
  <p v-if="busy" role="status" class="loading-line">
    <span class="spinner" /> Working…
  </p>
</template>
