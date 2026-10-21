<script setup lang="ts">
import { t, systemText } from "../../i18n";
import { computed, onMounted, ref, watch } from "vue";
import { Upload, Link, Library, FileText } from "lucide-vue-next";
import { api } from "../../api";
import { documentApi } from "../../document-api";
import type { Material, CourseMaterial, SessionDetail } from "../../types";
import type { DocumentCapability } from "../../document-types";
import {
  appendMaterialFiles,
  uploadMaterialQueue,
  type MaterialUpload,
  materialReadbackMatches,
  uploadSuccessMessage,
} from "../../material-upload";
import {
  materialKinds,
  materialFormats,
  acceptFormats,
  effectiveUploadSettings,
} from "../../upload-capabilities";
import { safeExternal, withVersion } from "../../stage2";
import { clone, label, useTask, askConfirm, navigate } from "../state";
import ItemRow from "./ItemRow.vue";
import EditorDialog from "./EditorDialog.vue";
import FeedbackNotice from "./FeedbackNotice.vue";
import MaterialPreview from "./MaterialPreview.vue";
import VisibilitySelect from "./VisibilitySelect.vue";
import MaterialSelector from "./MaterialSelector.vue";
import FilterBar from "./FilterBar.vue";
import Pagination from "./Pagination.vue";
const props = defineProps<{
  materials: Material[];
  session?: SessionDetail;
  courseId?: string;
  version?: string | null;
}>();
const emit = defineEmits<{
  changed: [SessionDetail];
  libraryChanged: [CourseMaterial[]];
}>();
const editable = computed(() => !!(props.session || props.courseId));
const target = computed(() => props.session?.id || props.courseId!);
const scope = computed(() =>
  props.session ? ("session" as const) : ("course" as const),
);
const { busy, error, success, run } = useTask();
const previewHeld = ref(false),
  previewDirty = ref(false);
const mode = ref<"upload" | "link" | "reuse" | "edit" | "preview" | null>(null),
  editing = ref<Material | null>(null);
const query = ref(""),
  kindFilter = ref(""),
  offset = ref(0);
const title = ref(""),
  url = ref(""),
  visibility = ref<"student" | "teacher">("student"),
  kind = ref("reading");
const selected = ref<string[]>([]),
  library = ref<CourseMaterial[]>([]),
  queue = ref<MaterialUpload[]>([]),
  capability = ref<DocumentCapability | null>(null),
  initial = ref("");
const reusePreview = ref<Material | null>(null);
const fields = computed(() =>
  JSON.stringify([title.value, url.value, visibility.value, kind.value]),
);
const dirty = computed(() =>
  mode.value === "preview"
    ? previewDirty.value
    : fields.value !== initial.value ||
      !!selected.value.length ||
      queue.value.some((q) => q.status === "queued" || q.status === "failed"),
);
const visible = computed(() =>
  props.materials.filter(
    (m) =>
      `${m.title} ${m.source_label} ${m.source_relative_path || ""}`
        .toLowerCase()
        .includes(query.value.trim().toLowerCase()) &&
      (!kindFilter.value || m.kind === kindFilter.value),
  ),
);
const available = computed(() =>
  library.value.filter((m) => !props.materials.some((x) => x.id === m.id)),
);
const formats = computed(() => materialFormats(capability.value));
watch([query, kindFilter], () => (offset.value = 0));
watch(
  () => props.materials.length,
  () => {
    offset.value = Math.min(
      offset.value,
      Math.max(0, Math.ceil(visible.value.length / 20) - 1) * 20,
    );
  },
);
onMounted(async () => {
  if (!editable.value) return;
  try {
    capability.value = await documentApi.capability();
  } catch {
    /* Preview formats remain available. */
  }
});
async function open(next: typeof mode.value, material?: Material) {
  mode.value = next;
  previewHeld.value = false;
  previewDirty.value = false;
  selected.value = [];
  editing.value = material ? clone(material) : null;
  title.value = material?.title || "";
  url.value = material?.url || "";
  visibility.value = material?.visibility || "student";
  kind.value = material?.kind || "reading";
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
async function readback(expected: Material[] = []) {
  let materials: Material[];
  if (props.session) {
    const detail = await api.session(props.session.id);
    materials = detail.materials;
    emit("changed", detail);
  } else {
    const result = await api.courseMaterials(props.courseId!);
    materials = result.materials;
    emit("libraryChanged", result.materials);
  }
  if (
    expected.some(
      (item) =>
        !materialReadbackMatches(
          item,
          materials.find((m) => m.id === item.id),
        ),
    )
  )
    throw Error(
      t("The material update could not be verified. Refresh before retrying."),
    );
  return materials;
}
async function save() {
  const ok = await run(
    async () => {
      const saved: Material[] = [];
      if (mode.value === "edit")
        saved.push(
          await api.updateMaterial(
            target.value,
            editing.value!.id,
            {
              title: title.value,
              ...effectiveUploadSettings(
                {},
                { kind: kind.value, visibility: visibility.value },
              ),
              ...(editing.value?.kind === "link" ? { url: url.value } : {}),
            },
            scope.value,
          ),
        );
      else if (mode.value === "link")
        saved.push(
          await api.createLink(
            target.value,
            {
              title: title.value,
              url: url.value,
              visibility: visibility.value,
            },
            scope.value,
          ),
        );
      else if (mode.value === "reuse") {
        try {
          for (const mid of selected.value)
            saved.push(await api.attachMaterial(props.session!.id, mid));
        } finally {
          await readback(saved);
          selected.value = selected.value.filter(
            (mid) => !saved.some((item) => item.id === mid),
          );
        }
        return;
      }
      await readback(saved);
    },
    props.session
      ? t("Material saved. Publish the course to share draft changes.")
      : t(
          "Course materials saved. Only attached materials are included when publishing.",
        ),
  );
  if (ok) mode.value = null;
}
async function upload() {
  let resultMessage = "";
  const ok = await run(async () => {
    const accepted = await uploadMaterialQueue(
      target.value,
      queue.value.filter((q) => q.status === "queued" || q.status === "failed"),
      { visibility: visibility.value, kind: kind.value },
      (item) => {
        queue.value = queue.value.map((q) => (q.key === item.key ? item : q));
      },
      () => true,
      (id, file, visibleTo, fileKind, processing, progress, relativePath) =>
        api.upload(
          id,
          file,
          visibleTo,
          fileKind,
          processing,
          progress,
          relativePath,
          scope.value,
        ),
    );
    await readback(accepted);
    if (queue.value.some((q) => q.status === "failed"))
      throw Error(
        t(
          "Some files could not be uploaded. Review each result before retrying.",
        ),
      );
    if (!accepted.length) throw Error(t("No new files were uploaded."));
    resultMessage = uploadSuccessMessage(accepted);
  });
  if (ok) {
    initial.value = fields.value;
    success.value = resultMessage;
  }
}
function selectFiles(event: Event) {
  const input = event.target as HTMLInputElement;
  queue.value = appendMaterialFiles(
    queue.value,
    Array.from(input.files || []),
    capability.value || false,
  );
  input.value = "";
}
async function refreshMaterials() {
  await run(async () => {
    await readback();
  });
}
async function remove(material: Material) {
  if (
    !(await askConfirm(
      props.session
        ? t(
            "Remove “{0}” from this session? The file remains in the course library.",
            [material.title],
          )
        : t(
            "Remove “{0}” from the course library? Published versions retain their copy. Materials used in session drafts must be detached first.",
            [material.title],
          ),
      { title: t("Remove material"), confirmLabel: t("Remove"), danger: true },
    ))
  )
    return;
  await run(async () => {
    await api.archiveMaterial(target.value, material.id, scope.value);
    if ((await readback()).some((item) => item.id === material.id))
      throw Error(t("Removal could not be verified."));
  }, t("Material removed."));
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
            : editable
              ? t(
                  "Manage course files here, then attach them to the sessions that need them.",
                )
              : t("Read and revisit your course materials.")
        }}
      </p>
    </div>
    <div v-if="editable" class="actions">
      <button class="primary" :disabled="busy" @click="open('upload')">
        <Upload :size="16" />{{ t("Upload files") }}</button
      ><button class="secondary" :disabled="busy" @click="open('link')">
        <Link :size="16" />{{ t("Add link") }}</button
      ><button
        v-if="session"
        class="secondary"
        :disabled="busy"
        @click="open('reuse')"
      >
        <Library :size="16" />{{ t("Reuse material") }}
      </button>
    </div>
  </div>
  <FeedbackNotice :error="mode ? '' : error" :success="mode ? '' : success" />
  <FilterBar :active="!!query || !!kindFilter"
    ><label class="grow"
      >{{ t("Search materials")
      }}<input
        v-model="query"
        type="search"
        :placeholder="t('Search title or source path…')" /></label
    ><label
      >{{ t("Type")
      }}<select v-model="kindFilter">
        <option value="">{{ t("All types") }}</option>
        <option v-for="k in [...materialKinds, 'link']" :key="k" :value="k">
          {{ label(k) }}
        </option>
      </select></label
    ></FilterBar
  >
  <div class="item-list">
    <ItemRow
      v-for="m in visible.slice(offset, offset + 20)"
      :key="m.id"
      :title="m.title"
      :description="m.source_relative_path || m.source_label"
      expandable
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
          v-if="editable"
          class="secondary"
          :disabled="busy"
          @click="open('edit', m)"
        >
          {{ t("Edit") }}</button
        ><button
          v-if="editable"
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
          editable
            ? t("Upload files or add a link to get started.")
            : t("Your teacher’s materials will appear here.")
        }}
      </p>
    </div>
  </div>
  <Pagination
    :offset="offset"
    :total="visible.length"
    @change="offset = $event"
  />
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
    :wide="mode === 'preview' || mode === 'reuse'"
    :close-label="
      mode === 'preview' ||
      (mode === 'upload' &&
        queue.length &&
        queue.every((item) => item.status === 'uploaded'))
        ? t('Close')
        : undefined
    "
    @close="mode = null"
  >
    <FeedbackNotice :error="error" :success="success" :busy="busy" />
    <MaterialPreview
      v-if="mode === 'preview' && editing"
      :material="editing"
      :version="version"
      :teacher="editable"
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
        ><MaterialSelector
          v-model="selected"
          :materials="available"
          :disabled="busy"
          @preview="reusePreview = $event"
        />
        <p v-if="!available.length && !busy" class="muted">
          {{
            t(
              "All existing course materials are already attached to this session.",
            )
          }}
        </p>
        <button
          type="button"
          class="link-button"
          @click="
            navigate({ page: 'course-materials', sid: session!.course_id })
          "
        >
          {{ t("Open course library") }}
        </button></template
      >
      <template v-else>
        <template v-if="mode === 'upload'"
          ><p class="notice">
            {{
              t("Supported formats: {0}.", [formats.join(", ").toUpperCase()])
            }}
            {{ t("Text and OCR previews: up to 25 MiB per file.")
            }}<template v-if="capability?.available">
              {{
                t("Complete processing: {0}; up to {1} MiB per file.", [
                  capability.formats.join(", ").toUpperCase(),
                  capability.max_upload_bytes / 1048576,
                ])
              }}</template
            ><br />{{
              t(
                "Export WPS documents to one of these formats first. Folder paths are kept as searchable source information; the library stays flat.",
              )
            }}
          </p>
          <label
            >{{ t("Add files")
            }}<input
              type="file"
              multiple
              :accept="acceptFormats(formats)"
              :disabled="busy"
              @change="selectFiles"
            /><small>{{
              t(
                "Selections are appended. Identical files are skipped; files with the same name in different folders are kept.",
              )
            }}</small></label
          ><label
            >{{ t("Or choose a folder")
            }}<input
              type="file"
              webkitdirectory
              multiple
              :accept="acceptFormats(formats)"
              :disabled="busy"
              @change="selectFiles" /></label
        ></template>
        <p v-if="mode === 'edit'" class="notice">
          {{
            t(
              "Changes apply to this shared material in every session draft that uses it. Published versions are unchanged.",
            )
          }}
        </p>
        <label v-if="mode !== 'upload'"
          >{{ t("Title")
          }}<input v-model="title" :required="mode === 'edit'" maxlength="500"
        /></label>
        <label v-if="mode === 'link' || editing?.kind === 'link'"
          >{{ t("Source URL")
          }}<input
            v-model="url"
            type="url"
            required
            placeholder="https://…"
          /><small>{{
            t(
              "Use a public page or direct document URL. Netdisk share links with extraction codes need to be downloaded locally before upload.",
            )
          }}</small></label
        >
        <div class="form-grid">
          <label v-if="mode !== 'link' && editing?.kind !== 'link'"
            >{{ t("Material type")
            }}<select v-model="kind">
              <option v-for="k in materialKinds" :key="k" :value="k">
                {{ label(k) }}
              </option>
            </select></label
          ><label
            >{{ t("Visible to")
            }}<VisibilitySelect
              :model-value="visibility"
              :kind="kind"
              @update:model-value="visibility = $event || 'student'"
          /></label>
        </div>
        <div v-for="item in queue" :key="item.key" class="upload-result">
          <div class="section-header">
            <strong>{{ item.relativePath || item.file.name }}</strong
            ><button
              v-if="item.status !== 'uploaded'"
              type="button"
              class="secondary danger"
              :disabled="busy"
              @click="queue = queue.filter((q) => q.key !== item.key)"
            >
              {{ t("Remove from queue") }}
            </button>
          </div>
          <span
            >{{ label(item.status)
            }}<template v-if="item.progress?.total">
              ·
              {{
                Math.round((item.progress.loaded / item.progress.total) * 100)
              }}%</template
            >
            · {{ t("{0} MiB", [(item.file.size / 1048576).toFixed(2)]) }}</span
          >
          <p v-if="item.error" class="field-error">
            {{ systemText(item.error) }}
          </p>
          <div
            v-if="item.status === 'queued' || item.status === 'failed'"
            class="form-grid"
          >
            <label
              >{{ t("File type")
              }}<select v-model="item.kind" :disabled="busy">
                <option :value="undefined">
                  {{ t("Use") }} {{ label(kind) }}
                </option>
                <option v-for="k in materialKinds" :key="k" :value="k">
                  {{ label(k) }}
                </option>
              </select></label
            ><label
              >{{ t("File visibility")
              }}<VisibilitySelect
                v-model="item.visibility"
                :kind="item.kind || kind"
                :default-visibility="visibility"
                allow-default
                :disabled="busy"
            /></label>
          </div>
        </div>
      </template>
    </form>
    <template v-if="mode !== 'preview'" #actions
      ><button
        class="primary"
        form="material-editor"
        :disabled="
          busy ||
          (mode === 'reuse' && !selected.length) ||
          (mode === 'upload' &&
            !queue.some((q) => q.status === 'queued' || q.status === 'failed'))
        "
      >
        {{
          mode === "upload"
            ? t("Upload selected files")
            : mode === "reuse"
              ? t("Attach selected materials")
              : t("Save material")
        }}
      </button></template
    >
    <template v-else #actions
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
  <EditorDialog
    v-if="reusePreview"
    :title="reusePreview.title"
    wide
    :close-label="t('Close')"
    @close="reusePreview = null"
    ><MaterialPreview :material="reusePreview"
  /></EditorDialog>
</template>
