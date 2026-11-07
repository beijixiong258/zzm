<script setup lang="ts">
import {
  Button as TButton,
  DatePicker as TDatePicker,
  InputNumber as TInputNumber,
  RadioGroup as TRadioGroup,
  Select as TSelect,
  TimePicker as TTimePicker,
} from "tdesign-vue-next";
import { computed, ref } from "vue";
import { locale, systemText, t } from "../i18n";
import type { TaskSchedule } from "../classroom-api";
import AppDialog from "./AppDialog.vue";

const props = defineProps<{
  title: string;
  submitLabel: string;
  current?: TaskSchedule;
  busy: boolean;
  error: string;
}>();
const emit = defineEmits<{ close: []; submit: [schedule: TaskSchedule] }>();
const mode = ref(props.current?.closesAt ? "deadline" : "");
const initialTime = Date.parse(props.current?.closesAt || "");
function localDateTime(value: Date) {
  return new Date(
    value.getTime() - value.getTimezoneOffset() * 60000,
  ).toISOString();
}
const initialLocal =
  initialTime > Date.now() ? localDateTime(new Date(initialTime)) : "";
const date = ref(initialLocal.slice(0, 10));
const time = ref(initialLocal.slice(11, 16));
const duration = ref<number | undefined>();
const units = { minutes: 60000, hours: 3600000, days: 86400000 };
const durationUnit = ref<keyof typeof units>("hours");
const localError = ref("");
const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
const canSubmit = computed(() =>
  mode.value === "duration"
    ? Number.isInteger(duration.value) &&
      duration.value! >= 1 &&
      duration.value! <= 9999
    : mode.value === "deadline" && !!date.value && !!time.value,
);

function submitSchedule() {
  if (props.busy || !canSubmit.value) return;
  const now = Date.now();
  const local = date.value + "T" + time.value;
  const instant =
    mode.value === "duration"
      ? new Date(now + duration.value! * units[durationUnit.value])
      : new Date(local);
  if (
    !Number.isFinite(instant.getTime()) ||
    instant.getTime() <= now ||
    (mode.value === "deadline" && localDateTime(instant).slice(0, 16) !== local)
  ) {
    localError.value = t("Choose a valid time in the future.");
    return;
  }
  localError.value = "";
  emit("submit", { closesAt: instant.toISOString() });
}
</script>

<template>
  <AppDialog :title="title" :busy="busy" @close="emit('close')">
    <form
      class="form-stack task-schedule-form"
      @submit.prevent="submitSchedule"
    >
      <fieldset>
        <legend>{{ t("Choose a schedule") }}</legend>
        <TRadioGroup
          v-model="mode"
          class="task-schedule-modes"
          :disabled="busy"
          :options="[
            { value: 'deadline', label: t('Set a deadline') },
            { value: 'duration', label: t('Set a duration') },
          ]"
          @change="localError = ''"
        />
      </fieldset>
      <p v-if="mode" class="muted">
        {{ t("The task opens immediately and closes at the deadline.") }}
      </p>
      <fieldset v-if="mode === 'deadline'">
        <legend>{{ t("Closing time") }}</legend>
        <div class="task-schedule-fields">
          <label>
            {{ t("Date") }}
            <TDatePicker
              :value="date"
              :format="locale === 'en' ? 'DD/MM/YYYY' : 'YYYY-MM-DD'"
              :disabled="busy || !mode"
              :popup-props="{ overlayClassName: 'task-schedule-picker' }"
              :placeholder="t('Select a date')"
              value-type="YYYY-MM-DD"
              allow-input
              clearable
              @change="
                (value) => {
                  date = typeof value === 'string' ? value : '';
                  localError = '';
                }
              "
            />
          </label>
          <label>
            {{ t("Time") }}
            <TTimePicker
              v-model="time"
              :disabled="busy || !mode"
              :popup-props="{ overlayClassName: 'task-schedule-picker' }"
              :placeholder="t('Select a time')"
              format="HH:mm"
              allow-input
              clearable
              @change="localError = ''"
            />
          </label>
        </div>
        <small class="muted">{{ t("Time zone: {0}", [timeZone]) }}</small>
      </fieldset>
      <fieldset v-if="mode === 'duration'">
        <legend>{{ t("Availability duration") }}</legend>
        <div class="task-schedule-fields">
          <label>
            {{ t("Length") }}
            <TInputNumber
              v-model="duration"
              :min="1"
              :max="9999"
              :decimal-places="0"
              :disabled="busy"
              @change="localError = ''"
            />
          </label>
          <label>
            {{ t("Unit") }}
            <TSelect
              v-model="durationUnit"
              :disabled="busy"
              :options="[
                { value: 'minutes', label: t('Minutes') },
                { value: 'hours', label: t('Hours') },
                { value: 'days', label: t('Days') },
              ]"
            />
          </label>
        </div>
        <small class="muted">{{
          t("The duration starts when you confirm.")
        }}</small>
      </fieldset>
      <p v-if="localError || error" role="alert" class="error">
        {{ localError || systemText(error) }}
      </p>
      <div class="row wrap end">
        <TButton
          theme="default"
          variant="outline"
          type="button"
          :disabled="busy"
          @click="emit('close')"
        >
          {{ t("Cancel") }}
        </TButton>
        <TButton
          theme="primary"
          type="submit"
          :loading="busy"
          :disabled="busy || !canSubmit"
        >
          {{ submitLabel }}
        </TButton>
      </div>
    </form>
  </AppDialog>
</template>

<style scoped>
.task-schedule-form > p {
  margin: 0;
}
.task-schedule-modes {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 18px;
  margin-top: 6px;
}
.task-schedule-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin: 6px 0;
}
.task-schedule-fields > label {
  min-width: 0;
}
@media (max-width: 440px) {
  .task-schedule-fields {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
