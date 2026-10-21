<script setup lang="ts">
import { t } from "../../i18n";

import { computed, onMounted, onBeforeUnmount, ref, useId } from "vue";
import { X } from "lucide-vue-next";
import { useDirty } from "../state";
const props = withDefaults(
  defineProps<{
    title: string;
    busy?: boolean;
    dirty?: boolean;
    wide?: boolean;
    compact?: boolean;
    closeLabel?: string;
  }>(),
  { busy: false, dirty: false, wide: false, compact: false },
);
const emit = defineEmits<{ close: [] }>();
const dialog = ref<HTMLDialogElement>();
const titleId = useId();
const discarding = ref(false);
const held = computed(() => props.dirty || props.busy);
useDirty(held);
let previous: HTMLElement | null = null;
let overflow = "";
onMounted(() => {
  previous = document.activeElement as HTMLElement;
  overflow = document.body.style.overflow;
  document.body.style.overflow = "hidden";
  dialog.value?.showModal();
});
onBeforeUnmount(() => {
  dialog.value?.close();
  document.body.style.overflow = overflow;
  if (previous?.isConnected) previous.focus();
});
function close() {
  if (props.busy) return;
  if (props.dirty) discarding.value = true;
  else emit("close");
}
</script>
<template>
  <Teleport to="body"
    ><dialog
      ref="dialog"
      class="editor-dialog"
      :class="{ wide, compact }"
      :aria-labelledby="titleId"
      @cancel.prevent="close"
    >
      <header class="dialog-heading">
        <h2 :id="titleId">{{ title }}</h2>
        <button
          class="icon-button"
          :aria-label="t('Close window')"
          :disabled="busy"
          @click="close"
        >
          <X :size="20" />
        </button>
      </header>
      <div class="dialog-body"><slot /></div>
      <footer class="dialog-footer">
        <template v-if="discarding"
          ><span class="discard-message" role="alert">{{
            t("Discard unsaved changes?")
          }}</span
          ><button class="secondary" @click="discarding = false">
            {{ t("Keep editing") }}</button
          ><button class="secondary danger" @click="emit('close')">
            {{ t("Discard changes") }}
          </button></template
        ><template v-else
          ><button class="secondary" :disabled="busy" @click="close">
            {{ closeLabel || t("Cancel") }}</button
          ><slot name="actions"
        /></template>
      </footer></dialog
  ></Teleport>
</template>
