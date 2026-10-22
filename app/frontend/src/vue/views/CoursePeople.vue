<script setup lang="ts">
import { ref } from "vue";
import { t } from "../../i18n";
import { call, key, type Member } from "../../classroom-api";
const props = defineProps<{ courseId: string }>();
const people = ref<Member[]>([]),
  error = ref(""),
  busy = ref(false),
  showForm = ref(false);
const form = ref({ name: "", email: "", password: "", role: "student" });
const importRows = ref<
  { name: string; email: string; password: string; role: string }[]
>([]);
const importPassword = ref("");
function parseCsv(source: string) {
  const rows: string[][] = [];
  let row: string[] = [],
    field = "",
    quoted = false;
  for (let index = 0; index < source.length; index++) {
    const value = source[index];
    if (value === '"') {
      if (quoted && source[index + 1] === '"') {
        field += '"';
        index++;
      } else quoted = !quoted;
    } else if (value === "," && !quoted) {
      row.push(field.trim());
      field = "";
    } else if ((value === "\n" || value === "\r") && !quoted) {
      if (value === "\r" && source[index + 1] === "\n") index++;
      row.push(field.trim());
      if (row.some(Boolean)) rows.push(row);
      row = [];
      field = "";
    } else field += value;
  }
  if (quoted) throw Error(t("The CSV contains an unclosed quoted field."));
  row.push(field.trim());
  if (row.some(Boolean)) rows.push(row);
  return rows;
}
async function readImport(event: Event) {
  const input = event.target as HTMLInputElement,
    file = input.files?.[0];
  if (!file) return;
  error.value = "";
  try {
    if (file.size > 1024 * 1024)
      throw Error(t("The roster file must be smaller than 1 MB."));
    const rows = parseCsv((await file.text()).replace(/^\uFEFF/, ""));
    const header = rows.shift()?.map((cell) => cell.toLowerCase()) || [];
    const nameIndex = header.findIndex((cell) =>
      ["name", "姓名"].includes(cell),
    );
    const emailIndex = header.findIndex((cell) =>
      ["email", "邮箱"].includes(cell),
    );
    const passwordIndex = header.findIndex((cell) =>
      ["password", "密码"].includes(cell),
    );
    if (nameIndex < 0 || emailIndex < 0 || !rows.length || rows.length > 1000)
      throw Error(
        t("Use name and email columns, with 1 to 1,000 student rows."),
      );
    importRows.value = rows.map((row) => ({
      name: row[nameIndex] || "",
      email: row[emailIndex] || "",
      password: row[passwordIndex] || "",
      role: "student",
    }));
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    input.value = "";
  }
}
async function commitImport() {
  await action(async () => {
    await call(`/courses/${key(props.courseId)}/members/batch`, "POST", {
      members: importRows.value.map((row) => ({
        ...row,
        password: row.password || importPassword.value || null,
      })),
    });
    importRows.value = [];
    importPassword.value = "";
  });
}
async function load() {
  people.value = await call<Member[]>(
    `/courses/${key(props.courseId)}/members`,
  );
}
async function action(fn: () => Promise<void>) {
  busy.value = true;
  error.value = "";
  try {
    await fn();
    await load();
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
async function add() {
  await action(async () => {
    await call(`/courses/${key(props.courseId)}/members`, "POST", {
      ...form.value,
      password: form.value.password || null,
    });
    showForm.value = false;
    form.value = { name: "", email: "", password: "", role: "student" };
  });
}
async function archive(person: Member) {
  if (
    !window.confirm(
      t(
        person.membershipArchived
          ? "Restore this course membership?"
          : "Archive this course membership? Learning records will be retained.",
      ),
    )
  )
    return;
  await action(async () => {
    await call(
      `/courses/${key(props.courseId)}/members/${key(person.id)}/archive?archived=${!person.membershipArchived}`,
      "POST",
    );
  });
}
void load().catch((e) => (error.value = e.message));
</script>
<template>
  <header class="page-heading">
    <div>
      <p class="eyebrow">{{ t("PEOPLE & CLASSES") }}</p>
      <h1>{{ t("Manage class") }}</h1>
      <p class="muted">
        {{ t("Manage students and teaching staff for this course.") }}
      </p>
    </div>
    <div class="row">
      <label class="button"
        >{{ t("Import student CSV")
        }}<input
          type="file"
          accept=".csv,text/csv"
          hidden
          :disabled="busy"
          @change="readImport" /></label
      ><button class="primary" @click="showForm = true">
        ＋ {{ t("Add member") }}
      </button>
    </div>
  </header>
  <p v-if="error" class="error" role="alert">{{ error }}</p>
  <section class="panel table-wrap">
    <table>
      <thead>
        <tr>
          <th>{{ t("Name") }}</th>
          <th>{{ t("Email") }}</th>
          <th>{{ t("Role") }}</th>
          <th>{{ t("Status") }}</th>
          <th>{{ t("Actions") }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="person in people" :key="person.id">
          <td>{{ person.name }}</td>
          <td>{{ person.email }}</td>
          <td>
            {{ t(person.membershipRole === "student" ? "Student" : "Teacher") }}
          </td>
          <td>{{ t(person.membershipArchived ? "Archived" : "Active") }}</td>
          <td>
            <button :disabled="busy" @click="archive(person)">
              {{ t(person.membershipArchived ? "Restore" : "Archive") }}
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </section>
  <div v-if="showForm" class="modal-backdrop" @click.self="showForm = false">
    <form
      class="modal form-stack"
      role="dialog"
      aria-modal="true"
      :aria-label="t('Add member')"
      @submit.prevent="add"
    >
      <h2>{{ t("Add member") }}</h2>
      <label
        >{{ t("Name")
        }}<input v-model="form.name" required maxlength="100" /></label
      ><label
        >{{ t("Email")
        }}<input v-model="form.email" type="email" required /></label
      ><label
        >{{ t("Role")
        }}<select v-model="form.role">
          <option value="student">{{ t("Student") }}</option>
          <option value="teacher">{{ t("Teacher") }}</option>
        </select></label
      ><label v-if="form.role === 'student'"
        >{{ t("Temporary password for a new student")
        }}<input
          v-model="form.password"
          type="password"
          minlength="8"
          autocomplete="new-password"
        /><small>{{
          t(
            "Leave blank when adding an existing account. New students must change this password after signing in.",
          )
        }}</small></label
      >
      <p v-else class="muted">
        {{
          t(
            "Teaching staff must already have a teacher or administrator account.",
          )
        }}
      </p>
      <div class="row end">
        <button type="button" @click="showForm = false">
          {{ t("Cancel") }}</button
        ><button class="primary" :disabled="busy">{{ t("Add") }}</button>
      </div>
    </form>
  </div>
  <div
    v-if="importRows.length"
    class="modal-backdrop"
    @click.self="importRows = []"
  >
    <form
      class="modal wide form-stack"
      role="dialog"
      aria-modal="true"
      :aria-label="t('Review student import')"
      @submit.prevent="commitImport"
    >
      <h2>{{ t("Review student import") }}</h2>
      <p class="muted">
        {{
          t(
            "Existing accounts are added to this course. New student accounts require a temporary password.",
          )
        }}
      </p>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>{{ t("Name") }}</th>
              <th>{{ t("Email") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, index) in importRows" :key="index">
              <td>
                <input v-model="row.name" required :aria-label="t('Name')" />
              </td>
              <td>
                <input
                  v-model="row.email"
                  type="email"
                  required
                  :aria-label="t('Email')"
                />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <label
        >{{ t("Temporary password for new accounts without a password column")
        }}<input
          v-model="importPassword"
          type="password"
          minlength="8"
          autocomplete="new-password"
      /></label>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <div class="row end">
        <button type="button" @click="importRows = []">{{ t("Cancel") }}</button
        ><button class="primary" :disabled="busy">
          {{ t("Import {0} students", [importRows.length]) }}
        </button>
      </div>
    </form>
  </div>
</template>
