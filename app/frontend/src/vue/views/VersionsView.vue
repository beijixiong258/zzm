<script setup lang="ts">
import { askConfirm } from "../state";
import { ref } from "vue";
import { api } from "../../api";
import type {
  VersionList,
  VersionEntry,
  VersionSnapshot,
  VersionDiff,
} from "../../types";
import { courses, dateText, useTask, refreshCourses } from "../state";
import PageHeader from "../components/PageHeader.vue";
import ItemRow from "../components/ItemRow.vue";
import EditorDialog from "../components/EditorDialog.vue";
import FeedbackNotice from "../components/FeedbackNotice.vue";
const props = defineProps<{ courseId: string }>();
const { busy, error, success, run } = useTask();
const list = ref<VersionList | null>(null),
  snapshot = ref<VersionSnapshot | null>(null),
  diff = ref<VersionDiff | null>(null),
  publicationLabel = ref(""),
  selected = ref<VersionEntry | null>(null);
async function load() {
  await run(async () => {
    list.value = await api.versions(props.courseId);
  });
}
void load();
async function publish() {
  if (
    !(await askConfirm("Publish the complete saved course draft to students?"))
  )
    return;
  await run(async () => {
    await api.publishVersion(props.courseId, publicationLabel.value);
    list.value = await api.versions(props.courseId);
    await refreshCourses();
    publicationLabel.value = "";
  }, "Course published. Students can now access this version.");
}
async function browse(v: VersionEntry) {
  selected.value = v;
  snapshot.value = null;
  diff.value = null;
  await run(async () => {
    const [s, d] = await Promise.all([
      api.version(props.courseId, v.id),
      api.versionDiff(props.courseId, v.id),
    ]);
    snapshot.value = s;
    diff.value = d;
  });
}
async function restore(v: VersionEntry) {
  if (
    !(await askConfirm(
      `Restore version ${v.number} as a new published version? This replaces the saved draft. Learning records and schedules are retained.`,
    ))
  )
    return;
  await run(async () => {
    await api.restoreVersion(props.courseId, v.id, publicationLabel.value);
    list.value = await api.versions(props.courseId);
    await refreshCourses();
    selected.value = null;
  }, "Restored and published as a new version.");
}
const fieldName = (key: string) => {
  const names: Record<string, string> = {
    source_link_inputs: "Source links",
    source_material_ids: "Source materials",
    teaching_profile: "Teaching approach",
    reference_answers: "Instructor answers",
    schema_version: "Format version",
  };
  const text = names[key] || key.replaceAll("_", " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
};
function changeTitle(path: string) {
  const sessionId = path.match(/^sessions\[([^\]]+)\]/)?.[1];
  const session = snapshot.value?.sessions.find((s) => s.id === sessionId);
  return path
    .split(".")
    .map((part) => {
      const collection = part.match(/^(\w+)\[([^\]]+)\]$/);
      if (!collection) return fieldName(part);
      const [, kind, id] = collection;
      if (kind === "sessions")
        return session ? `Session ${session.number}` : "Session";
      if (kind === "questions") {
        const question = session?.questions.find((q) => q.id === id);
        return question ? `Question ${question.ordinal}` : "Question";
      }
      if (kind === "materials")
        return session?.materials.find((m) => m.id === id)?.title || "Material";
      return fieldName(kind);
    })
    .join(" · ");
}
function display(value: unknown): string {
  if (value == null) return "Not set";
  if (value === "") return "Empty";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value))
    return value.length
      ? value.map((item) => `• ${display(item)}`).join("\n")
      : "No items";
  if (typeof value === "object")
    return Object.entries(value)
      .map(([key, item]) => `${fieldName(key)}: ${display(item)}`)
      .join("\n");
  return String(value);
}
</script>
<template>
  <PageHeader
    title="Publish & history"
    :eyebrow="courses.find((c) => c.id === courseId)?.code"
    description="Save your draft first, then publish it to students."
    ><button class="secondary" :disabled="busy" @click="load">
      Refresh
    </button></PageHeader
  ><FeedbackNotice
    :error="selected ? '' : error"
    :success="success"
    :busy="busy && !selected"
  /><template v-if="list"
    ><section class="panel publish-panel">
      <div>
        <span class="badge positive"
          >Student-visible version
          {{
            list.versions.find((v) => v.id === list!.current_version_id)
              ?.number || "—"
          }}</span
        >
        <h2>
          {{
            list.has_unpublished_changes
              ? "Draft changes ready to publish"
              : "Your published version is up to date"
          }}
        </h2>
        <p>
          Publishing updates the complete course. Availability is controlled
          separately in each session.
        </p>
      </div>
      <form class="form-stack" @submit.prevent="publish">
        <label
          ><span>Version label <span class="optional">optional</span></span
          ><input
            v-model="publicationLabel"
            placeholder="e.g. Week 2 materials" /></label
        ><button class="primary" :disabled="busy">Publish course draft</button>
      </form>
    </section>
    <div class="section-header">
      <h2>
        Version history <span class="count">{{ list.versions.length }}</span>
      </h2>
    </div>
    <div class="item-list">
      <ItemRow
        v-for="v in list.versions"
        :key="v.id"
        :title="v.label || `Course version ${v.number}`"
        :number="v.number"
        ><template #meta
          ><span>{{ dateText(v.created_at) }}</span
          ><span>{{ v.created_by }}</span
          ><span v-if="v.id === list.current_version_id" class="badge positive"
            >Current</span
          ></template
        ><template #actions
          ><button class="secondary" :disabled="busy" @click="browse(v)">
            View & compare</button
          ><button class="secondary" :disabled="busy" @click="restore(v)">
            Restore
          </button></template
        ></ItemRow
      >
      <div v-if="!list.versions.length" class="empty-state">
        No published versions yet.
      </div>
    </div></template
  ><EditorDialog
    v-if="selected"
    :title="`Version ${selected.number} · ${selected.label || 'Course snapshot'}`"
    wide
    :busy="busy"
    @close="selected = null"
    ><FeedbackNotice :error="error" :busy="busy" /><template v-if="snapshot"
      ><h3>{{ snapshot.course.title }}</h3>
      <p>{{ snapshot.course.description }}</p>
      <h3>Compared with the current saved draft</h3>
      <div v-if="diff?.changes.length" class="diff-list">
        <section v-for="(c, i) in diff.changes" :key="i" class="panel">
          <h4>{{ changeTitle(c.path) }}</h4>
          <div class="form-grid">
            <div>
              <strong>Selected version</strong>
              <pre class="diff-value">{{ display(c.before) }}</pre>
            </div>
            <div>
              <strong>Saved draft</strong>
              <pre class="diff-value">{{ display(c.after) }}</pre>
            </div>
          </div>
        </section>
      </div>
      <p v-else class="notice success">No content differences.</p>
      <h3>Included sessions</h3>
      <ItemRow
        v-for="s in snapshot.sessions"
        :key="s.id"
        :title="s.title"
        :number="s.number"
        ><template #meta
          >{{ s.questions.length }} questions ·
          {{ s.materials.length }} materials</template
        ></ItemRow
      ></template
    ><template #actions
      ><button
        class="primary"
        :disabled="busy || !snapshot"
        @click="restore(selected!)"
      >
        Restore as new version
      </button></template
    ></EditorDialog
  >
</template>
