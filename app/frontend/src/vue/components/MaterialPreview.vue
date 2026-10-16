<script setup lang="ts">
import { computed, ref, onMounted, watch } from "vue";
import type { Material } from "../../types";
import type {
  DocumentSummary,
  DocumentPage,
  DocumentCapability,
  DocumentBlock,
  DocumentInfo,
  DocumentReviewRequest,
  DocumentJobRequest,
  DocumentSupplementSharing,
} from "../../document-types";
import { documentApi } from "../../document-api";
import {
  authorizedDocumentAsset,
  jobIsActive,
  processingLabel,
  reviewReadbackMatches,
  reviewChangeError,
  uncertainDocumentWrite,
} from "../../document-state";
import { withVersion } from "../../stage2";
import { clientId } from "../../ids";
import { useTask, user } from "../state";
import FeedbackNotice from "./FeedbackNotice.vue";
import RichText from "./RichText.vue";
const props = defineProps<{
  material: Material;
  version?: string | null;
  teacher?: boolean;
}>();
const emit = defineEmits<{ held: [boolean]; dirty: [boolean]; changed: [] }>();
type Pending =
  | {
      kind: "review";
      before: DocumentInfo;
      page: number;
      payload: DocumentReviewRequest;
    }
  | { kind: "job"; payload: DocumentJobRequest }
  | {
      kind: "sharing";
      before: DocumentInfo;
      ids: string[];
      payload: DocumentSupplementSharing;
    };
const summary = ref<DocumentSummary | null>(null),
  page = ref<DocumentPage | null>(null),
  number = ref(1),
  capability = ref<DocumentCapability | null>(null);
const draft = ref<{
    blockId: string;
    text: string;
    quality: "approved" | "excluded";
    reason: string;
    revision: string;
  } | null>(null),
  pending = ref<Pending | null>(null);
const { busy, error, success, run } = useTask();
const canReview = computed(() => props.teacher && props.version == null);
const active = computed(() => jobIsActive(summary.value?.latest_job || null));
const revision = computed(() => summary.value?.document?.revision_id);
const sourceFormat = computed(
  () =>
    props.material.source_format ||
    props.material.title.split(".").pop()?.toLowerCase(),
);
const canProcess = computed(
  () =>
    !!capability.value?.available &&
    capability.value.formats.includes(sourceFormat.value || ""),
);
const image = computed(() =>
  page.value && revision.value
    ? authorizedDocumentAsset(
        page.value.image_url,
        props.material.id,
        revision.value,
        props.version,
      )
    : null,
);
const recoveryKey = `aicademiya.vue.document:${user.value?.id}:${props.material.id}:${props.version || "draft"}`;
watch(busy, (value) => emit("held", value));
watch(
  [draft, pending],
  () => {
    emit("dirty", !!draft.value || !!pending.value);
    if (!canReview.value) return;
    try {
      if (draft.value || pending.value)
        sessionStorage.setItem(
          recoveryKey,
          JSON.stringify({
            draft: draft.value,
            pending: pending.value,
            number: number.value,
          }),
        );
      else sessionStorage.removeItem(recoveryKey);
    } catch {
      error.value =
        "Browser recovery storage is unavailable. Keep this window open until the request is confirmed.";
    }
  },
  { deep: true },
);
async function read() {
  summary.value = await documentApi.summary(props.material.id, props.version);
  if (summary.value.document) {
    number.value = Math.min(
      number.value,
      Math.max(summary.value.document.page_count, 1),
    );
    page.value = await documentApi.page(
      props.material.id,
      number.value,
      summary.value.document.revision_id,
      props.version,
    );
  }
}
async function loadPage() {
  await run(async () => {
    if (revision.value)
      page.value = await documentApi.page(
        props.material.id,
        number.value,
        revision.value,
        props.version,
      );
  });
}
async function refresh() {
  await run(read);
}
onMounted(async () => {
  if (canReview.value) {
    try {
      const saved = JSON.parse(sessionStorage.getItem(recoveryKey) || "null");
      if (saved) {
        draft.value = saved.draft;
        pending.value = saved.pending;
        number.value = saved.number || 1;
      }
    } catch {
      error.value = "The previous source review could not be restored.";
    }
  }
  if (props.material.kind !== "link")
    await run(async () => {
      await read();
      if (canReview.value) capability.value = await documentApi.capability();
    });
});
function edit(block: DocumentBlock) {
  draft.value = {
    blockId: block.id,
    text: block.text,
    quality: "approved",
    reason: "",
    revision: revision.value!,
  };
}
async function verify(request: Pending) {
  if (request.kind === "job") {
    const job = await documentApi.jobByRequest(
      props.material.id,
      request.payload.request_id,
    );
    if (!job.id || job.material_id !== props.material.id)
      throw Error("The processing request could not be verified.");
    await read();
  } else {
    const receipt = await documentApi.reviewByRequest(
      props.material.id,
      request.payload.request_id,
    );
    const current = await documentApi.summary(props.material.id, props.version);
    if (!current.document) throw Error("The updated document is unavailable.");
    if (request.kind === "review") {
      const updatedPage = await documentApi.page(
        props.material.id,
        request.page,
        receipt.document.revision_id,
        props.version,
      );
      if (
        !reviewReadbackMatches(
          request.before,
          receipt.document,
          current.document,
          updatedPage,
          request.payload.changes,
        )
      )
        throw Error(
          "The saved source correction could not be verified. Keep this request for inspection.",
        );
      page.value = updatedPage;
      draft.value = null;
    } else {
      const expected = request.payload.visible_to_students
        ? "student"
        : "teacher";
      if (
        current.document.revision_id !== receipt.document.revision_id ||
        current.document.revision_id === request.before.revision_id ||
        current.document.source_sha256 !== request.before.source_sha256 ||
        current.supplements?.length !== request.ids.length ||
        !current.supplements?.every(
          (item) =>
            request.ids.includes(item.id) && item.visibility === expected,
        )
      )
        throw Error("Source-note sharing could not be verified.");
    }
    summary.value = current;
  }
  pending.value = null;
  emit("changed");
}
async function mutate(request?: Pending) {
  const target = request || pending.value;
  if (!target || !canReview.value || (request && pending.value)) return;
  await run(
    async () => {
      if (request) {
        pending.value = request;
        try {
          if (request.kind === "job")
            await documentApi.start(props.material.id, request.payload);
          else if (request.kind === "sharing")
            await documentApi.shareSupplements(
              props.material.id,
              request.payload,
            );
          else await documentApi.review(props.material.id, request.payload);
        } catch (e) {
          if (!uncertainDocumentWrite(e)) {
            pending.value = null;
            throw e;
          }
        }
      }
      await verify(target);
    },
    target.kind === "job"
      ? "Processing request verified. Use Refresh to check its progress."
      : "Draft source updated. Publish a new version to share it with students.",
  );
}
async function saveReview() {
  if (!draft.value || !summary.value?.document) return;
  const invalid = reviewChangeError(draft.value.text, draft.value.reason);
  if (invalid) {
    error.value = invalid;
    return;
  }
  if (draft.value.revision !== revision.value) {
    error.value =
      "This source has changed. Refresh, then check the current block before saving.";
    return;
  }
  await mutate({
    kind: "review",
    before: summary.value.document,
    page: number.value,
    payload: {
      request_id: clientId(),
      expected_revision: draft.value.revision,
      changes: [
        {
          block_id: draft.value.blockId,
          text: draft.value.text,
          quality: draft.value.quality,
          reason: draft.value.reason,
        },
      ],
    },
  });
}
async function shareNotes() {
  if (!summary.value?.document || !summary.value.supplements?.length) return;
  const share = !summary.value.supplements.every(
    (item) => item.visibility === "student",
  );
  await mutate({
    kind: "sharing",
    before: summary.value.document,
    ids: summary.value.supplements.map((item) => item.id),
    payload: {
      request_id: clientId(),
      expected_revision: revision.value!,
      visible_to_students: share,
      reason: share
        ? "Teacher selected source notes for sharing on publication."
        : "Teacher restricted source notes to staff.",
    },
  });
}
</script>
<template>
  <FeedbackNotice :error="error" :success="success" :busy="busy" />
  <div v-if="summary?.latest_job" class="notice">
    <p>{{ processingLabel(summary.latest_job) }}</p>
    <p v-if="summary.latest_job.error">{{ summary.latest_job.error }}</p>
    <button
      class="secondary"
      :disabled="busy || !!draft || !!pending"
      @click="refresh"
    >
      Refresh status
    </button>
  </div>
  <p v-if="pending" class="notice warning">
    The last request has not been confirmed. Check its saved result before
    making another change.
    <button class="secondary" :disabled="busy" @click="mutate()">
      Check request result
    </button>
  </p>
  <template v-if="summary?.document">
    <div class="section-header">
      <label
        >Page<select
          v-model.number="number"
          :disabled="busy || !!draft || !!pending"
          @change="loadPage"
        >
          <option v-for="p in summary.pages" :key="p.number" :value="p.number">
            Page {{ p.number }}
            {{ p.printed_label ? `· ${p.printed_label}` : "" }}
          </option>
        </select></label
      ><span>{{ summary.document.page_count }} pages</span>
    </div>
    <div v-if="page" class="document-page">
      <img v-if="image" :src="image" :alt="`Page ${number}`" />
      <div>
        <section v-for="b in page.blocks" :key="b.id" class="document-block">
          <RichText v-if="b.text_format === 'markdown'" :text="b.text" />
          <p v-else class="preserve-text">{{ b.text }}</p>
          <p v-if="b.visual_description" class="muted">
            {{ b.visual_description }}
          </p>
          <template v-for="asset in b.assets" :key="asset"
            ><img
              v-if="
                authorizedDocumentAsset(asset, material.id, revision!, version)
              "
              class="material-image"
              :src="
                authorizedDocumentAsset(asset, material.id, revision!, version)!
              "
              alt="Source illustration" /></template
          ><small v-if="teacher">{{ b.quality.replaceAll("_", " ") }}</small>
          <details
            v-if="teacher && (b.raw_text || b.review)"
            class="form-section"
          >
            <summary>Original text & review</summary>
            <p v-if="b.raw_text" class="preserve-text">{{ b.raw_text }}</p>
            <p v-if="b.review">
              {{ b.review.reason }} · {{ b.review.by }} · {{ b.review.at }}
            </p>
          </details>
          <button
            v-if="canReview"
            class="secondary"
            :disabled="busy || active || !!draft || !!pending"
            @click="edit(b)"
          >
            Review source block
          </button>
        </section>
      </div>
    </div>
    <form v-if="draft" class="panel form-stack" @submit.prevent="saveReview">
      <h3>Review against the original</h3>
      <label
        >Checked source text<textarea
          v-model="draft.text"
          rows="7"
          :disabled="busy || !!pending"
        /></label
      ><label
        >Quality<select v-model="draft.quality" :disabled="busy || !!pending">
          <option value="approved">Checked and approved</option>
          <option value="excluded">Exclude from teaching</option>
        </select></label
      ><label
        >Reason<textarea
          v-model="draft.reason"
          rows="2"
          required
          maxlength="2000"
          :disabled="busy || !!pending"
        />
      </label>
      <div class="actions">
        <button class="primary" :disabled="busy || !!pending">
          Save source correction</button
        ><button
          type="button"
          class="secondary"
          :disabled="busy || !!pending"
          @click="draft = null"
        >
          Discard correction
        </button>
      </div>
    </form>
    <details v-if="summary.supplements?.length" class="form-section">
      <summary>Source notes · {{ summary.supplements.length }}</summary>
      <section
        v-for="item in summary.supplements"
        :key="item.id"
        class="document-block"
      >
        <strong>{{ item.kind.replaceAll("_", " ") }}</strong
        ><span class="badge">{{
          item.visibility === "teacher" ? "Teachers only" : "Student context"
        }}</span>
        <p class="preserve-text">{{ item.preview }}</p>
        <a
          :href="
            documentApi.supplementUrl(material.id, item.id, revision!, version)
          "
          target="_blank"
          rel="noopener"
          >Open full note</a
        >
      </section>
      <button
        v-if="canReview"
        class="secondary"
        :disabled="busy || active || !!draft || !!pending"
        @click="shareNotes"
      >
        {{
          summary.supplements.every((item) => item.visibility === "student")
            ? "Restrict notes to teachers"
            : "Share notes on next publication"
        }}
      </button>
    </details>
  </template>
  <iframe
    v-else-if="material.preview_kind === 'pdf' && material.preview_url"
    class="pdf-preview"
    :src="withVersion(material.preview_url, version)"
    :title="material.title"
  />
  <img
    v-else-if="material.preview_kind === 'image' && material.preview_url"
    class="material-image"
    :src="withVersion(material.preview_url, version)"
    :alt="material.title"
  />
  <RichText
    v-else
    :text="
      material.excerpt ||
      'No text preview is available. Open or download the original material.'
    "
  />
  <details v-if="teacher" class="form-section">
    <summary>Document processing</summary>
    <template v-if="material.extraction_report"
      ><p>
        {{ material.extraction_report.units_processed }} /
        {{ material.extraction_report.units_total }} parts processed ·
        {{ material.extraction_report.chars_extracted }} characters extracted.
      </p>
      <p v-for="note in material.extraction_report.notes" :key="note">
        {{ note }}
      </p></template
    >
    <p v-if="!canProcess" class="muted">
      Complete processing is not configured for this file format.
    </p>
    <button
      v-if="canReview && canProcess"
      class="secondary"
      :disabled="busy || active || !!draft || !!pending"
      @click="
        mutate({
          kind: 'job',
          payload: {
            request_id: clientId(),
            expected_revision: revision || null,
          },
        })
      "
    >
      {{ revision ? "Reprocess original" : "Process complete document" }}
    </button>
  </details>
</template>
