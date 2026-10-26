<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import {
  call,
  key,
  type Course,
  type Member,
  type TeacherReply,
} from "../classroom-api";
import { systemText, t } from "../i18n";
import {
  courses,
  dirty,
  navigate,
  refreshCourses,
  retainCourseAddress,
  tasks,
  user,
} from "../classroom-state";
import TeacherConversation from "../components/TeacherConversation.vue";
const props = defineProps<{ courseId?: string }>();
const currentId = ref(props.courseId || "");
const existing = courses.value.find((course) => course.id === currentId.value);
const form = ref({
  title: existing?.title || "",
  code: existing?.code || "",
  description: existing?.description || "",
  courseInformation: existing?.courseInformation || existing?.description || "",
  studentProfile: existing?.studentProfile || "",
  systemInstructions: existing?.systemInstructions || "",
});
const members = ref<Member[] | null>(null),
  chatting = ref(false),
  saving = ref(false),
  saved = ref(false),
  error = ref("");
let savedConfiguration = JSON.stringify(form.value);
watch(
  form,
  () => {
    dirty.value = JSON.stringify(form.value) !== savedConfiguration;
    saved.value = false;
    error.value = "";
  },
  { deep: true, flush: "sync" },
);
onBeforeUnmount(() => {
  dirty.value = false;
});
const conversationKey = computed(
  () => `${user.value?.id}:course:${currentId.value || "new"}`,
);
const courseTasks = computed(() =>
  (tasks.value[currentId.value] || []).filter((task) => !task.archived),
);
async function saveCourse() {
  const course = await call<Course>(
    currentId.value ? "/courses/" + key(currentId.value) : "/courses",
    currentId.value ? "PUT" : "POST",
    form.value,
  );
  currentId.value = course.id;
  savedConfiguration = JSON.stringify(form.value);
  dirty.value = false;
  retainCourseAddress(course.id);
  await refreshCourses();
}
async function save() {
  saving.value = true;
  saved.value = false;
  error.value = "";
  try {
    await saveCourse();
    saved.value = true;
  } catch (e) {
    error.value = systemText((e as Error).message);
  } finally {
    saving.value = false;
  }
}
async function configure(reply: TeacherReply) {
  const courseFields = Object.keys(form.value) as (keyof typeof form.value)[];
  const changed = courseFields.filter((name) =>
    Object.hasOwn(reply.fields, name),
  );
  for (const name of changed) form.value[name] = reply.fields[name];
  let outcome = "";
  if (changed.length) {
    if (!form.value.title.trim() || !form.value.code.trim()) {
      outcome = t(
        "The course draft is retained here. Provide a course name and code to save it.",
      );
    } else {
      await saveCourse();
      outcome = t("Course configuration saved.");
    }
  }
  if (
    [
      "newTask",
      "members",
      "progress",
      "inviteStudent",
      "files",
      "selectFiles",
    ].includes(reply.action) &&
    !currentId.value
  )
    return (
      outcome +
      "\n" +
      t("Create the course first by telling AI its name and code.")
    );
  if (reply.action === "members") {
    members.value = await call<Member[]>(
      `/courses/${key(currentId.value)}/members`,
    );
    outcome += "\n" + t("The current class members are shown below.");
  } else if (reply.action === "inviteStudent") {
    if (
      !reply.fields.studentName?.trim() ||
      !reply.fields.studentUsername?.trim()
    )
      return (
        outcome +
        "\n" +
        t("Provide the student's name and a username for the invitation.")
      );
    const result = await call<{ invitationCode: string }>(
      `/courses/${key(currentId.value)}/student-invitations`,
      "POST",
      {
        name: reply.fields.studentName,
        username: reply.fields.studentUsername,
      },
    );
    outcome +=
      "\n" +
      t(
        "Student invitation created. Username: {0}; personal invitation code: {1}.",
        [reply.fields.studentUsername, result.invitationCode],
      );
    members.value = await call<Member[]>(
      `/courses/${key(currentId.value)}/members`,
    );
  } else if (reply.action === "newTask")
    outcome +=
      "\n" + t("Use New task conversation below to configure the task.");
  else if (reply.action === "progress")
    outcome +=
      "\n" + t("Open a task conversation to view its student progress.");
  else if (["files", "selectFiles"].includes(reply.action))
    outcome +=
      "\n" + t("Use File management below to organize the course materials.");
  return outcome.trim();
}
</script>
<template>
  <div class="teacher-chat-page">
    <header class="conversation-heading">
      <div>
        <p class="eyebrow">{{ t("Teaching conversation") }}</p>
        <strong>{{ form.title || t("New course conversation") }}</strong>
      </div>
      <button
        v-if="currentId"
        :disabled="chatting || saving"
        @click="navigate({ page: 'materials', courseId: currentId })"
      >
        {{ t("File management") }}
      </button>
    </header>
    <TeacherConversation
      :conversation-key="conversationKey"
      :context="{
        scope: 'course',
        courseId: currentId || null,
        courseDraft: form,
      }"
      :apply-reply="configure"
      :disabled="saving"
      @pending="chatting = $event"
      :welcome="
        t(
          'Tell me the course you want to create, who the students are, and what you want them to learn. We can configure it together.',
        )
      "
    >
      <template #results>
        <section class="conversation-result">
          <strong>{{ t("Current course configuration") }}</strong>
          <p class="muted">
            {{
              t(
                "Edit these fields directly, or describe changes in the conversation.",
              )
            }}
          </p>
          <form @submit.prevent="save">
            <fieldset :disabled="chatting || saving">
              <dl class="configuration-summary">
                <dt>
                  <label for="course-title">{{ t("Course name") }}</label>
                </dt>
                <dd>
                  <input
                    id="course-title"
                    v-model.trim="form.title"
                    maxlength="300"
                    required
                  />
                </dd>
                <dt>
                  <label for="course-code">{{ t("Course code") }}</label>
                </dt>
                <dd>
                  <input
                    id="course-code"
                    v-model.trim="form.code"
                    maxlength="100"
                    required
                  />
                </dd>
                <dt>
                  <label for="course-information">{{
                    t("Course information")
                  }}</label>
                </dt>
                <dd>
                  <textarea
                    id="course-information"
                    v-model="form.courseInformation"
                    rows="3"
                    maxlength="20000"
                  />
                </dd>
                <dt>
                  <label for="course-student-profile">{{
                    t("Student profile")
                  }}</label>
                </dt>
                <dd>
                  <textarea
                    id="course-student-profile"
                    v-model="form.studentProfile"
                    rows="3"
                    maxlength="20000"
                  />
                </dd>
                <dt>
                  <label for="course-instructions">{{
                    t("Course instructions")
                  }}</label>
                </dt>
                <dd>
                  <textarea
                    id="course-instructions"
                    v-model="form.systemInstructions"
                    rows="3"
                    maxlength="20000"
                  />
                </dd>
              </dl>
              <div class="row wrap end configuration-actions">
                <button class="primary" type="submit">
                  {{ t(saving ? "Saving…" : "Save course configuration") }}
                </button>
                <template v-if="currentId">
                  <button
                    type="button"
                    @click="navigate({ page: 'task', courseId: currentId })"
                  >
                    ＋ {{ t("New task conversation") }}
                  </button>
                  <button
                    type="button"
                    @click="
                      navigate({ page: 'materials', courseId: currentId })
                    "
                  >
                    {{ t("File management") }}
                  </button>
                </template>
              </div>
            </fieldset>
            <p v-if="saved" class="success" role="status">
              {{ t("Course configuration saved.") }}
            </p>
            <p v-if="error" class="error" role="alert">{{ error }}</p>
          </form>
          <div v-if="courseTasks.length" class="conversation-task-links">
            <button
              v-for="task in courseTasks"
              :key="task.id"
              :disabled="chatting || saving"
              @click="
                navigate({ page: 'task', courseId: currentId, taskId: task.id })
              "
            >
              {{ task.title }} →
            </button>
          </div>
        </section>
        <section v-if="members" class="conversation-result">
          <strong>{{ t("Class members") }}</strong>
          <p v-for="member in members" :key="member.id">
            {{ member.name }} · {{ member.username || member.email }} ·
            {{ t(member.role === "student" ? "Student" : "Teacher") }}
          </p>
          <p v-if="!members.length" class="muted">
            {{ t("No students have joined this course yet.") }}
          </p>
        </section>
      </template>
    </TeacherConversation>
  </div>
</template>
