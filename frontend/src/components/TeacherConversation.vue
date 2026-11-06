<script setup lang="ts">
import { Textarea as TTextarea, Button as TButton } from "tdesign-vue-next";
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { call, type ChatMessage, type TeacherReply } from "../classroom-api";
import { locale, systemText, t } from "../i18n";
import RichText from "./RichText.vue";
import ContextMeter from "./ContextMeter.vue";
import ProgressStatus from "./ProgressStatus.vue";
const props = defineProps<{
  conversationKey: string;
  context: Record<string, unknown>;
  applyReply: (reply: TeacherReply, message: string) => Promise<string | void>;
  disabled?: boolean;
  welcome: string;
}>();
const emit = defineEmits<{ pending: [value: boolean] }>();
const messages = ref<ChatMessage[]>([]),
  prompt = ref(""),
  busy = ref(false),
  error = ref("");
const replyProgress = ref<number | null>(null);
const transcript = ref<HTMLElement | null>(null);
let storageKey = "";
let disposed = false;
let request: AbortController | undefined;
let progressTimer: ReturnType<typeof setInterval> | undefined;
let progressDismissal: ReturnType<typeof setTimeout> | undefined;
function finishReplyProgress(completed = false) {
  clearInterval(progressTimer);
  clearTimeout(progressDismissal);
  progressTimer = undefined;
  progressDismissal = undefined;
  replyProgress.value = completed ? 100 : null;
  if (completed) {
    progressDismissal = setTimeout(() => {
      replyProgress.value = null;
      progressDismissal = undefined;
    }, 450);
  }
}
function startReplyProgress() {
  finishReplyProgress();
  replyProgress.value = 8;
  const startedAt = performance.now();
  progressTimer = setInterval(() => {
    // 等待进度仅作视觉反馈，真实回复应用完成后才显示 100%。
    replyProgress.value =
      8 + 87 * (1 - Math.exp(-(performance.now() - startedAt) / 45000));
  }, 1000);
  void nextTick(() => scrollToLatest("smooth"));
}
function scrollToLatest(behavior: ScrollBehavior = "auto") {
  transcript.value?.scrollTo({
    top: transcript.value.scrollHeight,
    behavior,
  });
}
function persist() {
  if (!storageKey) return;
  try {
    localStorage.setItem(
      storageKey,
      JSON.stringify({ messages: messages.value, prompt: prompt.value }),
    );
  } catch {
    error.value = t(
      "This browser could not retain the conversation. Keep this page open.",
    );
  }
}
watch(
  () => props.conversationKey,
  (value, previous) => {
    persist();
    storageKey = "aicademiya.teacher-chat." + value;
    if (previous?.endsWith(":new") && !value.endsWith(":new")) {
      persist();
      try {
        localStorage.removeItem("aicademiya.teacher-chat." + previous);
      } catch {
        /* 历史记录已保存在新的存储键下。 */
      }
      return;
    }
    messages.value = [];
    prompt.value = "";
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey) || "null") as {
        messages: ChatMessage[];
        prompt: string;
      } | null;
      if (saved) {
        messages.value = saved.messages;
        prompt.value = saved.prompt;
      }
    } catch {
      error.value = t("The saved conversation could not be read.");
    }
  },
  { immediate: true },
);
watch([messages, prompt], persist, { deep: true });
onMounted(() => scrollToLatest());
onBeforeUnmount(() => {
  disposed = true;
  request?.abort();
  finishReplyProgress();
  persist();
});
async function send() {
  if (disposed || busy.value || props.disabled || !prompt.value.trim()) return;
  if (messages.value.length >= 1000) {
    error.value = t(
      "This conversation has reached its message limit. Start a new conversation to continue; your history will be kept.",
    );
    return;
  }
  const message = prompt.value.trim();
  busy.value = true;
  emit("pending", true);
  error.value = "";
  startReplyProgress();
  request = new AbortController();
  try {
    const response = await call<TeacherReply>(
      "/teacher/assistant",
      "POST",
      {
        ...props.context,
        message,
        history: messages.value,
        locale: locale.value,
      },
      request.signal,
    );
    if (disposed) return;
    const outcome = await props.applyReply(response, message);
    if (disposed) return;
    messages.value.push(
      { role: "user", content: message },
      {
        role: "assistant",
        content: response.message + (outcome ? "\n\n" + outcome : ""),
        usage: response.usage,
      },
    );
    prompt.value = "";
    finishReplyProgress(true);
    await nextTick();
    scrollToLatest("smooth");
  } catch (e) {
    finishReplyProgress();
    if (!disposed) error.value = systemText((e as Error).message);
  } finally {
    request = undefined;
    busy.value = false;
    if (!disposed) emit("pending", false);
  }
}
function enter(event: KeyboardEvent) {
  if (!event.shiftKey && !event.isComposing) {
    event.preventDefault();
    void send();
  }
}
</script>
<template>
  <section class="teacher-conversation">
    <slot name="results" />
    <div class="conversation-panel">
      <div
        ref="transcript"
        class="teacher-transcript"
        role="log"
        tabindex="0"
        :aria-label="t('Teaching conversation')"
      >
        <div v-if="!messages.length" class="conversation-welcome">
          <strong>{{ t("Course assistant") }}</strong>
          <p>{{ welcome }}</p>
        </div>
        <article
          v-for="(message, index) in messages"
          :key="index"
          :class="['conversation-message', message.role]"
        >
          <small>{{
            t(message.role === "user" ? "You" : "AI assistant")
          }}</small>
          <RichText :text="message.content" />
          <details v-if="message.usage" class="conversation-usage">
            <summary>{{ t("Usage and local estimate") }}</summary>
            <ContextMeter :usage="message.usage" />
          </details>
        </article>
        <ProgressStatus
          v-if="replyProgress != null"
          class="conversation-progress"
          :class="{ 'is-complete': replyProgress === 100 }"
          :label="t(replyProgress === 100 ? 'Completed' : 'Thinking…')"
          :value="replyProgress"
          :active="busy && replyProgress < 100"
        />
      </div>
      <p v-if="error" class="error" role="alert">{{ systemText(error) }}</p>
      <div class="conversation-composer">
        <form @submit.prevent="send">
          <TTextarea
            v-control-attrs="{
              rows: '2',
              'aria-label': t('Message to the teaching assistant'),
            }"
            :autosize="{ minRows: 2, maxRows: 8 }"
            v-model="prompt"
            maxlength="10000"
            :disabled="busy || disabled"
            :placeholder="
              t('Describe what to create or change. AI will help configure it.')
            "
            @keydown="(_, { e }) => e.key === 'Enter' && enter(e)"
          />
          <div class="row spread">
            <small class="muted">{{
              t("Enter to send · Shift+Enter for a new line")
            }}</small>
            <TButton
              theme="primary"
              variant="base"
              type="submit"
              class="primary"
              :disabled="busy || disabled || !prompt.trim()"
            >
              {{ t("Send") }} ↑
            </TButton>
          </div>
        </form>
      </div>
    </div>
    <small class="conversation-footnote">{{
      t(
        "Conversation history is saved in this browser. Review AI-generated content before publishing.",
      )
    }}</small>
  </section>
</template>
<style scoped>
.conversation-progress {
  margin: 16px 0 4px;
}
.conversation-progress :deep(.t-progress) {
  margin-top: 8px;
}
.conversation-progress :deep(.t-progress__inner) {
  transition: width 1s linear;
}
.conversation-progress.is-complete :deep(.t-progress__inner) {
  transition-duration: 0.2s;
}
@media (prefers-reduced-motion: reduce) {
  .conversation-progress :deep(.t-progress__inner::before) {
    animation: none;
  }
}
</style>
