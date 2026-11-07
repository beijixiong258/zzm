<script setup lang="ts">
import { Button as TButton, Input as TInput } from "tdesign-vue-next";
import { computed, onBeforeUnmount, ref, watch } from "vue";
import {
  assessmentStatusText,
  call,
  dateText,
  key,
  type Assessment,
  type AssessmentHistory,
  type AssessmentStatus,
  type AssessmentSummary,
} from "../classroom-api";
import { systemText, t } from "../i18n";
import ProgressStatus from "./ProgressStatus.vue";

const props = defineProps<{
  recordId: string;
  latest: AssessmentSummary;
  canGrade?: boolean;
}>();
const emit = defineEmits<{
  updated: [assessment: AssessmentSummary];
  unavailable: [error: unknown];
}>();
const selected = ref(props.latest.id);
const assessment = ref<Assessment | null>(null);
const history = ref<AssessmentHistory | null>(null);
const historyBusy = ref(false);
const historyError = ref("");
const busy = ref(false);
const loading = ref(false);
const error = ref("");
const scoreDraft = ref("");
const scoreSaved = ref(false);
const scoreChanged = computed(
  () => scoreDraft.value !== String(assessment.value?.teacherScore ?? ""),
);
const validScore = computed(
  () =>
    !scoreDraft.value.trim() ||
    (/^\d{1,3}(\.\d{1,2})?$/.test(scoreDraft.value) &&
      Number(scoreDraft.value) <= 100),
);
const summary = computed(
  () =>
    assessment.value ??
    (selected.value === props.latest.id
      ? props.latest
      : history.value?.items.find((item) => item.id === selected.value)),
);
const feedback = computed(() => assessment.value?.feedback);
const sections = computed(() => [
  {
    title: t("What you did well"),
    points: feedback.value?.strengths,
    empty: t(
      "There is not enough evidence to identify a strength in this submission.",
    ),
  },
  {
    title: t("What you still need to improve"),
    points: feedback.value?.improvements,
    empty: t("No immediate corrections were identified."),
  },
  {
    title: t("What you can try next"),
    points: feedback.value?.nextSteps,
    empty: "",
  },
]);
const judgementLabels = {
  met: "Meets the requirements",
  partial: "Partly meets the requirements",
  revise: "Needs correction",
  insufficient: "Insufficient evidence",
} as const;
let timer: ReturnType<typeof setTimeout> | undefined;
let loadSequence = 0;
let historySequence = 0;
let disposed = false;

function pending(status?: AssessmentStatus) {
  return status === "queued" || status === "running";
}
function endpoint() {
  return `/records/${key(props.recordId)}/assessments/${key(selected.value)}`;
}
function receive(value: Assessment, preserveScore = false) {
  const previous = summary.value;
  const editing = preserveScore && scoreChanged.value;
  assessment.value = value;
  if (!editing) scoreDraft.value = String(value.teacherScore ?? "");
  if (history.value) {
    history.value.items = history.value.items.map((item) =>
      item.id === value.id ? value : item,
    );
  }
  if (
    selected.value === props.latest.id &&
    (previous?.status !== value.status ||
      previous?.teacherScore !== value.teacherScore)
  )
    emit("updated", value);
  if (pending(value.status)) timer = setTimeout(loadAssessment, 2500);
}
function showError(value: unknown) {
  error.value = (value as Error).message;
  if (error.value === "Task is not currently available.")
    emit("unavailable", value);
}
async function loadAssessment() {
  clearTimeout(timer);
  if (disposed || busy.value) return;
  const sequence = ++loadSequence;
  loading.value = !assessment.value;
  try {
    const value = await call<Assessment>(endpoint());
    if (disposed || sequence !== loadSequence) return;
    error.value = "";
    receive(value, !!assessment.value);
  } catch (e) {
    if (!disposed && sequence === loadSequence) showError(e);
  } finally {
    if (!disposed && sequence === loadSequence) loading.value = false;
  }
}
async function updateAssessment(operation: "retry" | "score") {
  if (busy.value || disposed || !assessment.value) return;
  clearTimeout(timer);
  const sequence = ++loadSequence;
  busy.value = true;
  error.value = "";
  scoreSaved.value = false;
  try {
    const value = await call<Assessment>(
      `${endpoint()}/${operation}`,
      operation === "score" ? "PUT" : "POST",
      operation === "score"
        ? { score: scoreDraft.value.trim() ? Number(scoreDraft.value) : null }
        : undefined,
    );
    if (disposed || sequence !== loadSequence) return;
    receive(value);
    scoreSaved.value = operation === "score";
  } catch (e) {
    if (!disposed && sequence === loadSequence) {
      showError(e);
      if (pending(summary.value?.status))
        timer = setTimeout(loadAssessment, 2500);
    }
  } finally {
    if (!disposed && sequence === loadSequence) busy.value = false;
  }
}
async function loadHistory(page: number) {
  const sequence = ++historySequence;
  historyBusy.value = true;
  historyError.value = "";
  try {
    const result = await call<AssessmentHistory>(
      `/records/${key(props.recordId)}/assessments?page=${page}`,
    );
    if (!disposed && sequence === historySequence) history.value = result;
  } catch (e) {
    if (!disposed && sequence === historySequence)
      historyError.value = (e as Error).message;
  } finally {
    if (!disposed && sequence === historySequence) historyBusy.value = false;
  }
}
function toggleHistory(event: Event) {
  if (
    (event.currentTarget as HTMLDetailsElement).open &&
    !history.value &&
    !historyBusy.value
  )
    void loadHistory(1);
}
function selectAssessment(id: string) {
  if (busy.value) return;
  selected.value = id;
  assessment.value = null;
  scoreDraft.value = "";
  scoreSaved.value = false;
  error.value = "";
  void loadAssessment();
}
watch(
  [() => props.recordId, () => props.latest.id],
  () => {
    ++historySequence;
    history.value = null;
    historyBusy.value = false;
    historyError.value = "";
    busy.value = false;
    selectAssessment(props.latest.id);
  },
  { immediate: true },
);
onBeforeUnmount(() => {
  disposed = true;
  clearTimeout(timer);
});
</script>

<template>
  <section
    class="formative-assessment"
    :aria-label="t('AI formative feedback')"
  >
    <header class="row wrap spread">
      <h3>{{ t("AI formative feedback") }}</h3>
      <small v-if="summary" class="muted">{{
        dateText(summary.submittedAt)
      }}</small>
    </header>
    <p v-if="error" class="error" role="alert">
      {{ systemText(error) }}
      <TButton
        theme="default"
        variant="text"
        :disabled="busy || loading"
        @click="loadAssessment"
        >{{ t("Refresh") }}</TButton
      >
    </p>
    <ProgressStatus
      v-else-if="summary && pending(summary.status)"
      :label="assessmentStatusText(summary.status)"
      :value="
        summary.evaluatedCount
          ? (summary.evaluatedCount * 100) / summary.questionCount
          : null
      "
      :detail="
        t('Assessed {0} of {1} questions', [
          summary.evaluatedCount,
          summary.questionCount,
        ])
      "
    />
    <p v-else-if="loading" class="muted">{{ t("Loading…") }}</p>
    <template v-else-if="assessment?.status === 'failed'">
      <p class="notice">
        {{
          t("The assessment did not finish. Your submitted answers are saved.")
        }}
      </p>
      <TButton
        theme="default"
        variant="outline"
        :disabled="busy"
        @click="updateAssessment('retry')"
        >{{ t("Retry assessment") }}</TButton
      >
    </template>
    <p v-else-if="assessment && !feedback" class="muted">
      {{ assessmentStatusText(assessment.status) }}
    </p>
    <template v-if="feedback">
      <section
        v-for="section in sections"
        :key="section.title"
        class="feedback-section"
      >
        <h4>{{ section.title }}</h4>
        <ul v-if="section.points?.length">
          <li v-for="point in section.points" :key="point.questionNumber">
            <strong>{{ t("Question {0}", [point.questionNumber]) }}</strong>
            {{ point.text }}
          </li>
        </ul>
        <p v-else class="muted">{{ section.empty }}</p>
      </section>
      <details class="question-feedback">
        <summary>{{ t("Feedback by question") }}</summary>
        <details
          v-for="question in feedback.questions"
          :key="question.questionId"
          class="feedback-question"
        >
          <summary>
            <span>{{ t("Question {0}", [question.number]) }}</span>
            <span class="muted">
              · {{ t(judgementLabels[question.judgement]) }}</span
            >
          </summary>
          <p class="feedback-prompt">{{ question.prompt }}</p>
          <p
            v-if="question.evidenceLabel || question.quote"
            class="muted feedback-prompt"
          >
            <strong>{{ question.evidenceLabel || t("Your answer") }}</strong>
            <span v-if="question.quote"> · {{ question.quote }}</span>
          </p>
          <p v-if="question.strength">{{ question.strength }}</p>
          <p v-if="question.improvement">{{ question.improvement }}</p>
          <p>{{ question.nextStep }}</p>
        </details>
      </details>
    </template>
    <section
      v-if="assessment && (canGrade || assessment.teacherScore != null)"
      class="assessment-score"
    >
      <template v-if="canGrade">
        <div class="row wrap">
          <label>
            {{ t("Teacher score") }}
            <TInput
              :value="scoreDraft"
              v-control-attrs="{ min: 0, max: 100, step: 0.01 }"
              type="number"
              :disabled="busy"
              @change="
                (value) => {
                  scoreDraft = String(value ?? '');
                  scoreSaved = false;
                }
              "
            />
          </label>
          <TButton
            theme="default"
            variant="outline"
            :disabled="busy || !validScore || !scoreChanged"
            @click="updateAssessment('score')"
          >
            {{ t("Save score") }}
          </TButton>
        </div>
        <small v-if="!validScore" class="error">{{
          t("Enter a score between 0 and 100 with up to two decimal places.")
        }}</small>
        <small v-else-if="scoreSaved" role="status">{{
          t("Score saved.")
        }}</small>
        <small v-else class="muted">{{
          t("Leave blank for an ungraded submission.")
        }}</small>
      </template>
      <p v-else>
        <strong>{{ t("Teacher score") }}</strong> ·
        {{ assessment.teacherScore }} / 100
      </p>
    </section>
    <details class="assessment-history" @toggle="toggleHistory">
      <summary>{{ t("Assessment history") }}</summary>
      <p v-if="historyError" class="error" role="alert">
        {{ systemText(historyError) }}
      </p>
      <p v-if="historyBusy" class="muted">{{ t("Loading…") }}</p>
      <div v-if="history" class="assessment-history-list">
        <TButton
          v-for="item in history.items"
          :key="item.id"
          theme="default"
          variant="outline"
          :disabled="busy || item.id === selected"
          @click="selectAssessment(item.id)"
        >
          {{ dateText(item.submittedAt) }} ·
          {{ assessmentStatusText(item.status) }}
        </TButton>
        <div v-if="history.page > 1 || history.hasMore" class="row wrap">
          <TButton
            theme="default"
            variant="text"
            :disabled="historyBusy || history.page === 1"
            @click="loadHistory(history.page - 1)"
          >
            {{ t("Previous page") }}
          </TButton>
          <TButton
            theme="default"
            variant="text"
            :disabled="historyBusy || !history.hasMore"
            @click="loadHistory(history.page + 1)"
          >
            {{ t("Next page") }}
          </TButton>
        </div>
      </div>
    </details>
  </section>
</template>

<style scoped>
.formative-assessment {
  min-width: 0;
  margin: 18px 0;
  padding: clamp(12px, 2vw, 20px);
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--paper);
  overflow-wrap: anywhere;
}
.formative-assessment > header {
  margin-bottom: 12px;
}
.feedback-section,
.question-feedback,
.assessment-score,
.assessment-history {
  margin-top: 14px;
}
.feedback-section ul {
  margin: 0;
  padding-inline-start: 20px;
}
.feedback-section li {
  margin-bottom: 6px;
}
.feedback-question,
.assessment-score {
  border-top: 1px solid var(--line);
  padding-top: 10px;
}
.feedback-prompt {
  margin-top: 8px;
  white-space: pre-wrap;
}
.assessment-score > .row {
  align-items: flex-end;
}
.assessment-score label {
  width: min(140px, 100%);
}
.assessment-history-list {
  display: grid;
  gap: 8px;
  margin-top: 8px;
}
</style>
