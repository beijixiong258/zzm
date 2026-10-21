<script setup lang="ts">
import { computed } from "vue";
import { t } from "../../i18n";
import type { Question } from "../../types";
import {
  answerFieldCount,
  parseAnswerFields,
  formatAnswerFields,
} from "../../answer-fields";
const props = defineProps<{
  question: Question;
  modelValue: string;
  readonly?: boolean;
}>();
const emit = defineEmits<{ "update:modelValue": [string] }>();
const structured = computed(() =>
  ["fill_in_blank", "image_matching"].includes(props.question.type),
);
const fields = computed(() =>
  parseAnswerFields(props.modelValue, answerFieldCount(props.question)),
);
function update(index: number, value: string) {
  const next = [...fields.value!];
  next[index] = value;
  emit("update:modelValue", formatAnswerFields(next));
}
</script>
<template>
  <fieldset v-if="question.type === 'single_choice'" class="answer-fields">
    <legend>{{ t("Choose one answer") }}</legend>
    <label
      v-for="(option, index) in question.options"
      :key="index"
      class="check answer-choice"
      ><input
        type="radio"
        name="question-answer"
        :value="option"
        :checked="modelValue === option"
        :disabled="readonly"
        required
        @change="emit('update:modelValue', option)"
      />{{ option }}</label
    >
  </fieldset>
  <fieldset v-else-if="structured && fields" class="answer-fields">
    <legend>
      {{
        question.type === "image_matching"
          ? t("Match each image")
          : t("Complete every blank")
      }}
    </legend>
    <label v-for="(value, index) in fields" :key="index"
      ><span>{{
        question.type === "image_matching"
          ? question.images[index]?.label || t("Image {0}", [index + 1])
          : t("Blank {0}", [index + 1])
      }}</span>
      <select
        v-if="question.type === 'image_matching' && question.options.length"
        :value="value"
        :disabled="readonly"
        required
        @change="update(index, ($event.target as HTMLSelectElement).value)"
      >
        <option value="">{{ t("Choose a match") }}</option>
        <option
          v-for="(option, i) in question.options"
          :key="i"
          :value="option"
        >
          {{ option }}
        </option>
      </select>
      <input
        v-else
        type="text"
        :value="value"
        :readonly="readonly"
        required
        maxlength="8000"
        @input="update(index, ($event.target as HTMLInputElement).value)"
    /></label>
  </fieldset>
  <label v-else
    >{{ t("Your answer")
    }}<small v-if="structured">{{
      t(
        "This answer uses the previous text format. You can continue editing it here.",
      )
    }}</small
    ><textarea
      :value="modelValue"
      rows="6"
      :readonly="readonly"
      required
      @input="
        emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)
      "
    />
  </label>
</template>
