<script setup lang="ts">
import { t, locale } from "../../i18n";

import { askConfirm } from "../state";
import { computed, ref, watch } from "vue";
import { Plus, ArrowRight, Clock3, ListChecks, Archive } from "lucide-vue-next";
import { api } from "../../api";
import type { Course, SessionSummary } from "../../types";
import {
  courses,
  staff,
  navigate,
  refreshCourses,
  useTask,
  label,
  errorText,
  route,
  updateRouteContext,
} from "../state";
import PageHeader from "../components/PageHeader.vue";
import ItemRow from "../components/ItemRow.vue";
import EditorDialog from "../components/EditorDialog.vue";
import FeedbackNotice from "../components/FeedbackNotice.vue";
const selected = computed({
    get: () =>
      courses.value.some((c) => c.id === route.value.course)
        ? route.value.course!
        : courses.value[0]?.id || "",
    set: (course: string) => updateRouteContext({ course }),
  }),
  loading = ref(false),
  sessions = ref<SessionSummary[]>([]),
  trash = ref(false),
  removed = ref<SessionSummary[]>([]),
  deletedCourses = ref<Course[]>([]);
const course = computed(() =>
  courses.value.find((c) => c.id === selected.value),
);
const { busy, error, success, run } = useTask();
const modal = ref<"course" | "session" | "join" | null>(null),
  editId = ref(""),
  title = ref(""),
  code = ref(""),
  description = ref(""),
  number = ref(1),
  initial = ref(""),
  teachingLanguage = ref("en");
const formKey = computed(() =>
  JSON.stringify([
    title.value,
    code.value,
    description.value,
    number.value,
    teachingLanguage.value,
  ]),
);
const dirty = computed(() => formKey.value !== initial.value);
let loadId = 0;
async function load() {
  const id = ++loadId,
    cid = selected.value;
  loading.value = true;
  error.value = "";
  sessions.value = [];
  try {
    const next = cid ? await api.sessions(cid) : [];
    if (id === loadId && cid === selected.value) sessions.value = next;
  } catch (e) {
    if (id === loadId) error.value = errorText(e);
  } finally {
    if (id === loadId) loading.value = false;
  }
}
watch(
  selected,
  () => {
    trash.value = false;
    void load();
  },
  { immediate: true },
);
watch(courses, () => {
  if (!courses.value.some((c) => c.id === selected.value))
    selected.value = courses.value[0]?.id || "";
});
function open(
  kind: "course" | "session" | "join",
  item?: Course | SessionSummary,
) {
  modal.value = kind;
  editId.value = item?.id || "";
  title.value = item?.title || "";
  code.value = item && "code" in item ? item.code : "";
  description.value =
    item && "description" in item
      ? item.description
      : item && "subtitle" in item
        ? item.subtitle
        : "";
  number.value =
    item && "number" in item
      ? item.number
      : Math.max(0, ...sessions.value.map((s) => s.number)) + 1;
  teachingLanguage.value = locale.value === "zh-CN" ? "zh-CN" : "en";
  initial.value = formKey.value;
}
async function save() {
  const ok = await run(async () => {
    if (modal.value === "join") {
      const c = await api.joinCourse(code.value);
      await refreshCourses();
      selected.value = c.id;
    } else if (modal.value === "course") {
      const c = editId.value
        ? await api.updateCourse(editId.value, {
            title: title.value,
            code: code.value,
            description: description.value,
          })
        : await api.createCourse(title.value, code.value, description.value);
      const verified = await api.courseDetails(c.id);
      if (
        verified.title !== title.value.trim() ||
        verified.code !== code.value.trim()
      )
        throw Error(
          t("The saved course could not be verified. Refresh before retrying."),
        );
      await refreshCourses();
      selected.value = c.id;
    } else {
      if (editId.value)
        await api.updateSession(editId.value, {
          title: title.value,
          subtitle: description.value,
          number: number.value,
        });
      else
        await api.createSession(
          selected.value,
          title.value,
          number.value,
          description.value,
          teachingLanguage.value,
        );
      sessions.value = await api.sessions(selected.value);
    }
  }, t("Saved."));
  if (ok) modal.value = null;
}
async function copyCode() {
  if (!course.value?.join_code) return;
  await run(async () => {
    await navigator.clipboard.writeText(course.value!.join_code!);
  }, t("Invitation code copied."));
}
async function removeSession(s: SessionSummary) {
  if (
    !(await askConfirm(
      t("Delete “{0}” from the draft? It can be restored from Deleted items.", [
        s.title,
      ]),
      {
        title: t("Delete session"),
        confirmLabel: t("Move to Deleted items"),
        danger: true,
      },
    ))
  )
    return;
  await run(async () => {
    await api.deleteSession(s.id);
    sessions.value = await api.sessions(selected.value);
    if (sessions.value.some((row) => row.id === s.id))
      throw Error(t("Deletion could not be verified."));
  }, t("Session moved to Deleted items."));
}
async function removeCourse() {
  if (
    !course.value ||
    !(await askConfirm(
      t("Move “{0}” to Deleted items?", [course.value.title]),
      {
        title: t("Delete course"),
        confirmLabel: t("Move to Deleted items"),
        danger: true,
      },
    ))
  )
    return;
  const id = course.value.id;
  await run(async () => {
    await api.trashCourse(id);
    await refreshCourses();
  }, t("Course moved to Deleted items."));
}
async function showTrash() {
  await run(async () => {
    const [a, b] = await Promise.all([
      selected.value
        ? api.deletedSessions(selected.value)
        : Promise.resolve({ sessions: [] }),
      api.courseTrash(),
    ]);
    removed.value = a.sessions;
    deletedCourses.value = b.courses;
    trash.value = true;
  });
}
async function restore(id: string, kind: "course" | "session") {
  await run(async () => {
    if (kind === "course") {
      await api.restoreCourse(id);
      await refreshCourses();
      deletedCourses.value = (await api.courseTrash()).courses;
    } else {
      await api.restoreSession(id);
      sessions.value = await api.sessions(selected.value);
      removed.value = (await api.deletedSessions(selected.value)).sessions;
    }
  }, t("Restored."));
}
</script>
<template>
  <PageHeader
    :title="t('Courses')"
    :eyebrow="staff ? t('TEACH & ORGANIZE') : t('YOUR LEARNING')"
    :description="
      staff
        ? t('Your courses, materials and sessions, in one place.')
        : t('Find your courses, study materials and continue learning.')
    "
    ><button v-if="staff" class="primary" @click="open('course')">
      <Plus :size="17" /> {{ t("New course") }}</button
    ><button v-else class="primary" @click="open('join')">
      <Plus :size="17" /> {{ t("Join course") }}</button
    ><button v-if="staff" class="secondary" @click="showTrash">
      <Archive :size="16" /> {{ t("Deleted items") }}
    </button></PageHeader
  ><FeedbackNotice :error="error" :success="success" :busy="busy || loading" />
  <div v-if="courses.length" class="course-switch">
    <label
      >{{ t("Course")
      }}<select v-model="selected" :disabled="busy">
        <option v-for="c in courses" :key="c.id" :value="c.id">
          {{ c.code }} · {{ c.title }}
        </option>
      </select></label
    ><span class="muted">{{
      t(courses.length === 1 ? "{0} course" : "{0} courses", [courses.length])
    }}</span>
  </div>
  <template v-if="course"
    ><section class="course-overview">
      <div>
        <span class="eyebrow">{{ course.code }}</span>
        <h2>{{ course.title }}</h2>
        <p v-if="course.description">{{ course.description }}</p>
        <div class="item-meta">
          <span>{{
            loading
              ? t("Loading sessions…")
              : t("{0} sessions", [sessions.length])
          }}</span
          ><span>{{ course.student_count }} {{ t("students") }}</span
          ><span v-if="staff && course.join_code"
            >{{ t("Invitation code") }}
            <strong class="code">{{ course.join_code }}</strong
            ><button type="button" class="link-button" @click="copyCode">
              {{ t("Copy code") }}
            </button></span
          >
        </div>
      </div>
      <div v-if="staff" class="actions">
        <button class="secondary" @click="open('course', course)">
          {{ t("Edit course") }}</button
        ><button class="secondary danger" @click="removeCourse">
          {{ t("Delete course") }}
        </button>
      </div>
    </section>
    <nav v-if="staff" class="course-tools" :aria-label="t('Course management')">
      <button
        class="secondary"
        @click="navigate({ page: 'roster', sid: selected })"
      >
        {{ t("People") }}</button
      ><button
        class="secondary"
        @click="navigate({ page: 'course-materials', sid: selected })"
      >
        {{ t("Course materials") }}</button
      ><button
        class="secondary"
        @click="navigate({ page: 'versions', sid: selected })"
      >
        {{ t("Publish & history") }}
        <span v-if="course.has_unpublished_changes" class="dot" />
      </button>
    </nav>
    <div class="section-header">
      <div>
        <h2>
          {{ t("Sessions") }}
          <span v-if="!loading" class="count">{{ sessions.length }}</span>
        </h2>
        <p>
          {{ t("Open a session to") }}
          {{
            staff ? t("prepare your teaching.") : t("continue your learning.")
          }}
        </p>
      </div>
      <button
        v-if="staff"
        class="primary"
        :disabled="busy || loading"
        @click="open('session')"
      >
        <Plus :size="16" /> {{ t("New session") }}
      </button>
    </div>
    <div class="item-list">
      <ItemRow
        v-for="s in sessions"
        :key="s.id"
        :title="s.title"
        :description="s.subtitle"
        :number="s.number"
        ><template #meta
          ><span
            ><Clock3 :size="14" /> {{ s.estimated_minutes }}
            {{ t("min") }}</span
          ><span
            ><ListChecks :size="14" /> {{ s.question_count }}
            {{ t("questions") }}</span
          ><span
            class="badge"
            :class="s.effective_active ? 'positive' : 'neutral'"
            >{{ s.effective_active ? t("Open") : t("Closed") }}</span
          ><span v-if="!staff" class="badge">{{
            label(s.student_status || "not_started")
          }}</span></template
        ><template #actions
          ><button
            class="primary"
            @click="
              navigate({ page: staff ? 'teacher' : 'workspace', sid: s.id })
            "
          >
            {{
              staff
                ? t("Open session")
                : s.student_status === "not_started"
                  ? t("Start learning")
                  : t("Continue learning")
            }}<ArrowRight :size="15" /></button
          ><button v-if="staff" class="secondary" @click="open('session', s)">
            {{ t("Edit") }}</button
          ><button
            v-if="staff"
            class="secondary danger"
            @click="removeSession(s)"
          >
            {{ t("Delete") }}
          </button></template
        ></ItemRow
      >
    </div>
    <div
      v-if="!sessions.length && !busy && !loading && !error"
      class="empty-state"
    >
      <h3>{{ t("No sessions yet") }}</h3>
      <p>
        {{
          staff
            ? t("Add your first session to start organizing this course.")
            : t("Your teacher has not published a session yet.")
        }}
      </p>
    </div></template
  >
  <div v-else-if="!busy" class="empty-state">
    <h2>{{ t("No courses yet") }}</h2>
    <p>
      {{
        staff
          ? t("Create a course to begin.")
          : t("Join a course using your invitation code.")
      }}
    </p>
  </div>
  <EditorDialog
    v-if="modal"
    :title="
      modal === 'join'
        ? t('Join a course')
        : modal === 'course'
          ? t(editId ? 'Edit course' : 'New course')
          : t(editId ? 'Edit session' : 'New session')
    "
    :busy="busy"
    :dirty="dirty"
    @close="modal = null"
    ><FeedbackNotice :error="error" />
    <form id="home-editor" class="form-stack" @submit.prevent="save">
      <label v-if="modal !== 'join'"
        >{{ t("Title")
        }}<input v-model="title" required maxlength="300" /></label
      ><label v-if="modal === 'course' || modal === 'join'"
        >{{ modal === "join" ? t("Invitation code") : t("Course code")
        }}<input v-model="code" required maxlength="100" /></label
      ><label v-if="modal === 'session'"
        >{{ t("Session number")
        }}<input
          v-model.number="number"
          type="number"
          min="1"
          required /></label
      ><label v-if="modal !== 'join'"
        >{{ modal === "course" ? t("Description") : t("Subtitle")
        }}<textarea v-model="description" rows="3" />
      </label>
      <label v-if="modal === 'session' && !editId"
        >{{ t("Teaching language")
        }}<select v-model="teachingLanguage">
          <option value="zh-CN">{{ t("Chinese") }}</option>
          <option value="en">{{ t("English") }}</option></select
        ><small>{{
          t(
            "Sets defaults for new teaching content. Changing the interface language does not translate saved course content.",
          )
        }}</small></label
      >
    </form>
    <template #actions
      ><button form="home-editor" class="primary" :disabled="busy">
        {{ modal === "join" ? t("Join course") : t("Save") }}
      </button></template
    ></EditorDialog
  >
  <EditorDialog
    v-if="trash"
    :title="t('Deleted items')"
    :close-label="t('Close')"
    :busy="busy"
    @close="trash = false"
    ><FeedbackNotice :error="error" />
    <h3>{{ t("Courses") }}</h3>
    <ItemRow
      v-for="c in deletedCourses"
      :key="c.id"
      :title="c.title"
      :description="c.code"
      ><template #actions
        ><button
          class="secondary"
          :disabled="busy"
          @click="restore(c.id, 'course')"
        >
          {{ t("Restore") }}
        </button></template
      ></ItemRow
    >
    <p v-if="!deletedCourses.length" class="muted">
      {{ t("No deleted courses.") }}
    </p>
    <h3>{{ t("Sessions in this course") }}</h3>
    <ItemRow v-for="s in removed" :key="s.id" :title="s.title"
      ><template #actions
        ><button
          class="secondary"
          :disabled="busy"
          @click="restore(s.id, 'session')"
        >
          {{ t("Restore") }}
        </button></template
      ></ItemRow
    >
    <p v-if="!removed.length" class="muted">
      {{ t("No deleted sessions.") }}
    </p></EditorDialog
  >
</template>
