<script setup lang="ts">
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
} from "../state";
import PageHeader from "../components/PageHeader.vue";
import ItemRow from "../components/ItemRow.vue";
import EditorDialog from "../components/EditorDialog.vue";
import FeedbackNotice from "../components/FeedbackNotice.vue";
const selected = ref(courses.value[0]?.id || ""),
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
  initial = ref("");
const formKey = computed(() =>
  JSON.stringify([title.value, code.value, description.value, number.value]),
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
          "The saved course could not be verified. Refresh before retrying.",
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
        );
      sessions.value = await api.sessions(selected.value);
    }
  }, "Saved.");
  if (ok) modal.value = null;
}
async function removeSession(s: SessionSummary) {
  if (
    !(await askConfirm(
      `Delete “${s.title}” from the draft? It can be restored from Deleted items.`,
    ))
  )
    return;
  await run(async () => {
    await api.deleteSession(s.id);
    sessions.value = await api.sessions(selected.value);
    if (sessions.value.some((row) => row.id === s.id))
      throw Error("Deletion could not be verified.");
  }, "Session moved to Deleted items.");
}
async function removeCourse() {
  if (
    !course.value ||
    !(await askConfirm(`Move “${course.value.title}” to Deleted items?`))
  )
    return;
  const id = course.value.id;
  await run(async () => {
    await api.trashCourse(id);
    await refreshCourses();
  }, "Course moved to Deleted items.");
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
  }, "Restored.");
}
</script>
<template>
  <PageHeader
    title="Courses"
    :eyebrow="staff ? 'TEACH & ORGANIZE' : 'YOUR LEARNING'"
    description="Your courses, materials and sessions, in one place."
    ><button v-if="staff" class="primary" @click="open('course')">
      <Plus :size="17" /> New course</button
    ><button v-else class="primary" @click="open('join')">
      <Plus :size="17" /> Join course</button
    ><button v-if="staff" class="secondary" @click="showTrash">
      <Archive :size="16" /> Deleted items
    </button></PageHeader
  ><FeedbackNotice :error="error" :success="success" :busy="busy || loading" />
  <div v-if="courses.length" class="course-switch">
    <label
      >Course<select v-model="selected" :disabled="busy">
        <option v-for="c in courses" :key="c.id" :value="c.id">
          {{ c.code }} · {{ c.title }}
        </option>
      </select></label
    ><span class="muted"
      >{{ courses.length }}
      {{ courses.length === 1 ? "course" : "courses" }}</span
    >
  </div>
  <template v-if="course"
    ><section class="course-overview">
      <div>
        <span class="eyebrow">{{ course.code }}</span>
        <h2>{{ course.title }}</h2>
        <p v-if="course.description">{{ course.description }}</p>
        <div class="item-meta">
          <span>{{
            loading ? "Loading sessions…" : `${sessions.length} sessions`
          }}</span
          ><span>{{ course.student_count }} students</span
          ><span v-if="staff && course.join_code"
            >Invitation code
            <strong class="code">{{ course.join_code }}</strong></span
          >
        </div>
      </div>
      <div v-if="staff" class="actions">
        <button class="secondary" @click="open('course', course)">
          Edit course</button
        ><button class="secondary danger" @click="removeCourse">
          Delete course
        </button>
      </div>
    </section>
    <nav v-if="staff" class="course-tools" aria-label="Course management">
      <button
        class="secondary"
        @click="navigate({ page: 'roster', sid: selected })"
      >
        People</button
      ><button
        class="secondary"
        @click="navigate({ page: 'course-materials', sid: selected })"
      >
        Course materials</button
      ><button
        class="secondary"
        @click="navigate({ page: 'versions', sid: selected })"
      >
        Publish & history
        <span v-if="course.has_unpublished_changes" class="dot" />
      </button>
    </nav>
    <div class="section-header">
      <div>
        <h2>
          Sessions
          <span v-if="!loading" class="count">{{ sessions.length }}</span>
        </h2>
        <p>
          Open a session to
          {{ staff ? "prepare your teaching." : "continue your learning." }}
        </p>
      </div>
      <button
        v-if="staff"
        class="primary"
        :disabled="busy || loading"
        @click="open('session')"
      >
        <Plus :size="16" /> New session
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
          ><span><Clock3 :size="14" /> {{ s.estimated_minutes }} min</span
          ><span
            ><ListChecks :size="14" /> {{ s.question_count }} questions</span
          ><span
            class="badge"
            :class="s.effective_active ? 'positive' : 'neutral'"
            >{{ s.effective_active ? "Open" : "Closed" }}</span
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
                ? "Open session"
                : s.student_status === "not_started"
                  ? "Start learning"
                  : "Continue learning"
            }}<ArrowRight :size="15" /></button
          ><button v-if="staff" class="secondary" @click="open('session', s)">
            Edit</button
          ><button
            v-if="staff"
            class="secondary danger"
            @click="removeSession(s)"
          >
            Delete
          </button></template
        ></ItemRow
      >
    </div>
    <div
      v-if="!sessions.length && !busy && !loading && !error"
      class="empty-state"
    >
      <h3>No sessions yet</h3>
      <p>Add your first session to start organizing this course.</p>
    </div></template
  >
  <div v-else-if="!busy" class="empty-state">
    <h2>No courses yet</h2>
    <p>
      {{
        staff
          ? "Create a course to begin."
          : "Join a course using your invitation code."
      }}
    </p>
  </div>
  <EditorDialog
    v-if="modal"
    :title="
      modal === 'join' ? 'Join a course' : `${editId ? 'Edit' : 'New'} ${modal}`
    "
    :busy="busy"
    :dirty="dirty"
    @close="modal = null"
    ><FeedbackNotice :error="error" />
    <form id="home-editor" class="form-stack" @submit.prevent="save">
      <label v-if="modal !== 'join'"
        >Title<input v-model="title" required maxlength="300" /></label
      ><label v-if="modal === 'course' || modal === 'join'"
        >{{ modal === "join" ? "Invitation code" : "Course code"
        }}<input v-model="code" required maxlength="100" /></label
      ><label v-if="modal === 'session'"
        >Session number<input
          v-model.number="number"
          type="number"
          min="1"
          required /></label
      ><label v-if="modal !== 'join'"
        >{{ modal === "course" ? "Description" : "Subtitle"
        }}<textarea v-model="description" rows="3" />
      </label>
    </form>
    <template #actions
      ><button form="home-editor" class="primary" :disabled="busy">
        {{ modal === "join" ? "Join course" : "Save" }}
      </button></template
    ></EditorDialog
  >
  <EditorDialog
    v-if="trash"
    title="Deleted items"
    :busy="busy"
    @close="trash = false"
    ><FeedbackNotice :error="error" />
    <h3>Courses</h3>
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
          Restore
        </button></template
      ></ItemRow
    >
    <p v-if="!deletedCourses.length" class="muted">No deleted courses.</p>
    <h3>Sessions in this course</h3>
    <ItemRow v-for="s in removed" :key="s.id" :title="s.title"
      ><template #actions
        ><button
          class="secondary"
          :disabled="busy"
          @click="restore(s.id, 'session')"
        >
          Restore
        </button></template
      ></ItemRow
    >
    <p v-if="!removed.length" class="muted">
      No deleted sessions.
    </p></EditorDialog
  >
</template>
