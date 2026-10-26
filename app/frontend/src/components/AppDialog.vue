<script setup lang="ts">
import { t } from "../i18n";

defineProps<{ title: string; wide?: boolean; busy?: boolean }>();
defineEmits<{ close: [] }>();
</script>

<template>
  <div
    class="modal-backdrop"
    @click.self="!busy && $emit('close')"
    @keydown.esc.stop="!busy && $emit('close')"
  >
    <section
      class="modal"
      :class="{ wide }"
      role="dialog"
      aria-modal="true"
      :aria-label="title"
    >
      <header class="page-return-bar">
        <strong>{{ title }}</strong>
        <button type="button" :disabled="busy" @click="$emit('close')">
          {{ t("Close") }}
        </button>
      </header>
      <slot />
    </section>
  </div>
</template>
