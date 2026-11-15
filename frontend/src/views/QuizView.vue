<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { listDocuments } from "../api/documents";
import { createQuiz, getQuiz, listQuizzes, submitQuiz } from "../api/quizzes";
import QuizQuestion from "../components/QuizQuestion.vue";
import type { DocumentOut, QuizDetail, QuizSummary } from "../types";

const STORAGE_KEY = "coursemate.quizId";
const documents = ref<DocumentOut[]>([]);
const quizzes = ref<QuizSummary[]>([]);
const selected = ref<string[]>([]);
const topic = ref("");
const language = ref<"zh" | "en">("en");
const currentId = ref("");
const detail = ref<QuizDetail | null>(null);
const picks = ref<Record<string, string>>({});
const generating = ref(false);
const submitting = ref(false);
const error = ref("");

const availableIds = computed(() => documents.value.map((document) => document.id));
const questions = computed(() => detail.value?.result?.questions ?? detail.value?.questions ?? []);
const ready = computed(
  () =>
    questions.value.length > 0 &&
    questions.value.every((question) => picks.value[question.id]),
);

onMounted(async () => {
  try {
    await Promise.all([loadDocuments(), loadQuizzes()]);
    const saved = sessionStorage.getItem(STORAGE_KEY);
    if (saved && quizzes.value.some((item) => item.id === saved)) {
      await openQuiz(saved);
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Could not load quizzes.";
  }
});

watch(currentId, (id) => {
  if (id) {
    sessionStorage.setItem(STORAGE_KEY, id);
  } else {
    sessionStorage.removeItem(STORAGE_KEY);
  }
});

async function loadDocuments() {
  documents.value = await listDocuments();
}

async function loadQuizzes() {
  quizzes.value = await listQuizzes();
}

function showForm() {
  if (generating.value || submitting.value) {
    return;
  }
  currentId.value = "";
  detail.value = null;
  picks.value = {};
  error.value = "";
}

async function openQuiz(id: string) {
  if (generating.value || submitting.value) {
    return;
  }
  error.value = "";
  await loadQuiz(id);
}

async function loadQuiz(id: string) {
  const quiz = await getQuiz(id);
  currentId.value = id;
  detail.value = quiz;
  picks.value = {};
  for (const question of quiz.result?.questions ?? []) {
    picks.value[question.id] = question.selected_option;
  }
}

async function generate() {
  const text = topic.value.trim();
  if (generating.value || selected.value.length < 1 || selected.value.length > 5 || !text) {
    return;
  }
  generating.value = true;
  error.value = "";
  try {
    const created = await createQuiz(selected.value, text, language.value);
    await loadQuizzes();
    await loadQuiz(created.id);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Could not generate the quiz.";
  } finally {
    generating.value = false;
  }
}

async function submit() {
  if (!detail.value || detail.value.result || submitting.value || !ready.value) {
    return;
  }
  submitting.value = true;
  error.value = "";
  try {
    await submitQuiz(
      detail.value.id,
      detail.value.questions.map((question) => ({
        question_id: question.id,
        option: picks.value[question.id],
      })),
    );
    await loadQuizzes();
    await loadQuiz(detail.value.id);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Could not submit the quiz.";
  } finally {
    submitting.value = false;
  }
}

function choose(id: string, option: string) {
  picks.value = { ...picks.value, [id]: option };
}
</script>

<template>
  <section class="page quiz-page">
    <aside class="history">
      <el-button :disabled="generating || submitting" @click="showForm">New quiz</el-button>
      <p v-if="!quizzes.length" class="empty">No quizzes yet.</p>
      <button
        v-for="item in quizzes"
        :key="item.id"
        type="button"
        class="history-item"
        :class="{ active: item.id === currentId }"
        :disabled="generating || submitting"
        @click="openQuiz(item.id)"
      >
        <span class="topic">{{ item.topic }}</span>
        <span class="state">{{ item.submitted ? "Submitted" : "Not submitted" }}</span>
      </button>
    </aside>

    <div v-if="!detail" class="thread">
      <h1>New quiz</h1>
      <p>Select 1 to 5 documents, then generate three questions.</p>
      <p v-if="!documents.length">Upload a PDF on the Documents page first.</p>
      <el-checkbox-group v-else v-model="selected" :max="5">
        <el-checkbox v-for="document in documents" :key="document.id" :value="document.id">
          {{ document.filename }}
        </el-checkbox>
      </el-checkbox-group>
      <p>{{ selected.length }} of 5 selected</p>
      <el-input v-model="topic" maxlength="200" show-word-limit placeholder="Topic" />
      <el-radio-group v-model="language">
        <el-radio value="en">English</el-radio>
        <el-radio value="zh">Chinese</el-radio>
      </el-radio-group>
      <el-button
        type="primary"
        :disabled="generating || selected.length < 1 || !topic.trim()"
        @click="generate"
      >
        Generate
      </el-button>
      <el-alert v-if="error" class="alert" :title="error" type="error" show-icon :closable="false" />
    </div>

    <div v-else class="thread">
      <h1>{{ detail.topic }}</h1>
      <p v-if="detail.result" class="score">Score: {{ detail.result.correct_count }} / {{ detail.result.total }}</p>
      <QuizQuestion
        v-for="question in questions"
        :key="question.id"
        :question="question"
        :selected="picks[question.id] ?? ''"
        :disabled="Boolean(detail.result) || submitting"
        :available-ids="availableIds"
        @select="choose(question.id, $event)"
      />
      <el-button
        v-if="!detail.result"
        type="primary"
        :disabled="!ready || submitting"
        @click="submit"
      >
        Submit
      </el-button>
      <el-alert v-if="error" class="alert" :title="error" type="error" show-icon :closable="false" />
    </div>
  </section>
</template>

<style scoped>
.quiz-page {
  max-width: none;
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}

.history {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: calc(100vh - 140px);
  overflow: auto;
}

.history-item {
  display: flex;
  flex-direction: column;
  width: 100%;
  padding: 8px;
  text-align: left;
  border: 0;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
}

.history-item.active {
  background: #ecf5ff;
}

.topic {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.state,
.empty {
  color: #606266;
  font-size: 12px;
}

.thread .el-input,
.thread .el-radio-group,
.thread .el-checkbox {
  display: flex;
  margin-bottom: 12px;
}

.score {
  font-weight: 700;
}

.alert {
  margin: 12px 0;
}
</style>
