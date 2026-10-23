<script setup lang="ts">
import { computed } from "vue";
import { t } from "../../i18n";
import type { ContextUsage } from "../../classroom-api";
const props = defineProps<{ usage: ContextUsage | null; loading?: boolean }>();
const inputLimit = computed(() => props.usage?.inputLimit ?? 40000);
const inputRemaining = computed(() => inputLimit.value - (props.usage?.inputUpperBound ?? 0));
const contextRemaining = computed(() => props.usage
  ? props.usage.window - props.usage.inputUpperBound - props.usage.outputReserve - props.usage.safetyReserve
  : 0);
const number = (value: number) => value.toLocaleString();
</script>
<template>
  <section class="context-meter" aria-live="polite">
    <strong>{{ t("Input budget") }} · {{ number(inputLimit) }} tokens</strong>
    <p v-if="loading" class="muted">{{ t("Estimating context…") }}</p>
    <template v-if="usage">
      <meter
        :value="Math.min(usage.inputUpperBound, inputLimit)"
        :max="inputLimit"
        :high="inputLimit * 0.85"
        :optimum="0"
        :aria-label="t('Input budget')"
      />
      <p>
        {{
          t("Estimated input: {0}; conservative upper bound: {1} tokens.", [
            number(usage.inputEstimate),
            number(usage.inputUpperBound),
          ])
        }}
      </p>
      <p>{{ t("Image input: {0} tokens; remaining input allowance: {1}.", [
        number(usage.imageEstimate), number(Math.max(0, inputRemaining)),
      ]) }}</p>
      <small>{{
        t("Reserved for output: {0}; safety buffer: {1}.", [
          number(usage.outputReserve),
          number(usage.safetyReserve),
        ])
      }}</small>
      <p class="muted">{{ t("Total context: {0} tokens, including input, output and the safety buffer.", [number(usage.window)]) }}</p>
      <p v-if="usage.pendingMaterials?.length" class="notice">
        {{
          t(
            "Some materials are still processing. Their complete content is not included in this estimate yet.",
          )
        }}
      </p>
      <p v-if="usage.incompleteMaterials?.length" class="error">
        {{
          t(
            "Some selected materials are incomplete. Reprocess them or remove them from this task.",
          )
        }}
      </p>
      <p v-if="inputRemaining < 0 || contextRemaining < 0" class="error">
        {{
          t(
            "This request exceeds the 40,000-token input limit or the total context window. Select fewer materials or split the task.",
          )
        }}
      </p>
      <p v-if="usage.promptTokensActual != null" class="muted">
        {{
          t("Provider-reported usage: {0} input, {1} output tokens.", [
            number(usage.promptTokensActual),
            number(usage.completionTokensActual || 0),
          ])
        }}
      </p>
      <details>
        <summary>{{ t("How this is calculated") }}</summary>
        <p>
          {{
            t(
              "Text uses an estimate and a conservative UTF-8 upper bound. Images use SiliconFlow’s Qwen high-detail rule. The provider’s usage is the actual count. Upload size is not a token count.",
            )
          }}
        </p>
        <p>
          {{
            t(
              "PDF images are sent directly with each request that uses them. All pages count toward that request’s input limit. PDF preparation uses no OCR or AI calls.",
            )
          }}
        </p>
      </details>
    </template>
  </section>
</template>
