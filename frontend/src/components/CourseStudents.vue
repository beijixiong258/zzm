<script setup lang="ts">
import {
  Button as TButton,
  Input as TInput,
  RadioGroup as TRadioGroup,
  Table as TTable,
  MessagePlugin,
} from "tdesign-vue-next";
import { computed, onBeforeUnmount, ref, watch } from "vue";
import {
  call,
  key,
  type Course,
  type Member,
  type StudentInvitation,
} from "../classroom-api";
import { systemText, t } from "../i18n";
import AppDialog from "./AppDialog.vue";

const props = defineProps<{ course: Course }>();
const emit = defineEmits<{ close: [] }>();
const members = ref<Member[]>([]);
const loading = ref(false),
  adding = ref(false),
  membersError = ref(""),
  formError = ref("");
const addMode = ref("existing");
const account = ref("");
const student = ref({ name: "", username: "" });
const createdStudent = ref<StudentInvitation | null>(null);
let sequence = 0;
let disposed = false;
const activeMembers = computed(() =>
  members.value.filter(
    (member) => !member.membershipArchived && !member.archived,
  ),
);
const studentCount = computed(
  () =>
    activeMembers.value.filter((member) => member.membershipRole === "student")
      .length,
);
const columns = computed(() => [
  { colKey: "name", title: t("Name") },
  { colKey: "account", title: t("Username") + " / " + t("Email") },
  { colKey: "membershipRole", title: t("Role"), width: 100 },
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
  if (disposed || adding.value) return;
  adding.value = true;
  formError.value = "";
  try {
    if (addMode.value === "existing") {
      await call("/courses/" + key(props.course.id) + "/students", "POST", {
        account: account.value.trim(),
      });
      if (disposed) return;
      account.value = "";
      void MessagePlugin.success({
        content: t("Student added to this course."),
        duration: 4000,
        closeBtn: true,
      });
    } else {
      const result = await call<StudentInvitation>(
        "/courses/" + key(props.course.id) + "/student-invitations",
        "POST",
        {
          name: student.value.name.trim(),
          username: student.value.username.trim().toLowerCase(),
        },
      );
      if (disposed) return;
      createdStudent.value = result;
      student.value = { name: "", username: "" };
    }
    await refreshMembers();
  } catch (e) {
    if (!disposed) formError.value = systemText((e as Error).message);
  } finally {
    if (!disposed) adding.value = false;
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
function copyStudentSignIn() {
  const result = createdStudent.value;
  if (!result) return;
  void copyText(
    [
      t("Name") + ": " + result.name,
      t("Username") + ": " + result.username,
      t("Personal sign-in code") + ": " + result.invitationCode,
    ].join("\n"),
  );
}
watch(
  () => props.course.id,
  () => {
    members.value = [];
    createdStudent.value = null;
    void refreshMembers();
  },
  { immediate: true },
);
watch(addMode, () => (formError.value = ""));
onBeforeUnmount(() => {
  disposed = true;
  sequence++;
});
</script>

<template>
  <AppDialog
    :title="course.title + ' · ' + t('Student management')"
    :busy="adding"
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
        <TRadioGroup
          v-model="addMode"
          :disabled="adding"
          :options="[
            { value: 'existing', label: t('Add an existing student') },
            { value: 'new', label: t('Create a student account') },
          ]"
        />
        <form class="course-student-form" @submit.prevent="addStudent">
          <label v-if="addMode === 'existing'" class="student-account-field">
            {{ t("Student username or email") }}
            <TInput
              v-control-attrs="{
                required: true,
                'aria-label': t('Student username or email'),
              }"
              v-model="account"
              :disabled="adding"
              maxlength="254"
              @blur="account = account.trim()"
            />
          </label>
          <template v-else>
            <label>
              {{ t("Name") }}
              <TInput
                v-control-attrs="{ required: true, 'aria-label': t('Name') }"
                v-model="student.name"
                :disabled="adding"
                maxlength="100"
                @blur="student.name = student.name.trim()"
              />
            </label>
            <label>
              {{ t("Username") }}
              <TInput
                v-control-attrs="{
                  required: true,
                  pattern: '[A-Za-z0-9_.-]{3,64}',
                  'aria-label': t('Username'),
                  title: t(
                    'Use 3–64 letters, numbers, underscores, full stops or hyphens.',
                  ),
                }"
                v-model="student.username"
                :disabled="adding"
                maxlength="64"
                @blur="student.username = student.username.trim().toLowerCase()"
              />
            </label>
          </template>
          <TButton
            theme="primary"
            type="submit"
            :loading="adding"
            :disabled="adding"
          >
            {{
              t(
                addMode === "existing"
                  ? "Add student"
                  : "Create and add student",
              )
            }}
          </TButton>
        </form>
        <small v-if="addMode === 'new'" class="muted">
          {{
            t(
              "New students are added to this course automatically. Give them the username and personal sign-in code to sign in.",
            )
          }}
        </small>
        <p v-if="formError" class="error" role="alert">{{ formError }}</p>
      </section>
      <section
        v-if="createdStudent"
        class="student-sign-in-details"
        role="status"
      >
        <strong>
          {{ t("Student created and added to this course.") }}
          {{ createdStudent.name }}
        </strong>
        <div class="course-student-form">
          <label>
            {{ t("Username") }}
            <TInput
              v-control-attrs="{ 'aria-label': t('Username') }"
              :value="createdStudent.username"
              readonly
            />
          </label>
          <label>
            {{ t("Personal sign-in code") }}
            <TInput
              v-control-attrs="{ 'aria-label': t('Personal sign-in code') }"
              :value="createdStudent.invitationCode"
              readonly
            />
          </label>
          <TButton
            theme="default"
            variant="outline"
            type="button"
            @click="copyStudentSignIn"
          >
            {{ t("Copy sign-in details") }}
          </TButton>
        </div>
        <small class="muted">
          {{
            t(
              "This personal code is for signing in. The student has already joined this course.",
            )
          }}
        </small>
      </section>
      <section>
        <div class="row spread wrap">
          <h3>{{ t("Current course members") }}</h3>
          <div class="row">
            <small class="muted">{{
              t("Student count: {0}", [studentCount])
            }}</small>
            <TButton
              theme="default"
              variant="text"
              type="button"
              :loading="loading"
              :disabled="loading || adding"
              @click="refreshMembers"
            >
              {{ t("Refresh") }}
            </TButton>
          </div>
        </div>
        <p v-if="membersError" class="error" role="alert">{{ membersError }}</p>
        <TTable
          row-key="id"
          :data="activeMembers"
          :columns="columns"
          :loading="loading"
          :max-height="320"
          size="small"
        >
          <template #account="{ row }">
            {{ row.username || row.email || "—" }}
          </template>
          <template #membershipRole="{ row }">
            {{ t(row.membershipRole === "student" ? "Student" : "Teacher") }}
          </template>
        </TTable>
      </section>
    </div>
  </AppDialog>
</template>

<style scoped>
.course-students {
  display: grid;
  gap: 24px;
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
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto;
  align-items: end;
  gap: 12px;
  margin: 14px 0 8px;
}
.course-student-form label {
  min-width: 0;
}
.student-account-field {
  grid-column: span 2;
}
.student-sign-in-details {
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--soft);
}
@media (max-width: 650px) {
  .course-student-form {
    grid-template-columns: minmax(0, 1fr);
  }
  .student-account-field {
    grid-column: auto;
  }
  .course-student-form > .t-button {
    justify-self: start;
  }
}
</style>
