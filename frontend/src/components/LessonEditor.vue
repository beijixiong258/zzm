<script setup lang="ts">
import {
  Button as TButton,
  Input as TInput,
  InputNumber as TInputNumber,
  Textarea as TTextarea,
  Select as TSelect,
  Option as TOption,
  CheckboxGroup as TCheckboxGroup,
  Checkbox as TCheckbox,
} from "tdesign-vue-next";
import { computed } from "vue";
import {
  multipleChoiceAnswers,
  questionTypes,
  studentTask,
  type Question,
  type Task,
} from "../classroom-api";
import { t } from "../i18n";
import TaskContent from "./TaskContent.vue";

defineProps<{ disabled?: boolean }>();
const task = defineModel<Task>({ required: true });
const preview = computed(() => studentTask(task.value));
const description = computed({
  get: () => task.value.description,
  set: (value: string) => {
    task.value.description = value;
    task.value.content.description = value;
  },
});
const goals = computed({
  get: () => task.value.learningGoals,
  set: (value: string) => {
    task.value.learningGoals = value;
    task.value.content.learningGoals = value
      .split("\n")
      .filter((line) => line.trim());
  },
});
function updateOption(question: Question, index: number, value: string) {
  const previous = question.options[index];
  const selected = multipleChoiceAnswers(
    question.referenceAnswer || "",
    question.options,
  );
  question.options[index] = value;
  if (question.type === "multipleChoice") {
    question.referenceAnswer = selected.length
      ? JSON.stringify(
          selected.map((answer) => (answer === previous ? value : answer)),
        )
      : "";
  } else if (question.referenceAnswer === previous)
    question.referenceAnswer = value;
}
function removeOption(question: Question, index: number) {
  const previous = question.options[index];
  const selected = multipleChoiceAnswers(
    question.referenceAnswer || "",
    question.options,
  ).filter((answer) => answer !== previous);
  question.options.splice(index, 1);
  if (question.type === "multipleChoice")
    question.referenceAnswer = selected.length ? JSON.stringify(selected) : "";
  else if (question.referenceAnswer === previous) question.referenceAnswer = "";
}
function hasUnmatchedChoiceAnswer(question: Question) {
  const reference = question.referenceAnswer || "";
  if (!reference.trim()) return false;
  const selected =
    question.type === "multipleChoice"
      ? multipleChoiceAnswers(reference, question.options)
      : [reference];
  return (
    !selected.length ||
    selected.some((answer) => !question.options.includes(answer))
  );
}
function addQuestion() {
  task.value.content.questions.push({
    id: crypto.randomUUID(),
    type: "openResponse",
    prompt: "",
    options: [],
    answerSlots: 1,
    referenceAnswer: "",
    explanation: "",
    hint: "",
    sourceMaterialIds: [],
    imageMaterialIds: [],
  });
}
</script>

<template>
  <div class="lesson-editor">
    <div class="lesson-editor-fields">
      <fieldset class="form-stack" :disabled="disabled">
        <label
          >{{ t("Task name")
          }}<TInput v-model="task.title" maxlength="300" :disabled="disabled"
        /></label>
        <label
          >{{ t("Lesson text") }}
          <TTextarea
            v-model="task.content.handout"
            :autosize="{ minRows: 12, maxRows: 24 }"
            maxlength="180000"
            :disabled="disabled"
          />
        </label>
        <details class="lesson-edit-section">
          <summary>{{ t("Introduction and learning plan") }}</summary>
          <div class="form-stack">
            <label
              >{{ t("Description")
              }}<TTextarea
                v-model="description"
                :autosize="{ minRows: 2, maxRows: 5 }"
                maxlength="10000"
                :disabled="disabled"
            /></label>
            <label
              >{{ t("Opening message")
              }}<TTextarea
                v-model="task.content.openingMessage"
                :autosize="{ minRows: 3, maxRows: 8 }"
                maxlength="20000"
                :disabled="disabled"
            /></label>
            <label
              >{{ t("Learning goals")
              }}<TTextarea
                v-model="goals"
                :autosize="{ minRows: 3, maxRows: 8 }"
                maxlength="20000"
                :disabled="disabled"
            /></label>
            <div
              v-for="(step, index) in task.content.learningPlan"
              :key="index"
              class="form-stack lesson-edit-step"
            >
              <label
                >{{ t("Step title")
                }}<TInput v-model="step.title" :disabled="disabled"
              /></label>
              <label
                >{{ t("Description")
                }}<TTextarea
                  v-model="step.description"
                  :autosize="{ minRows: 2, maxRows: 5 }"
                  :disabled="disabled"
              /></label>
              <label
                >{{ t("Duration in minutes")
                }}<TInputNumber
                  v-model="step.durationMinutes"
                  :min="1"
                  :max="480"
                  :disabled="disabled"
              /></label>
              <TButton
                theme="default"
                variant="text"
                :disabled="disabled"
                @click="task.content.learningPlan.splice(index, 1)"
                >{{ t("Remove step") }}</TButton
              >
            </div>
            <TButton
              theme="default"
              variant="outline"
              :disabled="disabled || task.content.learningPlan.length >= 30"
              @click="
                task.content.learningPlan.push({
                  title: '',
                  description: '',
                  durationMinutes: 5,
                })
              "
              >{{ t("Add step") }}</TButton
            >
          </div>
        </details>
        <section class="lesson-edit-section">
          <h3>
            {{ t("Questions and reference answers") }} ·
            {{ task.content.questions.length }}
          </h3>
          <details
            v-for="(question, index) in task.content.questions"
            :key="question.id"
            class="lesson-edit-question"
          >
            <summary>
              {{ index + 1 }}. {{ question.prompt || t("New question") }}
            </summary>
            <div class="form-stack">
              <label
                >{{ t("Question type") }}
                <TSelect v-model="question.type" :disabled="disabled">
                  <TOption
                    v-for="(label, type) in questionTypes"
                    :key="type"
                    :value="type"
                    :label="t(label)"
                  />
                </TSelect>
              </label>
              <label
                >{{ t("Question text")
                }}<TTextarea
                  v-model="question.prompt"
                  :autosize="{ minRows: 3, maxRows: 10 }"
                  maxlength="20000"
                  :disabled="disabled"
              /></label>
              <label v-if="question.type === 'fillInBlank'"
                >{{ t("Number of blanks")
                }}<TInputNumber
                  v-model="question.answerSlots"
                  :min="1"
                  :max="20"
                  :disabled="disabled"
              /></label>
              <template
                v-if="
                  ['singleChoice', 'multipleChoice', 'trueFalse'].includes(
                    question.type,
                  )
                "
              >
                <div
                  v-for="(option, optionIndex) in question.options"
                  :key="optionIndex"
                >
                  <label>
                    {{ t("Option {0}", [optionIndex + 1]) }}
                    <TTextarea
                      :value="option"
                      :autosize="{ minRows: 1, maxRows: 5 }"
                      :disabled="disabled"
                      @update:value="
                        updateOption(question, optionIndex, String($event))
                      "
                    />
                  </label>
                  <TButton
                    theme="default"
                    variant="text"
                    :disabled="disabled"
                    @click="removeOption(question, optionIndex)"
                    >{{ t("Remove option") }}</TButton
                  >
                </div>
                <TButton
                  theme="default"
                  variant="outline"
                  :disabled="disabled || question.options.length >= 20"
                  @click="question.options.push('')"
                  >{{ t("Add option") }}</TButton
                >
                <label v-if="hasUnmatchedChoiceAnswer(question)"
                  >{{ t("Reference answer") }}
                  <TTextarea
                    v-model="question.referenceAnswer"
                    :autosize="{ minRows: 2, maxRows: 8 }"
                    :disabled="disabled"
                  />
                </label>
                <label v-else-if="question.type !== 'multipleChoice'"
                  >{{ t("Reference answer") }}
                  <TSelect
                    v-model="question.referenceAnswer"
                    clearable
                    :disabled="disabled"
                  >
                    <TOption
                      v-for="(option, optionIndex) in question.options"
                      :key="optionIndex"
                      :value="option"
                      :label="option"
                    />
                  </TSelect>
                </label>
                <div v-else>
                  <p>{{ t("Reference answer") }}</p>
                  <TCheckboxGroup
                    :value="
                      multipleChoiceAnswers(
                        question.referenceAnswer || '',
                        question.options,
                      )
                    "
                    :disabled="disabled"
                    @change="
                      question.referenceAnswer = $event.length
                        ? JSON.stringify($event)
                        : ''
                    "
                  >
                    <TCheckbox
                      v-for="(option, optionIndex) in question.options"
                      :key="optionIndex"
                      :value="option"
                      >{{ option }}</TCheckbox
                    >
                  </TCheckboxGroup>
                </div>
              </template>
              <label v-else
                >{{ t("Reference answer")
                }}<TTextarea
                  v-model="question.referenceAnswer"
                  :autosize="{ minRows: 2, maxRows: 8 }"
                  :disabled="disabled"
              /></label>
              <label
                >{{ t("Hint")
                }}<TTextarea
                  v-model="question.hint"
                  :autosize="{ minRows: 2, maxRows: 5 }"
                  :disabled="disabled"
              /></label>
              <label
                >{{ t("Explanation")
                }}<TTextarea
                  v-model="question.explanation"
                  :autosize="{ minRows: 2, maxRows: 6 }"
                  :disabled="disabled"
              /></label>
              <TButton
                theme="danger"
                variant="text"
                :disabled="disabled"
                @click="task.content.questions.splice(index, 1)"
                >{{ t("Remove question") }}</TButton
              >
            </div>
          </details>
          <TButton
            theme="default"
            variant="outline"
            :disabled="disabled || task.content.questions.length >= 100"
            @click="addQuestion"
            >{{ t("Add question") }}</TButton
          >
        </section>
        <details class="lesson-edit-section">
          <summary>{{ t("Tutor settings") }}</summary>
          <div class="form-stack">
            <label
              >{{ t("Teaching language") }}
              <TSelect v-model="task.teachingLanguage" :disabled="disabled">
                <TOption value="zh-CN" label="中文" /><TOption
                  value="en"
                  label="English"
                />
              </TSelect>
            </label>
            <label
              >{{ t("Task type") }}
              <TSelect v-model="task.sessionType" :disabled="disabled">
                <TOption value="tutor" :label="t('AI tutor')" /><TOption
                  value="assignment"
                  :label="t('Assignment')"
                />
              </TSelect>
            </label>
            <label
              >{{ t("Additional instructions for AI")
              }}<TTextarea
                v-model="task.additionalInstructions"
                :autosize="{ minRows: 6, maxRows: 16 }"
                maxlength="20000"
                :disabled="disabled"
            /></label>
          </div>
        </details>
      </fieldset>
    </div>
    <section
      class="lesson-editor-preview"
      :aria-label="t('Live lesson preview')"
    >
      <h3>{{ t("Live lesson preview") }}</h3>
      <TaskContent :task="preview" preview readonly />
    </section>
  </div>
</template>
