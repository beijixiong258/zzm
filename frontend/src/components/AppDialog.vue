<script setup lang="ts">
import { Dialog as TDialog } from "tdesign-vue-next";
import { nextTick, onMounted, onUnmounted, ref } from "vue";

defineProps<{ title: string; wide?: boolean; busy?: boolean }>();
defineEmits<{ close: [] }>();
const trigger = document.activeElement as HTMLElement | null;
const content = ref<HTMLElement | null>(null);
onMounted(async () => {
  await nextTick();
  content.value?.focus();
});
onUnmounted(() => trigger?.focus());
</script>

<template>
  <TDialog
    visible
    :header="title"
    :footer="false"
    :close-btn="!busy"
    :close-on-esc-keydown="!busy"
    :close-on-overlay-click="!busy"
    :width="
      wide
        ? 'min(1100px, calc(100vw - 32px))'
        : 'min(580px, calc(100vw - 32px))'
    "
    placement="center"
    dialog-class-name="app-dialog"
    @close="$emit('close')"
  >
    <div
      ref="content"
      class="app-dialog-content"
      role="dialog"
      aria-modal="true"
      :aria-label="title"
      tabindex="-1"
    >
      <slot />
    </div>
  </TDialog>
</template>
