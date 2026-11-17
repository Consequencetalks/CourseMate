<script setup lang="ts">
import { computed, ref } from "vue";
import { renderMarkdown } from "../markdown";
import { speak } from "../speech";
import SourceCard from "./SourceCard.vue";
import type { MessageOut } from "../types";

const props = defineProps<{
  message: MessageOut;
  availableIds: string[];
  speakable?: boolean;
}>();

const sourcesOpen = ref(false);
const html = computed(() =>
  props.message.role === "assistant" && props.message.content
    ? renderMarkdown(props.message.content)
    : "",
);
const showReplay = computed(
  () => Boolean(props.speakable && props.message.role === "assistant" && props.message.content),
);

function replay() {
  if (!props.message.content) {
    return;
  }
  void speak(props.message.content);
}
</script>

<template>
  <article class="bubble" :class="message.role">
    <p class="role">{{ message.role === "user" ? "You" : "CourseMate" }}</p>
    <p v-if="message.role === 'user'" class="text">{{ message.content }}</p>
    <p v-else-if="!message.content" class="text">…</p>
    <div v-else class="markdown" v-html="html" />
    <button v-if="showReplay" type="button" class="sources-toggle" @click="replay">Replay</button>
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
