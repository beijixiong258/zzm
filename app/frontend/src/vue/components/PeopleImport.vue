<script setup lang="ts">
import { computed, ref, watch, onBeforeUnmount } from "vue";
import { api } from "../../api";
import { accountApi } from "../../account-management-api";
import type { Role, RosterPreview } from "../../types";
import type { AccountImportPreview } from "../../account-management-types";
import { useTask } from "../state";
import FeedbackNotice from "./FeedbackNotice.vue";
const props = defineProps<{ courseId?: string }>();
const emit = defineEmits<{ changed: []; hold: [boolean]; dirty: [boolean] }>();
const file = ref<File | null>(null),
  password = ref(""),
  role = ref<Role>("student"),
  preview = ref<RosterPreview | AccountImportPreview | null>(null),
  committed = ref(false);
const { busy, error, success, run } = useTask();
const valid = computed(
  () => !!preview.value && preview.value.error_count === 0 && !committed.value,
);
watch(busy, (v) => emit("hold", v));
watch(
  [file, password, preview, committed],
  () =>
    emit(
      "dirty",
      !committed.value && (!!file.value || !!password.value || !!preview.value),
    ),
  { immediate: true },
);
onBeforeUnmount(() => {
  emit("hold", false);
  emit("dirty", false);
});
async function inspect() {
  if (!file.value) return;
  await run(async () => {
    preview.value = props.courseId
      ? await api.rosterPreview(props.courseId, file.value!, password.value)
      : await accountApi.preview(file.value!, role.value, password.value);
  });
}
async function commit() {
  if (!preview.value || !valid.value) return;
  emit("hold", true);
  try {
    await run(async () => {
      if (props.courseId) {
        const r = await api.rosterCommit(
          props.courseId,
          preview.value!.import_id,
        );
        await api.roster(props.courseId);
        success.value = `${r.created} created, ${r.enrolled} enrolled, ${r.restored} restored.`;
      } else {
        try {
          await accountApi.commit(preview.value!.import_id);
        } catch (e) {
          const state = await accountApi.importState(preview.value!.import_id);
          if (state.status !== "committed") throw e;
        }
        await accountApi.list();
      }
      committed.value = true;
      password.value = "";
      emit("changed");
    }, "Import complete.");
  } finally {
    emit("hold", false);
  }
}
</script>
<template>
  <FeedbackNotice :error="error" :success="success" :busy="busy" />
  <form v-if="!preview" class="form-stack" @submit.prevent="inspect">
    <p>
      CSV or XLSX with name and email columns. Review the rows before importing.
    </p>
    <label
      >File<input
        type="file"
        accept=".csv,.xlsx"
        required
        @change="
          file = ($event.target as HTMLInputElement).files?.[0] || null
        " /></label
    ><label v-if="!courseId"
      >Default role<select v-model="role">
        <option value="student">Student</option>
        <option value="teacher">Teacher</option>
        <option value="admin">Administrator</option>
      </select></label
    ><label
      >Default temporary password<input
        v-model="password"
        type="password"
        autocomplete="new-password"
      /><small
        >Required for new accounts unless each row includes temporary_password.
        Use at least 8 characters with letters and numbers.</small
      ></label
    ><button class="primary" :disabled="busy || !file">Review import</button>
  </form>
  <template v-else
    ><p>
      {{ preview.valid_count }} valid rows · {{ preview.error_count }} errors
    </p>
    <div class="import-rows">
      <div
        v-for="row in preview.rows"
        :key="row.row_number"
        class="upload-result"
      >
        <strong>{{ row.name }} · {{ row.email }}</strong
        ><span class="badge">{{ row.action }}</span>
        <p v-for="message in [...row.errors, ...row.warnings]" :key="message">
          {{ message }}
        </p>
      </div>
    </div>
    <div class="actions">
      <button
        class="secondary"
        :disabled="busy"
        @click="
          preview = null;
          committed = false;
        "
      >
        Choose another file</button
      ><button class="primary" :disabled="busy || !valid" @click="commit">
        {{ committed ? "Imported" : "Confirm import" }}
      </button>
    </div></template
  >
</template>
