<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { t } from "../i18n";
import {
  call,
  dateText,
  fileUrl,
  key,
  type ChatMessage,
  type LearningRecord,
  type Question,
} from "../classroom-api";
import RichText from "./RichText.vue";

type Entry = {
  id: string;
  savedAt?: string;
  archivedAt?: string;
  revision?: number;
  answers?: Record<string, string>;
  messageCount?: number;
  title?: string;
  removedAt?: string;
  removedBy?: string;
  recycled?: boolean;
};
type HistoryPage<T> = {
  items: T[];
  page: number;
  size: number;
  total: number;
  hasMore: boolean;
  revision: number;
  removedAttachments?: Record<string, string>;
};
const props = defineProps<{
  record: LearningRecord;
  questions: Question[];
  kind: "answer" | "conversation" | "attachment" | "current";
}>();
const expanded = ref(false),
  loading = ref(false),
  error = ref("");
const entries = ref<HistoryPage<Entry> | null>(null);
const messages = ref<HistoryPage<ChatMessage> | null>(null);
const selected = ref("");
let sequence = 0;
const title = computed(() =>
  t(
    {
      answer: "Answer history",
      conversation: "Previous conversations",
      attachment: "Attachment removal log",
      current: "View the full current conversation",
    }[props.kind],
  ),
);
const removed = computed(() => ({
  ...props.record.removedAttachments,
  ...messages.value?.removedAttachments,
}));
watch(
  () => [props.record.id, props.record.revision],
  () => {
    sequence++;
    entries.value = null;
    messages.value = null;
    selected.value = "";
    error.value = "";
    loading.value = false;
    if (expanded.value) void load(1);
  },
);
async function load(page: number) {
  if (props.kind === "current") return loadMessages("current", page);
  const request = ++sequence;
  loading.value = true;
  error.value = "";
  try {
    const result = await call<HistoryPage<Entry>>(
      "/records/" +
        key(props.record.id) +
        "/history?kind=" +
        props.kind +
        "&page=" +
        page +
        "&size=" +
        (props.kind === "conversation" ? 10 : 20) +
        "&revision=" +
        props.record.revision,
    );
    if (request !== sequence) return;
    entries.value = result;
    messages.value = null;
    selected.value = "";
  } catch (e) {
    if (request === sequence) error.value = (e as Error).message;
  } finally {
    if (request === sequence) loading.value = false;
  }
}
async function loadMessages(id: string, page: number) {
  const request = ++sequence;
  loading.value = true;
  error.value = "";
  try {
    const result = await call<HistoryPage<ChatMessage>>(
      "/records/" +
        key(props.record.id) +
        "/history/" +
        key(id) +
        "/messages?page=" +
        page +
        "&size=50&revision=" +
        props.record.revision,
    );
    if (request !== sequence) return;
    selected.value = id;
    messages.value = result;
  } catch (e) {
    if (request === sequence) error.value = (e as Error).message;
  } finally {
    if (request === sequence) loading.value = false;
  }
}
function toggle(event: Event) {
  expanded.value = (event.target as HTMLDetailsElement).open;
  if (expanded.value && !entries.value && !messages.value && !loading.value)
    void load(1);
}
</script>
<template>
  <details class="record-history" @toggle="toggle">
    <summary>{{ title }}</summary>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="loading" class="muted">{{ t("Loading history…") }}</p>
    <template v-if="entries">
      <p v-if="!entries.total" class="muted">{{ t("No history yet.") }}</p>
      <section
        v-for="entry in entries.items"
        :key="entry.id"
        class="history-entry"
      >
        <template v-if="kind === 'answer'">
          <h4>{{ dateText(entry.savedAt) }}</h4>
          <div v-for="(answer, id) in entry.answers" :key="id">
            <small>{{
              t("Question {0}", [questions.findIndex((q) => q.id === id) + 1])
            }}</small>
            <RichText :text="answer" />
          </div>
        </template>
        <button
          v-else-if="kind === 'conversation'"
          type="button"
          :disabled="loading"
          :aria-expanded="selected === entry.id"
          @click="loadMessages(entry.id, 1)"
        >
          {{ dateText(entry.archivedAt) }} ·
          {{ t("{0} messages", [entry.messageCount || 0]) }}
        </button>
        <template v-else>
          <strong>{{ entry.title }}</strong>
          <p class="muted">
            {{ dateText(entry.removedAt) }} ·
            {{ entry.removedBy || t("Unknown account") }}
          </p>
          <small>{{
            t(
              entry.recycled
                ? "Moved to the recycle directory"
                : "Waiting for file recycling",
            )
          }}</small>
        </template>
      </section>
      <div v-if="entries.total > entries.size" class="history-pagination">
        <button
          type="button"
          :disabled="loading || entries.page <= 1"
          @click="load(entries.page - 1)"
        >
          {{ t("Previous page") }}
        </button>
        <small>{{
          t("Page {0} of {1}", [
            entries.page,
            Math.ceil(entries.total / entries.size),
          ])
        }}</small>
        <button
          type="button"
          :disabled="loading || !entries.hasMore"
          @click="load(entries.page + 1)"
        >
          {{ t("Next page") }}
        </button>
      </div>
    </template>
    <section v-if="messages" class="history-conversation">
      <h4>{{ t("Conversation history") }}</h4>
      <article
        v-for="(message, index) in messages.items"
        :key="index"
        :class="['message', message.role]"
      >
        <small
          >{{ t(message.role === "user" ? "Student" : "AI tutor") }} ·
          {{ dateText(message.createdAt) }}</small
        >
        <p v-if="message.pendingReview" class="notice">
          {{ t("AI feedback is awaiting teacher review.") }}
        </p>
        <RichText v-else :text="message.content" />
        <div v-for="id in message.attachmentIds || []" :key="id">
          <span v-if="removed[id]" class="muted">{{
            t("Removed attachment: {0}", [removed[id]])
          }}</span>
          <a v-else :href="fileUrl(id)" target="_blank" rel="noopener">{{
            t("Attachment")
          }}</a>
        </div>
      </article>
      <p v-if="!messages.total" class="muted">
        {{ t("No conversation yet.") }}
      </p>
      <div v-if="messages.total > messages.size" class="history-pagination">
        <button
          type="button"
          :disabled="loading || messages.page <= 1"
          @click="loadMessages(selected, messages.page - 1)"
        >
          {{ t("Previous page") }}
        </button>
        <small>{{
          t("Page {0} of {1}", [
            messages.page,
            Math.ceil(messages.total / messages.size),
          ])
        }}</small>
        <button
          type="button"
          :disabled="loading || !messages.hasMore"
          @click="loadMessages(selected, messages.page + 1)"
        >
          {{ t("Next page") }}
        </button>
      </div>
    </section>
  </details>
</template>
<style scoped>
.record-history {
  margin-top: 16px;
}
.record-history summary {
  cursor: pointer;
  font-weight: 600;
}
.history-entry {
  padding: 12px 0;
  border-bottom: 1px solid var(--line, #dce6de);
}
.history-entry p {
  margin: 4px 0;
}
.history-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 12px;
  flex-wrap: wrap;
}
.history-pagination button {
  min-height: 36px;
  padding: 6px 10px;
}
.history-conversation {
  margin-top: 16px;
}
</style>
