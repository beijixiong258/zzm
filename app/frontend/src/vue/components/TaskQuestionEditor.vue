<script setup lang="ts">
import { t } from "../../i18n";
import {
  questionTypes,
  type Question,
  type Material,
} from "../../classroom-api";
const props = defineProps<{
  questions: Question[];
  materials: Material[];
  teachingLanguage: "zh-CN" | "en";
  disabled?: boolean;
}>();
function add() {
  props.questions.push({
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
function move(index: number, delta: number) {
  const target = index + delta;
  if (target < 0 || target >= props.questions.length) return;
  [props.questions[index], props.questions[target]] = [
    props.questions[target],
    props.questions[index],
  ];
}
function duplicate(index: number) {
  const copy = JSON.parse(JSON.stringify(props.questions[index])) as Question;
  copy.id = crypto.randomUUID();
  props.questions.splice(index + 1, 0, copy);
}
function changeType(question: Question) {
  if (question.type === "trueFalse")
    question.options =
      props.teachingLanguage === "zh-CN" ? ["正确", "错误"] : ["True", "False"];
  else if (
    ["singleChoice", "multipleChoice"].includes(question.type) &&
    question.options.length < 2
  )
    question.options = ["", ""];
  if (!["singleChoice", "multipleChoice", "trueFalse"].includes(question.type))
    question.options = [];
  question.referenceAnswer = "";
}
function remove(index: number) {
  if (window.confirm(t("Remove this question from the draft?")))
    props.questions.splice(index, 1);
}
</script>
<template>
  <fieldset :disabled="disabled" class="question-editor">
    <div class="row spread">
      <h3>{{ t("Questions and reference answers") }}</h3>
      <button type="button" @click="add">＋ {{ t("Add question") }}</button>
    </div>
    <p class="muted">
      {{
        t(
          "Reference answers and explanations are visible only to teachers and the AI tutor.",
        )
      }}
    </p>
    <p v-if="!questions.length" class="empty">
      {{
        t(
          "Generate questions from materials, import an existing worksheet, or add a question.",
        )
      }}
    </p>
    <details
      v-for="(question, index) in questions"
      :key="question.id"
      class="question-edit"
      :open="!question.prompt"
    >
      <summary>
        <span
          >{{ index + 1 }}.
          {{ question.prompt.slice(0, 64) || t("Untitled question") }}</span
        ><small>{{
          t(
            questionTypes[question.type as keyof typeof questionTypes] ||
              question.type,
          )
        }}</small>
      </summary>
      <div class="question-fields">
        <div class="row spread">
          <label
            >{{ t("Question type")
            }}<select v-model="question.type" @change="changeType(question)">
              <option
                v-for="(name, value) in questionTypes"
                :key="value"
                :value="value"
              >
                {{ t(name) }}
              </option>
            </select></label
          >
          <div class="row">
            <button
              type="button"
              :disabled="index === 0"
              :aria-label="t('Move up')"
              @click="move(index, -1)"
            >
              ↑</button
            ><button
              type="button"
              :disabled="index === questions.length - 1"
              :aria-label="t('Move down')"
              @click="move(index, 1)"
            >
              ↓</button
            ><button type="button" @click="duplicate(index)">
              {{ t("Duplicate") }}</button
            ><button type="button" class="danger" @click="remove(index)">
              {{ t("Remove") }}
            </button>
          </div>
        </div>
        <label
          >{{ t("Question text")
          }}<textarea v-model="question.prompt" rows="4" maxlength="20000" />
        </label>
        <div
          v-if="
            [
              'singleChoice',
              'multipleChoice',
              'trueFalse',
              'imageMatching',
            ].includes(question.type)
          "
        >
          <div class="row spread">
            <strong>{{ t("Answer options") }}</strong
            ><button
              type="button"
              :disabled="question.options.length >= 20"
              @click="question.options.push('')"
            >
              ＋ {{ t("Add option") }}
            </button>
          </div>
          <div
            v-for="(_, optionIndex) in question.options"
            :key="optionIndex"
            class="row option-row"
          >
            <input
              v-model="question.options[optionIndex]"
              :aria-label="t('Option {0}', [optionIndex + 1])"
            /><button
              type="button"
              :aria-label="t('Remove option')"
              @click="question.options.splice(optionIndex, 1)"
            >
              ×
            </button>
          </div>
        </div>
        <label v-if="question.type === 'fillInBlank'"
          >{{ t("Number of blanks")
          }}<input
            v-model.number="question.answerSlots"
            type="number"
            min="1"
            max="20"
        /></label>
        <label
          >{{ t("Reference answer")
          }}<select
            v-if="['singleChoice', 'trueFalse'].includes(question.type)"
            v-model="question.referenceAnswer"
          >
            <option value="">{{ t("Choose the correct option") }}</option>
            <option
              v-for="(option, optionIndex) in question.options"
              :key="optionIndex"
              :value="option"
            >
              {{ option }}
            </option></select
          ><textarea
            v-else
            v-model="question.referenceAnswer"
            rows="3"
            :placeholder="
              question.type === 'multipleChoice'
                ? t(
                    'Enter each correct option on a separate line, matching the option text exactly.',
                  )
                : ''
            "
          />
        </label>
        <label
          >{{ t("Answer explanation")
          }}<textarea v-model="question.explanation" rows="2" />
        </label>
        <label
          >{{ t("Hint for students")
          }}<textarea v-model="question.hint" rows="2" />
        </label>
        <label
          >{{ t("Source materials")
          }}<select v-model="question.sourceMaterialIds" multiple>
            <option
              v-for="material in materials"
              :key="material.id"
              :value="material.id"
            >
              {{ material.title }}
            </option>
          </select></label
        >
        <label v-if="question.type === 'imageMatching'"
          >{{ t("Question illustrations")
          }}<select v-model="question.imageMaterialIds" multiple>
            <option
              v-for="material in materials.filter(
                (m) =>
                  m.mimeType.startsWith('image/') && m.visibility === 'student',
              )"
              :key="material.id"
              :value="material.id"
            >
              {{ material.title }}
            </option>
          </select></label
        >
      </div>
    </details>
  </fieldset>
</template>
