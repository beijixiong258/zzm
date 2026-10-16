<script setup lang="ts">
import { t, systemText } from "../../i18n";

import { askConfirm } from "../state";
import { computed, onMounted, ref } from "vue";
import { Upload, Link, Library, FileText } from "lucide-vue-next";
import { api } from "../../api";
import { documentApi } from "../../document-api";
import type { Material, CourseMaterial, SessionDetail } from "../../types";
import type { DocumentCapability } from "../../document-types";
import {
  selectMaterialFiles,
  uploadMaterialQueue,
  type MaterialUpload,
  materialReadbackMatches,
  uploadSuccessMessage,
} from "../../material-upload";
import { safeExternal, withVersion } from "../../stage2";
import { clone, label, useTask } from "../state";
import ItemRow from "./ItemRow.vue";
import EditorDialog from "./EditorDialog.vue";
import FeedbackNotice from "./FeedbackNotice.vue";
import MaterialPreview from "./MaterialPreview.vue";
const props = defineProps<{
  materials: Material[];
  session?: SessionDetail;
  version?: string | null;
}>();
const emit = defineEmits<{ changed: [SessionDetail] }>();
const { busy, error, success, run } = useTask();
const previewHeld = ref(false),
  previewDirty = ref(false);
const mode = ref<"upload" | "link" | "reuse" | "edit" | "preview" | null>(null),
  editing = ref<Material | null>(null),
  query = ref(""),
  kindFilter = ref("");
const title = ref(""),
  url = ref(""),
  visibility = ref<"student" | "teacher">("student"),
  kind = ref("reading"),
  selected = ref(""),
  library = ref<CourseMaterial[]>([]),
  queue = ref<MaterialUpload[]>([]),
  capability = ref<DocumentCapability | null>(null),
  initial = ref("");
const fields = computed(() =>
  JSON.stringify([title.value, url.value, visibility.value, kind.value]),
);
const dirty = computed(() =>
  mode.value === "preview"
    ? previewDirty.value
    : fields.value !== initial.value ||
      queue.value.some((q) => q.status === "queued" || q.status === "failed"),
);
const visible = computed(() =>
  props.materials.filter(
    (m) =>
      (!query.value ||
        m.title.toLowerCase().includes(query.value.toLowerCase())) &&
      (!kindFilter.value || m.kind === kindFilter.value),
  ),
);
const available = computed(() =>
  library.value.filter((m) => !props.materials.some((x) => x.id === m.id)),
);
onMounted(async () => {
  try {
    capability.value = await documentApi.capability();
  } catch {
    /* Upload retains the bounded text preview path. */
  }
});
async function open(next: typeof mode.value, m?: Material) {
  mode.value = next;
  previewHeld.value = false;
  previewDirty.value = false;
  selected.value = "";
  editing.value = m ? clone(m) : null;
  title.value = m?.title || "";
  url.value = m?.url || "";
  visibility.value = m?.visibility || "student";
  kind.value = m?.kind || "reading";
  queue.value = [];
  initial.value = fields.value;
  error.value = "";
  if (next === "reuse")
    await run(async () => {
      library.value = (
        await api.courseMaterials(props.session!.course_id)
      ).materials;
    });
}
async function readback(expected?: Material) {
  const s = await api.session(props.session!.id);
  if (
    expected &&
    !materialReadbackMatches(
      expected,
      s.materials.find((m) => m.id === expected.id),
    )
  )
    throw Error(
      t("The material update could not be verified. Refresh before retrying."),
    );
  emit("changed", s);
  return s;
}
async function save() {
  if (!props.session) return;
  const ok = await run(async () => {
    let saved: Material | undefined;
    if (mode.value === "edit")
      saved = await api.updateMaterial(props.session!.id, editing.value!.id, {
        title: title.value,
        visibility: kind.value === "answer_key" ? "teacher" : visibility.value,
        kind: kind.value,
        ...(editing.value?.kind === "link" ? { url: url.value } : {}),
      });
    else if (mode.value === "link")
      saved = await api.createLink(props.session!.id, {
        title: title.value,
        url: url.value,
        visibility: visibility.value,
      });
    else if (mode.value === "reuse")
      saved = await api.attachMaterial(props.session!.id, selected.value);
    await readback(saved);
  }, t("Material saved. Publish the course to share draft changes."));
  if (ok) mode.value = null;
}
async function upload() {
  let resultMessage = "";
  const ok = await run(async () => {
    const accepted = await uploadMaterialQueue(
      props.session!.id,
      queue.value.filter((q) => q.status === "queued" || q.status === "failed"),
      { visibility: visibility.value, kind: kind.value },
      (item) => {
        queue.value = queue.value.map((q) => (q.key === item.key ? item : q));
      },
      () => true,
    );
    await readback();
    if (queue.value.some((q) => q.status === "failed"))
      throw Error(
        t(
          "Some files could not be uploaded. Review each result before retrying.",
        ),
      );
    if (!accepted.length) throw Error(t("No new files were uploaded."));
    resultMessage = uploadSuccessMessage(accepted);
  }, t("Files saved. You can close this window."));
  if (ok) success.value = resultMessage;
}
function selectFiles(e: Event) {
  queue.value = selectMaterialFiles(
    Array.from((e.target as HTMLInputElement).files || []),
    capability.value || false,
  );
}
async function refreshMaterials() {
  await run(async () => {
    await readback();
  });
}
async function remove(m: Material) {
  if (
    !(await askConfirm(
      t(
        "Remove “{0}” from this session? The file remains in the course library.",
        [m.title],
      ),
    ))
  )
    return;
  await run(async () => {
    await api.archiveMaterial(props.session!.id, m.id);
    const s = await readback();
    if (s.materials.some((x) => x.id === m.id))
      throw Error(t("Removal could not be verified."));
  }, t("Material removed from this session."));
}
</script>
<template>
  <div class="section-header">
    <div>
      <h2>
        {{ t("Materials") }} <span class="count">{{ materials.length }}</span>
      </h2>
      <p>
        {{
          session
            ? t("Files and links attached to this session.")
            : t("Read and revisit your course materials.")
        }}
      </p>
    </div>
    <div v-if="session" class="actions">
      <button class="primary" :disabled="busy" @click="open('upload')">
        <Upload :size="16" /> {{ t("Upload files") }}</button
      ><button class="secondary" :disabled="busy" @click="open('link')">
        <Link :size="16" /> {{ t("Add link") }}</button
      ><button class="secondary" :disabled="busy" @click="open('reuse')">
        <Library :size="16" /> {{ t("Reuse material") }}
      </button>
    </div>
  </div>
  <FeedbackNotice :error="mode ? '' : error" :success="success" />
  <div class="filter-bar">
    <label class="grow"
      >{{ t("Search materials")
      }}<input v-model="query" :placeholder="t('Search by title…')" /></label
    ><label
      >{{ t("Type")
      }}<select v-model="kindFilter">
        <option value="">{{ t("All types") }}</option>
        <option
          v-for="k in [
            'reading',
            'worksheet',
            'answer_key',
            'slides',
            'reference',
            'link',
          ]"
          :key="k"
          :value="k"
        >
          {{ label(k) }}
        </option>
      </select></label
    >
  </div>
  <div class="item-list">
    <ItemRow
      v-for="m in visible"
      :key="m.id"
      :title="m.title"
      :description="m.source_label"
      ><template #meta
        ><FileText :size="15" /><span>{{ label(m.kind) }}</span
        ><span
          class="badge"
          :class="m.visibility === 'teacher' ? 'private' : 'positive'"
          >{{
            m.visibility === "teacher"
              ? t("Teacher only")
              : t("Student visible")
          }}</span
        ><span class="badge">{{ label(m.status) }}</span></template
      >
      <p v-if="m.warning" class="field-warning">{{ systemText(m.warning) }}</p>
      <template #actions
        ><button class="secondary" @click="open('preview', m)">
          {{ t("Preview") }}</button
        ><button
          v-if="session"
          class="secondary"
          :disabled="busy"
          @click="open('edit', m)"
        >
          {{ t("Edit") }}</button
        ><button
          v-if="session"
          class="secondary danger"
          :disabled="busy"
          @click="remove(m)"
        >
          {{ t("Remove") }}
        </button></template
      ></ItemRow
    >
    <div v-if="!visible.length" class="empty-state">
      <h3>
        {{
          materials.length ? t("No matching materials") : t("No materials yet")
        }}
      </h3>
      <p>
        {{
          session
            ? t(
                "Upload files, add a link, or reuse materials from your course.",
              )
            : t("Your teacher’s materials will appear here.")
        }}
      </p>
    </div>
  </div>
  <EditorDialog
    v-if="mode"
    :title="
      mode === 'preview'
        ? editing!.title
        : mode === 'edit'
          ? t('Edit material')
          : mode === 'reuse'
            ? t('Reuse course material')
            : mode === 'upload'
              ? t('Upload files')
              : t('Add a link')
    "
    :busy="busy || previewHeld"
    :dirty="dirty"
    :wide="mode === 'preview'"
    @close="mode = null"
    ><FeedbackNotice :error="error" :busy="busy" /><MaterialPreview
      v-if="mode === 'preview' && editing"
      :material="editing"
      :version="version"
      :teacher="!!session"
      @held="previewHeld = $event"
      @dirty="previewDirty = $event"
      @changed="refreshMaterials"
    />
    <form
      v-else
      id="material-editor"
      class="form-stack"
      @submit.prevent="mode === 'upload' ? upload() : save()"
    >
      <template v-if="mode === 'reuse'"
        ><label
          >{{ t("Course material")
          }}<select
            v-model="selected"
            :disabled="busy || !available.length"
            required
          >
            <option value="">{{ t("Choose a material") }}</option>
            <option v-for="m in available" :key="m.id" :value="m.id">
              {{ m.title }} · {{ label(m.kind) }}
            </option>
          </select></label
        >
        <p v-if="!available.length && !busy" class="muted">
          {{
            t(
              "All existing course materials are already attached to this session.",
            )
          }}
        </p></template
      ><template v-else
        ><label v-if="mode === 'upload'"
          >{{ t("Files")
          }}<input
            type="file"
            multiple
            :disabled="busy"
            @change="selectFiles"
          /><small>{{
            t(
              "Files are stored in the course library and linked to this session.",
            )
          }}</small></label
        ><label v-if="mode === 'upload'"
          >{{ t("Or choose a folder")
          }}<input
            type="file"
            webkitdirectory
            multiple
            :disabled="busy"
            @change="selectFiles" /></label
        ><label v-if="mode !== 'upload'"
          >{{ t("Title")
          }}<input v-model="title" :required="mode === 'edit'" /></label
        ><label v-if="mode === 'link' || editing?.kind === 'link'"
          >{{ t("Source URL")
          }}<input v-model="url" type="url" required placeholder="https://…"
        /></label>
        <div class="form-grid">
          <label v-if="mode !== 'link' && editing?.kind !== 'link'"
            >{{ t("Material type")
            }}<select
              v-model="kind"
              @change="
                () => {
                  if (kind === 'answer_key') visibility = 'teacher';
                }
              "
            >
              <option
                v-for="k in [
                  'reading',
                  'worksheet',
                  'answer_key',
                  'slides',
                  'reference',
                ]"
                :key="k"
                :value="k"
              >
                {{ label(k) }}
              </option>
            </select></label
          ><label
            >{{ t("Visible to")
            }}<select v-model="visibility" :disabled="kind === 'answer_key'">
              <option value="student">{{ t("Students and teachers") }}</option>
              <option value="teacher">{{ t("Teachers only") }}</option>
            </select></label
          >
        </div>
        <div v-for="q in queue" :key="q.key" class="upload-result">
          <strong>{{ q.relativePath || q.file.name }}</strong
          ><span
            >{{ label(q.status) }}
            <template v-if="q.progress?.total"
              >·
              {{
                Math.round((q.progress.loaded / q.progress.total) * 100)
              }}%</template
            ></span
          >
          <p v-if="q.error" class="field-error">{{ systemText(q.error) }}</p>
          <div
            v-if="q.status === 'queued' || q.status === 'failed'"
            class="form-grid"
          >
            <label
              >{{ t("File type")
              }}<select v-model="q.kind" :disabled="busy">
                <option :value="undefined">
                  {{ t("Use") }} {{ label(kind) }}
                </option>
                <option
                  v-for="k in [
                    'reading',
                    'worksheet',
                    'answer_key',
                    'slides',
                    'reference',
                  ]"
                  :key="k"
                  :value="k"
                >
                  {{ label(k) }}
                </option>
              </select></label
            >
            <label
              >{{ t("File visibility")
              }}<select
                v-model="q.visibility"
                :disabled="busy || q.kind === 'answer_key'"
              >
                <option :value="undefined">
                  {{ t("Use default visibility") }}
                </option>
                <option value="student">
                  {{ t("Students and teachers") }}
                </option>
                <option value="teacher">{{ t("Teachers only") }}</option>
              </select></label
            >
          </div>
        </div></template
      >
    </form>
    <template v-if="mode !== 'preview'" #actions
      ><button
        class="primary"
        form="material-editor"
        :disabled="
          busy ||
          (mode === 'reuse' && !selected) ||
          (mode === 'upload' &&
            !queue.some((q) => q.status === 'queued' || q.status === 'failed'))
        "
      >
        {{
          mode === "upload"
            ? t("Upload selected files")
            : mode === "reuse"
              ? t("Attach material")
              : t("Save material")
        }}
      </button></template
    ><template v-else #actions
      ><a
        v-if="editing?.download_url"
        class="secondary"
        :href="withVersion(editing.download_url, version)"
        target="_blank"
        rel="noopener"
        >{{ t("Download original") }}</a
      ><a
        v-if="editing?.kind === 'link' && safeExternal(editing.url)"
        class="primary"
        :href="safeExternal(editing.url)!"
        target="_blank"
        rel="noopener"
        >{{ t("Open source link") }}</a
      ></template
    ></EditorDialog
  >
</template>
