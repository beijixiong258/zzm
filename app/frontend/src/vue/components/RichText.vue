<script setup lang="ts">
import { computed } from "vue";
import { marked } from "marked";
import DOMPurify from "dompurify";
const props = defineProps<{ text: string }>();
const html = computed(() =>
  DOMPurify.sanitize(
    marked.parse(props.text || "", { async: false }) as string,
  ),
);
</script>
<template><div class="rich-text" v-html="html" /></template>
