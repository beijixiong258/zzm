<script setup lang="ts">
import { t } from "../../i18n";

import { ref } from "vue";
import { ArrowRight, BookOpen } from "lucide-vue-next";
import { api } from "../../api";
import type { Bootstrap, Role } from "../../types";
import { useTask } from "../state";
import LanguageSelect from "../components/LanguageSelect.vue";
import FeedbackNotice from "../components/FeedbackNotice.vue";
defineProps<{ bootstrap: Bootstrap | null }>();
const emit = defineEmits<{ authenticated: [] }>();
const email = ref(""),
  password = ref(""),
  name = ref(""),
  code = ref(""),
  register = ref(false);
const { busy, error, run } = useTask();
async function login(role?: Role) {
  await run(async () => {
    if (role) await api.demo(role);
    else if (register.value)
      await api.register(name.value, email.value, password.value, code.value);
    else await api.login(email.value, password.value);
    emit("authenticated");
  });
}
</script>
<template>
  <div class="login-page">
    <header class="login-brand brand">
      <img src="/aicademiya-mark.svg" alt="" /><span>AIcademiya</span
      ><LanguageSelect />
    </header>
    <div class="login-layout">
      <section class="login-copy">
        <p class="eyebrow">{{ t("A SPACE TO THINK, ASK & LEARN") }}</p>
        <h1>
          {{ t("Good questions.") }}<br />{{ t("Deeper understanding.") }}
        </h1>
        <p>
          {{
            t(
              "Bring your course materials, questions and learning conversations together in one clear workspace.",
            )
          }}
        </p>
        <div class="login-detail">
          <BookOpen :size="20" /><span
            >{{ t("For teachers who guide.") }}<br />{{
              t("For students who explore.")
            }}</span
          >
        </div>
      </section>
      <section class="login-card">
        <p class="eyebrow">{{ t("WELCOME") }}</p>
        <h2>
          {{
            register ? t("Create your account") : t("Sign in to your workspace")
          }}
        </h2>
        <FeedbackNotice :error="error" />
        <form @submit.prevent="login()">
          <label v-if="register"
            >{{ t("Your name")
            }}<input v-model="name" required autocomplete="name" /></label
          ><label
            >{{ t("Email address")
            }}<input
              v-model="email"
              type="email"
              required
              autocomplete="username"
              placeholder="you@example.com" /></label
          ><label
            >{{ t("Password")
            }}<input
              v-model="password"
              type="password"
              required
              :autocomplete="register ? 'new-password' : 'current-password'"
              minlength="8" /></label
          ><label v-if="register"
            >{{ t("Course invitation code")
            }}<input v-model="code" required /></label
          ><button class="primary full" :disabled="busy">
            {{
              busy
                ? t("Please wait…")
                : register
                  ? t("Create account")
                  : t("Sign in")
            }}
            <ArrowRight :size="16" />
          </button>
        </form>
        <p v-if="!register" class="muted">
          {{
            t(
              "Use the email address provided by your teacher or administrator. Contact them if you need a password reset.",
            )
          }}
        </p>
        <button
          v-if="bootstrap?.registration_enabled"
          class="link-button"
          @click="register = !register"
        >
          {{
            register
              ? t("Already have an account? Sign in")
              : t("Join with a course invitation")
          }}
        </button>
        <div v-if="bootstrap?.demo_enabled" class="demo-signin">
          <strong>{{ t("Explore the local demo") }}</strong>
          <p>{{ t("Synthetic accounts and course content.") }}</p>
          <div class="actions">
            <button
              v-for="role in ['teacher', 'student', 'admin'] as const"
              :key="role"
              class="secondary"
              :disabled="busy"
              @click="login(role)"
            >
              {{
                role === "admin"
                  ? t("Admin")
                  : role === "teacher"
                    ? t("Teacher")
                    : t("Student")
              }}
            </button>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>
