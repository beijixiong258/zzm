<script setup lang="ts">
import { computed, ref, watch } from "vue";
import MaterialProgress from "./MaterialProgress.vue";
import { t, systemText } from "../../i18n";
import {
  call,
  fileUrl,
  key,
  statusText,
  type Material,
} from "../../classroom-api";
const props = defineProps<{ material: Material }>();
const isPdf = computed(() => props.material.mimeType === "application/pdf" || props.material.fileName.toLowerCase().endsWith(".pdf"));
const pdfMode = computed(() => props.material.extractionReport?.pdfInputMode);
const visibleWarning = computed(() =>
  ["ready", "needsReview"].includes(props.material.status) &&
  props.material.errorMessage === "Check figures, handwriting and layout against the original."
    ? ""
    : props.material.errorMessage,
);
const text = ref(""),
  error = ref("");
watch(
  () => [props.material.id, props.material.status],
  async ([id]) => {
    text.value = "";
    error.value = "";
    if (isPdf.value && pdfMode.value !== "text") return;
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
    <p class="row wrap">
      <span class="muted">{{ material.relativePath }}</span
      ><span class="badge status-label" :data-status="material.status">{{
        statusText(material.status)
      }}</span>
    </p>
    <p
      v-if="visibleWarning"
      :class="material.status === 'failed' ? 'error' : 'notice'"
    >
      {{ systemText(visibleWarning) }}
    </p>
    <MaterialProgress :material="material" />
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <p
      v-if="
        material.extractionReport &&
        ((material.extractionReport.schemaVersion ?? 0) < 2 ||
          (isPdf && !pdfMode))
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
      v-if="material.extractionReport && (!isPdf || pdfMode)"
      :open="
        material.status === 'processing' ||
        !!material.extractionReport.failedUnits.length
      "
    >
      <summary>{{ t("Processing report") }}</summary>
      <p v-if="isPdf">{{ t(pdfMode === "images"
        ? "PDF input: all pages as images, in their original order."
        : pdfMode === "text"
          ? "PDF input: the complete native text layer."
          : "Checking the PDF text layer…") }}</p>
      <p v-if="isPdf">{{ t("Prepared {0} of {1} pages. No OCR or AI request is used during PDF preparation.", [
        material.extractionReport.unitsProcessed, material.extractionReport.unitsTotal,
      ]) }}</p>
      <p v-else>
        {{
          t("Processed {0} of {1} units; AI interpreted {2} units.", [
            material.extractionReport.unitsProcessed,
            material.extractionReport.unitsTotal,
            material.extractionReport.visionUnits ?? 0,
          ])
        }}
      </p>
      <p v-if="!isPdf || pdfMode === 'text'">
        {{
          t(
            "Extracted text: {0} characters; about {1} tokens, with a conservative upper bound of {2}.",
            [
              material.extractionReport.textCharacters || 0,
              material.extractionReport.textTokensEstimated || 0,
              material.extractionReport.textTokensUpperBound || 0,
            ],
          )
        }}
      </p>
      <p v-if="pdfMode === 'images'">{{ t(
        "Prepared images: about {0} input tokens. The 40,000-token limit also includes prompts, other materials and chat history.",
        [(material.extractionReport.imageInputTokensEstimated || 0).toLocaleString()],
      ) }}</p>
      <p v-if="pdfMode === 'images' && (material.extractionReport.imageInputTokensEstimated || 0) > 40000" class="notice">
        {{ t("This file can stay in the library, but its images exceed the AI input limit. Split the PDF before using it with AI.") }}
      </p>
      <p v-if="!isPdf && material.extractionReport.visionUnits">
        {{
          t(
            "Visual reading so far: {0} estimated image tokens; {1} actual input tokens reported by the provider.",
            [
              material.extractionReport.visionInputTokensEstimated || 0,
              material.extractionReport.visionPromptTokensActual || 0,
            ],
          )
        }}
      </p>
      <p class="muted">
        {{
          t(
            "The final input budget includes native text or page images, prompts, other materials and chat history. File size is not a token count.",
          )
        }}
      </p>
      <p v-if="material.extractionReport.truncated" class="notice">
        {{
          t(
            "This file exceeds the processing limit. Split it and upload all parts before using it with AI.",
          )
        }}
      </p>
      <p v-if="material.extractionReport.visualReviewRequired" class="muted">
        {{ t("If needed, compare figures, handwriting and layout with the original.") }}
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
    <details v-if="isPdf && pdfMode && material.extractionReport?.pageInputs?.length">
      <summary>{{ t("PDF page inputs") }}</summary>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>{{ t("Page") }}</th>
              <th>{{ t("Input") }}</th>
              <th>{{ t("Size") }}</th>
              <th>{{ t("Estimated image tokens") }}</th>
              <th>{{ t("Status") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="page in material.extractionReport.pageInputs"
              :key="page.page"
            >
              <td>{{ page.page }}</td>
              <td>{{ t(page.kind === "text" ? "Text" : "Image") }}</td>
              <td>
                {{
                  page.kind === "text"
                    ? t("{0} characters", [page.textCharacters || 0])
                    : page.width + " × " + page.height
                }}
                <small v-if="page.kind === 'image'">
                  · {{ t(page.cropped ? "Cropped" : "Full page") }}</small
                >
              </td>
              <td>{{ page.kind === "image" ? (page.imageTokensEstimated || 0).toLocaleString() : "—" }}</td>
              <td>
                {{
                  page.status === "failed"
                    ? t("Failed")
                    : page.status === "prepared" || page.status === "extracted"
                      ? t("Completed")
                      : t("Processing")
                }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </details>
    <iframe
      v-if="isPdf"
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
