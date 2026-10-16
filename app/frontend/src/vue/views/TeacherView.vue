<script setup lang="ts">
import { computed, ref } from "vue";
import { Eye, Save } from "lucide-vue-next";
import { api } from "../../api";
import type {
  SessionDetail,
  StudentRow,
  VersionList,
  WorksheetDraft,
  TeachingPhase,
  TeachingPreview,
} from "../../types";
import {
  effectiveTeachingProfile,
  saveTeachingDraft,
  teachingPhaseLabels,
  toggleTeachingPhase,
} from "../../teaching-profile";
import { localDateTime, schedulePayload } from "../../stage2";
import {
  clone,
  dateText,
  label,
  navigate,
  useTask,
  useDirty,
  refreshCourses,
  askConfirm,
} from "../state";
import PageHeader from "../components/PageHeader.vue";
import FeedbackNotice from "../components/FeedbackNotice.vue";
import QuestionManager from "../components/QuestionManager.vue";
import WorksheetImporter from "../components/WorksheetImporter.vue";
import MaterialsPane from "../components/MaterialsPane.vue";
import ItemRow from "../components/ItemRow.vue";
import EditorDialog from "../components/EditorDialog.vue";
import RichText from "../components/RichText.vue";
const props = defineProps<{ sid: string }>();
const session = ref<SessionDetail | null>(null),
  draft = ref<SessionDetail | null>(null),
  tab = ref("setup"),
  importing = ref(false),
  preview = ref(false),
  compiled = ref<TeachingPreview | null>(null),
  students = ref<StudentRow[]>([]);
const versions = ref<VersionList | null>(null),
  recordVersion = ref("");
const { busy, error, success, run } = useTask();
const dirty = computed(
  () => JSON.stringify(draft.value) !== JSON.stringify(session.value),
);
useDirty(dirty);
const profile = computed(() => draft.value!.teaching_profile!);
const objectives = computed({
  get: () => draft.value?.learning_objectives.join("\n") || "",
  set: (v: string) => {
    if (draft.value) draft.value.learning_objectives = v.split("\n");
  },
});
const worksheet = computed<WorksheetDraft>(() => ({
  title: draft.value!.title,
  groups: draft.value!.groups,
  questions: draft.value!.questions,
  reference_answers: draft.value!.reference_answers || {},
}));
const starts = ref(""),
  ends = ref(""),
  active = ref(true);
const scheduleDirty = computed(
  () =>
    !!session.value &&
    (starts.value !== localDateTime(session.value.starts_at) ||
      ends.value !== localDateTime(session.value.ends_at) ||
      active.value !== (session.value.active !== false)),
);
useDirty(scheduleDirty);
function fill(s: SessionDetail) {
  const keepSchedule = scheduleDirty.value;
  s = { ...s, teaching_profile: effectiveTeachingProfile(s) };
  session.value = clone(s);
  draft.value = clone(s);
  if (!keepSchedule) {
    starts.value = localDateTime(s.starts_at);
    ends.value = localDateTime(s.ends_at);
    active.value = s.active !== false;
  }
}
void run(async () => fill(await api.session(props.sid)));
async function save() {
  if (!draft.value) return;
  await run(async () => {
    fill(await saveTeachingDraft(props.sid, draft.value!));
    await refreshCourses();
  }, "Draft saved. Publish when ready to share with students.");
}
async function saveQuestions(value: WorksheetDraft) {
  const next = {
    ...clone(draft.value!),
    groups: value.groups,
    questions: value.questions,
    reference_answers: value.reference_answers,
  };
  const verified = await saveTeachingDraft(props.sid, next);
  if (
    JSON.stringify(verified.questions) !== JSON.stringify(next.questions) ||
    JSON.stringify(verified.groups) !== JSON.stringify(next.groups)
  )
    throw Error(
      "Saved questions could not be verified. Refresh before retrying.",
    );
  fill(verified);
  await refreshCourses();
}
async function availability() {
  await run(async () => {
    await api.updateSession(
      props.sid,
      schedulePayload(active.value, starts.value, ends.value),
    );
    const saved = await api.session(props.sid);
    const patch = {
      active: saved.active,
      starts_at: saved.starts_at,
      ends_at: saved.ends_at,
      effective_active: saved.effective_active,
      availability_reason: saved.availability_reason,
    };
    Object.assign(session.value!, patch);
    Object.assign(draft.value!, patch);
  }, "Availability updated.");
}
async function changeTab(value: string) {
  if (importing.value && value !== "questions") {
    if (
      !(await askConfirm(
        "Leave the question import? Unsaved import changes will be discarded.",
      ))
    )
      return;
    importing.value = false;
  }
  tab.value = value;
  if (value === "records") await loadRecords();
}
async function loadRecords() {
  await run(async () => {
    const [rows, editions] = await Promise.all([
      api.students(props.sid, recordVersion.value || undefined),
      api.versions(session.value!.course_id),
    ]);
    students.value = rows;
    versions.value = editions;
  });
}
async function importInstructions(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0];
  if (!file) return;
  await run(async () => {
    const result = await api.instructionPreview(props.sid, file);
    draft.value!.instructions = result.text;
  }, "Instructions extracted. Review and save the draft.");
}
function materialsChanged(s: SessionDetail) {
  session.value!.materials = s.materials;
  draft.value!.materials = s.materials;
}
async function discard() {
  if (await askConfirm("Discard your unsaved teaching changes?"))
    fill(session.value!);
}
async function inspect() {
  preview.value = true;
  await run(async () => {
    compiled.value = await api.teachingPreview(props.sid, {
      teaching_profile: profile.value,
      instructions: draft.value!.instructions,
      learning_objectives: draft.value!.learning_objectives,
      teaching_language: draft.value!.teaching_language,
      reference_policy: draft.value!.reference_policy,
    });
  });
}
</script>
<template>
  <template v-if="session && draft"
    ><PageHeader
      class="session-header"
      :class="{ compact: tab !== 'setup' }"
      :title="session.title"
      :eyebrow="`SESSION ${session.number} · TEACHING`"
      :description="tab === 'setup' ? session.subtitle : undefined"
      ><button class="secondary" :disabled="busy" @click="inspect">
        <Eye :size="16" /> Preview session</button
      ><button
        v-if="tab === 'setup' || dirty"
        class="primary"
        :disabled="busy || !dirty"
        @click="save"
      >
        <Save :size="16" /> Save draft
      </button></PageHeader
    >
    <div class="status-strip">
      <span>{{ dirty ? "Unsaved draft" : "Draft saved" }}</span
      ><span
        class="badge"
        :class="session.effective_active ? 'positive' : 'neutral'"
        >{{
          session.effective_active ? "Open to students" : "Closed to students"
        }}</span
      ><button
        class="link-button"
        @click="navigate({ page: 'versions', sid: session.course_id })"
      >
        Publish & history →
      </button>
    </div>
    <FeedbackNotice
      :error="preview ? '' : error"
      :success="success"
      :busy="busy && !preview"
    />
    <nav class="tabs session-tabs" aria-label="Session sections">
      <button
        v-for="[id, name] in [
          ['setup', 'Teaching setup'],
          ['questions', 'Questions'],
          ['materials', 'Materials'],
          ['records', 'Student work'],
        ]"
        :key="id"
        :class="{ active: tab === id }"
        :aria-current="tab === id ? 'page' : undefined"
        :disabled="busy"
        @click="changeTab(id)"
      >
        {{ name
        }}<span v-if="id === 'questions'" class="count">{{
          draft.questions.length
        }}</span>
      </button>
    </nav>
    <div v-if="tab === 'setup'" class="setup-layout">
      <div class="form-stack">
        <section class="panel">
          <div class="section-header">
            <div>
              <h2>Learning goals</h2>
              <p>Define what students should understand by the end.</p>
            </div>
          </div>
          <label
            >Objectives · one per line<textarea v-model="objectives" rows="4" />
          </label>
          <div class="form-grid">
            <label
              >Teaching language<select v-model="draft.teaching_language">
                <option value="en">English</option>
                <option value="zh">Chinese</option>
              </select></label
            ><label
              >Include in next publication<select v-model="draft.status">
                <option value="published">Included</option>
                <option value="draft">Draft only</option>
              </select></label
            >
          </div>
        </section>
        <section class="panel">
          <div class="section-header">
            <div>
              <h2>Teaching approach</h2>
              <p>Set the context and guidance for your teaching.</p>
            </div>
          </div>
          <label
            >Background<textarea
              v-model="profile.background"
              rows="3"
              maxlength="8000"
            /></label
          ><label
            >Student profile<textarea
              v-model="profile.student_profile"
              rows="2"
              maxlength="8000"
            /></label
          ><label
            >Response strategies<textarea
              v-model="profile.response_strategies"
              rows="3"
              maxlength="8000"
            />
          </label>
          <div class="form-grid">
            <label>Tone<input v-model="profile.tone" maxlength="1000" /></label
            ><label
              >Response detail<select v-model="profile.response_detail">
                <option value="concise">Concise</option>
                <option value="balanced">Balanced</option>
                <option value="detailed">Detailed</option>
              </select></label
            >
          </div>
          <details class="form-section">
            <summary>Teaching sequence & reference rules</summary>
            <div class="checkbox-list">
              <label
                v-for="phase in [
                  'warmup',
                  'worksheet',
                  'quiz',
                  'reading',
                  'wrap_up',
                ] as TeachingPhase[]"
                :key="phase"
                class="check"
                ><input
                  type="checkbox"
                  :checked="profile.phases.includes(phase)"
                  :disabled="phase === 'worksheet' || phase === 'wrap_up'"
                  @change="
                    profile.phases = toggleTeachingPhase(
                      profile.phases,
                      phase as 'warmup' | 'quiz' | 'reading',
                    )
                  "
                />{{ teachingPhaseLabels[phase] }}</label
              >
            </div>
            <label
              >Reading focus<textarea
                v-model="profile.reading_focus"
                rows="2"
              />
            </label>
            <div class="form-grid">
              <label
                >Reading questions<input
                  v-model.number="profile.reading_question_count"
                  type="number"
                  min="1"
                  max="5" /></label
              ><label
                >Question presentation<select v-model="profile.presentation">
                  <option value="full">All questions</option>
                  <option value="paced">One at a time</option>
                </select></label
              ><label
                >References become available<select
                  v-model="draft.reference_policy"
                >
                  <option value="after_attempt">After an attempt</option>
                  <option value="after_feedback">After feedback</option>
                  <option value="after_submit">After submission</option>
                </select></label
              ><label
                >Reference delivery<select v-model="profile.reference_delivery">
                  <option value="on_request">On request</option>
                  <option value="after_sufficient_answer">
                    After a sufficient answer
                  </option>
                </select></label
              ><label
                >Idle hint delay · seconds<input
                  v-model.number="profile.idle_hint_seconds"
                  type="number"
                  min="0"
                  max="300"
                /><small
                  >0 disables idle hints; otherwise use 10–300 seconds.</small
                ></label
              >
            </div>
          </details>
          <details class="form-section">
            <summary>Additional instructions</summary>
            <label
              >Instructions<textarea
                v-model="draft.instructions"
                rows="6"
                maxlength="30000"
              /></label
            ><label
              >Import instructions<input
                type="file"
                accept=".txt,.md,.docx,.pdf"
                @change="importInstructions"
            /></label>
          </details>
        </section>
      </div>
      <aside class="form-stack">
        <section class="panel">
          <h2>Availability</h2>
          <p class="muted">
            Controls when students can enter the published session.
          </p>
          <label class="check"
            ><input v-model="active" type="checkbox" />Open without a
            schedule</label
          ><label
            >Starts at<input v-model="starts" type="datetime-local" /></label
          ><label>Ends at<input v-model="ends" type="datetime-local" /></label
          ><small>A schedule takes precedence over the switch.</small
          ><button
            class="secondary full"
            :disabled="busy || !scheduleDirty"
            @click="availability"
          >
            Apply availability
          </button>
        </section>
        <section class="panel quiet-panel">
          <h3>Prepare → save → publish</h3>
          <p>
            Saving keeps your draft. Publishing updates the course students can
            see.
          </p>
          <button
            class="secondary full"
            @click="navigate({ page: 'versions', sid: session.course_id })"
          >
            Publish & history
          </button>
        </section>
      </aside>
    </div>
    <template v-else-if="tab === 'questions'"
      ><WorksheetImporter
        v-if="importing"
        :session="session"
        @close="importing = false"
        @saved="
          (s) => {
            fill(s);
            importing = false;
          }
        " /><template v-else
        ><p v-if="dirty" class="notice warning">
          Saving a question will also save your current teaching changes.
        </p>
        <QuestionManager
          :value="worksheet"
          :materials="session.materials"
          :save="saveQuestions"
          :disabled="busy"
          @import="
            () => {
              if (dirty) {
                error = 'Save or discard teaching changes before importing.';
              } else importing = true;
            }
          " /></template
    ></template>
    <MaterialsPane
      v-else-if="tab === 'materials'"
      :materials="session.materials"
      :session="session"
      @changed="materialsChanged"
    />
    <section v-else>
      <div class="section-header">
        <div>
          <h2>Student work</h2>
          <p>Review submissions from the selected course version.</p>
        </div>
        <button
          class="secondary"
          :disabled="busy"
          @click="changeTab('records')"
        >
          Refresh
        </button>
      </div>
      <div class="filter-bar">
        <label
          >Course version
          <select
            v-model="recordVersion"
            :disabled="busy"
            @change="loadRecords"
          >
            <option value="">Current published version</option>
            <option v-for="v in versions?.versions" :key="v.id" :value="v.id">
              Version {{ v.number }} · {{ v.label }}
            </option>
          </select>
        </label>
      </div>
      <div class="item-list">
        <ItemRow
          v-for="row in students"
          :key="row.user.id"
          :title="row.user.name"
          :description="row.user.email"
          ><template #meta
            ><span>{{ row.answered }} / {{ row.total }} answered</span
            ><span class="badge">{{ label(row.status) }}</span
            ><span>{{ dateText(row.last_active) }}</span></template
          ><template #actions
            ><button
              class="secondary"
              @click="
                navigate({
                  page: 'record',
                  sid,
                  uid: row.user.id,
                  version: recordVersion || row.version?.id || undefined,
                })
              "
            >
              Review work
            </button></template
          ></ItemRow
        >
        <div v-if="!students.length && !busy" class="empty-state">
          No student work yet.
        </div>
      </div>
    </section>
    <div v-if="tab === 'setup' && dirty" class="save-bar">
      <span>Unsaved teaching changes</span>
      <div class="actions">
        <button class="secondary" :disabled="busy" @click="discard">
          Discard</button
        ><button class="primary" :disabled="busy" @click="save">
          Save draft
        </button>
      </div>
    </div>
    <EditorDialog
      v-if="preview"
      title="Draft preview"
      wide
      :busy="busy"
      @close="preview = false"
      ><FeedbackNotice :error="error" :busy="busy" />
      <p class="notice">
        Previewing your current teaching setup. No AI request is made.
      </p>
      <h3>{{ draft.title }}</h3>
      <ul>
        <li v-for="goal in draft.learning_objectives" :key="goal">
          {{ goal }}
        </li>
      </ul>
      <h3>Questions</h3>
      <ItemRow
        v-for="q in draft.questions"
        :key="q.id"
        :title="q.prompt"
        :number="q.ordinal"
        ><template #meta>{{ label(q.type) }}</template></ItemRow
      >
      <details v-if="compiled" class="form-section">
        <summary>Compiled teaching instructions</summary>
        <RichText :text="compiled.text" />
      </details>
      <template #actions
        ><button
          class="primary"
          :disabled="busy"
          @click="
            preview = false;
            tab = 'setup';
          "
        >
          Back to teaching setup
        </button></template
      ></EditorDialog
    > </template
  ><FeedbackNotice v-else :error="error" :busy="busy" />
</template>
