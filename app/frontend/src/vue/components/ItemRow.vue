<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from "vue";
import { t } from "../../i18n";
const props = defineProps<{
  title: string;
  description?: string;
  number?: number | string;
  expandable?: boolean;
}>();
const expanded = ref(false),
  clipped = ref(false);
const body = ref<HTMLElement>(),
  titleElement = ref<HTMLElement>(),
  descriptionElement = ref<HTMLElement>();
let observer: ResizeObserver | undefined;
function measure() {
  if (expanded.value) return;
  clipped.value = [titleElement.value, descriptionElement.value].some(
    (el) => !!el && el.scrollHeight > el.clientHeight + 1,
  );
}
onMounted(() => {
  if (!props.expandable) return;
  measure();
  if (typeof ResizeObserver !== "undefined") {
    observer = new ResizeObserver(measure);
    if (body.value) observer.observe(body.value);
  }
});
onBeforeUnmount(() => observer?.disconnect());
watch(
  () => [props.title, props.description],
  async () => {
    expanded.value = false;
    await nextTick();
    measure();
  },
);
watch(expanded, async () => {
  if (!expanded.value) {
    await nextTick();
    measure();
  }
});
</script>
<template>
  <article class="item-row" :class="{ 'item-expanded': expanded }">
    <span v-if="number !== undefined" class="item-number">{{
      String(number).padStart(2, "0")
    }}</span>
    <div ref="body" class="item-body">
      <h3 ref="titleElement">{{ title }}</h3>
      <p v-if="description" ref="descriptionElement" class="item-description">
        {{ description }}
      </p>
      <button
        v-if="expandable && clipped"
        type="button"
        class="link-button row-expand"
        :aria-expanded="expanded"
        @click="expanded = !expanded"
      >
        {{ expanded ? t("Collapse text") : t("Read full text") }}
      </button>
      <div v-if="$slots.meta" class="item-meta"><slot name="meta" /></div>
      <slot />
    </div>
    <div v-if="$slots.actions" class="actions item-actions">
      <slot name="actions" />
    </div>
  </article>
</template>
