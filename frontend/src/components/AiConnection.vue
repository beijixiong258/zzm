<script setup lang="ts">
import { Button as TButton } from "tdesign-vue-next";
import { ref } from "vue";
import { t, systemText } from "../i18n";
import { call } from "../classroom-api";
const busy = ref(""),
  error = ref("");
const result = ref<{
  connected: boolean;
  model: string;
  elapsedMs: number;
  capability: string;
  detail?: string;
  response?: string;
} | null>(null);
async function check(vision: boolean) {
  busy.value = vision ? "vision" : "text";
  error.value = "";
  result.value = null;
  try {
    result.value = await call(`/ai/connection?vision=${vision}`, "POST");
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = "";
  }
}
</script>
<template>
  <div class="ai-connection">
    <div class="row wrap">
      <TButton
        theme="default"
        variant="outline"
        type="button"
        :disabled="!!busy"
        @click="check(false)"
      >
        {{
          t(busy === "text" ? "Checking connection…" : "Test AI connection")
        }}</TButton
      ><TButton
        theme="default"
        variant="outline"
        type="button"
        :disabled="!!busy"
        @click="check(true)"
      >
        {{
          t(busy === "vision" ? "Checking vision…" : "Test image understanding")
        }}
      </TButton>
    </div>
    <p
      v-if="result"
      :class="result.connected ? 'success' : 'error'"
      role="status"
    >
      {{ t(result.connected ? "Connection successful" : "Connection failed") }}
      · {{ result.model }} · {{ result.elapsedMs }} ms
      <span v-if="result.detail">— {{ systemText(result.detail) }}</span>
    </p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
  </div>
</template>
