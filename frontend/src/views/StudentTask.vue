<script setup lang="ts">
import { confirmAction } from "../confirmAction";
import {
  Checkbox as TCheckbox,
  CheckboxGroup as TCheckboxGroup,
  RadioGroup as TRadioGroup,
  Button as TButton,
  Select as TSelect,
  Option as TOption,
  Textarea as TTextarea,
} from "tdesign-vue-next";
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { t } from "../i18n";
import {
  call,
  download,
  key,
  statusText,
  versionParam,
  fileUrl,
  type LearningRecord,
  type Workspace,
  type Material,
  type ContextUsage,
} from "../classroom-api";
import { dirty } from "../classroom-state";
import TaskContent from "../components/TaskContent.vue";
import RichText from "../components/RichText.vue";
import RecordHistory from "../components/RecordHistory.vue";
import FileUploader from "../components/FileUploader.vue";
import ContextMeter from "../components/ContextMeter.vue";
import MaterialProgress from "../components/MaterialProgress.vue";
const props = defineProps<{
  taskId: string;
  versionId?: string;
  preview?: boolean;
}>();
const workspace = ref<Workspace | null>(null),
  answers = ref<Record<string, string>>({}),
  savedAnswers = ref("{}");
const busy = ref(false),
  error = ref(""),
  success = ref(""),
  prompt = ref("");
const pendingUploads = ref(0),
  feedbackDrafts = ref<Record<string, string>>({});
const attachments = ref<Material[]>([]),
  attachmentIds = ref<string[]>([]),
  questionId = ref("");
const usage = ref<ContextUsage | null>(null),
  checking = ref(false);
const record = computed(() => workspace.value?.record);
const previewPane = ref<"lesson" | "chat">("lesson");
const readonly = computed(
  () =>
    !record.value || ["submitted", "confirmed"].includes(record.value.status),
);
const changed = computed(
  () => JSON.stringify(answers.value) !== savedAnswers.value,
);
const awaiting = computed(() =>
  record.value?.messages.some((m) => m.pendingReview),
);
let timer: ReturnType<typeof setTimeout> | undefined,
  contextTimer: ReturnType<typeof setTimeout> | undefined,
  disposed = false,
  contextSequence = 0,
  attachmentSequence = 0,
  refreshSequence = 0;
watch(
  [changed, pendingUploads],
  ([value, pending]) => {
    if (!props.preview) dirty.value = value || pending > 0;
  },
  { flush: "sync" },
);
function updateRecord(value: LearningRecord) {
  if (!workspace.value || disposed) return;
  if (record.value?.id !== value.id) feedbackDrafts.value = {};
  const pending = new Set(
    value.messages
      .filter((message) => message.pendingReview)
      .map((message) => message.requestId),
  );
  for (const requestId of Object.keys(feedbackDrafts.value))
    if (!pending.has(requestId)) delete feedbackDrafts.value[requestId];
  workspace.value.record = value;
}
function accept(value: LearningRecord) {
  if (!workspace.value || disposed) return;
  updateRecord(value);
  answers.value = { ...value.answers };
  savedAnswers.value = JSON.stringify(answers.value);
  if (!props.preview) dirty.value = changed.value || pendingUploads.value > 0;
}
async function loadAttachments() {
  clearTimeout(timer);
  if (!record.value || disposed) return;
  const recordId = record.value.id;
  const sequence = ++attachmentSequence;
  const current = () =>
    !disposed &&
    record.value?.id === recordId &&
    sequence === attachmentSequence;
  try {
    const files = await call<Material[]>(
      `/records/${key(recordId)}/attachments`,
    );
    if (!current()) return;
    attachments.value = files;
    if (awaiting.value) await refreshRecord();
  } catch (e) {
    if (current()) error.value = (e as Error).message;
  }
  if (
    current() &&
    (awaiting.value ||
      attachments.value.some((m) =>
        ["queued", "processing"].includes(m.status),
      ))
  )
    timer = setTimeout(() => void loadAttachments(), 3000);
}
async function load() {
  try {
    const loaded = await call<Workspace>(
      `/sessions/${key(props.taskId)}/${props.preview ? "preview/workspace" : `workspace${versionParam(props.versionId)}`}`,
    );
    if (disposed) return;
    workspace.value = loaded;
    if (workspace.value.record) {
      accept(workspace.value.record);
      await loadAttachments();
      if (props.preview && awaiting.value) await refreshRecord();
    }
  } catch (e) {
    error.value = (e as Error).message;
  }
}
async function refreshRecord() {
  if (!record.value || disposed || busy.value) return;
  const recordId = record.value.id;
  const revision = record.value.revision;
  const sequence = ++refreshSequence;
  const current = () =>
    !disposed &&
    !busy.value &&
    sequence === refreshSequence &&
    record.value?.id === recordId &&
    record.value.revision === revision;
  if (props.preview) {
    const next = await call<Workspace>(
      `/records/${key(record.value.id)}/observe`,
    );
    if (next.record && current()) updateRecord(next.record);
  } else {
    const next = await call<Workspace>(
      `/sessions/${key(props.taskId)}/workspace${versionParam(workspace.value?.task.versionId)}`,
    );
    if (next.record && current()) updateRecord(next.record);
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
  if (pendingUploads.value) return;
  await action(async () => {
    accept(
      await call<LearningRecord>(
        `/sessions/${key(props.taskId)}/${props.preview ? "preview/start" : `start${versionParam(workspace.value?.task.versionId)}`}`,
        "POST",
      ),
    );
    attachments.value = [];
    attachmentIds.value = [];
    prompt.value = "";
    usage.value = null;
    await loadAttachments();
    if (props.preview) previewPane.value = "chat";
  });
}
async function saveAnswers() {
  if (record.value && changed.value)
    accept(
      await call<LearningRecord>(
        `/records/${key(record.value.id)}/answers`,
        "PUT",
        { revision: record.value.revision, answers: answers.value },
      ),
    );
}
async function exportTask() {
  if (!workspace.value || !record.value || props.preview) return;
  await action(async () => {
    await saveAnswers();
    await download(
      "/records/" + key(record.value!.id) + "/export?format=md",
      workspace.value!.task.title + "-learning-result.md",
    );
  });
}
async function resetConversation() {
  if (pendingUploads.value) return;
  if (
    !(await confirmAction(
      t(
        "Start a new conversation? Your previous conversation will remain in the history.",
      ),
    ))
  )
    return;
  await action(async () => {
    await saveAnswers();
    if (record.value)
      accept(
        await call<LearningRecord>(
          `/records/${key(record.value.id)}/conversation/reset`,
          "POST",
          { revision: record.value.revision },
        ),
      );
    attachmentIds.value = [];
    usage.value = null;
  });
}
async function save() {
  await action(async () => {
    await saveAnswers();
    success.value = t("Answers saved.");
  });
}
async function submit() {
  if (pendingUploads.value) return;
  if (!(await confirmAction(t("Submit your work for teacher review?")))) return;
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
async function checkContext() {
  const sequence = ++contextSequence;
  if (
    disposed ||
    !record.value ||
    !prompt.value.trim() ||
    record.value.conversationLimitReached
  ) {
    usage.value = null;
    checking.value = false;
    return;
  }
  checking.value = true;
  try {
    const value = await call<ContextUsage>(
      `/records/${key(record.value.id)}/context-budget`,
      "POST",
      {
        message: prompt.value,
        attachmentIds: attachmentIds.value,
        requestId: crypto.randomUUID(),
        revision: record.value.revision,
        answers: answers.value,
      },
    );
    if (sequence === contextSequence) usage.value = value;
  } catch {
    if (sequence === contextSequence) usage.value = null;
  } finally {
    if (sequence === contextSequence) checking.value = false;
  }
}
watch(
  [prompt, attachmentIds, answers],
  () => {
    clearTimeout(contextTimer);
    contextSequence++;
    checking.value = false;
    usage.value = null;
    contextTimer = setTimeout(() => void checkContext(), 500);
  },
  { deep: true },
);
async function chat() {
  if (!prompt.value.trim() || pendingUploads.value) return;
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
          attachmentIds: attachmentIds.value,
        },
      ),
    );
    prompt.value = "";
    attachmentIds.value = [];
    usage.value = record.value?.messages.at(-1)?.usage || null;
    await loadAttachments();
  });
}
function uploaded(material: Material) {
  attachments.value.push(material);
  attachmentIds.value.push(material.id);
  void loadAttachments();
}
async function retryAttachment(id: string) {
  await action(async () => {
    await call(`/materials/${key(id)}/retry`, "POST");
    await loadAttachments();
  });
}
async function removeAttachment(file: Material) {
  if (
    !(await confirmAction(
      t(
        "Remove this attachment? It will no longer be sent to the AI tutor. Previous messages will keep a removal notice.",
      ),
    ))
  )
    return;
  await action(async () => {
    await saveAnswers();
    if (!record.value) return;
    accept(
      await call<LearningRecord>(
        `/records/${key(record.value.id)}/attachments/${key(file.id)}?revision=${record.value.revision}`,
        "DELETE",
      ),
    );
    attachmentIds.value = attachmentIds.value.filter((id) => id !== file.id);
    usage.value = null;
    await loadAttachments();
    await checkContext();
  });
}
async function approve(requestId: string, text: string) {
  await action(async () => {
    if (record.value)
      accept(
        await call<LearningRecord>(
          `/records/${key(record.value.id)}/feedback/${key(requestId)}/approve`,
          "POST",
          { text },
        ),
      );
  });
}
onBeforeUnmount(() => {
  disposed = true;
  clearTimeout(timer);
  clearTimeout(contextTimer);
  contextSequence++;
  if (!props.preview) dirty.value = false;
});
void load();
</script>
<template>
  <div :class="{ 'simulation-workspace': preview }">
    <header v-if="!preview" class="page-heading">
      <div>
        <p class="eyebrow">
          {{ t(preview ? "TEACHER SIMULATION" : "YOUR LEARNING") }}
        </p>
        <h1 v-if="!preview">
          {{ workspace?.task.title || t("Learning task") }}
        </h1>
      </div>
      <span
        class="badge status-label"
        :data-status="record?.status || 'notStarted'"
        >{{ statusText(record?.status || "notStarted") }}</span
      >
    </header>
    <nav
      v-if="preview"
      class="preview-navigation"
      :aria-label="t('Student preview')"
    >
      <TRadioGroup
        v-model="previewPane"
        theme="button"
        variant="primary-filled"
        :options="[
          { value: 'lesson', label: t('Lesson and practice') },
          { value: 'chat', label: t('AI conversation') },
        ]"
      />
      <span
        class="badge status-label"
        :data-status="record?.status || 'notStarted'"
        >{{ statusText(record?.status || "notStarted") }}</span
      >
      <TButton
        theme="primary"
        variant="base"
        type="button"
        class="primary"
        :disabled="busy || pendingUploads > 0 || !workspace"
        @click="start"
      >
        {{ t(record ? "Start a new simulation" : "Start simulation") }}
      </TButton>
    </nav>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="success" class="success" role="status">{{ success }}</p>
    <div v-if="workspace" class="learning-layout">
      <section v-show="!preview || previewPane === 'lesson'" class="panel">
        <div v-if="!preview" class="row end">
          <TButton
            theme="default"
            variant="outline"
            type="button"
            :disabled="busy || !record"
            @click="exportTask"
          >
            {{ t("Export my learning result (Markdown)") }}
          </TButton>
        </div>
        <TaskContent
          :task="workspace.task"
          :answers="answers"
          :readonly="readonly || busy"
          @answer="(id, value) => (answers[id] = value)"
        />
        <div v-if="record || !preview" class="row wrap task-actions">
          <TButton
            theme="primary"
            variant="base"
            type="button"
            v-if="!record"
            class="primary"
            :disabled="busy"
            @click="start"
          >
            {{ t("Start learning") }}</TButton
          ><template v-else-if="!readonly"
            ><TButton
              theme="default"
              variant="outline"
              type="button"
              :disabled="busy || !changed"
              @click="save"
            >
              {{ t("Save answers") }}</TButton
            ><TButton
              theme="primary"
              variant="base"
              type="button"
              class="primary"
              :disabled="busy || pendingUploads > 0"
              @click="submit"
            >
              {{ t("Submit for review") }}
            </TButton></template
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
        <p v-if="pendingUploads" class="notice" role="status">
          {{
            t(
              "Wait for all uploads to finish before submitting or starting a new conversation.",
            )
          }}
        </p>
        <div v-if="record" class="student-attachments form-stack">
          <h3>{{ t("Your documents and images") }}</h3>
          <p class="muted">
            {{
              t("{0} / 100 attachments · {1} / {2} MiB", [
                attachments.length,
                (
                  attachments.reduce(
                    (total, file) => total + (file.fileSize || 0),
                    0,
                  ) / 1048576
                ).toFixed(1),
                ((record.attachmentMaxBytes || 524288000) / 1048576).toFixed(0),
              ])
            }}
          </p>
          <p class="muted">
            {{
              t(
                "Upload work for a question or select files for your next message. You can deselect a file while it is processing or remove it before submitting. Removed files are excluded from future AI context; previous messages keep a removal notice. Files are visible only within this learning record.",
              )
            }}
          </p>
          <template v-if="!readonly"
            ><label
              >{{ t("Attach to")
              }}<TSelect v-model="questionId">
                <TOption value="" :label="t('Conversation')" />
                <TOption
                  v-for="(q, index) in workspace.task.content.questions"
                  :key="q.id"
                  :value="q.id"
                  :label="t('Question {0}', [index + 1])"
                /> </TSelect></label
            ><FileUploader
              :key="record.id"
              :endpoint="`/records/${key(record.id)}/attachments`"
              :extra="{ questionId }"
              :folders="false"
              :disabled="busy"
              @pending="pendingUploads = $event"
              @uploaded="uploaded"
              @settled="loadAttachments"
          /></template>
          <TCheckboxGroup
            v-model="attachmentIds"
            class="student-attachment-list"
          >
            <div v-for="file in attachments" :key="file.id" class="check-label">
              <TCheckbox
                v-if="!readonly"
                :value="file.id"
                v-control-attrs="{
                  'aria-label': t('Select {0}', [file.title]),
                }"
                :disabled="
                  busy ||
                  (!attachmentIds.includes(file.id) &&
                    !['ready', 'needsReview'].includes(file.status))
                "
              /><a :href="fileUrl(file.id)" target="_blank" rel="noopener">{{
                file.title
              }}</a
              ><span class="status-label" :data-status="file.status">{{
                statusText(file.status)
              }}</span
              ><MaterialProgress :material="file" /><small
                v-if="file.questionId"
                >{{ t("Question attachment") }}</small
              ><TButton
                theme="default"
                variant="outline"
                v-if="
                  !readonly && ['incomplete', 'failed'].includes(file.status)
                "
                type="button"
                :disabled="busy"
                @click.prevent="retryAttachment(file.id)"
              >
                {{ t("Reprocess material") }}</TButton
              ><TButton
                theme="default"
                variant="outline"
                v-if="!readonly"
                type="button"
                :disabled="busy"
                @click.prevent="removeAttachment(file)"
              >
                {{ t("Remove attachment") }}
              </TButton>
            </div>
          </TCheckboxGroup>
        </div>
        <RecordHistory
          v-if="record"
          :record="record"
          :questions="workspace.task.content.questions"
          kind="answer"
        />
        <div v-if="record?.teacherNote" class="teacher-feedback">
          <h3>{{ t("Teacher feedback") }}</h3>
          <RichText :text="record.teacherNote" />
        </div>
      </section>
      <aside
        v-show="!preview || previewPane === 'chat'"
        class="panel tutor-panel"
      >
        <h2>{{ t("AI learning support") }}</h2>
        <p v-if="!record" class="empty">
          {{
            t(
              "Start this task to ask questions and save your learning progress.",
            )
          }}
        </p>
        <template v-else
          ><div class="chat-messages">
            <article
              v-for="(message, index) in record.messages"
              :key="index"
              :class="['message', message.role]"
            >
              <small>{{
                t(message.role === "user" ? "You" : "AI tutor")
              }}</small
              ><template v-if="message.pendingReview"
                ><p class="notice">
                  {{ t("AI feedback is awaiting teacher review.") }}
                </p>
                <template v-if="preview">
                  <TTextarea
                    v-control-attrs="{
                      rows: '6',
                      'aria-label': t('Review AI feedback'),
                    }"
                    :autosize="{ minRows: 6, maxRows: 10 }"
                    :value="
                      feedbackDrafts[message.requestId!] ?? message.content
                    "
                    :disabled="busy"
                    @change="
                      feedbackDrafts[message.requestId!] = String($event)
                    "
                  /><TButton
                    theme="default"
                    variant="outline"
                    type="button"
                    :disabled="busy"
                    @click="
                      approve(
                        message.requestId!,
                        feedbackDrafts[message.requestId!] ?? message.content,
                      )
                    "
                  >
                    {{ t("Approve and release feedback") }}
                  </TButton></template
                ></template
              ><RichText v-else :text="message.content" />
              <div v-for="id in message.attachmentIds || []" :key="id">
                <span v-if="record.removedAttachments?.[id]" class="muted">{{
                  t("Removed attachment: {0}", [record.removedAttachments[id]])
                }}</span>
                <a v-else :href="fileUrl(id)" target="_blank" rel="noopener">{{
                  attachments.find((a) => a.id === id)?.title || t("Attachment")
                }}</a>
              </div>
            </article>
          </div>
          <RecordHistory
            v-if="record"
            :record="record"
            :questions="workspace.task.content.questions"
            kind="conversation"
          />
          <TButton
            theme="default"
            variant="outline"
            type="button"
            v-if="!readonly"
            :disabled="busy || pendingUploads > 0 || awaiting"
            @click="resetConversation"
          >
            {{ t("Start a new conversation") }}
          </TButton>
          <RecordHistory
            v-if="record.messagesTruncated"
            :record="record"
            :questions="workspace.task.content.questions"
            kind="current"
          />
          <p v-if="record.conversationLimitReached" class="notice">
            {{
              t(
                "This conversation has reached its message limit. Start a new conversation to continue; your history will be kept.",
              )
            }}
          </p>
          <form v-if="!readonly" class="form-stack" @submit.prevent="chat">
            <TTextarea
              v-control-attrs="{
                rows: '3',
                'aria-label': t('Message to the AI tutor'),
              }"
              :autosize="{ minRows: 3, maxRows: 10 }"
              v-model="prompt"
              maxlength="10000"
              :disabled="busy || awaiting || record.conversationLimitReached"
              :placeholder="
                t('Ask about this task or describe where you are stuck.')
              "
            /><ContextMeter :usage="usage" :loading="checking" /><TButton
              theme="primary"
              variant="base"
              type="submit"
              class="primary"
              :disabled="
                busy ||
                pendingUploads > 0 ||
                awaiting ||
                record.conversationLimitReached ||
                !prompt.trim() ||
                usage?.materialsReady === false ||
                attachmentIds.some(
                  (id) =>
                    !attachments.some(
                      (f) =>
                        f.id === id &&
                        ['ready', 'needsReview'].includes(f.status),
                    ),
                )
              "
            >
              {{ t(busy ? "Thinking…" : "Send") }}
            </TButton>
          </form>
        </template>
      </aside>
    </div>
  </div>
</template>
