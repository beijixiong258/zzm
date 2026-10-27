<script setup lang="ts">
import {
  Textarea as TTextarea,
  Checkbox as TCheckbox,
  Radio as TRadio,
} from "tdesign-vue-next";
import { t } from "../i18n";
import { fileUrl, questionTypes, type Task } from "../classroom-api";
import RichText from "./RichText.vue";
import DiagramView from "./DiagramView.vue";
defineProps<{
  task: Task;
  answers?: Record<string, string>;
  readonly?: boolean;
  preview?: boolean;
}>();
const emit = defineEmits<{ answer: [id: string, value: string] }>();
function multiple(id: string, option: string, checked: boolean, answer = "") {
  const selected = new Set(answer.split("\n").filter(Boolean));
  if (checked) selected.add(option);
  else selected.delete(option);
  emit("answer", id, [...selected].join("\n"));
}
</script>

<template>
  <article class="task-content">
    <div class="eyebrow">
      {{ t(task.sessionType === "assignment" ? "Assignment" : "AI tutor") }}
    </div>
    <h2>{{ task.title || t("Untitled task") }}</h2>
    <RichText :text="task.description || task.content.description" />
    <section v-if="task.content.openingMessage" class="lesson-opening">
      <RichText :text="task.content.openingMessage" />
    </section>
    <section v-if="task.content.handout" class="lesson-handout">
      <RichText :text="task.content.handout" />
    </section>
    <img
      v-for="id in task.content.illustrationMaterialIds || []"
      :key="id"
      :src="fileUrl(id, task.versionId)"
      :alt="t('Lesson illustration')"
      class="question-image"
    />
    <DiagramView
      v-for="diagram in task.content.diagrams || []"
      :key="diagram.id"
      :diagram="diagram"
    />
    <section v-if="task.content.learningGoals.length">
      <h3>{{ t("Learning goals") }}</h3>
      <ul>
        <li v-for="goal in task.content.learningGoals" :key="goal">
          {{ goal }}
        </li>
      </ul>
    </section>
    <section v-if="task.content.learningPlan.length">
      <h3>{{ t("Learning plan") }}</h3>
      <ol class="learning-plan">
        <li v-for="(step, index) in task.content.learningPlan" :key="index">
          <strong>{{ step.title }}</strong
          ><span v-if="step.durationMinutes" class="muted">
            · {{ step.durationMinutes }} {{ t("min") }}</span
          >
          <p>{{ step.description }}</p>
        </li>
      </ol>
    </section>
    <p v-if="!task.content.learningPlan.length && preview" class="empty">
      {{ t("Generate a task to preview its learning plan and questions.") }}
    </p>
    <section
      v-if="task.materials.filter((m) => m.visibility === 'student').length"
    >
      <h3>{{ t("Learning materials") }}</h3>
      <div class="material-links">
        <a
          v-for="material in task.materials.filter(
            (m) => m.visibility === 'student',
          )"
          :key="material.id"
          :href="fileUrl(material.id, task.versionId)"
          target="_blank"
          rel="noopener"
          >{{ material.title }}</a
        >
      </div>
    </section>
    <section
      v-for="(question, index) in task.content.questions"
      :key="question.id"
      class="student-question"
    >
      <div class="row spread">
        <strong>{{ t("Question {0}", [index + 1]) }}</strong
        ><span class="muted">{{
          t(
            questionTypes[question.type as keyof typeof questionTypes] ||
              question.type,
          )
        }}</span>
      </div>
      <RichText :text="question.prompt" />
      <img
        v-for="imageId in question.imageMaterialIds || []"
        :key="imageId"
        :src="fileUrl(imageId, task.versionId)"
        :alt="t('Question illustration')"
        class="question-image"
      />
      <div
        v-if="
          ['singleChoice', 'trueFalse', 'multipleChoice'].includes(
            question.type,
          )
        "
        class="answer-options"
      >
        <div
          v-for="(option, optionIndex) in question.options"
          :key="optionIndex"
        >
          <TCheckbox
            v-if="question.type === 'multipleChoice'"
            :checked="
              (answers?.[question.id] || '').split('\n').includes(option)
            "
            :disabled="readonly || preview"
            @change="
              multiple(question.id, option, $event, answers?.[question.id])
            "
            >{{ option }}</TCheckbox
          >
          <TRadio
            v-else
            :name="`answer-${question.id}-${preview ? 'preview' : 'student'}`"
            :value="option"
            :disabled="readonly || preview"
            :checked="answers?.[question.id] === option"
            @change="emit('answer', question.id, option)"
            >{{ option }}</TRadio
          >
        </div>
      </div>
      <template v-else>
        <ol
          v-if="question.type === 'imageMatching' && question.options.length"
          class="matching-options"
        >
          <li
            v-for="(option, optionIndex) in question.options"
            :key="optionIndex"
          >
            {{ option }}
          </li>
        </ol>
        <TTextarea
          v-control-attrs="{
            'aria-label': t('Answer to question {0}', [index + 1]),
            rows: '3',
          }"
          :autosize="{ minRows: 3, maxRows: 10 }"
          :value="answers?.[question.id] || ''"
          :disabled="readonly || preview"
          :placeholder="t('Write your answer here')"
          @change="emit('answer', question.id, String($event))"
        />
      </template>
      <details v-if="question.hint">
        <summary>{{ t("Hint") }}</summary>
        <RichText :text="question.hint" />
      </details>
    </section>
  </article>
</template>
