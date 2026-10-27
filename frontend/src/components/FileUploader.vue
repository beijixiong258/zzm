<script setup lang="ts">
import { Button as TButton } from "tdesign-vue-next";
import { ref, watch } from "vue";
import { t } from "../i18n";
import { upload, type Material } from "../classroom-api";
import ProgressStatus from "./ProgressStatus.vue";
const props = withDefaults(
  defineProps<{
    endpoint: string;
    folders?: boolean;
    extra?: Record<string, string>;
    visibility?: "student" | "teacher";
    disabled?: boolean;
  }>(),
  { folders: true, visibility: "student" },
);
const emit = defineEmits<{
  uploaded: [material: Material];
  settled: [];
  pending: [count: number];
}>();
type Upload = {
  id: string;
  file: File;
  endpoint: string;
  extra: Record<string, string>;
  visibility: "student" | "teacher";
  status: "queued" | "uploading" | "done" | "failed";
  error: string;
  progress: number;
};
const queue = ref<Upload[]>([]);
const fileInput = ref<HTMLInputElement | null>(null);
const folderInput = ref<HTMLInputElement | null>(null);
watch(
  queue,
  () =>
    emit(
      "pending",
      queue.value.filter((item) =>
        ["queued", "uploading"].includes(item.status),
      ).length,
    ),
  { deep: true, flush: "sync" },
);
let active = 0;
function choose(event: Event) {
  if (props.disabled) return;
  const input = event.target as HTMLInputElement;
  for (const file of Array.from(input.files || []))
    queue.value.push({
      id: crypto.randomUUID(),
      file,
      endpoint: props.endpoint,
      extra: { ...props.extra },
      visibility: props.visibility,
      status: "queued",
      error: "",
      progress: 0,
    });
  input.value = "";
  pump();
}
function retry(item: Upload) {
  if (props.disabled) return;
  item.status = "queued";
  item.error = "";
  item.progress = 0;
  pump();
}
function pump() {
  while (active < 3) {
    const item = queue.value.find((entry) => entry.status === "queued");
    if (!item) return;
    item.status = "uploading";
    active++;
    void send(item).finally(() => {
      active--;
      emit("settled");
      pump();
    });
  }
}
async function send(item: Upload) {
  try {
    if (item.file.size > 25 * 1024 * 1024)
      throw Error(t("Each file must be 25 MiB or smaller."));
    const body = new FormData();
    body.set("file", item.file);
    body.set("relativePath", item.file.webkitRelativePath || item.file.name);
    Object.entries(item.extra).forEach(([key, value]) => body.set(key, value));
    body.set("visibility", item.visibility);
    const material = await upload<Material>(item.endpoint, body, (value) => {
      item.progress = value;
    });
    item.progress = 100;
    item.status = "done";
    emit("uploaded", material);
  } catch (error) {
    item.status = "failed";
    item.error = (error as Error).message;
  }
}
</script>
<template>
  <div class="file-uploader">
    <div class="row wrap">
      <TButton
        theme="default"
        variant="outline"
        :disabled="disabled"
        @click="fileInput?.click()"
      >
        ＋ {{ t("Upload files") }}
      </TButton>
      <input
        ref="fileInput"
        type="file"
        multiple
        hidden
        :disabled="disabled"
        accept=".pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.txt,.md,.png,.jpg,.jpeg,.webp,.epub"
        @change="choose"
      />
      <TButton
        v-if="folders"
        theme="default"
        variant="outline"
        :disabled="disabled"
        @click="folderInput?.click()"
      >
        ＋ {{ t("Upload folder") }}
      </TButton>
      <input
        v-if="folders"
        ref="folderInput"
        type="file"
        multiple
        webkitdirectory
        hidden
        :disabled="disabled"
        @change="choose"
      />
      <slot name="actions" />
    </div>
    <p class="muted">
      {{
        t(
          "Up to three files upload at once. Document processing continues in the background.",
        )
      }}
    </p>
    <ul v-if="queue.length" class="upload-queue" aria-live="polite">
      <li v-for="item in queue" :key="item.id">
        <span>{{ item.file.name }}</span
        ><small>{{
          t(
            {
              queued: "Queued",
              uploading: "Uploading",
              done: "Uploaded",
              failed: "Failed",
            }[item.status],
          )
        }}</small>
        <ProgressStatus
          v-if="item.status === 'uploading'"
          :label="t(item.progress >= 100 ? 'Saving upload…' : 'Uploading')"
          :value="item.progress >= 100 ? null : item.progress"
        />
        <span v-if="item.error" class="error">{{ item.error }}</span
        ><TButton
          theme="default"
          variant="outline"
          v-if="item.status === 'failed'"
          type="button"
          :disabled="disabled"
          @click="retry(item)"
        >
          {{ t("Retry") }}
        </TButton>
      </li>
    </ul>
  </div>
</template>
