<script setup lang="ts">
import { t, systemText } from "../../i18n";

import { askConfirm } from "../state";
import { computed, ref } from "vue";
import { api } from "../../api";
import type {
  SessionDetail,
  WorksheetPreview,
  WorksheetDraft,
} from "../../types";
import { useTask, useDirty } from "../state";
import { uploadFormats, acceptFormats } from "../../upload-capabilities";
import QuestionManager from "./QuestionManager.vue";
import FeedbackNotice from "./FeedbackNotice.vue";
const props = defineProps<{ session: SessionDetail }>();
const emit = defineEmits<{ saved: [SessionDetail]; close: [] }>();
const { busy, error, success, run } = useTask();
const file = ref<File | null>(null),
  preview = ref<WorksheetPreview | null>(null),
  useAi = ref(true),
  mode = ref<"append" | "replace">("append");
const source = ref(
    props.session.materials.some(
      (m) => m.kind !== "link" && m.kind !== "answer_key",
    )
      ? "material"
      : "upload",
  ),
  materialId = ref(""),
  answerMaterialId = ref("");
useDirty(computed(() => !!preview.value || busy.value));
async function close() {
  if (
    !preview.value ||
    (await askConfirm(
      t("Discard this import review and return to your saved questions?"),
    ))
  )
    emit("close");
}
async function inspect() {
  await run(async () => {
    if (source.value === "material") {
      if (!materialId.value) throw Error(t("Select a worksheet material."));
      preview.value = await api.worksheetFromMaterial(
        props.session.id,
        materialId.value,
        answerMaterialId.value || null,
        useAi.value,
      );
      return;
    }
    if (!file.value) throw Error(t("Choose a worksheet file."));
    preview.value = await api.worksheetPreview(
      props.session.id,
      file.value,
      useAi.value,
    );
  });
}
async function apply() {
  if (!preview.value?.draft.questions.length) return;
  if (
    mode.value === "replace" &&
    !(await askConfirm(
      t("Replace all draft questions with this reviewed worksheet?"),
    ))
  )
    return;
  await run(async () => {
    const s = await api.worksheetCommit(
      props.session.id,
      preview.value!.import_id,
      preview.value!.draft,
      mode.value,
    );
    const verified = await api.session(props.session.id);
    if (
      JSON.stringify(verified.questions) !== JSON.stringify(s.questions) ||
      JSON.stringify(verified.groups) !== JSON.stringify(s.groups)
    )
      throw Error(
        t(
          "The imported questions could not be verified. Refresh before retrying.",
        ),
      );
    preview.value = null;
    emit("saved", verified);
  });
}
async function edit(value: WorksheetDraft) {
  if (preview.value) preview.value.draft = value;
}
</script>
<template>
  <div class="section-header">
    <div>
      <h2>{{ t("Import questions") }}</h2>
      <p>
        {{
          t(
            "Choose an existing material or upload a worksheet, review, then save.",
          )
        }}
      </p>
    </div>
    <button class="secondary" :disabled="busy" @click="close">
      {{ t("Back to questions") }}
    </button>
  </div>
  <FeedbackNotice :error="error" :success="success" :busy="busy" />
  <form v-if="!preview" class="panel form-stack" @submit.prevent="inspect">
    <label
      >{{ t("Worksheet source")
      }}<select v-model="source" :disabled="busy">
        <option value="material">{{ t("Reuse a session material") }}</option>
        <option value="upload">{{ t("Upload a worksheet") }}</option>
      </select></label
    >
    <template v-if="source === 'material'"
      ><label
        >{{ t("Worksheet")
        }}<select v-model="materialId" required :disabled="busy">
          <option value="">{{ t("Choose material") }}</option>
          <option
            v-for="m in session.materials.filter(
              (m) => m.kind !== 'link' && m.kind !== 'answer_key',
            )"
            :key="m.id"
            :value="m.id"
          >
            {{ m.title }}
          </option>
        </select></label
      ><label
        >{{ t("Answer key · optional")
        }}<select v-model="answerMaterialId" :disabled="busy">
          <option value="">{{ t("No separate answer key") }}</option>
          <option
            v-for="m in session.materials.filter(
              (m) =>
                m.kind === 'answer_key' &&
                m.visibility === 'teacher' &&
                m.id !== materialId,
            )"
            :key="m.id"
            :value="m.id"
          >
            {{ m.title }}
          </option>
        </select></label
      ><small>{{ t("Uses the original saved files.") }}</small></template
    >
    <label v-else
      >{{ t("Worksheet file")
      }}<input
        type="file"
        :accept="acceptFormats(uploadFormats.worksheet)"
        required
        @change="file = ($event.target as HTMLInputElement).files?.[0] || null"
      /><small>{{
        t(
          "Worksheet import: TXT, Markdown, DOCX, PDF or PPTX; up to 25 MiB. Export WPS documents to one of these formats first.",
        )
      }}</small></label
    >
    <label class="check-label">
      <input v-model="useAi" type="checkbox" :disabled="busy" />
      {{ t("Use AI to recognize questions and match supplied answers") }}
    </label>
    <small>
      {{
        useAi
          ? t(
              "Sends the selected worksheet and answer key to the configured model. Review every question and answer before saving.",
            )
          : t(
              "Text extraction only; no AI request. Complex numbering may need manual review.",
            )
      }}
    </small>
    <button
      class="primary"
      :disabled="busy || (source === 'upload' ? !file : !materialId)"
    >
      {{ t("Review questions") }}
    </button>
  </form>
  <template v-else
    ><p v-if="!preview.draft.questions.length" class="notice warning">
      {{
        t(
          "No questions were found. Add questions manually or choose a different worksheet. Your saved questions have not changed.",
        )
      }}
    </p>
    <p
      v-for="warning in preview.warnings"
      :key="warning"
      class="notice warning"
    >
      {{ systemText(warning) }}
    </p>
    <QuestionManager
      :value="preview.draft"
      :materials="session.materials"
      :teaching-language="session.teaching_language"
      :save="edit"
      :disabled="busy"
      local
    />
    <div class="save-bar">
      <label
        >{{ t("Import mode")
        }}<select v-model="mode">
          <option value="append">
            {{ t("Append to existing questions") }}
          </option>
          <option value="replace">{{ t("Replace existing questions") }}</option>
        </select></label
      ><button
        class="primary"
        :disabled="busy || !preview.draft.questions.length"
        @click="apply"
      >
        {{ t("Save reviewed questions") }}
      </button>
    </div></template
  >
</template>
