<script setup lang="ts">
import { computed, ref } from "vue";
import { renderMarkdown } from "../markdown";
import SourceCard from "./SourceCard.vue";
import type { MessageOut } from "../types";

const props = defineProps<{
  message: MessageOut;
  availableIds: string[];
}>();

const sourcesOpen = ref(false);
const html = computed(() =>
  props.message.role === "assistant" && props.message.content
    ? renderMarkdown(props.message.content)
    : "",
);
</script>

<template>
  <article class="bubble" :class="message.role">
    <p class="role">{{ message.role === "user" ? "You" : "CourseMate" }}</p>
    <p v-if="message.role === 'user'" class="text">{{ message.content }}</p>
    <p v-else-if="!message.content" class="text">…</p>
    <div v-else class="markdown" v-html="html" />
    <SourceCard
      v-if="message.citations.length === 1"
      :citation="message.citations[0]"
      :available="availableIds.includes(message.citations[0].document_id)"
    />
    <template v-else-if="message.citations.length > 1">
      <button
        type="button"
        class="sources-toggle"
        :aria-expanded="sourcesOpen"
        @click="sourcesOpen = !sourcesOpen"
      >
        Sources ({{ message.citations.length }})
      </button>
      <div v-if="sourcesOpen">
        <SourceCard
          v-for="citation in message.citations"
          :key="citation.source_id"
          :citation="citation"
          :available="availableIds.includes(citation.document_id)"
        />
      </div>
    </template>
  </article>
</template>

<style scoped>
.bubble {
  margin-bottom: 12px;
  padding: 12px;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  background: #fff;
}

.bubble.user {
  background: #ecf5ff;
}

.role {
  margin: 0 0 4px;
  font-size: 12px;
  font-weight: 700;
  color: #606266;
}

.text {
  margin: 0;
  white-space: pre-wrap;
  line-height: 1.6;
}

.markdown {
  line-height: 1.6;
}

.markdown :deep(p),
.markdown :deep(ul),
.markdown :deep(ol),
.markdown :deep(pre),
.markdown :deep(table),
.markdown :deep(blockquote) {
  margin: 0 0 0.6em;
}

.markdown :deep(*:last-child) {
  margin-bottom: 0;
}

.markdown :deep(ul),
.markdown :deep(ol) {
  padding-left: 1.4em;
}

.markdown :deep(h1),
.markdown :deep(h2),
.markdown :deep(h3),
.markdown :deep(h4) {
  margin: 0.2em 0 0.4em;
  font-size: 1.05em;
  line-height: 1.4;
}

.markdown :deep(a) {
  color: #409eff;
}

.markdown :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  background: #f4f4f5;
  padding: 0 0.25em;
  border-radius: 4px;
}

.markdown :deep(pre) {
  padding: 8px 12px;
  overflow: auto;
  border-radius: 6px;
  background: #f4f4f5;
}

.markdown :deep(pre code) {
  padding: 0;
  background: none;
}

.markdown :deep(table) {
  width: 100%;
  border-collapse: collapse;
}

.markdown :deep(th),
.markdown :deep(td) {
  border: 1px solid #e4e7ed;
  padding: 4px 8px;
  text-align: left;
}

.markdown :deep(blockquote) {
  padding-left: 12px;
  border-left: 3px solid #dcdfe6;
  color: #606266;
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
</style>
