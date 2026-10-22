<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { t } from "../../i18n";
import {
  call,
  key,
  statusText,
  versionParam,
  type LearningRecord,
  type Workspace,
} from "../../classroom-api";
import { dirty } from "../classroom-state";
import TaskContent from "../components/TaskContent.vue";
import RichText from "../components/RichText.vue";
const props = defineProps<{ taskId: string; versionId?: string }>();
const workspace = ref<Workspace | null>(null),
  answers = ref<Record<string, string>>({}),
  savedAnswers = ref("{}");
const busy = ref(false),
  error = ref(""),
  success = ref(""),
  prompt = ref("");
const record = computed(() => workspace.value?.record);
const readonly = computed(
  () =>
    !record.value || ["submitted", "confirmed"].includes(record.value.status),
);
watch(
  answers,
  () => {
    dirty.value = JSON.stringify(answers.value) !== savedAnswers.value;
  },
  { deep: true, flush: "sync" },
);
function accept(value: LearningRecord) {
  if (!workspace.value) return;
  workspace.value.record = value;
  answers.value = { ...value.answers };
  savedAnswers.value = JSON.stringify(answers.value);
  dirty.value = false;
}
async function load() {
  try {
    workspace.value = await call<Workspace>(
      `/sessions/${key(props.taskId)}/workspace${versionParam(props.versionId)}`,
    );
    if (workspace.value.record) accept(workspace.value.record);
  } catch (e) {
    error.value = (e as Error).message;
  }
}
async function action(fn: () => Promise<void>) {
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  success.value = "";
  try {
    await fn();
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
async function start() {
  await action(async () =>
    accept(
      await call<LearningRecord>(
        `/sessions/${key(props.taskId)}/start${versionParam(workspace.value?.task.versionId)}`,
        "POST",
      ),
    ),
  );
}
async function saveAnswers() {
  if (record.value && dirty.value)
    accept(
      await call<LearningRecord>(
        `/records/${key(record.value.id)}/answers`,
        "PUT",
        { revision: record.value.revision, answers: answers.value },
      ),
    );
}
async function save() {
  await action(async () => {
    await saveAnswers();
    success.value = t("Answers saved.");
  });
}
async function submit() {
  if (!window.confirm(t("Submit your work for teacher review?"))) return;
  await action(async () => {
    await saveAnswers();
    if (record.value)
      accept(
        await call<LearningRecord>(
          `/records/${key(record.value.id)}/submit`,
          "POST",
          { revision: record.value.revision },
        ),
      );
  });
}
async function chat() {
  if (!prompt.value.trim()) return;
  await action(async () => {
    await saveAnswers();
    if (!record.value) return;
    accept(
      await call<LearningRecord>(
        `/records/${key(record.value.id)}/chat`,
        "POST",
        {
          message: prompt.value,
          requestId: crypto.randomUUID(),
          revision: record.value.revision,
        },
      ),
    );
    prompt.value = "";
  });
}
onBeforeUnmount(() => {
  dirty.value = false;
});
void load();
</script>
<template>
  <header class="page-heading">
    <div>
      <p class="eyebrow">{{ t("YOUR LEARNING") }}</p>
      <h1>{{ workspace?.task.title || t("Learning task") }}</h1>
    </div>
    <span class="badge">{{ statusText(record?.status || "notStarted") }}</span>
  </header>
  <p v-if="error" class="error" role="alert">{{ error }}</p>
  <p v-if="success" class="success" role="status">{{ success }}</p>
  <div v-if="workspace" class="learning-layout">
    <section class="panel">
      <TaskContent
        :task="workspace.task"
        :answers="answers"
        :readonly="readonly || busy"
        @answer="(id, value) => (answers[id] = value)"
      />
      <div class="row wrap task-actions">
        <button v-if="!record" class="primary" :disabled="busy" @click="start">
          {{ t("Start learning") }}</button
        ><template v-else-if="!readonly"
          ><button :disabled="busy || !dirty" @click="save">
            {{ t("Save answers") }}</button
          ><button class="primary" :disabled="busy" @click="submit">
            {{ t("Submit for review") }}
          </button></template
        >
        <p v-else class="muted">
          {{
            t(
              record?.status === "confirmed"
                ? "Your teacher has confirmed completion."
                : "Your work is waiting for teacher review.",
            )
          }}
        </p>
      </div>
      <div v-if="record?.teacherNote" class="teacher-feedback">
        <h3>{{ t("Teacher feedback") }}</h3>
        <RichText :text="record.teacherNote" />
      </div>
    </section>
    <aside class="panel tutor-panel">
      <h2>{{ t("AI learning support") }}</h2>
      <p v-if="!record" class="empty">
        {{
          t("Start this task to ask questions and save your learning progress.")
        }}
      </p>
      <template v-else
        ><div class="chat-messages">
          <article
            v-for="(message, index) in record.messages"
            :key="index"
            :class="['message', message.role]"
          >
            <small>{{ t(message.role === "user" ? "You" : "AI tutor") }}</small
            ><RichText :text="message.content" />
          </article>
        </div>
        <form v-if="!readonly" class="form-stack" @submit.prevent="chat">
          <textarea
            v-model="prompt"
            rows="3"
            :disabled="busy"
            :aria-label="t('Message to the AI tutor')"
            :placeholder="
              t('Ask about this task or describe where you are stuck.')
            "
          /><button class="primary" :disabled="busy || !prompt.trim()">
            {{ t(busy ? "Thinking…" : "Send") }}
          </button>
        </form></template
      >
    </aside>
  </div>
</template>
