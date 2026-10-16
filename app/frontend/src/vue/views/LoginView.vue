<script setup lang="ts">
import { ref } from "vue";
import { ArrowRight, BookOpen } from "lucide-vue-next";
import { api } from "../../api";
import type { Bootstrap, Role } from "../../types";
import { useTask } from "../state";
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
      <img src="/aicademiya-mark.svg" alt="" /><span>AIcademiya</span>
    </header>
    <div class="login-layout">
      <section class="login-copy">
        <p class="eyebrow">A SPACE TO THINK, ASK & LEARN</p>
        <h1>Good questions.<br />Deeper understanding.</h1>
        <p>
          Bring your course materials, questions and learning conversations
          together in one clear workspace.
        </p>
        <div class="login-detail">
          <BookOpen :size="20" /><span
            >For teachers who guide.<br />For students who explore.</span
          >
        </div>
      </section>
      <section class="login-card">
        <p class="eyebrow">WELCOME</p>
        <h2>
          {{ register ? "Create your account" : "Sign in to your workspace" }}
        </h2>
        <FeedbackNotice :error="error" />
        <form @submit.prevent="login()">
          <label v-if="register"
            >Your name<input
              v-model="name"
              required
              autocomplete="name" /></label
          ><label
            >Email address<input
              v-model="email"
              type="email"
              required
              autocomplete="username"
              placeholder="you@example.com" /></label
          ><label
            >Password<input
              v-model="password"
              type="password"
              required
              :autocomplete="register ? 'new-password' : 'current-password'"
              minlength="8" /></label
          ><label v-if="register"
            >Course invitation code<input v-model="code" required /></label
          ><button class="primary full" :disabled="busy">
            {{
              busy ? "Please wait…" : register ? "Create account" : "Sign in"
            }}
            <ArrowRight :size="16" />
          </button>
        </form>
        <button
          v-if="bootstrap?.registration_enabled"
          class="link-button"
          @click="register = !register"
        >
          {{
            register
              ? "Already have an account? Sign in"
              : "Join with a course invitation"
          }}
        </button>
        <div v-if="bootstrap?.demo_enabled" class="demo-signin">
          <strong>Explore the local demo</strong>
          <p>Synthetic accounts and course content.</p>
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
                  ? "Admin"
                  : role === "teacher"
                    ? "Teacher"
                    : "Student"
              }}
            </button>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>
