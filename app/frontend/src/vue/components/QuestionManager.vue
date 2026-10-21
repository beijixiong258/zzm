<script setup lang="ts">
import { t } from "../../i18n";

import { askConfirm } from "../state";
import { computed, ref, watch } from "vue";
import { Plus, Search } from "lucide-vue-next";
import type { Material, WorksheetDraft, SessionDetail } from "../../types";
import { authoringErrors, renumber } from "../../stage2";
import { newGroup, newQuestion } from "../../question-draft";
import { clone, label, useTask } from "../state";
import { api } from "../../api";
import { uploadFormats, acceptFormats } from "../../upload-capabilities";
import MaterialSelector from "./MaterialSelector.vue";
import MaterialPreview from "./MaterialPreview.vue";
import Pagination from "./Pagination.vue";
import FilterBar from "./FilterBar.vue";
import ItemRow from "./ItemRow.vue";
import EditorDialog from "./EditorDialog.vue";
import FeedbackNotice from "./FeedbackNotice.vue";
const props = defineProps<{
  value: WorksheetDraft;
  materials: Material[];
  save: (value: WorksheetDraft) => Promise<void>;
  local?: boolean;
  disabled?: boolean;
  sessionId?: string;
  teachingLanguage?: string;
}>();
const emit = defineEmits<{ import: []; materialsChanged: [SessionDetail] }>();
const imageSelection = ref<string[]>([]),
  imagePicker = ref(false),
  imagePreview = ref<Material | null>(null);
const imageMaterials = computed(() =>
  props.materials.filter(
    (m) =>
      m.preview_kind === "image" &&
      m.visibility === "student" &&
      m.kind !== "answer_key",
  ),
);
const pageOffset = ref(0);
const query = ref(""),
  groupFilter = ref(""),
  typeFilter = ref(""),
  groupsMode = ref(false);
const editor = ref<{
    kind: "question" | "group";
    id: string;
    value: WorksheetDraft;
    initial: string;
  } | null>(null),
  position = ref(1);
const { busy, error, success, run } = useTask();
const q = computed(() =>
  editor.value?.value.questions.find((q) => q.id === editor.value?.id),
);
const g = computed(() =>
  editor.value?.value.groups.find((g) => g.id === editor.value?.id),
);
const dirty = computed(
  () =>
    !!editor.value &&
    JSON.stringify([editor.value.value, position.value]) !==
      editor.value.initial,
);
const questions = computed(() =>
  props.value.questions.filter(
    (q) =>
      (!query.value ||
        q.prompt.toLowerCase().includes(query.value.toLowerCase())) &&
      (!groupFilter.value || q.group_id === groupFilter.value) &&
      (!typeFilter.value || q.type === typeFilter.value),
  ),
);
const questionTypes = [
  "open_response",
  "reading_response",
  "fill_in_blank",
  "single_choice",
  "image_matching",
] as const;
watch([query, groupFilter, typeFilter, groupsMode], () => {
  pageOffset.value = 0;
});
watch(
  () => [props.value.questions.length, props.value.groups.length],
  () => {
    const total = groupsMode.value
      ? props.value.groups.length
      : questions.value.length;
    pageOffset.value = Math.min(
      pageOffset.value,
      Math.max(0, Math.ceil(total / 20) - 1) * 20,
    );
  },
);
const options = computed({
  get: () => q.value?.options.join("\n") || "",
  set: (value: string) => {
    if (q.value) q.value.options = value.split("\n");
  },
});
const links = computed({
  get: () => q.value?.source_links?.join("\n") || "",
  set: (value: string) => {
    if (q.value) q.value.source_links = value.split("\n").filter(Boolean);
  },
});
function edit(kind: "question" | "group", id?: string) {
  const value = clone(props.value);
  let selected = id;
  if (!selected) {
    if (kind === "group") {
      const group = newGroup();
      selected = group.id;
      value.groups.push(group);
    } else {
      if (!value.groups.length)
        value.groups.push({
          ...newGroup(),
          title: props.teachingLanguage?.toLowerCase().startsWith("zh")
            ? "核心题目"
            : "Core questions",
        });
      const question = newQuestion(
        groupFilter.value || value.groups[0].id,
        value.questions.length + 1,
      );
      selected = question.id;
      value.questions.push(question);
    }
  }
  position.value =
    kind === "question"
      ? value.questions.findIndex((q) => q.id === selected) + 1
      : value.groups.findIndex((g) => g.id === selected) + 1;
  editor.value = {
    kind,
    id: selected,
    value,
    initial: JSON.stringify([value, position.value]),
  };
  error.value = "";
}
async function commit() {
  if (!editor.value) return;
  const next = clone(editor.value.value);
  if (editor.value.kind === "question") {
    const index = next.questions.findIndex((q) => q.id === editor.value!.id),
      [item] = next.questions.splice(index, 1);
    if (!item) return;
    next.questions.splice(position.value - 1, 0, item);
    next.questions = renumber(next.questions);
  } else {
    const index = next.groups.findIndex((g) => g.id === editor.value!.id),
      [item] = next.groups.splice(index, 1);
    if (!item) return;
    next.groups.splice(position.value - 1, 0, item);
  }
  const errors = authoringErrors(next.groups, next.questions);
  if (errors.length) {
    error.value = errors.join("; ");
    return;
  }
  if (
    q.value?.type === "single_choice" &&
    q.value.options.filter((x) => x.trim()).length < 2
  ) {
    error.value = t("Add at least two answer options.");
    return;
  }
  const ok = await run(
    () => props.save(next),
    props.local
      ? t("Changes applied.")
      : t(
          "Questions and groups saved. Teaching settings and availability are saved separately. Publish when ready.",
        ),
  );
  if (ok) editor.value = null;
}
async function remove(kind: "question" | "group", id: string) {
  const item =
    kind === "question"
      ? props.value.questions.find((q) => q.id === id)?.prompt
      : props.value.groups.find((g) => g.id === id)?.title;
  const count = props.value.questions.filter((q) => q.group_id === id).length;
  if (
    !(await askConfirm(
      t("Delete “{0}”{1} from the draft? Published versions are unchanged.", [
        item?.slice(0, 100),
        kind === "group" ? " " + t("and its {0} questions", [count]) : "",
      ]),
      {
        title: kind === "group" ? t("Delete group") : t("Delete question"),
        confirmLabel: t("Delete"),
        danger: true,
      },
    ))
  )
    return;
  const next = clone(props.value),
    ids =
      kind === "question"
        ? [id]
        : next.questions.filter((q) => q.group_id === id).map((q) => q.id);
  if (kind === "group") next.groups = next.groups.filter((g) => g.id !== id);
  next.questions = renumber(next.questions.filter((q) => !ids.includes(q.id)));
  ids.forEach((id) => delete next.reference_answers[id]);
  await run(() => props.save(next), t("Deleted from the draft."));
}
async function uploadImages(files: File[]) {
  if (!props.sessionId || !q.value || !files.length) return;
  const questionId = q.value.id;
  await run(async () => {
    for (const file of files) {
      if (
        !uploadFormats.images.includes(
          file.name
            .split(".")
            .pop()
            ?.toLowerCase() as (typeof uploadFormats.images)[number],
        )
      )
        throw Error(t("Choose PNG, JPEG or WebP images."));
      if (file.size > 25 * 1048576)
        throw Error(t("The upload limit is {0} MiB per file.", [25]));
      const material = await api.upload(
        props.sessionId!,
        file,
        "student",
        "reference",
        "preview",
      );
      emit("materialsChanged", await api.session(props.sessionId!));
      if (q.value?.id === questionId)
        q.value.images.push({
          label: "",
          alt: file.name,
          url: material.preview_url!,
        });
    }
  });
}
function pasteImages(event: ClipboardEvent) {
  const files = Array.from(event.clipboardData?.files || []).filter((file) =>
    file.type.startsWith("image/"),
  );
  if (files.length) {
    event.preventDefault();
    void uploadImages(files);
  }
}
function chooseImages() {
  if (!q.value) return;
  for (const mid of imageSelection.value) {
    const material = imageMaterials.value.find((m) => m.id === mid);
    if (
      material?.preview_url &&
      !q.value.images.some((image) => image.url === material.preview_url)
    )
      q.value.images.push({
        label: "",
        alt: material.title,
        url: material.preview_url,
      });
  }
  imagePicker.value = false;
  imageSelection.value = [];
}
function source(id: string, checked: boolean) {
  if (!q.value) return;
  const ids = q.value.source_material_ids || [];
  q.value.source_material_ids = checked
    ? [...ids, id]
    : ids.filter((x) => x !== id);
}
</script>
<template>
  <div class="section-header question-toolbar">
    <div>
      <h2>
        {{ groupsMode ? t("Question groups") : t("Questions") }}
        <span class="count">{{
          groupsMode ? value.groups.length : value.questions.length
        }}</span>
      </h2>
      <p>
        {{
          groupsMode
            ? t("Core groups are required. Students choose one reading group.")
            : t("Create, arrange and refine your questions.")
        }}
      </p>
    </div>
    <div class="actions">
      <button
        class="primary"
        :disabled="busy || disabled"
        @click="edit(groupsMode ? 'group' : 'question')"
      >
        <Plus :size="16" />
        {{ groupsMode ? t("Add group") : t("Add question") }}</button
      ><button
        v-if="!local && !groupsMode"
        class="secondary"
        :disabled="busy || disabled"
        @click="emit('import')"
      >
        {{ t("Import questions") }}</button
      ><button
        class="secondary"
        :disabled="busy || disabled"
        @click="groupsMode = !groupsMode"
      >
        {{ groupsMode ? t("Back to questions") : t("Manage groups") }}
      </button>
    </div>
  </div>
  <FeedbackNotice :error="editor ? '' : error" :success="success" />
  <FilterBar
    v-if="!groupsMode && value.questions.length"
    :active="!!query || !!groupFilter || !!typeFilter"
  >
    <label class="search-field"
      ><span>{{ t("Search questions") }}</span>
      <div>
        <Search :size="17" /><input
          v-model="query"
          :placeholder="t('Search question text…')"
        /></div></label
    ><label
      >{{ t("Group")
      }}<select v-model="groupFilter">
        <option value="">{{ t("All groups") }}</option>
        <option v-for="g in value.groups" :key="g.id" :value="g.id">
          {{ g.title }}
        </option>
      </select></label
    ><label
      >{{ t("Question type")
      }}<select v-model="typeFilter">
        <option value="">{{ t("All types") }}</option>
        <option v-for="type in questionTypes" :key="type" :value="type">
          {{ label(type) }}
        </option>
      </select></label
    >
  </FilterBar>
  <div class="item-list">
    <template v-if="groupsMode"
      ><ItemRow
        v-for="(g, i) in value.groups.slice(pageOffset, pageOffset + 20)"
        :key="g.id"
        :title="g.title || t('Untitled group')"
        :description="g.description"
        :number="pageOffset + i + 1"
        ><template #meta
          ><span class="badge">{{
            g.kind === "core" ? t("Required") : t("Reading choice")
          }}</span
          ><span
            >{{ value.questions.filter((q) => q.group_id === g.id).length }}
            {{ t("questions") }}</span
          ></template
        ><template #actions
          ><button
            class="secondary"
            :disabled="busy || disabled"
            @click="edit('group', g.id)"
          >
            {{ t("Edit") }}</button
          ><button
            class="secondary danger"
            :disabled="busy || disabled"
            @click="remove('group', g.id)"
          >
            {{ t("Delete") }}
          </button></template
        ></ItemRow
      ></template
    ><template v-else
      ><ItemRow
        v-for="q in questions.slice(pageOffset, pageOffset + 20)"
        :key="q.id"
        :title="q.prompt || t('Untitled question')"
        expandable
        :number="q.ordinal"
        ><template #meta
          ><span class="badge">{{ label(q.type) }}</span
          ><span>{{
            value.groups.find((g) => g.id === q.group_id)?.title
          }}</span
          ><span v-if="value.reference_answers[q.id]">{{
            t("Reference answer added")
          }}</span></template
        ><template #actions
          ><button
            class="secondary"
            :disabled="busy || disabled"
            @click="edit('question', q.id)"
          >
            {{ t("Edit") }}</button
          ><button
            class="secondary danger"
            :disabled="busy || disabled"
            @click="remove('question', q.id)"
          >
            {{ t("Delete") }}
          </button></template
        ></ItemRow
      >
      <div v-if="!questions.length" class="empty-state">
        <h3>
          {{
            value.questions.length
              ? t("No matching questions")
              : t("No questions yet")
          }}
        </h3>
        <p>
          {{
            value.questions.length
              ? t("Try a different search or filter.")
              : t("Use Add question or import a worksheet to begin.")
          }}
        </p>
      </div></template
    >
  </div>
  <Pagination
    :offset="pageOffset"
    :total="groupsMode ? value.groups.length : questions.length"
    :busy="busy"
    @change="pageOffset = $event"
  />
  <EditorDialog
    v-if="editor"
    :title="
      (editor.kind === 'question' ? value.questions : value.groups).some(
        (item) => item.id === editor!.id,
      )
        ? t(editor.kind === 'question' ? 'Edit question' : 'Edit group')
        : t(editor.kind === 'question' ? 'Add question' : 'Add group')
    "
    :busy="busy"
    :dirty="dirty"
    wide
    @close="editor = null"
    ><FeedbackNotice :error="error" />
    <form id="question-editor" class="form-stack" @submit.prevent="commit">
      <template v-if="editor.kind === 'group' && g"
        ><div class="form-grid">
          <label
            >{{ t("Group name") }}<input v-model="g.title" required /></label
          ><label
            >{{ t("Group type")
            }}<select v-model="g.kind">
              <option value="core">{{ t("Core · required") }}</option>
              <option value="reading">{{ t("Reading choice") }}</option>
            </select></label
          ><label class="span-2"
            >{{ t("Description") }}<textarea v-model="g.description" rows="3" />
          </label></div></template
      ><template v-else-if="q"
        ><div class="form-grid">
          <label
            >{{ t("Group")
            }}<select v-model="q.group_id">
              <option
                v-for="g in editor.value.groups"
                :key="g.id"
                :value="g.id"
              >
                {{ g.title }}
              </option>
            </select></label
          ><label
            >{{ t("Question type")
            }}<select v-model="q.type">
              <option v-for="type in questionTypes" :key="type" :value="type">
                {{ label(type) }}
              </option>
            </select></label
          ><label class="span-2"
            >{{ t("Question prompt")
            }}<textarea
              v-model="q.prompt"
              rows="5"
              required
              :placeholder="t('Write the question students will see…')"
            /></label
          ><label
            v-if="q.type === 'single_choice' || q.type === 'image_matching'"
            class="span-2"
            >{{ t("Options · one per line")
            }}<textarea v-model="options" rows="4" required /></label
          ><label
            v-if="q.type === 'fill_in_blank' || q.type === 'image_matching'"
            >{{ t("Answer slots")
            }}<input
              v-model.number="q.answer_slots"
              type="number"
              min="1"
              max="100"
              required /></label
          ><label
            ><span
              >{{ t("Hint") }}
              <span class="optional">{{ t("optional") }}</span></span
            ><input v-model="q.hint"
          /></label>
        </div>
        <label
          ><span
            >{{ t("Instructor answer / example") }}
            <span class="badge">{{ t("Private") }}</span></span
          ><textarea
            v-model="editor.value.reference_answers[q.id]"
            rows="4"
            :placeholder="t('An answer or example for the teaching process')"
          /><small>{{
            t("Delivery follows the reference rules in Teaching setup.")
          }}</small></label
        >
        <details class="form-section">
          <summary>
            {{ t("Sources & images") }}
            <span class="muted"
              >{{ q.source_material_ids?.length || 0 }}
              {{ t("selected sources ·") }} {{ q.images.length }}
              {{ t("images") }}</span
            >
          </summary>
          <p class="muted">
            {{
              t(
                "With no selection, all eligible session materials can inform this question.",
              )
            }}
          </p>
          <div class="checkbox-list">
            <label v-for="m in materials" :key="m.id" class="check"
              ><input
                type="checkbox"
                :checked="q.source_material_ids?.includes(m.id)"
                @change="
                  source(m.id, ($event.target as HTMLInputElement).checked)
                "
              />{{ m.title }}
              <span class="badge">{{
                m.visibility === "teacher" ? t("Private") : t("Student")
              }}</span></label
            >
          </div>
          <label
            >{{ t("Source links · one per line")
            }}<textarea v-model="links" rows="2" /></label
          ><label
            >{{ t("Source label") }}<input v-model="q.source_label"
          /></label>
          <div class="section-header">
            <h3>{{ t("Question images") }}</h3>
            <button
              type="button"
              class="secondary"
              @click="q.images.push({ label: '', url: '', alt: '' })"
            >
              {{ t("Add image") }}
            </button>
          </div>
          <div
            v-if="sessionId && !local"
            class="image-upload-zone"
            tabindex="0"
            @paste="pasteImages"
          >
            <label
              >{{ t("Upload or paste images")
              }}<input
                type="file"
                multiple
                :accept="acceptFormats(uploadFormats.images)"
                :disabled="busy"
                @change="
                  uploadImages(
                    Array.from(($event.target as HTMLInputElement).files || []),
                  );
                  ($event.target as HTMLInputElement).value = '';
                " /></label
            ><small>{{
              t(
                "PNG, JPEG or WebP; up to 25 MiB each. Click here and paste a screenshot. Images are saved to session materials immediately.",
              )
            }}</small>
          </div>
          <button
            v-if="imageMaterials.length"
            type="button"
            class="secondary"
            @click="
              imagePicker = true;
              imageSelection = [];
            "
          >
            {{ t("Choose material images") }}
          </button>
          <div v-for="(img, i) in q.images" :key="i" class="image-fields">
            <label
              >{{ t("Image URL")
              }}<input
                v-model="img.url"
                @input="img.asset_key = undefined" /></label
            ><label>{{ t("Label") }}<input v-model="img.label" /></label
            ><label
              >{{ t("Accessible description")
              }}<input v-model="img.alt" /></label
            ><button
              type="button"
              class="secondary danger"
              @click="q.images.splice(i, 1)"
            >
              {{ t("Remove image") }}
            </button>
          </div>
        </details></template
      ><label
        >{{ t("Position")
        }}<select v-model.number="position">
          <option
            v-for="n in editor.kind === 'question'
              ? editor.value.questions.length
              : editor.value.groups.length"
            :key="n"
            :value="n"
          >
            {{ n }}
          </option>
        </select></label
      >
    </form>
    <template #actions
      ><button class="primary" form="question-editor" :disabled="busy">
        {{
          busy
            ? t("Saving…")
            : local
              ? t("Apply changes")
              : editor.kind === "group"
                ? t("Save group draft")
                : t("Save question draft")
        }}
      </button></template
    ></EditorDialog
  >
  <EditorDialog
    v-if="imagePicker"
    :title="t('Choose material images')"
    wide
    @close="imagePicker = false"
    ><MaterialSelector
      v-model="imageSelection"
      :materials="imageMaterials"
      @preview="imagePreview = $event"
    /><template #actions
      ><button
        class="primary"
        :disabled="!imageSelection.length"
        @click="chooseImages"
      >
        {{ t("Use selected images") }}
      </button></template
    ></EditorDialog
  >
  <EditorDialog
    v-if="imagePreview"
    :title="imagePreview.title"
    :close-label="t('Close')"
    @close="imagePreview = null"
    ><MaterialPreview :material="imagePreview"
  /></EditorDialog>
</template>
