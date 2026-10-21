<script setup lang="ts">
import { t } from "../../i18n";

import { askConfirm } from "../state";
import { computed, ref, watch } from "vue";
import { api } from "../../api";
import { clientId } from "../../ids";
import type {
  FeedbackItem,
  FeedbackCategory,
  Settings,
  SearchSettings,
} from "../../types";
import {
  user,
  courses,
  route,
  navigate,
  useTask,
  dateText,
  label,
  refreshCourses,
  useDirty,
} from "../state";
import PageHeader from "../components/PageHeader.vue";
import FeedbackNotice from "../components/FeedbackNotice.vue";
import EditorDialog from "../components/EditorDialog.vue";
import ItemRow from "../components/ItemRow.vue";
import Pagination from "../components/Pagination.vue";
import PeopleView from "./PeopleView.vue";
const props = defineProps<{ forcePassword?: boolean }>();
const { busy, error, success, run } = useTask();
const section = computed(() =>
  props.forcePassword
    ? "password"
    : route.value.page === "accounts"
      ? "users"
      : route.value.section || "account",
);
const name = ref(user.value!.name),
  currentPassword = ref(""),
  newPassword = ref(""),
  passwordAgain = ref(""),
  courseId = ref(courses.value[0]?.id || "");
const feedback = ref<FeedbackItem[]>([]),
  offset = ref(0),
  total = ref(0),
  feedbackEditor = ref(false),
  subject = ref(""),
  message = ref(""),
  category = ref<FeedbackCategory>("general"),
  selected = ref<FeedbackItem | null>(null),
  reply = ref(""),
  requestId = ref("");
const model = ref<Settings | null>(null),
  search = ref<SearchSettings | null>(null);
useDirty(
  computed(
    () =>
      name.value !== user.value?.name ||
      !!currentPassword.value ||
      !!newPassword.value ||
      !!passwordAgain.value,
  ),
);
async function load() {
  await run(async () => {
    if (section.value === "feedback") {
      const page = await api.feedbackList(
        { offset: offset.value, limit: 20 },
        user.value!.role === "admin",
      );
      feedback.value = page.items;
      total.value = page.total;
    }
    if (["model", "search"].includes(section.value)) {
      [model.value, search.value] = await Promise.all([
        api.settings(),
        api.searchSettings(),
      ]);
    }
  });
}
watch(section, () => void load(), { immediate: true });
async function profile() {
  await run(async () => {
    await api.profile(name.value);
    user.value = (await api.me()).user;
  }, t("Profile saved."));
}
async function avatar(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0];
  if (file)
    await run(async () => {
      await api.uploadAvatar(file);
      user.value = (await api.me()).user;
    }, t("Photo updated."));
}
async function removeAvatar() {
  if (await askConfirm(t("Remove your profile photo?")))
    await run(async () => {
      await api.removeAvatar();
      user.value = (await api.me()).user;
    }, t("Photo removed."));
}
async function password() {
  if (newPassword.value !== passwordAgain.value) {
    error.value = t("The new passwords do not match.");
    return;
  }
  await run(async () => {
    await api.changePassword(currentPassword.value, newPassword.value);
    user.value = (await api.me()).user;
    currentPassword.value = "";
    newPassword.value = "";
    passwordAgain.value = "";
    await refreshCourses();
  }, t("Password updated."));
}
async function sendFeedback() {
  requestId.value = requestId.value || clientId();
  const ok = await run(async () => {
    await api.feedbackCreate({
      request_id: requestId.value,
      category: category.value,
      subject: subject.value,
      message: message.value,
    });
  }, t("Feedback saved."));
  if (ok) {
    feedbackEditor.value = false;
    subject.value = "";
    message.value = "";
    requestId.value = "";
    await load();
  }
}
async function reviewFeedback() {
  if (!selected.value) return;
  const ok = await run(async () => {
    await api.feedbackUpdate(selected.value!.id, {
      status: "reviewed",
      reply: reply.value,
      expected_revision: selected.value!.revision,
    });
  }, t("Reply saved."));
  if (ok) {
    selected.value = null;
    await load();
  }
}
</script>
<template>
  <template v-if="section === 'password'"
    ><PageHeader
      :title="t('Set your own password')"
      :description="
        t('Replace your temporary password to continue.')
      " /></template
  ><template v-else
    ><PageHeader
      :title="t('Settings')"
      :description="t('Manage your account and workspace.')"
    />
    <nav class="tabs" :aria-label="t('Settings sections')">
      <button
        v-for="[id, title] in [
          ['account', t('My account')],
          ['feedback', t('Feedback')],
          ...(user?.role !== 'student'
            ? [
                [
                  'users',
                  user?.role === 'admin'
                    ? t('User accounts')
                    : t('Course people'),
                ],
              ]
            : []),
          ...(user?.role === 'admin'
            ? [['model', t('Deployment information')]]
            : []),
        ]"
        :key="id"
        :class="{
          active: section === id || (id === 'model' && section === 'search'),
        }"
        @click="navigate({ page: 'settings', section: id as any })"
      >
        {{ title }}
      </button>
    </nav></template
  ><FeedbackNotice
    :error="feedbackEditor || selected ? '' : error"
    :success="success"
    :busy="busy && !feedbackEditor && !selected"
  />
  <div v-if="section === 'account'" class="settings-grid">
    <section class="panel">
      <h2>{{ t("Profile") }}</h2>
      <div class="profile-photo">
        <span class="avatar large"
          ><img
            v-if="user?.avatar_url"
            :src="user.avatar_url"
            :alt="t('Your profile photo')"
          /><template v-else>{{ user?.name.slice(0, 1) }}</template></span
        >
        <div>
          <label
            >{{ t("Profile photo")
            }}<input
              type="file"
              accept="image/png,image/jpeg,image/webp"
              :disabled="busy"
              @change="avatar" /></label
          ><button
            v-if="user?.avatar_url"
            class="link-button danger"
            @click="removeAvatar"
          >
            {{ t("Remove photo") }}
          </button>
        </div>
      </div>
      <form class="form-stack" @submit.prevent="profile">
        <label>{{ t("Name") }}<input v-model="name" required /></label
        ><label>{{ t("Email") }}<input :value="user?.email" readonly /></label
        ><button class="primary" :disabled="busy || name === user?.name">
          {{ t("Save profile") }}
        </button>
      </form>
    </section>
    <section class="panel">
      <h2>{{ t("Change password") }}</h2>
      <p v-if="user?.is_demo" class="muted">
        {{ t("Demo accounts use local demo sign-in and have no password.") }}
      </p>
      <form v-else class="form-stack" @submit.prevent="password">
        <label
          >{{ t("Current password")
          }}<input
            v-model="currentPassword"
            type="password"
            autocomplete="current-password"
            required /></label
        ><label
          >{{ t("New password")
          }}<input
            v-model="newPassword"
            type="password"
            autocomplete="new-password"
            minlength="8"
            required /></label
        ><label
          >{{ t("Repeat new password")
          }}<input
            v-model="passwordAgain"
            type="password"
            autocomplete="new-password"
            required /></label
        ><button class="primary" :disabled="busy">
          {{ t("Change password") }}
        </button>
      </form>
    </section>
  </div>
  <form
    v-else-if="section === 'password'"
    class="panel form-stack narrow"
    @submit.prevent="password"
  >
    <label
      >{{ t("Temporary password")
      }}<input
        v-model="currentPassword"
        type="password"
        autocomplete="current-password"
        required /></label
    ><label
      >{{ t("New password")
      }}<input
        v-model="newPassword"
        type="password"
        autocomplete="new-password"
        minlength="8"
        required /></label
    ><label
      >{{ t("Repeat new password")
      }}<input
        v-model="passwordAgain"
        type="password"
        autocomplete="new-password"
        required /></label
    ><button class="primary" :disabled="busy">{{ t("Set password") }}</button>
  </form>
  <section v-else-if="section === 'users'">
    <template v-if="user?.role === 'teacher'"
      ><label
        >{{ t("Course")
        }}<select v-model="courseId">
          <option v-for="c in courses" :key="c.id" :value="c.id">
            {{ c.code }} · {{ c.title }}
          </option>
        </select></label
      >
      <p class="muted">
        {{
          t("Manage students and teaching staff from the course people page.")
        }}
      </p>
      <button
        class="primary"
        :disabled="!courseId"
        @click="navigate({ page: 'roster', sid: courseId })"
      >
        {{ t("Open course people") }}
      </button></template
    ><PeopleView v-else embedded />
  </section>
  <section v-else-if="section === 'feedback'">
    <div class="section-header">
      <div>
        <h2>{{ t("Feedback") }}</h2>
        <p>
          {{
            user?.role === "admin"
              ? t("Review feedback from your workspace.")
              : t("Track your suggestions and reported issues.")
          }}
        </p>
      </div>
      <button class="primary" @click="feedbackEditor = true">
        {{ t("New feedback") }}
      </button>
    </div>
    <div class="item-list">
      <ItemRow
        v-for="f in feedback"
        :key="f.id"
        :title="f.subject"
        :description="f.message"
        ><template #meta
          ><span class="badge">{{ label(f.category) }}</span
          ><span>{{ f.status === "reviewed" ? t("Reviewed") : t("New") }}</span
          ><span>{{ dateText(f.created_at) }}</span
          ><span>{{ f.author?.name }}</span></template
        >
        <p v-if="f.reply" class="notice">{{ t("Reply:") }} {{ f.reply }}</p>
        <template v-if="user?.role === 'admin'" #actions
          ><button
            class="secondary"
            @click="
              selected = f;
              reply = f.reply;
            "
          >
            {{ t("Review") }}
          </button></template
        ></ItemRow
      >
      <div v-if="!feedback.length && !busy" class="empty-state">
        {{ t("No feedback yet.") }}
      </div>
    </div>
    <Pagination
      :offset="offset"
      :total="total"
      :busy="busy"
      @change="
        offset = $event;
        load();
      "
    />
  </section>
  <section v-else class="panel narrow">
    <h2>{{ t("Deployment information") }}</h2>
    <p class="notice">
      {{ t("Deployment settings are managed in") }} <strong>config.json</strong
      >{{ t(". Save the file and restart the local server to apply changes.") }}
    </p>
    <dl class="config-summary">
      <dt>{{ t("AI mode") }}</dt>
      <dd>
        {{
          model?.ai.mode === "demo"
            ? t("Demo responses")
            : t("Configured model service")
        }}
      </dd>
      <dt>{{ t("Model") }}</dt>
      <dd>{{ model?.ai.model || t("Not configured") }}</dd>
      <dt>{{ t("Endpoint") }}</dt>
      <dd>{{ model?.ai.base_url || t("Not configured") }}</dd>
      <dt>{{ t("API key") }}</dt>
      <dd>{{ model?.api_key_set ? t("Configured") : t("Not configured") }}</dd>
      <dt>{{ t("Web search") }}</dt>
      <dd>{{ search?.enabled ? t("Enabled") : t("Disabled") }}</dd>
    </dl>
    <p class="muted">
      {{
        t(
          "Ask the deployment administrator to change model, search or upload processing settings, then restart this application. Demo sign-in and demo AI responses are separate settings.",
        )
      }}
    </p>
    <p class="muted">
      {{
        t(
          "The interface does not display API keys or send connection tests automatically.",
        )
      }}
    </p>
  </section>
  <EditorDialog
    v-if="feedbackEditor"
    :title="t('New feedback')"
    :busy="busy"
    :dirty="!!subject || !!message"
    @close="feedbackEditor = false"
    ><FeedbackNotice :error="error" />
    <form id="feedback-form" class="form-stack" @submit.prevent="sendFeedback">
      <label
        >{{ t("Category")
        }}<select v-model="category">
          <option value="general">{{ t("General") }}</option>
          <option value="bug">{{ t("Issue") }}</option>
          <option value="idea">{{ t("Suggestion") }}</option>
        </select></label
      ><label
        >{{ t("Subject")
        }}<input v-model="subject" required maxlength="200" /></label
      ><label
        >{{ t("Message")
        }}<textarea v-model="message" rows="5" required maxlength="10000" />
      </label>
    </form>
    <template #actions
      ><button form="feedback-form" class="primary" :disabled="busy">
        {{ t("Submit feedback") }}
      </button></template
    ></EditorDialog
  ><EditorDialog
    v-if="selected"
    :title="t('Review feedback')"
    :busy="busy"
    :dirty="reply !== selected.reply"
    @close="selected = null"
    ><FeedbackNotice :error="error" />
    <h3>{{ selected.subject }}</h3>
    <p>{{ selected.message }}</p>
    <label>{{ t("Reply") }}<textarea v-model="reply" rows="4" /></label
    ><template #actions
      ><button class="primary" :disabled="busy" @click="reviewFeedback">
        {{ t("Save review") }}
      </button></template
    ></EditorDialog
  >
</template>
