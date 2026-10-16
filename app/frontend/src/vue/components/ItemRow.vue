<script setup lang="ts">
defineProps<{
  title: string;
  description?: string;
  number?: number | string;
}>();
</script>
<template>
  <article class="item-row">
    <span v-if="number !== undefined" class="item-number">{{
      String(number).padStart(2, "0")
    }}</span>
    <div class="item-body">
      <h3>{{ title }}</h3>
      <p v-if="description" class="item-description">{{ description }}</p>
      <div v-if="$slots.meta" class="item-meta"><slot name="meta" /></div>
      <slot />
    </div>
    <div class="actions item-actions"><slot name="actions" /></div>
  </article>
</template>
