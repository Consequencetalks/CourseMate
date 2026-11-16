<script setup lang="ts">
import { computed, ref } from "vue";
import SourceCard from "./SourceCard.vue";
import type { PublicQuestion, QuestionResult } from "../types";

const props = defineProps<{
  question: PublicQuestion | QuestionResult;
  selected: string;
  disabled: boolean;
  availableIds: string[];
  asking?: boolean;
}>();

const emit = defineEmits<{ select: [value: string]; ask: [] }>();
const sourcesOpen = ref(false);
const letters = ["A", "B", "C", "D"] as const;
const result = computed(() => ("correct" in props.question ? props.question : null));
const citations = computed(() => result.value?.citations ?? []);

function choose(value: string | number | boolean | undefined) {
  if (typeof value === "string") {
    emit("select", value);
  }
}
</script>

<template>
  <article class="question">
    <p class="stem">{{ question.stem }}</p>
    <el-radio-group :model-value="selected" :disabled="disabled" @change="choose">
      <el-radio v-for="letter in letters" :key="letter" :value="letter">
        {{ letter }}. {{ question.options[letter] }}
      </el-radio>
    </el-radio-group>
    <template v-if="result">
      <p class="verdict" :class="{ correct: result.correct }">
        {{ result.correct ? "Correct" : `Correct answer: ${result.correct_option}` }}
      </p>
      <button
        v-if="!result.correct"
        type="button"
        class="sources-toggle"
        :disabled="asking"
        @click="emit('ask')"
      >
        Ask about this
      </button>
      <p class="explanation">{{ result.explanation }}</p>
      <SourceCard
        v-if="citations.length === 1"
        :citation="citations[0]"
        :available="availableIds.includes(citations[0].document_id)"
      />
      <template v-else-if="citations.length > 1">
        <button
          type="button"
          class="sources-toggle"
          :aria-expanded="sourcesOpen"
          @click="sourcesOpen = !sourcesOpen"
        >
          Sources ({{ citations.length }})
        </button>
        <div v-if="sourcesOpen">
          <SourceCard
            v-for="citation in citations"
            :key="citation.source_id"
            :citation="citation"
            :available="availableIds.includes(citation.document_id)"
          />
        </div>
      </template>
    </template>
  </article>
</template>

<style scoped>
.question {
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 1px solid #e4e7ed;
}

.stem,
.explanation {
  margin: 0 0 8px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.el-radio {
  display: flex;
  height: auto;
  margin: 4px 0;
  white-space: normal;
}

.verdict {
  margin: 8px 0 4px;
  font-weight: 700;
  color: #f56c6c;
}

.verdict.correct {
  color: #67c23a;
}

.sources-toggle {
  margin-top: 8px;
  padding: 2px 8px;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  background: #fafafa;
  color: #409eff;
  font-size: 13px;
  line-height: 1.4;
  cursor: pointer;
}

.sources-toggle:disabled {
  cursor: default;
  opacity: 0.6;
}
</style>
