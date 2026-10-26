<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from "vue";
import { call, type ChatMessage, type TeacherReply } from "../classroom-api";
import { locale, systemText, t } from "../i18n";
import RichText from "./RichText.vue";
import ContextMeter from "./ContextMeter.vue";
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
const end = ref<HTMLElement | null>(null);
let storageKey = "";
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
        /* The new key retains the history. */
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
onBeforeUnmount(persist);
async function send() {
  if (busy.value || props.disabled || !prompt.value.trim()) return;
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
  try {
    const response = await call<TeacherReply>("/teacher/assistant", "POST", {
      ...props.context,
      message,
      history: messages.value,
      locale: locale.value,
    });
    const outcome = await props.applyReply(response, message);
    messages.value.push(
      { role: "user", content: message },
      {
        role: "assistant",
        content: response.message + (outcome ? "\n\n" + outcome : ""),
        usage: response.usage,
      },
    );
    prompt.value = "";
    await nextTick();
    end.value?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  } catch (e) {
    error.value = systemText((e as Error).message);
  } finally {
    busy.value = false;
    emit("pending", false);
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
    <div
      class="teacher-transcript"
      role="log"
      :aria-label="t('Teaching conversation')"
    >
      <div v-if="!messages.length" class="conversation-welcome">
        <span class="conversation-mark" aria-hidden="true">✦</span>
        <h1>{{ t("What would you like to prepare?") }}</h1>
        <p>{{ welcome }}</p>
      </div>
      <article
        v-for="(message, index) in messages"
        :key="index"
        :class="['conversation-message', message.role]"
      >
        <small>{{ t(message.role === "user" ? "You" : "AI assistant") }}</small>
        <RichText :text="message.content" />
        <details v-if="message.usage" class="conversation-usage">
          <summary>{{ t("Usage and local estimate") }}</summary>
          <ContextMeter :usage="message.usage" />
        </details>
      </article>
      <p v-if="busy" role="status" class="muted">{{ t("Thinking…") }}</p>
      <div ref="end" />
    </div>
    <slot name="results" />
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div class="conversation-composer">
      <slot name="attachments" />
      <form @submit.prevent="send">
        <textarea
          v-model="prompt"
          rows="3"
          maxlength="10000"
          :disabled="busy || disabled"
          :aria-label="t('Message to the teaching assistant')"
          :placeholder="
            t('Describe what to create or change. AI will help configure it.')
          "
          @keydown.enter="enter"
        />
        <div class="row spread">
          <small class="muted">{{
            t("Enter to send · Shift+Enter for a new line")
          }}</small>
          <button
            class="primary"
            :disabled="busy || disabled || !prompt.trim()"
          >
            {{ t("Send") }} ↑
          </button>
        </div>
      </form>
    </div>
    <small class="conversation-footnote">{{
      t(
        "Conversation history is saved in this browser. Review AI-generated content before publishing.",
      )
    }}</small>
  </section>
</template>
