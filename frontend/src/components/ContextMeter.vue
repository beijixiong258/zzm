<script setup lang="ts">
import { t } from "../i18n";
import type { ContextUsage } from "../classroom-api";
defineProps<{
  usage: ContextUsage | null;
  loading?: boolean;
  embedded?: boolean;
}>();
const number = (value: number) => value.toLocaleString();
</script>
<template>
  <section
    class="context-meter"
    :class="{ 'is-embedded': embedded }"
    aria-live="polite"
  >
    <template v-if="!embedded">
      <strong>{{ t("Local token estimate") }}</strong>
      <p class="muted">
        {{
          t(
            "Local estimates are advisory only. The provider determines capacity, actual usage and request acceptance.",
          )
        }}
      </p>
    </template>
    <p v-if="loading" class="muted">{{ t("Estimating context…") }}</p>
    <template v-if="usage">
      <p>
        {{
          t("Estimated input: {0}; conservative upper bound: {1} tokens.", [
            number(usage.inputEstimate),
            number(usage.inputUpperBound),
          ])
        }}
      </p>
      <p>
        {{
          t(
            "Reference context: {0}; input reminder line: {1}; estimated images: {2} tokens.",
            [
              number(usage.window),
              number(usage.inputLimit ?? 200000),
              number(usage.imageEstimate),
            ],
          )
        }}
      </p>
      <small>{{
        t(
          "Requested maximum output: {0} tokens. This is independent of the local input estimate.",
          [number(usage.outputReserve)],
        )
      }}</small>
      <p v-if="usage.estimatedOverReference" class="notice">
        {{
          t(
            usage.contextStrategy === "retrieval"
              ? "The required context exceeds the configured tutor limit. Narrow the question before sending."
              : "The local estimate exceeds a reference line. You can still send; the provider may accept or reject the request.",
          )
        }}
      </p>
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
        <p v-if="usage.contextStrategy === 'retrieval'">
          {{
            t(
              "The tutor selects relevant questions, recent conversation and source excerpts. Earlier records remain available. The estimate before sending excludes any additional reading.",
            )
          }}
        </p>
        <p v-else>
          {{
            t(
              "All selected PDF pages are sent in order. Local estimates never remove pages, materials or conversation history.",
            )
          }}
        </p>
      </details>
    </template>
  </section>
</template>
<style scoped>
.context-meter.is-embedded {
  padding: 0;
  border: 0;
  background: none;
}
</style>
