<script setup lang="ts">
import {
  Button as TButton,
  Input as TInput,
  Table as TTable,
  MessagePlugin,
} from "tdesign-vue-next";
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { call, key, type Course, type Member } from "../classroom-api";
import { confirmAction } from "../confirmAction";
import { systemText, t } from "../i18n";
import AppDialog from "./AppDialog.vue";

const props = defineProps<{ course: Course }>();
const emit = defineEmits<{ close: [] }>();
const members = ref<Member[]>([]);
const loading = ref(false),
  adding = ref(false),
  membersError = ref(""),
  formError = ref("");
const account = ref("");
const removingId = ref("");
const busy = computed(() => adding.value || !!removingId.value);
let sequence = 0;
let disposed = false;
const activeStudents = computed(() =>
  members.value.filter(
    (member) =>
      member.membershipRole === "student" &&
      !member.membershipArchived &&
      !member.archived,
  ),
);
const columns = computed(() => [
  { colKey: "name", title: t("Name"), width: "30%" },
  {
    colKey: "account",
    title: t("Username") + " / " + t("Email"),
    width: "40%",
  },
  { colKey: "actions", title: t("Actions"), width: "30%" },
]);

async function refreshMembers() {
  const requestSequence = ++sequence;
  loading.value = true;
  membersError.value = "";
  try {
    const result = await call<Member[]>(
      "/courses/" + key(props.course.id) + "/members",
    );
    if (!disposed && requestSequence === sequence) members.value = result;
  } catch (e) {
    if (!disposed && requestSequence === sequence)
      membersError.value = systemText((e as Error).message);
  } finally {
    if (!disposed && requestSequence === sequence) loading.value = false;
  }
}
async function addStudent() {
  if (disposed || busy.value || !account.value.trim()) return;
  const courseId = props.course.id;
  adding.value = true;
  formError.value = "";
  try {
    await call("/courses/" + key(courseId) + "/students", "POST", {
      account: account.value.trim(),
    });
    if (disposed || props.course.id !== courseId) return;
    account.value = "";
    void MessagePlugin.success({
      content: t("Student added to this course."),
      duration: 4000,
      closeBtn: true,
    });
    await refreshMembers();
  } catch (e) {
    if (!disposed && props.course.id === courseId)
      formError.value = systemText((e as Error).message);
  } finally {
    if (!disposed) adding.value = false;
  }
}
async function removeStudent(member: Member) {
  if (disposed || busy.value) return;
  const courseId = props.course.id;
  removingId.value = member.id;
  try {
    const confirmed = await confirmAction(
      t(
        "Remove {0} from this course? Their learning records, answers and conversations in this course will be deleted. Their account and other courses will be kept.",
        [member.name],
      ),
      {
        header: t("Remove student"),
        confirmLabel: t("Remove from course"),
        danger: true,
      },
    );
    if (!confirmed || disposed || props.course.id !== courseId) return;
    await call(
      `/courses/${key(courseId)}/students/${key(member.id)}`,
      "DELETE",
    );
    if (disposed || props.course.id !== courseId) return;
    members.value = members.value.filter((value) => value.id !== member.id);
    void MessagePlugin.success({
      content: t(
        "Student removed. Their learning records in this course have been deleted.",
      ),
      duration: 4000,
      closeBtn: true,
    });
    await refreshMembers();
  } catch (e) {
    if (!disposed && props.course.id === courseId)
      void MessagePlugin.error({
        content: systemText((e as Error).message),
        duration: 4000,
        closeBtn: true,
      });
  } finally {
    if (!disposed) removingId.value = "";
  }
}
async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    if (!disposed)
      void MessagePlugin.success({
        content: t("Copied."),
        duration: 4000,
        closeBtn: true,
      });
  } catch {
    if (!disposed)
      void MessagePlugin.error({
        content: t(
          "Could not copy automatically. Select and copy the information manually.",
        ),
        duration: 4000,
        closeBtn: true,
      });
  }
}
watch(
  () => props.course.id,
  () => {
    members.value = [];
    account.value = "";
    formError.value = "";
    void refreshMembers();
  },
  { immediate: true },
);
onBeforeUnmount(() => {
  disposed = true;
  sequence++;
});
</script>

<template>
  <AppDialog
    :title="course.title + ' · ' + t('Student management')"
    :busy="busy"
    wide
    @close="emit('close')"
  >
    <div class="course-students">
      <section>
        <div class="course-invitation-code">
          <label>
            {{ t("Course invitation code") }}
            <TInput
              v-control-attrs="{ 'aria-label': t('Course invitation code') }"
              :value="course.joinCode || ''"
              readonly
            />
          </label>
          <TButton
            theme="default"
            variant="outline"
            type="button"
            :disabled="!course.joinCode"
            @click="copyText(course.joinCode || '')"
          >
            {{ t("Copy code") }}
          </TButton>
        </div>
        <small class="muted">
          {{
            t(
              "Share this course invitation code with existing students. After signing in, they can use it on their home page to join this course.",
            )
          }}
        </small>
      </section>
      <section class="course-student-add">
        <h3>{{ t("Add student") }}</h3>
        <form class="course-student-form" @submit.prevent="addStudent">
          <label>
            {{ t("Student username or email") }}
            <TInput
              v-control-attrs="{
                required: true,
                'aria-label': t('Student username or email'),
              }"
              v-model="account"
              :disabled="busy"
              maxlength="254"
              @blur="account = account.trim()"
            />
          </label>
          <TButton
            theme="primary"
            type="submit"
            :loading="adding"
            :disabled="busy || !account.trim()"
          >
            {{ t("Add student") }}
          </TButton>
        </form>
        <small class="muted">
          {{
            t(
              "Enter an existing student's username or email to add them to this course. Account creation is managed by administrators.",
            )
          }}
        </small>
        <p v-if="formError" class="error" role="alert">{{ formError }}</p>
      </section>
      <section>
        <div class="row spread wrap">
          <h3>{{ t("Current students") }}</h3>
          <div class="row">
            <small class="muted">{{
              t("Student count: {0}", [activeStudents.length])
            }}</small>
            <TButton
              theme="default"
              variant="text"
              type="button"
              :loading="loading"
              :disabled="loading || busy"
              @click="refreshMembers"
            >
              {{ t("Refresh") }}
            </TButton>
          </div>
        </div>
        <p v-if="membersError" class="error" role="alert">{{ membersError }}</p>
        <TTable
          row-key="id"
          table-layout="fixed"
          :data="activeStudents"
          :columns="columns"
          :loading="loading"
          :max-height="320"
          size="small"
        >
          <template #account="{ row }">
            {{ row.username || row.email || "—" }}
          </template>
          <template #actions="{ row }">
            <TButton
              theme="danger"
              variant="text"
              type="button"
              :loading="removingId === row.id"
              :disabled="busy"
              @click="removeStudent(row)"
            >
              {{ t("Remove from course") }}
            </TButton>
          </template>
        </TTable>
      </section>
    </div>
  </AppDialog>
</template>

<style scoped>
.course-students {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 24px;
}
.course-students > section {
  min-width: 0;
}
.course-students :deep(th),
.course-students :deep(td) {
  white-space: normal;
  overflow-wrap: anywhere;
}
.course-students :deep(td .t-button) {
  padding-inline: 0;
}
.course-students h3 {
  margin: 0 0 12px;
}
.course-invitation-code {
  display: flex;
  align-items: flex-end;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 8px;
}
.course-invitation-code label {
  flex: 1;
  min-width: min(240px, 100%);
}
.course-student-add {
  padding-top: 18px;
  border-top: 1px solid var(--line);
}
.course-student-form {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: end;
  gap: 12px;
  margin: 14px 0 8px;
}
.course-student-form label {
  min-width: 0;
}
@media (max-width: 650px) {
  .course-student-form {
    grid-template-columns: minmax(0, 1fr);
  }
  .course-student-form > .t-button {
    justify-self: start;
  }
}
</style>
