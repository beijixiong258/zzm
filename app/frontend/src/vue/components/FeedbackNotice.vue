<script setup lang="ts">
import { t, systemText } from "../../i18n";

defineProps<{ error?: string; success?: string; busy?: boolean }>();
</script>
<template>
  <p v-if="error" role="alert" class="notice error">{{ systemText(error) }}</p>
  <p v-if="success" role="status" class="notice success">
    {{ systemText(success) }}
  </p>
  <p v-if="busy" role="status" class="loading-line">
    <span class="spinner" /> {{ t("Working…") }}
  </p>
</template>
