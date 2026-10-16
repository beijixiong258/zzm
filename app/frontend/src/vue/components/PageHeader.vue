<script setup lang="ts">
defineProps<{
  title: string;
  eyebrow?: string;
  description?: string;
  level?: 1 | 2;
}>();
</script>
<template>
  <header class="page-header">
    <div>
      <p v-if="eyebrow" class="eyebrow">{{ eyebrow }}</p>
      <component :is="level === 2 ? 'h2' : 'h1'">{{ title }}</component>
      <p v-if="description" class="muted">{{ description }}</p>
    </div>
    <div class="actions"><slot /></div>
  </header>
</template>
