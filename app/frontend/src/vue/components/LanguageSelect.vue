<script setup lang="ts">
import { locale, setLocale, t } from "../../i18n";
</script>

<template>
  <select
    class="language-select"
    :aria-label="t('Interface language')"
    :title="
      t(
        'The interface language does not change course content or the teaching language.',
      )
    "
    :value="locale"
    @change="setLocale(($event.target as HTMLSelectElement).value)"
  >
    <option value="zh-CN">简体中文</option>
    <option value="en">English</option>
  </select>
</template>
