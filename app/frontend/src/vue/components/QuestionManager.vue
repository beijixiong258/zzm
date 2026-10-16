<script setup lang="ts">
import { askConfirm } from "../state";
import { computed, ref } from "vue";
import { Plus, Search } from "lucide-vue-next";
import type { Material, WorksheetDraft } from "../../types";
import { authoringErrors, renumber } from "../../stage2";
import { newGroup, newQuestion } from "../../question-draft";
import { clone, label, useTask } from "../state";
import ItemRow from "./ItemRow.vue";
import EditorDialog from "./EditorDialog.vue";
import FeedbackNotice from "./FeedbackNotice.vue";
const props = defineProps<{
  value: WorksheetDraft;
  materials: Material[];
  save: (value: WorksheetDraft) => Promise<void>;
  local?: boolean;
  disabled?: boolean;
}>();
const emit = defineEmits<{ import: [] }>();
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
        value.groups.push({ ...newGroup(), title: "Core questions" });
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
    error.value = "Add at least two answer options.";
    return;
  }
  const ok = await run(
    () => props.save(next),
    props.local
      ? "Changes applied."
      : "Draft saved. Publish the course when it is ready for students.",
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
      `Delete “${item?.slice(0, 100)}”${kind === "group" ? ` and its ${count} questions` : ""} from the draft? Published versions are unchanged.`,
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
  await run(() => props.save(next), "Deleted from the draft.");
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
        {{ groupsMode ? "Question groups" : "Questions" }}
        <span class="count">{{
          groupsMode ? value.groups.length : value.questions.length
        }}</span>
      </h2>
      <p>
        {{
          groupsMode
            ? "Core groups are required. Students choose one reading group."
            : "Create, arrange and refine your questions."
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
        {{ groupsMode ? "Add group" : "Add question" }}</button
      ><button
        v-if="!local && !groupsMode"
        class="secondary"
        :disabled="busy || disabled"
        @click="emit('import')"
      >
        Import questions</button
      ><button
        class="secondary"
        :disabled="busy || disabled"
        @click="groupsMode = !groupsMode"
      >
        {{ groupsMode ? "Back to questions" : "Manage groups" }}
      </button>
    </div>
  </div>
  <FeedbackNotice :error="editor ? '' : error" :success="success" />
  <div v-if="!groupsMode && value.questions.length" class="filter-bar">
    <label class="search-field"
      ><span>Search questions</span>
      <div>
        <Search :size="17" /><input
          v-model="query"
          placeholder="Search question text…"
        /></div></label
    ><label
      >Group<select v-model="groupFilter">
        <option value="">All groups</option>
        <option v-for="g in value.groups" :key="g.id" :value="g.id">
          {{ g.title }}
        </option>
      </select></label
    ><label
      >Question type<select v-model="typeFilter">
        <option value="">All types</option>
        <option v-for="type in questionTypes" :key="type" :value="type">
          {{ label(type) }}
        </option>
      </select></label
    >
  </div>
  <div class="item-list">
    <template v-if="groupsMode"
      ><ItemRow
        v-for="(g, i) in value.groups"
        :key="g.id"
        :title="g.title || 'Untitled group'"
        :description="g.description"
        :number="i + 1"
        ><template #meta
          ><span class="badge">{{
            g.kind === "core" ? "Required" : "Reading choice"
          }}</span
          ><span
            >{{
              value.questions.filter((q) => q.group_id === g.id).length
            }}
            questions</span
          ></template
        ><template #actions
          ><button
            class="secondary"
            :disabled="busy || disabled"
            @click="edit('group', g.id)"
          >
            Edit</button
          ><button
            class="secondary danger"
            :disabled="busy || disabled"
            @click="remove('group', g.id)"
          >
            Delete
          </button></template
        ></ItemRow
      ></template
    ><template v-else
      ><ItemRow
        v-for="q in questions"
        :key="q.id"
        :title="q.prompt || 'Untitled question'"
        :number="q.ordinal"
        ><template #meta
          ><span class="badge">{{ label(q.type) }}</span
          ><span>{{
            value.groups.find((g) => g.id === q.group_id)?.title
          }}</span
          ><span v-if="value.reference_answers[q.id]"
            >Reference answer added</span
          ></template
        ><template #actions
          ><button
            class="secondary"
            :disabled="busy || disabled"
            @click="edit('question', q.id)"
          >
            Edit</button
          ><button
            class="secondary danger"
            :disabled="busy || disabled"
            @click="remove('question', q.id)"
          >
            Delete
          </button></template
        ></ItemRow
      >
      <div v-if="!questions.length" class="empty-state">
        <h3>
          {{
            value.questions.length
              ? "No matching questions"
              : "No questions yet"
          }}
        </h3>
        <p>
          {{
            value.questions.length
              ? "Try a different search or filter."
              : "Use Add question or import a worksheet to begin."
          }}
        </p>
      </div></template
    >
  </div>
  <EditorDialog
    v-if="editor"
    :title="`${(editor.kind === 'question' ? value.questions : value.groups).some((item) => item.id === editor!.id) ? 'Edit' : 'Add'} ${editor.kind}`"
    :busy="busy"
    :dirty="dirty"
    wide
    @close="editor = null"
    ><FeedbackNotice :error="error" />
    <form id="question-editor" class="form-stack" @submit.prevent="commit">
      <template v-if="editor.kind === 'group' && g"
        ><div class="form-grid">
          <label>Group name<input v-model="g.title" required /></label
          ><label
            >Group type<select v-model="g.kind">
              <option value="core">Core · required</option>
              <option value="reading">Reading choice</option>
            </select></label
          ><label class="span-2"
            >Description<textarea v-model="g.description" rows="3" />
          </label></div></template
      ><template v-else-if="q"
        ><div class="form-grid">
          <label
            >Group<select v-model="q.group_id">
              <option
                v-for="g in editor.value.groups"
                :key="g.id"
                :value="g.id"
              >
                {{ g.title }}
              </option>
            </select></label
          ><label
            >Question type<select v-model="q.type">
              <option v-for="type in questionTypes" :key="type" :value="type">
                {{ label(type) }}
              </option>
            </select></label
          ><label class="span-2"
            >Question prompt<textarea
              v-model="q.prompt"
              rows="5"
              required
              placeholder="Write the question students will see…"
            /></label
          ><label
            v-if="q.type === 'single_choice' || q.type === 'image_matching'"
            class="span-2"
            >Options · one per line<textarea
              v-model="options"
              rows="4"
              required
            /></label
          ><label
            v-if="q.type === 'fill_in_blank' || q.type === 'image_matching'"
            >Answer slots<input
              v-model.number="q.answer_slots"
              type="number"
              min="1"
              max="100"
              required /></label
          ><label
            ><span>Hint <span class="optional">optional</span></span
            ><input v-model="q.hint"
          /></label>
        </div>
        <label
          ><span
            >Instructor answer / example
            <span class="badge">Private</span></span
          ><textarea
            v-model="editor.value.reference_answers[q.id]"
            rows="4"
            placeholder="An answer or example for the teaching process"
          /><small
            >Delivery follows the reference rules in Teaching setup.</small
          ></label
        >
        <details class="form-section">
          <summary>
            Sources & images
            <span class="muted"
              >{{ q.source_material_ids?.length || 0 }} selected sources ·
              {{ q.images.length }} images</span
            >
          </summary>
          <p class="muted">
            With no selection, all eligible session materials can inform this
            question.
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
                m.visibility === "teacher" ? "Private" : "Student"
              }}</span></label
            >
          </div>
          <label
            >Source links · one per line<textarea
              v-model="links"
              rows="2"
            /></label
          ><label>Source label<input v-model="q.source_label" /></label>
          <div class="section-header">
            <h3>Question images</h3>
            <button
              type="button"
              class="secondary"
              @click="q.images.push({ label: '', url: '', alt: '' })"
            >
              Add image
            </button>
          </div>
          <div v-for="(img, i) in q.images" :key="i" class="image-fields">
            <label
              >Image URL<input
                v-model="img.url"
                @input="img.asset_key = undefined" /></label
            ><label>Label<input v-model="img.label" /></label
            ><label>Accessible description<input v-model="img.alt" /></label
            ><button
              type="button"
              class="secondary danger"
              @click="q.images.splice(i, 1)"
            >
              Remove image
            </button>
          </div>
        </details></template
      ><label
        >Position<select v-model.number="position">
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
        {{ busy ? "Saving…" : local ? "Apply changes" : "Save draft" }}
      </button></template
    ></EditorDialog
  >
</template>
