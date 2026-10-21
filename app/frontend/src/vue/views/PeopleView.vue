<script setup lang="ts">
import { t } from "../../i18n";

import { askConfirm } from "../state";
import { computed, ref, watch } from "vue";
import { Plus } from "lucide-vue-next";
import { api } from "../../api";
import { accountApi } from "../../account-management-api";
import type { RosterEntry, Role, User } from "../../types";
import type {
  AccountDetail,
  GlobalAccount,
  StaffResponse,
} from "../../account-management-types";
import { courses, user, useTask, label } from "../state";
import PageHeader from "../components/PageHeader.vue";
import ItemRow from "../components/ItemRow.vue";
import EditorDialog from "../components/EditorDialog.vue";
import FeedbackNotice from "../components/FeedbackNotice.vue";
import FilterBar from "../components/FilterBar.vue";
import Pagination from "../components/Pagination.vue";
import PeopleImport from "../components/PeopleImport.vue";
const props = defineProps<{ courseId?: string; embedded?: boolean }>();
const { busy, error, success, run } = useTask();
const tab = ref("students"),
  query = ref(""),
  roleFilter = ref(""),
  archived = ref(false),
  offset = ref(0),
  total = ref(0),
  roster = ref<RosterEntry[]>([]),
  accounts = ref<GlobalAccount[]>([]),
  staff = ref<StaffResponse | null>(null),
  candidates = ref<User[]>([]);
const modal = ref<"new" | "edit" | "import" | "staff" | null>(null),
  detail = ref<AccountDetail | null>(null),
  name = ref(""),
  email = ref(""),
  password = ref(""),
  role = ref<Role>("student"),
  staffId = ref(""),
  initial = ref(""),
  importHeld = ref(false),
  importDirty = ref(false);
const formKey = computed(() =>
  JSON.stringify([
    name.value,
    email.value,
    password.value,
    role.value,
    staffId.value,
  ]),
);
const dirty = computed(() => formKey.value !== initial.value);
const filtered = computed(() =>
  roster.value.filter((r) =>
    `${r.user.name} ${r.user.email}`
      .toLowerCase()
      .includes(query.value.toLowerCase()),
  ),
);
async function load() {
  await run(async () => {
    if (props.courseId) {
      if (tab.value === "staff")
        staff.value = await accountApi.staff(props.courseId);
      else roster.value = await api.roster(props.courseId, archived.value);
    } else {
      const page = await accountApi.list({
        q: query.value,
        role: (roleFilter.value || undefined) as Role | undefined,
        offset: offset.value,
        limit: 20,
      });
      accounts.value = page.items;
      total.value = page.total;
    }
  });
}
void load();
watch([tab, archived], () => {
  void load();
});
async function open(kind: typeof modal.value, uid?: string) {
  modal.value = kind;
  error.value = "";
  name.value = "";
  email.value = "";
  password.value = "";
  role.value = "student";
  staffId.value = "";
  detail.value = null;
  if (kind === "edit" && uid)
    await run(async () => {
      detail.value = await accountApi.get(uid);
      role.value = detail.value.user.role;
    });
  if (kind === "staff")
    await run(async () => {
      const [a, b] = await Promise.all([
        accountApi.list({ role: "teacher", active: true, limit: 100 }),
        accountApi.list({ role: "admin", active: true, limit: 100 }),
      ]);
      candidates.value = [...a.items, ...b.items]
        .map((a) => a.user)
        .filter((u) => !staff.value?.staff.some((m) => m.user.id === u.id));
    });
  initial.value = formKey.value;
}
async function save() {
  const ok = await run(async () => {
    if (modal.value === "edit" && detail.value) {
      await accountApi.role(detail.value.user.id, role.value);
      const got = await accountApi.get(detail.value.user.id);
      if (got.user.role !== role.value)
        throw Error(t("The role change could not be verified."));
    } else if (modal.value === "staff") {
      await accountApi.addStaff(props.courseId!, staffId.value);
      staff.value = await accountApi.staff(props.courseId!);
    } else {
      if (
        (!props.courseId || password.value) &&
        (!/[A-Za-z]/.test(password.value) || !/[0-9]/.test(password.value))
      )
        throw Error(t("Use a temporary password with letters and numbers."));
      if (props.courseId) {
        await api.provisionStudent(props.courseId, {
          name: name.value,
          email: email.value,
          temporary_password: password.value,
        });
        roster.value = await api.roster(props.courseId, archived.value);
      } else {
        const created = await accountApi.create({
          name: name.value,
          email: email.value,
          role: role.value,
          temporary_password: password.value,
        });
        await accountApi.get(created.user.id);
      }
    }
  }, t("Saved."));
  if (ok) {
    modal.value = null;
    password.value = "";
    await load();
  }
}
async function enrollment(r: RosterEntry) {
  if (
    !(await askConfirm(
      t(
        archived.value
          ? "Restore {0} to this course?"
          : "Remove {0} from this course?",
        [r.user.name],
      ),
      {
        title: archived.value
          ? t("Restore enrollment")
          : t("Remove enrollment"),
        confirmLabel: archived.value ? t("Restore") : t("Remove"),
        danger: !archived.value,
      },
    ))
  )
    return;
  await run(
    async () => {
      await api.rosterAction(
        archived.value ? "restore" : "archive",
        [r.user.id],
        props.courseId,
      );
      roster.value = await api.roster(props.courseId, archived.value);
    },
    archived.value
      ? t("Enrollment restored.")
      : t("Student removed from this course."),
  );
}
async function status(a: GlobalAccount) {
  if (
    !(await askConfirm(
      t("{0} the account for {1}?", [
        a.active ? t("Disable") : t("Enable"),
        a.user.name,
      ]),
      {
        title: t("Account status"),
        confirmLabel: a.active ? t("Disable") : t("Enable"),
        danger: a.active,
      },
    ))
  )
    return;
  await run(async () => {
    await accountApi.status(a.user.id, !a.active);
    const updated = await accountApi.get(a.user.id);
    if (updated.active === a.active)
      throw Error(t("Account status could not be verified."));
    accounts.value = accounts.value.map((x) =>
      x.user.id === a.user.id ? updated : x,
    );
  }, t("Account status updated."));
}
async function removeStaff(uid: string, primary = false) {
  if (
    !(await askConfirm(
      primary
        ? t("Transfer primary responsibility to this person?")
        : t("Remove this teaching assignment?"),
      {
        title: t("Teaching assignment"),
        confirmLabel: primary ? t("Transfer responsibility") : t("Remove"),
        danger: true,
      },
    ))
  )
    return;
  await run(async () => {
    if (primary) await accountApi.primary(props.courseId!, uid);
    else await accountApi.removeStaff(props.courseId!, uid);
    staff.value = await accountApi.staff(props.courseId!);
  }, t("Teaching assignment updated."));
}
</script>
<template>
  <PageHeader
    :level="embedded ? 2 : 1"
    :title="courseId ? t('Course people') : t('User accounts')"
    :eyebrow="
      embedded
        ? undefined
        : courseId
          ? courses.find((c) => c.id === courseId)?.code
          : t('ADMINISTRATION')
    "
    :description="
      courseId
        ? t('Manage students and teaching assignments.')
        : t('Manage platform accounts and their roles.')
    "
    ><button
      v-if="tab !== 'staff'"
      class="primary"
      :disabled="busy"
      @click="open('new')"
    >
      <Plus :size="16" />
      {{ courseId ? t("Add student") : t("New account") }}</button
    ><button v-if="tab !== 'staff'" class="secondary" @click="open('import')">
      {{ t("Import accounts") }}</button
    ><button
      v-if="tab === 'staff' && user?.role === 'admin'"
      class="primary"
      @click="open('staff')"
    >
      {{ t("Add teaching staff") }}
    </button></PageHeader
  >
  <nav v-if="courseId" class="tabs" :aria-label="t('Course people')">
    <button
      :disabled="busy"
      :class="{ active: tab === 'students' }"
      @click="tab = 'students'"
    >
      {{ t("Students") }}</button
    ><button
      :disabled="busy"
      :class="{ active: tab === 'staff' }"
      @click="tab = 'staff'"
    >
      {{ t("Teaching staff") }}
    </button>
  </nav>
  <FeedbackNotice
    :error="modal ? '' : error"
    :success="success"
    :busy="busy && !modal"
  />
  <template v-if="tab !== 'staff'"
    ><FilterBar :active="!!query || !!roleFilter || archived"
      ><form
        class="filter-form"
        @submit.prevent="
          offset = 0;
          load();
        "
      >
        <label class="grow"
          >{{ t(courseId ? "Search students" : "Search accounts")
          }}<input v-model="query" :placeholder="t('Name or email')" /></label
        ><label v-if="!courseId"
          >{{ t("Role")
          }}<select
            v-model="roleFilter"
            @change="
              offset = 0;
              load();
            "
          >
            <option value="">{{ t("All roles") }}</option>
            <option value="student">{{ t("Student") }}</option>
            <option value="teacher">{{ t("Teacher") }}</option>
            <option value="admin">{{ t("Administrator") }}</option>
          </select></label
        ><label v-else
          >{{ t("Status")
          }}<select v-model="archived" :disabled="busy">
            <option :value="false">{{ t("Enrolled") }}</option>
            <option :value="true">{{ t("Removed") }}</option>
          </select></label
        ><button v-if="!courseId" class="secondary" :disabled="busy">
          {{ t("Search") }}
        </button>
      </form></FilterBar
    >
    <div class="item-list">
      <template v-if="courseId"
        ><ItemRow
          v-for="r in filtered"
          :key="r.user.id"
          :title="r.user.name"
          :description="r.user.email"
          ><template #meta
            ><span class="badge">{{
              archived ? t("Removed") : t("Enrolled")
            }}</span
            ><span v-if="r.has_work">{{
              t("Learning records retained")
            }}</span></template
          ><template #actions
            ><button
              class="secondary"
              :class="{ danger: !archived }"
              :disabled="busy"
              @click="enrollment(r)"
            >
              {{ archived ? t("Restore") : t("Remove") }}
            </button></template
          ></ItemRow
        >
        <div v-if="!filtered.length && !busy" class="empty-state">
          {{ t("No matching students.") }}
        </div></template
      ><template v-else
        ><p class="list-caption">{{ t("{0} accounts", [total]) }}</p>
        <ItemRow
          v-for="a in accounts"
          :key="a.user.id"
          :title="a.user.name"
          :description="a.user.email"
          ><template #meta
            ><span class="badge">{{ label(a.user.role) }}</span
            ><span class="badge" :class="a.active ? 'positive' : 'neutral'">{{
              a.active ? t("Active") : t("Disabled")
            }}</span
            ><span v-if="a.user.is_demo">{{
              t("Demo account")
            }}</span></template
          ><template #actions
            ><button
              class="secondary"
              :disabled="busy || a.user.is_demo"
              @click="open('edit', a.user.id)"
            >
              {{ t("Edit role") }}</button
            ><button
              class="secondary"
              :class="{ danger: a.active }"
              :disabled="busy || a.user.is_demo || a.user.id === user?.id"
              @click="status(a)"
            >
              {{ a.active ? t("Disable") : t("Enable") }}
            </button></template
          ></ItemRow
        >
        <div v-if="!accounts.length && !busy" class="empty-state">
          {{ t("No matching accounts.") }}
        </div>
        <Pagination
          :offset="offset"
          :total="total"
          :busy="busy"
          @change="
            offset = $event;
            load();
          "
      /></template></div
  ></template>
  <div v-else class="item-list">
    <ItemRow
      v-for="member in staff?.staff"
      :key="member.user.id"
      :title="member.user.name"
      :description="member.user.email"
      ><template #meta
        ><span class="badge">{{ label(member.user.role) }}</span
        ><span v-if="member.is_primary" class="badge positive">{{
          t("Primary responsibility")
        }}</span></template
      ><template v-if="user?.role === 'admin' && !member.is_primary" #actions
        ><button
          class="secondary"
          :disabled="busy"
          @click="removeStaff(member.user.id, true)"
        >
          {{ t("Make primary") }}</button
        ><button
          class="secondary danger"
          :disabled="busy"
          @click="removeStaff(member.user.id)"
        >
          {{ t("Remove") }}
        </button></template
      ></ItemRow
    >
  </div>
  <EditorDialog
    v-if="modal"
    :title="
      modal === 'import'
        ? t('Import accounts')
        : modal === 'staff'
          ? t('Add teaching staff')
          : modal === 'edit'
            ? t('Edit account role')
            : courseId
              ? t('Add student')
              : t('New account')
    "
    :busy="busy || importHeld"
    :dirty="dirty || importDirty"
    @close="modal = null"
    ><FeedbackNotice :error="error" /><PeopleImport
      v-if="modal === 'import'"
      :course-id="courseId"
      @changed="load"
      @hold="importHeld = $event"
      @dirty="importDirty = $event"
    />
    <form v-else id="person-editor" class="form-stack" @submit.prevent="save">
      <template v-if="modal === 'staff'"
        ><label
          >{{ t("Staff member")
          }}<select v-model="staffId" required>
            <option value="">
              {{ t("Select a teacher or administrator") }}
            </option>
            <option v-for="u in candidates" :key="u.id" :value="u.id">
              {{ u.name }} · {{ u.email }}
            </option>
          </select></label
        ></template
      ><template v-else
        ><template v-if="modal === 'edit'"
          ><p>{{ detail?.user.name }} · {{ detail?.user.email }}</p>
          <p class="notice warning">
            {{
              t(
                "Changing a global role may affect course responsibilities and access.",
              )
            }}
          </p></template
        ><template v-else
          ><label
            >{{ t("Name")
            }}<input v-model="name" required maxlength="120" /></label
          ><label
            >{{ t("Email")
            }}<input v-model="email" type="email" required /></label
          ><label
            >{{ t("Temporary password")
            }}<input
              v-model="password"
              type="password"
              autocomplete="new-password"
              minlength="8"
              :required="!courseId"
            /><small>{{
              t(
                "At least 8 characters with letters and numbers. The user changes it on first sign-in.",
              )
            }}</small></label
          ></template
        ><label v-if="!courseId"
          >{{ t("Role")
          }}<select v-model="role">
            <option value="student">{{ t("Student") }}</option>
            <option value="teacher">{{ t("Teacher") }}</option>
            <option value="admin">{{ t("Administrator") }}</option>
          </select></label
        ></template
      >
    </form>
    <template v-if="modal !== 'import'" #actions
      ><button class="primary" form="person-editor" :disabled="busy">
        {{ t("Save") }}
      </button></template
    ></EditorDialog
  >
</template>
