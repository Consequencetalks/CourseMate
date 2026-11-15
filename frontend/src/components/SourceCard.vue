<script setup lang="ts">
import { computed } from "vue";
import { documentFileUrl } from "../api/documents";
import type { Citation } from "../types";

const props = defineProps<{
  citation: Citation;
  available: boolean;
}>();

const href = computed(
  () => `${documentFileUrl(props.citation.document_id)}#page=${props.citation.page}`,
);
const label = computed(
  () => `${props.citation.source_id} · ${props.citation.filename} · page ${props.citation.page}`,
);
</script>

<template>
  <p class="source-card">
    <a v-if="available" :href="href" target="_blank" rel="noopener">{{ label }}</a>
    <span v-else>{{ label }} · File unavailable</span>
  </p>
</template>

<style scoped>
.source-card {
  margin: 4px 0 0;
  padding: 2px 8px;
  border-left: 2px solid #409eff;
  background: #fafafa;
  font-size: 13px;
  line-height: 1.4;
}

.source-card a {
  color: #409eff;
  text-decoration: none;
}

.source-card span {
  color: #606266;
}
</style>
