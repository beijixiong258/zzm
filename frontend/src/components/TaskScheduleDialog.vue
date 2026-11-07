<script setup lang="ts">
import {
  Button as TButton,
  DatePicker as TDatePicker,
  RadioGroup as TRadioGroup,
  TimePicker as TTimePicker,
} from "tdesign-vue-next";
import { ref } from "vue";
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
const mode = ref(
  props.current?.opensAt ? "open" : props.current?.closesAt ? "close" : "",
);
const initialTime = Date.parse(
  props.current?.opensAt || props.current?.closesAt || "",
);
function localDateTime(value: Date) {
  return new Date(
    value.getTime() - value.getTimezoneOffset() * 60000,
  ).toISOString();
}
const initialLocal =
  initialTime > Date.now() ? localDateTime(new Date(initialTime)) : "";
const date = ref(initialLocal.slice(0, 10));
const time = ref(initialLocal.slice(11, 16));
const localError = ref("");
const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;

function submitSchedule() {
  if (props.busy || !mode.value || !date.value || !time.value) return;
  const local = date.value + "T" + time.value;
  const instant = new Date(local);
  if (
    !Number.isFinite(instant.getTime()) ||
    instant.getTime() <= Date.now() ||
    localDateTime(instant).slice(0, 16) !== local
  ) {
    localError.value = t("Choose a valid time in the future.");
    return;
  }
  localError.value = "";
  emit("submit", {
    opensAt: mode.value === "open" ? instant.toISOString() : null,
    closesAt: mode.value === "close" ? instant.toISOString() : null,
  });
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
            { value: 'open', label: t('Scheduled opening') },
            { value: 'close', label: t('Scheduled closing') },
          ]"
          @change="localError = ''"
        />
      </fieldset>
      <p v-if="mode" class="muted">
        {{
          t(
            mode === "open"
              ? "The task opens at this time and stays open until you move it to the recycle bin or change its schedule."
              : "The task opens immediately and closes at this time.",
          )
        }}
      </p>
      <fieldset class="task-schedule-time">
        <legend>
          {{
            t(
              mode === "open"
                ? "Opening time"
                : mode === "close"
                  ? "Closing time"
                  : "Date and time",
            )
          }}
        </legend>
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
          :disabled="busy || !mode || !date || !time"
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
