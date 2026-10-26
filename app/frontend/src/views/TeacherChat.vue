<script setup lang="ts">
import { computed, ref } from "vue";
import {
  call,
  key,
  type Course,
  type Member,
  type TeacherReply,
} from "../classroom-api";
import { t } from "../i18n";
import {
  courses,
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
  courseInformation: existing?.courseInformation || "",
  studentProfile: existing?.studentProfile || "",
  systemInstructions: existing?.systemInstructions || "",
});
const members = ref<Member[] | null>(null),
  chatting = ref(false);
const conversationKey = computed(
  () => `${user.value?.id}:course:${currentId.value || "new"}`,
);
const courseTasks = computed(() =>
  (tasks.value[currentId.value] || []).filter((task) => !task.archived),
);
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
      const course = await call<Course>(
        currentId.value ? `/courses/${key(currentId.value)}` : "/courses",
        currentId.value ? "PUT" : "POST",
        form.value,
      );
      currentId.value = course.id;
      retainCourseAddress(course.id);
      await refreshCourses();
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
        :disabled="chatting"
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
      @pending="chatting = $event"
      :welcome="
        t(
          'Tell me the course you want to create, who the students are, and what you want them to learn. We can configure it together.',
        )
      "
    >
      <template #results>
        <section v-if="form.title || currentId" class="conversation-result">
          <strong>{{ t("Current course configuration") }}</strong>
          <dl class="configuration-summary">
            <dt>{{ t("Course name") }}</dt>
            <dd>{{ form.title || "—" }}</dd>
            <dt>{{ t("Course code") }}</dt>
            <dd>{{ form.code || "—" }}</dd>
            <dt>{{ t("Course information") }}</dt>
            <dd>{{ form.courseInformation || form.description || "—" }}</dd>
            <dt>{{ t("Student profile") }}</dt>
            <dd>{{ form.studentProfile || "—" }}</dd>
            <dt>{{ t("Course instructions") }}</dt>
            <dd>{{ form.systemInstructions || "—" }}</dd>
          </dl>
          <div v-if="currentId" class="row wrap">
            <button
              class="primary"
              :disabled="chatting"
              @click="navigate({ page: 'task', courseId: currentId })"
            >
              ＋ {{ t("New task conversation") }}
            </button>
            <button
              :disabled="chatting"
              @click="navigate({ page: 'materials', courseId: currentId })"
            >
              {{ t("File management") }}
            </button>
          </div>
          <div v-if="courseTasks.length" class="conversation-task-links">
            <button
              v-for="task in courseTasks"
              :key="task.id"
              :disabled="chatting"
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
