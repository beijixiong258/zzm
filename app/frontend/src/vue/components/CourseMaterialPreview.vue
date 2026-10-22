<script setup lang="ts">
import { ref, watch } from "vue";
import { t, systemText } from "../../i18n";
import { call, fileUrl, key, type Material } from "../../classroom-api";
const props = defineProps<{ material: Material }>();
const text = ref(""),
  error = ref("");
watch(
  () => [props.material.id, props.material.status],
  async ([id]) => {
    text.value = "";
    error.value = "";
    try {
      const result = await call<{ text: string }>(`/materials/${key(id)}/text`);
      if (props.material.id === id) text.value = result.text;
    } catch (e) {
      if (props.material.id === id) error.value = (e as Error).message;
    }
  },
  { immediate: true },
);
</script>
<template>
  <div class="material-preview">
    <div class="row spread">
      <h3>{{ material.title }}</h3>
      <a :href="fileUrl(material.id)" target="_blank" rel="noopener">{{
        t("Open original")
      }}</a>
    </div>
    <p class="muted">{{ material.relativePath }}</p>
    <p v-if="material.errorMessage" class="notice">
      {{ systemText(material.errorMessage) }}
    </p>
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <p
      v-if="
        material.extractionReport &&
        (material.extractionReport.schemaVersion ?? 0) < 2
      "
      class="notice"
    >
      {{
        t(
          "Reprocess this material to verify it with the current document parser.",
        )
      }}
    </p>
    <details
      v-if="material.extractionReport"
      :open="
        material.status === 'processing' ||
        !!material.extractionReport.failedUnits.length
      "
    >
      <summary>{{ t("Extraction report") }}</summary>
      <p>
        {{
          t("Processed {0} of {1} units; AI interpreted {2} units.", [
            material.extractionReport.unitsProcessed,
            material.extractionReport.unitsTotal,
            material.extractionReport.visionUnits ?? 0,
          ])
        }}
      </p>
      <p v-if="material.extractionReport.truncated" class="notice">
        {{
          t(
            "The extracted text was truncated. Check the original for the remaining content.",
          )
        }}
      </p>
      <p v-if="material.extractionReport.visualReviewRequired" class="notice">
        {{ t("Check figures, handwriting and layout against the original.") }}
      </p>
      <ul v-if="material.extractionReport.failedUnits.length">
        <li v-for="unit in material.extractionReport.failedUnits" :key="unit">
          {{ systemText(unit) }}
        </li>
      </ul>
      <ul>
        <li v-for="note in material.extractionReport.notes" :key="note">
          {{ systemText(note) }}
        </li>
      </ul>
    </details>
    <iframe
      v-if="material.mimeType === 'application/pdf'"
      :src="fileUrl(material.id)"
      :title="material.title"
    />
    <img
      v-else-if="material.mimeType.startsWith('image/')"
      :src="fileUrl(material.id)"
      :alt="material.title"
    />
    <pre v-else>{{
      text || t("The extracted text will appear after processing.")
    }}</pre>
    <details
      v-if="
        text &&
        (material.mimeType === 'application/pdf' ||
          material.mimeType.startsWith('image/'))
      "
    >
      <summary>{{ t("Extracted text") }}</summary>
      <pre>{{ text }}</pre>
    </details>
  </div>
</template>
