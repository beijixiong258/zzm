<script setup lang="ts">
import {
  Button as TButton,
  Input as TInput,
  Textarea as TTextarea,
} from "tdesign-vue-next";
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { Save } from "lucide-vue-next";
import { call, key, type Course, type TeacherReply } from "../classroom-api";
import { systemText, t } from "../i18n";
import {
  courses,
  dirty,
  navigate,
  refreshCourses,
  retainCourseAddress,
  user,
} from "../classroom-state";
import TeacherConversation from "../components/TeacherConversation.vue";
import CourseStudents from "../components/CourseStudents.vue";
const props = defineProps<{ courseId?: string }>();
const currentId = ref(props.courseId || "");
const existing = courses.value.find((course) => course.id === currentId.value);
const currentCourse = computed(() =>
  courses.value.find((course) => course.id === currentId.value),
);
const form = ref({
  title: existing?.title || "",
  code: existing?.code || "",
  description: existing?.description || "",
  courseInformation: existing?.courseInformation || existing?.description || "",
  studentProfile: existing?.studentProfile || "",
  systemInstructions: existing?.systemInstructions || "",
});
const showStudents = ref(false),
  chatting = ref(false),
  saving = ref(false),
  saved = ref(false),
  error = ref("");
let savedConfiguration = JSON.stringify(form.value);
let disposed = false;
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
  disposed = true;
  dirty.value = false;
});
const conversationKey = computed(
  () => `${user.value?.id}:course:${currentId.value || "new"}`,
);
async function saveCourse() {
  if (disposed) return;
  const course = await call<Course>(
    currentId.value ? "/courses/" + key(currentId.value) : "/courses",
    currentId.value ? "PUT" : "POST",
    form.value,
  );
  if (disposed) return;
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
  if (disposed) return;
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
      if (disposed) return;
      outcome = t("Course information saved.");
    }
  }
  if (
    ["newTask", "members", "progress", "files", "selectFiles"].includes(
      reply.action,
    ) &&
    !currentId.value
  )
    return outcome + "\n" + t("Save a course name and code before continuing.");
  if (reply.action === "members") {
    showStudents.value = true;
    outcome += "\n" + t("The current class members are shown below.");
  } else if (reply.action === "newTask")
    outcome +=
      "\n" +
      t(
        dirty.value
          ? "Save the course information before creating a task."
          : "Use Create task in the course header to upload materials and generate a lesson.",
      );
  else if (reply.action === "progress")
    outcome += "\n" + t("Open a task to view its student progress.");
  else if (["files", "selectFiles"].includes(reply.action))
    outcome +=
      "\n" +
      t("Use Course materials in the sidebar to organize this course's files.");
  return outcome.trim();
}
</script>
<template>
  <div class="teacher-chat-page course-editor-page">
    <section class="course-editor-card">
      <header class="conversation-heading course-editor-heading">
        <div>
          <p class="eyebrow">
            {{ t(currentId ? "Course information" : "New course") }}
          </p>
          <h1>{{ form.title || t("Course basics") }}</h1>
        </div>
        <div class="row wrap course-editor-actions">
          <TButton
            v-if="currentCourse"
            theme="default"
            variant="outline"
            type="button"
            :disabled="chatting || saving"
            @click="showStudents = true"
          >
            {{ t("Student management") }}
          </TButton>
          <TButton
            v-if="currentId"
            theme="primary"
            variant="base"
            type="button"
            class="primary"
            :disabled="chatting || saving || dirty"
            :title="
              dirty
                ? t('Save the course information before creating a task.')
                : undefined
            "
            @click="navigate({ page: 'task', courseId: currentId })"
          >
            ＋ {{ t("Create task") }}
          </TButton>
          <TButton
            theme="default"
            variant="outline"
            type="submit"
            form="course-information-form"
            class="course-save-button"
            :aria-label="t('Save course information')"
            :title="t('Save course information')"
            :disabled="chatting || saving || (!!currentId && !dirty)"
          >
            <Save :size="17" aria-hidden="true" />
            {{ t(saving ? "Saving…" : "Save") }}
          </TButton>
        </div>
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
            'Describe the course information, students and teaching requirements. You can also edit the fields above.',
          )
        "
      >
        <template #results>
          <section class="course-information-section">
            <form id="course-information-form" @submit.prevent="save">
              <fieldset
                class="course-information-fields"
                :disabled="chatting || saving"
              >
                <label for="course-title"
                  >{{ t("Course name") }}
                  <TInput
                    :disabled="chatting || saving"
                    v-control-attrs="{ id: 'course-title', required: true }"
                    v-model="form.title"
                    @blur="form.title = form.title.trim()"
                    maxlength="300"
                  />
                </label>
                <label for="course-code"
                  >{{ t("Course code") }}
                  <TInput
                    :disabled="chatting || saving"
                    v-control-attrs="{ id: 'course-code', required: true }"
                    v-model="form.code"
                    @blur="form.code = form.code.trim()"
                    maxlength="100"
                  />
                </label>
                <label for="course-information" class="course-information-wide"
                  >{{ t("Course information") }}
                  <TTextarea
                    :disabled="chatting || saving"
                    v-control-attrs="{ id: 'course-information', rows: '2' }"
                    :autosize="{ minRows: 2, maxRows: 8 }"
                    v-model="form.courseInformation"
                    maxlength="20000"
                  />
                </label>
                <label for="course-student-profile"
                  >{{ t("Student profile") }}
                  <TTextarea
                    :disabled="chatting || saving"
                    v-control-attrs="{
                      id: 'course-student-profile',
                      rows: '2',
                    }"
                    :autosize="{ minRows: 2, maxRows: 8 }"
                    v-model="form.studentProfile"
                    maxlength="20000"
                  />
                </label>
                <label for="course-instructions"
                  >{{ t("Course instructions") }}
                  <TTextarea
                    :disabled="chatting || saving"
                    v-control-attrs="{ id: 'course-instructions', rows: '2' }"
                    :autosize="{ minRows: 2, maxRows: 8 }"
                    v-model="form.systemInstructions"
                    maxlength="20000"
                  />
                </label>
              </fieldset>
              <div class="course-information-state">
                <small v-if="!currentId || dirty" class="muted">
                  {{ t("Save the course information before creating a task.") }}
                </small>
              </div>
              <p v-if="saved" class="success" role="status">
                {{ t("Course information saved.") }}
              </p>
              <p v-if="error" class="error" role="alert">
                {{ systemText(error) }}
              </p>
            </form>
          </section>
        </template>
      </TeacherConversation>
      <CourseStudents
        v-if="showStudents && currentCourse"
        :course="currentCourse"
        @close="showStudents = false"
      />
    </section>
  </div>
</template>
