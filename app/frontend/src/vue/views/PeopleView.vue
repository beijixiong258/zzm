<script setup lang="ts">
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
import { courses, user, useTask } from "../state";
import PageHeader from "../components/PageHeader.vue";
import ItemRow from "../components/ItemRow.vue";
import EditorDialog from "../components/EditorDialog.vue";
import FeedbackNotice from "../components/FeedbackNotice.vue";
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
        throw Error("The role change could not be verified.");
    } else if (modal.value === "staff") {
      await accountApi.addStaff(props.courseId!, staffId.value);
      staff.value = await accountApi.staff(props.courseId!);
    } else {
      if (
        (!props.courseId || password.value) &&
        (!/[A-Za-z]/.test(password.value) || !/[0-9]/.test(password.value))
      )
        throw Error("Use a temporary password with letters and numbers.");
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
  }, "Saved.");
  if (ok) {
    modal.value = null;
    password.value = "";
    await load();
  }
}
async function enrollment(r: RosterEntry) {
  if (
    !(await askConfirm(
      `${archived.value ? "Restore" : "Remove"} ${r.user.name} ${archived.value ? "to" : "from"} this course?`,
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
      ? "Enrollment restored."
      : "Student removed from this course.",
  );
}
async function status(a: GlobalAccount) {
  if (
    !(await askConfirm(
      `${a.active ? "Disable" : "Enable"} the account for ${a.user.name}?`,
    ))
  )
    return;
  await run(async () => {
    await accountApi.status(a.user.id, !a.active);
    const updated = await accountApi.get(a.user.id);
    if (updated.active === a.active)
      throw Error("Account status could not be verified.");
    accounts.value = accounts.value.map((x) =>
      x.user.id === a.user.id ? updated : x,
    );
  }, "Account status updated.");
}
async function removeStaff(uid: string, primary = false) {
  if (
    !(await askConfirm(
      primary
        ? "Transfer primary responsibility to this person?"
        : "Remove this teaching assignment?",
    ))
  )
    return;
  await run(async () => {
    if (primary) await accountApi.primary(props.courseId!, uid);
    else await accountApi.removeStaff(props.courseId!, uid);
    staff.value = await accountApi.staff(props.courseId!);
  }, "Teaching assignment updated.");
}
</script>
<template>
  <PageHeader
    :level="embedded ? 2 : 1"
    :title="courseId ? 'Course people' : 'User accounts'"
    :eyebrow="
      embedded
        ? undefined
        : courseId
          ? courses.find((c) => c.id === courseId)?.code
          : 'ADMINISTRATION'
    "
    :description="
      courseId
        ? 'Manage students and teaching assignments.'
        : 'Manage platform accounts and their roles.'
    "
    ><button
      v-if="tab !== 'staff'"
      class="primary"
      :disabled="busy"
      @click="open('new')"
    >
      <Plus :size="16" /> {{ courseId ? "Add student" : "New account" }}</button
    ><button v-if="tab !== 'staff'" class="secondary" @click="open('import')">
      Import accounts</button
    ><button
      v-if="tab === 'staff' && user?.role === 'admin'"
      class="primary"
      @click="open('staff')"
    >
      Add teaching staff
    </button></PageHeader
  >
  <nav v-if="courseId" class="tabs" aria-label="Course people">
    <button
      :disabled="busy"
      :class="{ active: tab === 'students' }"
      @click="tab = 'students'"
    >
      Students</button
    ><button
      :disabled="busy"
      :class="{ active: tab === 'staff' }"
      @click="tab = 'staff'"
    >
      Teaching staff
    </button>
  </nav>
  <FeedbackNotice
    :error="modal ? '' : error"
    :success="success"
    :busy="busy && !modal"
  />
  <template v-if="tab !== 'staff'"
    ><form
      class="filter-bar"
      @submit.prevent="
        offset = 0;
        load();
      "
    >
      <label class="grow"
        >Search {{ courseId ? "students" : "accounts"
        }}<input v-model="query" placeholder="Name or email" /></label
      ><label v-if="!courseId"
        >Role<select
          v-model="roleFilter"
          @change="
            offset = 0;
            load();
          "
        >
          <option value="">All roles</option>
          <option value="student">Student</option>
          <option value="teacher">Teacher</option>
          <option value="admin">Administrator</option>
        </select></label
      ><label v-else
        >Status<select v-model="archived" :disabled="busy">
          <option :value="false">Enrolled</option>
          <option :value="true">Removed</option>
        </select></label
      ><button class="secondary" :disabled="busy">Search</button>
    </form>
    <div class="item-list">
      <template v-if="courseId"
        ><ItemRow
          v-for="r in filtered"
          :key="r.user.id"
          :title="r.user.name"
          :description="r.user.email"
          ><template #meta
            ><span class="badge">{{ archived ? "Removed" : "Enrolled" }}</span
            ><span v-if="r.has_work">Learning records retained</span></template
          ><template #actions
            ><button
              class="secondary"
              :class="{ danger: !archived }"
              :disabled="busy"
              @click="enrollment(r)"
            >
              {{ archived ? "Restore" : "Remove" }}
            </button></template
          ></ItemRow
        >
        <div v-if="!filtered.length && !busy" class="empty-state">
          No matching students.
        </div></template
      ><template v-else
        ><p class="list-caption">{{ total }} accounts</p>
        <ItemRow
          v-for="a in accounts"
          :key="a.user.id"
          :title="a.user.name"
          :description="a.user.email"
          ><template #meta
            ><span class="badge">{{ a.user.role }}</span
            ><span class="badge" :class="a.active ? 'positive' : 'neutral'">{{
              a.active ? "Active" : "Disabled"
            }}</span
            ><span v-if="a.user.is_demo">Demo account</span></template
          ><template #actions
            ><button
              class="secondary"
              :disabled="busy || a.user.is_demo"
              @click="open('edit', a.user.id)"
            >
              Edit role</button
            ><button
              class="secondary"
              :class="{ danger: a.active }"
              :disabled="busy || a.user.is_demo || a.user.id === user?.id"
              @click="status(a)"
            >
              {{ a.active ? "Disable" : "Enable" }}
            </button></template
          ></ItemRow
        >
        <div v-if="!accounts.length && !busy" class="empty-state">
          No matching accounts.
        </div>
        <div class="pagination">
          <button
            class="secondary"
            :disabled="busy || offset === 0"
            @click="
              offset -= 20;
              load();
            "
          >
            Previous</button
          ><span
            >{{ total ? offset + 1 : 0 }}–{{ Math.min(offset + 20, total) }} of
            {{ total }}</span
          ><button
            class="secondary"
            :disabled="busy || offset + 20 >= total"
            @click="
              offset += 20;
              load();
            "
          >
            Next
          </button>
        </div></template
      >
    </div></template
  >
  <div v-else class="item-list">
    <ItemRow
      v-for="member in staff?.staff"
      :key="member.user.id"
      :title="member.user.name"
      :description="member.user.email"
      ><template #meta
        ><span class="badge">{{ member.user.role }}</span
        ><span v-if="member.is_primary" class="badge positive"
          >Primary responsibility</span
        ></template
      ><template v-if="user?.role === 'admin' && !member.is_primary" #actions
        ><button
          class="secondary"
          :disabled="busy"
          @click="removeStaff(member.user.id, true)"
        >
          Make primary</button
        ><button
          class="secondary danger"
          :disabled="busy"
          @click="removeStaff(member.user.id)"
        >
          Remove
        </button></template
      ></ItemRow
    >
  </div>
  <EditorDialog
    v-if="modal"
    :title="
      modal === 'import'
        ? 'Import accounts'
        : modal === 'staff'
          ? 'Add teaching staff'
          : modal === 'edit'
            ? 'Edit account role'
            : courseId
              ? 'Add student'
              : 'New account'
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
          >Staff member<select v-model="staffId" required>
            <option value="">Select a teacher or administrator</option>
            <option v-for="u in candidates" :key="u.id" :value="u.id">
              {{ u.name }} · {{ u.email }}
            </option>
          </select></label
        ></template
      ><template v-else
        ><template v-if="modal === 'edit'"
          ><p>{{ detail?.user.name }} · {{ detail?.user.email }}</p>
          <p class="notice warning">
            Changing a global role may affect course responsibilities and
            access.
          </p></template
        ><template v-else
          ><label>Name<input v-model="name" required maxlength="120" /></label
          ><label>Email<input v-model="email" type="email" required /></label
          ><label
            >Temporary password<input
              v-model="password"
              type="password"
              autocomplete="new-password"
              minlength="8"
              :required="!courseId"
            /><small
              >At least 8 characters with letters and numbers. The user changes
              it on first sign-in.</small
            ></label
          ></template
        ><label v-if="!courseId"
          >Role<select v-model="role">
            <option value="student">Student</option>
            <option value="teacher">Teacher</option>
            <option value="admin">Administrator</option>
          </select></label
        ></template
      >
    </form>
    <template v-if="modal !== 'import'" #actions
      ><button class="primary" form="person-editor" :disabled="busy">
        Save
      </button></template
    ></EditorDialog
  >
</template>
