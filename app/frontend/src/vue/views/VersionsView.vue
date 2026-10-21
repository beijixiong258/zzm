<script setup lang="ts">
import { t } from "../../i18n";

import { askConfirm } from "../state";
import { ref } from "vue";
import { api } from "../../api";
import type {
  VersionList,
  VersionEntry,
  VersionSnapshot,
  VersionDiff,
} from "../../types";
import { courses, dateText, useTask, refreshCourses, label } from "../state";
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
    !(await askConfirm(
      t("Publish the complete saved course draft to students?"),
      { title: t("Publish course draft"), confirmLabel: t("Publish") },
    ))
  )
    return;
  await run(async () => {
    await api.publishVersion(props.courseId, publicationLabel.value);
    list.value = await api.versions(props.courseId);
    await refreshCourses();
    publicationLabel.value = "";
  }, t("Course published. Students can now access this version."));
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
      t(
        "Restore version {0} as a new published version? This replaces the saved draft. Learning records and schedules are retained.",
        [v.number],
      ),
      {
        title: t("Replace draft and publish"),
        confirmLabel: t("Replace and publish"),
        danger: true,
      },
    ))
  )
    return;
  await run(async () => {
    await api.restoreVersion(props.courseId, v.id, publicationLabel.value);
    list.value = await api.versions(props.courseId);
    await refreshCourses();
    selected.value = null;
  }, t("Restored and published as a new version."));
}
const fieldName = (key: string) => {
  const names: Record<string, string> = {
    code: t("Course code"),
    number: t("Session number"),
    learning_objectives: t("Learning goals"),
    instructions: t("Instructions"),
    reference_policy: t("References become available"),
    teaching_language: t("Teaching language"),
    groups: t("Question groups"),
    questions: t("Questions"),
    materials: t("Materials"),
    prompt: t("Question prompt"),
    type: t("Type"),
    kind: t("Type"),
    group_id: t("Group"),
    options: t("Options · one per line"),
    answer_slots: t("Answer slots"),
    source_label: t("Source label"),
    images: t("Question images"),
    visibility: t("Visible to"),
    ordinal: t("Position"),
    source_link_inputs: t("Source links"),
    source_material_ids: t("Source materials"),
    teaching_profile: t("Teaching approach"),
    reference_answers: t("Instructor answers"),
    schema_version: t("Format version"),
    background: t("Background"),
    student_profile: t("Student profile"),
    response_strategies: t("Response strategies"),
    tone: t("Tone"),
    response_detail: t("Response detail"),
    phases: t("Teaching sequence"),
    reading_focus: t("Reading focus"),
    reading_question_count: t("Reading questions"),
    reference_delivery: t("Reference delivery"),
    idle_hint_seconds: t("Idle hint delay · seconds"),
    presentation: t("Question presentation"),
    title: t("Title"),
    description: t("Description"),
    subtitle: t("Subtitle"),
    source_relative_path: t("Source path"),
    alt: t("Accessible description"),
    label: t("Label"),
    url: t("Source URL"),
  };
  const text = names[key] || key.replaceAll("_", " ");
  return t(text.charAt(0).toUpperCase() + text.slice(1));
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
        return session ? t("Session {0}", [session.number]) : t("Session");
      if (kind === "questions") {
        const question = session?.questions.find((q) => q.id === id);
        return question ? t("Question {0}", [question.ordinal]) : t("Question");
      }
      if (kind === "materials")
        return (
          session?.materials.find((m) => m.id === id)?.title || t("Material")
        );
      return fieldName(kind);
    })
    .join(" · ");
}
function display(value: unknown, field = ""): string {
  if (value == null) return t("Not set");
  if (value === "") return t("Empty");
  if (typeof value === "boolean") return value ? t("Yes") : t("No");
  if (Array.isArray(value))
    return value.length
      ? value.map((item) => `• ${display(item, field)}`).join("\n")
      : t("No items");
  if (typeof value === "object")
    return Object.entries(value)
      .map(([key, item]) => `${fieldName(key)}: ${display(item, key)}`)
      .join("\n");
  const enums = [
    "type",
    "kind",
    "visibility",
    "reference_policy",
    "teaching_language",
    "response_detail",
    "phases",
    "reference_delivery",
    "presentation",
    "status",
  ];
  return typeof value === "string" && enums.includes(field)
    ? label(value)
    : String(value);
}
</script>
<template>
  <PageHeader
    :title="t('Publish &amp; history')"
    :eyebrow="courses.find((c) => c.id === courseId)?.code"
    :description="t('Save your draft first, then publish it to students.')"
    ><button class="secondary" :disabled="busy" @click="load">
      {{ t("Refresh") }}
    </button></PageHeader
  ><FeedbackNotice
    :error="selected ? '' : error"
    :success="success"
    :busy="busy && !selected"
  /><template v-if="list"
    ><section class="panel publish-panel">
      <div>
        <span class="badge positive"
          >{{ t("Student-visible version") }}
          {{
            list.versions.find((v) => v.id === list!.current_version_id)
              ?.number || "—"
          }}</span
        >
        <h2>
          {{
            list.has_unpublished_changes
              ? t("Draft changes ready to publish")
              : t("Your published version is up to date")
          }}
        </h2>
        <p>
          {{
            t(
              "Publishing updates the complete course. Availability is controlled separately in each session.",
            )
          }}
        </p>
      </div>
      <form class="form-stack" @submit.prevent="publish">
        <label
          ><span
            >{{ t("Version label") }}
            <span class="optional">{{ t("optional") }}</span></span
          ><input
            v-model="publicationLabel"
            :placeholder="t('e.g. Week 2 materials')" /></label
        ><button
          class="primary"
          :disabled="busy || !list.has_unpublished_changes"
        >
          {{ t("Publish course draft") }}
        </button>
      </form>
    </section>
    <div class="section-header">
      <h2>
        {{ t("Version history") }}
        <span class="count">{{ list.versions.length }}</span>
      </h2>
    </div>
    <div class="item-list">
      <ItemRow
        v-for="v in list.versions"
        :key="v.id"
        :title="v.label || t('Course version {0}', [v.number])"
        :number="v.number"
        ><template #meta
          ><span>{{ dateText(v.created_at) }}</span
          ><span>{{ v.created_by }}</span
          ><span
            v-if="v.id === list.current_version_id"
            class="badge positive"
            >{{ t("Current") }}</span
          ></template
        ><template #actions
          ><button class="secondary" :disabled="busy" @click="browse(v)">
            {{ t("View & compare") }}</button
          ><button
            class="secondary danger"
            :disabled="
              busy ||
              (v.id === list.current_version_id &&
                !list.has_unpublished_changes)
            "
            @click="restore(v)"
          >
            {{ t("Replace draft and publish") }}
          </button></template
        ></ItemRow
      >
      <div v-if="!list.versions.length" class="empty-state">
        {{ t("No published versions yet.") }}
      </div>
    </div></template
  ><EditorDialog
    v-if="selected"
    :title="
      t('Version {0} · {1}', [
        selected.number,
        selected.label || t('Course snapshot'),
      ])
    "
    wide
    :close-label="t('Close')"
    :busy="busy"
    @close="selected = null"
    ><FeedbackNotice :error="error" :busy="busy" /><template v-if="snapshot"
      ><h3>{{ snapshot.course.title }}</h3>
      <p>{{ snapshot.course.description }}</p>
      <h3>{{ t("Compared with the current saved draft") }}</h3>
      <div v-if="diff?.changes.length" class="diff-list">
        <section v-for="(c, i) in diff.changes" :key="i" class="panel">
          <h4>{{ changeTitle(c.path) }}</h4>
          <div class="form-grid">
            <div>
              <strong>{{ t("Selected version") }}</strong>
              <pre class="diff-value">{{
                display(c.before, c.path.split(".").at(-1))
              }}</pre>
            </div>
            <div>
              <strong>{{ t("Saved draft") }}</strong>
              <pre class="diff-value">{{
                display(c.after, c.path.split(".").at(-1))
              }}</pre>
            </div>
          </div>
        </section>
      </div>
      <p v-else class="notice success">{{ t("No content differences.") }}</p>
      <h3>{{ t("Included sessions") }}</h3>
      <ItemRow
        v-for="s in snapshot.sessions"
        :key="s.id"
        :title="s.title"
        :number="s.number"
        ><template #meta
          >{{ s.questions.length }} {{ t("questions ·") }}
          {{ s.materials.length }} {{ t("materials") }}</template
        ></ItemRow
      ></template
    ><template #actions
      ><button
        class="secondary danger"
        :disabled="
          busy ||
          !snapshot ||
          (selected.id === list?.current_version_id &&
            !list?.has_unpublished_changes)
        "
        @click="restore(selected!)"
      >
        {{ t("Replace draft and publish") }}
      </button></template
    ></EditorDialog
  >
</template>
