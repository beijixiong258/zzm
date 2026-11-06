<script setup lang="ts">
import { Button as TButton } from "tdesign-vue-next";
import { onBeforeUnmount, ref } from "vue";
import { t, systemText } from "../i18n";
import { call } from "../classroom-api";
type ConnectionResult = {
  connected: boolean;
  model: string;
  elapsedMs: number;
  capability: string;
  detail?: string;
  response?: string;
};
const busy = ref(""),
  error = ref("");
const result = ref<ConnectionResult | null>(null);
let request: AbortController | undefined;
let disposed = false;
onBeforeUnmount(() => {
  disposed = true;
  request?.abort();
});
async function check(vision: boolean) {
  if (disposed || busy.value) return;
  busy.value = vision ? "vision" : "text";
  error.value = "";
  result.value = null;
  const controller = new AbortController();
  request = controller;
  const timeout = setTimeout(() => controller.abort(), 18000);
  try {
    const response = await call<ConnectionResult>(
      `/ai/connection?vision=${vision}`,
      "POST",
      undefined,
      controller.signal,
    );
    if (!disposed) result.value = response;
  } catch (e) {
    if (!disposed)
      error.value = controller.signal.aborted
        ? t("The connection check did not finish in time. Try again shortly.")
        : systemText((e as Error).message);
  } finally {
    clearTimeout(timeout);
    request = undefined;
    if (!disposed) busy.value = "";
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
    <p v-if="error" class="error" role="alert">{{ systemText(error) }}</p>
  </div>
</template>
