<script setup lang="ts">
import { t } from "../../i18n";

import { askConfirm } from "../state";
import { computed, ref, watch } from "vue";
import { Send, FileText, BookmarkCheck, CheckCheck } from "lucide-vue-next";
import { api } from "../../api";
import type { Workspace, Question } from "../../types";
import { clientId } from "../../ids";
import {
  readDraft,
  writeDraft,
  clearDraft,
  type DraftScope,
} from "../../drafts";
import { activeQuestions, canReveal, canSubmit, isLocked } from "../../study";
import { dateText, useTask, useDirty, label } from "../state";
import PageHeader from "../components/PageHeader.vue";
import ItemRow from "../components/ItemRow.vue";
import EditorDialog from "../components/EditorDialog.vue";
import MaterialsPane from "../components/MaterialsPane.vue";
import RichText from "../components/RichText.vue";
import FeedbackNotice from "../components/FeedbackNotice.vue";
const props = defineProps<{ sid: string; uid?: string; version?: string }>();
const { busy, error, success, run } = useTask();
const workspace = ref<Workspace | null>(null),
  panel = ref("conversation"),
  message = ref(""),
  question = ref<Question | null>(null),
  answer = ref(""),
  answerInitial = ref(""),
  reference = ref(""),
  note = ref(""),
  pendingRequest = ref("");
const readonly = computed(
  () => !!props.uid || (!!workspace.value && isLocked(workspace.value)),
);
const dirty = computed(
  () =>
    !!message.value ||
    (!!question.value && answer.value !== answerInitial.value) ||
    (!!props.uid &&
      !!workspace.value &&
      note.value !== workspace.value.submission.teacher_note),
);
useDirty(dirty);
const questions = computed(() =>
  workspace.value ? activeQuestions(workspace.value) : [],
);
let requestFingerprint = "";
function requestFor(value: string) {
  if (!pendingRequest.value || requestFingerprint !== value) {
    pendingRequest.value = clientId();
    requestFingerprint = value;
  }
  return pendingRequest.value;
}
const previewId = computed(() => workspace.value?.preview?.id || undefined);
function draftScope(intent: DraftScope["intent"], questionId = ""): DraftScope {
  return {
    user: workspace.value!.user.id,
    session: props.sid,
    version: workspace.value!.version?.id || props.version || null,
    question: questionId,
    intent,
    preview: !!workspace.value!.preview,
    preview_run_id: previewId.value,
  };
}
watch(message, (value) => {
  if (workspace.value && !readonly.value)
    writeDraft(draftScope("conversation"), value);
});
watch(answer, (value) => {
  if (workspace.value && question.value && !readonly.value)
    writeDraft(draftScope("saved-answer", question.value.id), value);
});
async function load() {
  await run(async () => {
    workspace.value = props.uid
      ? await api.studentWorkspace(props.sid, props.uid, props.version)
      : await api.workspace(props.sid, props.version);
    note.value = workspace.value.submission.teacher_note;
    if (!readonly.value)
      message.value = readDraft(draftScope("conversation")) || "";
  });
}
void load();
function edit(q: Question) {
  question.value = q;
  answerInitial.value = workspace.value?.attempts[q.id]?.answer || "";
  answer.value =
    (!readonly.value && readDraft(draftScope("saved-answer", q.id))) ||
    answerInitial.value;
  reference.value = "";
  error.value = "";
}
function closeAnswer() {
  if (question.value && !readonly.value)
    clearDraft(draftScope("saved-answer", question.value.id));
  question.value = null;
}
async function saveAnswer() {
  if (!question.value) return;
  const ok = await run(async () => {
    workspace.value = await api.answer(
      props.sid,
      question.value!.id,
      answer.value,
      props.version,
      previewId.value,
    );
    const saved = workspace.value.attempts[question.value!.id];
    if (!saved || saved.answer !== answer.value.trim())
      throw Error(t("The saved answer could not be verified."));
  }, t("Answer saved."));
  if (ok) closeAnswer();
}
async function start() {
  await run(async () => {
    if (workspace.value?.preview) {
      const info = await api.previewInfo(props.sid);
      if (info.reset_required || !info.id)
        workspace.value = await api.resetPreview(
          props.sid,
          info.current_revision,
        );
    }
    requestFor("start");
    workspace.value = await api.tutorStart(
      props.sid,
      pendingRequest.value,
      props.version,
      previewId.value,
    );
    pendingRequest.value = "";
  });
}
async function send(action: "message" | "hint" | "skip_quiz" = "message") {
  if (!message.value.trim() && action === "message") return;
  const text = message.value;
  await run(async () => {
    requestFor(JSON.stringify([text, action]));
    workspace.value = await api.tutorTurn(
      props.sid,
      {
        message: text,
        request_id: pendingRequest.value,
        preview_id: previewId.value,
        action,
      },
      props.version,
    );
    pendingRequest.value = "";
    clearDraft(draftScope("conversation"));
    message.value = "";
  });
}
async function submit() {
  if (!(await askConfirm(t("Submit your saved work to the teacher?")))) return;
  await run(async () => {
    workspace.value = await api.submit(
      props.sid,
      props.version,
      previewId.value,
    );
  }, t("Work submitted."));
}
function composerKey(event: KeyboardEvent) {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    if (!busy.value && workspace.value?.ai.configured) void send();
  }
}
async function review(status: "confirmed" | "needs_revision") {
  if (!props.uid) return;
  await run(async () => {
    workspace.value = await api.review(
      props.sid,
      props.uid!,
      status,
      note.value,
      props.version,
    );
  }, t("Review saved."));
}
async function chooseReading(id: string) {
  await run(async () => {
    workspace.value = await api.reading(
      props.sid,
      id,
      props.version,
      previewId.value,
    );
  });
}
async function example() {
  if (!question.value) return;
  await run(async () => {
    reference.value = (
      await api.reference(
        props.sid,
        question.value!.id,
        props.version,
        previewId.value,
      )
    ).reference;
  });
}
</script>
<template>
  <template v-if="workspace"
    ><PageHeader
      :title="workspace.session.title"
      :eyebrow="
        t('SESSION {0} · {1}', [
          workspace.session.number,
          uid ? t('STUDENT WORK') : t('LEARNING'),
        ])
      "
      ><a
        class="secondary"
        :href="api.exportUrl(sid, uid, version)"
        target="_blank"
        rel="noopener"
        >{{ t("Export work") }}</a
      ><button
        v-if="!readonly"
        class="primary"
        :disabled="busy || !canSubmit(workspace)"
        @click="submit"
      >
        <CheckCheck :size="17" /> {{ t("Submit work") }}
      </button></PageHeader
    >
    <div class="status-strip">
      <span class="badge positive">{{
        label(workspace.submission.status)
      }}</span
      ><span
        >{{ workspace.progress.answered }} / {{ workspace.progress.total }}
        {{ t("answered") }}</span
      ><span v-if="workspace.version?.number"
        >{{ t("Course version") }} {{ workspace.version.number }}</span
      ><span v-if="uid">{{ workspace.user.name }}</span>
    </div>
    <p v-if="workspace.read_only_reason" class="notice warning">
      {{ workspace.read_only_reason }}
    </p>
    <FeedbackNotice
      :error="question ? '' : error"
      :success="success"
      :busy="busy && !question"
    />
    <nav class="tabs learning-tabs" :aria-label="t('Learning sections')">
      <button
        :class="{ active: panel === 'conversation' }"
        @click="panel = 'conversation'"
      >
        <Send :size="15" /> {{ t("Conversation") }}</button
      ><button
        :class="{ active: panel === 'answers' }"
        @click="panel = 'answers'"
      >
        <BookmarkCheck :size="16" /> {{ t("Questions & answers") }}</button
      ><button
        :class="{ active: panel === 'materials' }"
        @click="panel = 'materials'"
      >
        <FileText :size="16" /> {{ t("Materials") }}
      </button>
    </nav>
    <section v-if="panel === 'conversation'" class="learning-conversation">
      <div v-if="!readonly && !workspace.ai.configured" class="notice warning">
        {{
          t(
            "The AI tutor has not been configured. You can still browse materials and save your answers.",
          )
        }}
      </div>
      <div v-if="!workspace.messages.length" class="conversation-empty">
        <span class="learning-symbol">“</span>
        <h2>{{ t("A place to work through your thinking.") }}</h2>
        <p>
          {{ t("Start with the materials and questions for this session.") }}
        </p>
        <div class="actions">
          <button class="secondary" @click="panel = 'answers'">
            {{ t("View questions") }}</button
          ><button
            v-if="!readonly"
            class="primary"
            :disabled="busy || !workspace.ai.configured"
            @click="start"
          >
            {{ t("Start conversation") }}
          </button>
        </div>
      </div>
      <div v-else class="conversation-messages">
        <article
          v-for="m in workspace.messages"
          :key="m.id"
          class="message"
          :class="m.role"
        >
          <div class="message-heading">
            <strong>{{
              m.role === "user" ? t("You") : t("Learning tutor")
            }}</strong
            ><time>{{ dateText(m.created_at) }}</time>
          </div>
          <RichText :text="m.content" />
          <section
            v-if="
              m.metadata?.presented_question &&
              (!m.content.includes(m.metadata.presented_question.prompt) ||
                m.metadata.presented_question.options?.length)
            "
            class="presented-question"
          >
            <RichText
              v-if="!m.content.includes(m.metadata.presented_question.prompt)"
              :text="m.metadata.presented_question.prompt"
            />
            <div
              v-if="m.metadata.presented_question.options?.length"
              class="actions"
            >
              <button
                v-for="option in m.metadata.presented_question.options"
                :key="option"
                class="secondary"
                :disabled="busy || readonly"
                @click="message = option"
              >
                {{ option }}
              </button>
            </div>
          </section>
          <div v-if="m.citations?.length" class="citation-list">
            <template v-for="(c, i) in m.citations" :key="i"
              ><a
                v-if="c.url && /^https?:\/\//.test(c.url)"
                :href="c.url"
                target="_blank"
                rel="noopener"
                >{{ c.source_label }}</a
              ><span v-else>{{ c.source_label }}</span></template
            >
          </div>
        </article>
      </div>
      <form v-if="!readonly" class="composer" @submit.prevent="send()">
        <label class="sr-only" for="learning-message">{{
          t("Message to the tutor")
        }}</label
        ><textarea
          id="learning-message"
          @keydown="composerKey"
          v-model="message"
          rows="2"
          :disabled="busy || !workspace.ai.configured"
          :placeholder="t('Explain your thinking, or ask a question…')"
        />
        <div class="composer-actions">
          <div class="actions">
            <button
              type="button"
              class="secondary"
              :disabled="
                busy || !workspace.ai.configured || !workspace.tutor?.started_at
              "
              @click="send('hint')"
            >
              {{ t("Ask for a hint") }}</button
            ><button
              v-if="
                workspace.tutor?.phase === 'quiz_offer' ||
                workspace.tutor?.phase === 'quiz'
              "
              type="button"
              class="secondary"
              :disabled="busy"
              @click="send('skip_quiz')"
            >
              {{ t("Skip optional quiz") }}
            </button>
          </div>
          <button
            class="primary"
            :disabled="busy || !workspace.ai.configured || !message.trim()"
          >
            <Send :size="16" /> {{ t("Send") }}
          </button>
        </div>
      </form>
    </section>
    <section v-else-if="panel === 'answers'">
      <div class="section-header">
        <div>
          <h2>{{ t("Questions & saved answers") }}</h2>
          <p>
            {{
              readonly
                ? t("Your retained answers for this course version.")
                : t("Save your answers as you work. Submit when ready.")
            }}
          </p>
        </div>
      </div>
      <div
        v-if="
          workspace.session.groups.some((g) => g.kind === 'reading') &&
          !readonly
        "
        class="panel"
      >
        <h3>{{ t("Reading choice") }}</h3>
        <div class="actions">
          <button
            v-for="g in workspace.session.groups.filter(
              (g) => g.kind === 'reading',
            )"
            :key="g.id"
            :class="
              workspace.selected_reading === g.id ? 'primary' : 'secondary'
            "
            :disabled="busy"
            @click="chooseReading(g.id)"
          >
            {{ g.title }}
          </button>
        </div>
      </div>
      <div class="item-list">
        <ItemRow
          v-for="q in questions"
          :key="q.id"
          :title="q.prompt"
          :number="q.ordinal"
          ><template #meta
            ><span>{{ label(q.type) }}</span
            ><span
              class="badge"
              :class="workspace.attempts[q.id] ? 'positive' : 'neutral'"
              >{{
                workspace.attempts[q.id] ? t("Answer saved") : t("Not answered")
              }}</span
            ></template
          ><RichText
            v-if="workspace.attempts[q.id]"
            :text="workspace.attempts[q.id].answer"
          /><template #actions
            ><button class="secondary" @click="edit(q)">
              {{
                readonly
                  ? t("View answer")
                  : workspace.attempts[q.id]
                    ? t("Edit answer")
                    : t("Write answer")
              }}
            </button></template
          ></ItemRow
        >
        <div v-if="!questions.length" class="empty-state">
          {{ t("No active questions in this session.") }}
        </div>
      </div>
    </section>
    <MaterialsPane
      v-else
      :materials="
        workspace.session.materials.filter((m) => m.visibility === 'student')
      "
      :version="version"
    />
    <section v-if="uid" class="panel review-panel">
      <h2>{{ t("Teacher review") }}</h2>
      <label
        >{{ t("Feedback to the student") }}<textarea v-model="note" rows="3" />
      </label>
      <div class="actions">
        <button class="primary" :disabled="busy" @click="review('confirmed')">
          {{ t("Confirm completion") }}</button
        ><button
          class="secondary"
          :disabled="busy"
          @click="review('needs_revision')"
        >
          {{ t("Request revision") }}
        </button>
      </div>
    </section>
    <p v-else-if="workspace.submission.teacher_note" class="notice">
      {{ t("Teacher feedback:") }} {{ workspace.submission.teacher_note }}
    </p>
    <EditorDialog
      v-if="question"
      :title="t('Question {0}', [question.ordinal])"
      :busy="busy"
      :dirty="answer !== answerInitial"
      @close="closeAnswer"
      ><FeedbackNotice :error="error" /><RichText :text="question.prompt" />
      <div v-for="img in question.images" :key="img.url">
        <img class="question-image" :src="img.url" :alt="img.alt" />
      </div>
      <form id="answer-editor" class="form-stack" @submit.prevent="saveAnswer">
        <template v-if="question.type === 'single_choice'"
          ><label v-for="option in question.options" :key="option" class="check"
            ><input
              v-model="answer"
              type="radio"
              :value="option"
              :disabled="readonly"
            />{{ option }}</label
          ></template
        ><label v-else
          >{{ t("Your answer")
          }}<textarea v-model="answer" rows="6" :readonly="readonly" required />
        </label>
      </form>
      <p v-if="question.hint" class="muted">
        {{ t("Hint:") }} {{ question.hint }}
      </p>
      <button
        v-if="!uid"
        class="secondary"
        :disabled="busy || !canReveal(workspace, question.id)"
        @click="example"
      >
        {{ t("Request example") }}</button
      ><RichText v-if="reference" :text="reference" /><template
        v-if="!readonly"
        #actions
        ><button
          form="answer-editor"
          class="primary"
          :disabled="busy || !answer.trim()"
        >
          {{ t("Save answer") }}
        </button></template
      ></EditorDialog
    > </template
  ><FeedbackNotice v-else :error="error" :busy="busy" />
</template>
