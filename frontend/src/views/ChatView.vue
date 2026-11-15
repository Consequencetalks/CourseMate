<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { listDocuments } from "../api/documents";
import { createConversation, listConversations, listMessages, streamChat } from "../api/chat";
import MessageItem from "../components/MessageItem.vue";
import { useChatStore } from "../stores/chat";
import type { DocumentOut, MessageOut } from "../types";

const STORAGE_KEY = "coursemate.chatId";
const store = useChatStore();
const documents = ref<DocumentOut[]>([]);
const selected = ref<string[]>([]);
const draft = ref("");
const starting = ref(false);
const pendingUser = ref<MessageOut | null>(null);
const pendingAssistant = ref<MessageOut | null>(null);
const thread = ref<HTMLElement | null>(null);

const availableIds = computed(() => documents.value.map((document) => document.id));
const current = computed(() => store.conversations.find((item) => item.id === store.currentId));
const currentTitle = computed(() => current.value?.title ?? "Chat");
const scopeMissing = computed(() => {
  if (!current.value) {
    return false;
  }
  return current.value.document_ids.some((id) => !availableIds.value.includes(id));
});
const scopeLabel = computed(() => {
  if (!current.value) {
    return "";
  }
  return current.value.document_ids
    .map((id) => documents.value.find((document) => document.id === id)?.filename ?? "File unavailable")
    .join(", ");
});

onMounted(async () => {
  try {
    await Promise.all([loadDocuments(), loadConversations()]);
    const saved = sessionStorage.getItem(STORAGE_KEY);
    if (saved && store.conversations.some((item) => item.id === saved)) {
      await openConversation(saved);
    }
  } catch (err) {
    store.error = err instanceof Error ? err.message : "Could not load chats.";
  }
});

watch(
  () => store.currentId,
  (id) => {
    if (id) {
      sessionStorage.setItem(STORAGE_KEY, id);
    } else {
      sessionStorage.removeItem(STORAGE_KEY);
    }
  },
);

watch(
  () => [store.messages.length, pendingAssistant.value?.content],
  () => scrollDown(),
);

async function loadDocuments() {
  documents.value = await listDocuments();
}

async function loadConversations() {
  store.conversations = await listConversations();
}

async function openConversation(id: string) {
  if (store.generating) {
    return;
  }
  store.currentId = id;
  store.error = "";
  pendingUser.value = null;
  pendingAssistant.value = null;
  store.messages = await listMessages(id);
  await loadDocuments();
}

function showPicker() {
  if (store.generating) {
    return;
  }
  store.currentId = "";
  store.messages = [];
  store.error = "";
  pendingUser.value = null;
  pendingAssistant.value = null;
}

async function startChat() {
  if (starting.value || selected.value.length < 1 || selected.value.length > 5) {
    return;
  }
  starting.value = true;
  store.error = "";
  try {
    const created = await createConversation(selected.value);
    selected.value = [];
    await loadConversations();
    store.currentId = created.id;
    store.messages = [];
  } catch (err) {
    store.error = err instanceof Error ? err.message : "Could not start the chat.";
  } finally {
    starting.value = false;
  }
}

async function send() {
  const text = draft.value.trim();
  if (!store.currentId || store.generating || scopeMissing.value || !text || text.length > 2000) {
    return;
  }
  draft.value = "";
  store.generating = true;
  store.error = "";
  pendingUser.value = {
    id: "pending-user",
    role: "user",
    content: text,
    citations: [],
    created_at: new Date().toISOString(),
  };
  pendingAssistant.value = {
    id: "pending-assistant",
    role: "assistant",
    content: "",
    citations: [],
    created_at: new Date().toISOString(),
  };
  let outcome: "done" | "error" | "dropped" = "dropped";
  try {
    await streamChat(store.currentId, text, {
      onDelta(delta) {
        if (pendingAssistant.value) {
          pendingAssistant.value.content += delta;
        }
      },
      onDone() {
        outcome = "done";
      },
      onError(error) {
        outcome = "error";
        store.error = error.message;
      },
    });
  } catch (err) {
    outcome = "dropped";
    store.error = err instanceof Error ? err.message : "The reply failed.";
  }
  if (outcome === "done") {
    pendingUser.value = null;
    pendingAssistant.value = null;
    try {
      store.messages = await listMessages(store.currentId);
      await loadConversations();
    } catch (err) {
      store.error = err instanceof Error ? err.message : "Could not refresh the chat.";
    }
  } else {
    pendingUser.value = null;
    pendingAssistant.value = null;
    draft.value = text;
    if (!store.error) {
      store.error = "The reply ended before it finished.";
    }
  }
  store.generating = false;
}

function scrollDown() {
  nextTick(() => {
    thread.value?.scrollTo({ top: thread.value.scrollHeight });
  });
}
</script>

<template>
  <section class="page chat-page">
    <aside class="history">
      <el-button :disabled="store.generating" @click="showPicker">New chat</el-button>
      <p v-if="!store.conversations.length" class="empty">No chats yet.</p>
      <button
        v-for="item in store.conversations"
        :key="item.id"
        type="button"
        class="history-item"
        :class="{ active: item.id === store.currentId }"
        :disabled="store.generating"
        @click="openConversation(item.id)"
      >
        {{ item.title }}
      </button>
    </aside>

    <div v-if="!store.currentId" class="thread">
      <h1>New chat</h1>
      <p>Select 1 to 5 documents. The selection stays fixed for this chat.</p>
      <p v-if="!documents.length">Upload a PDF on the Documents page first.</p>
      <el-checkbox-group v-else v-model="selected" :max="5">
        <el-checkbox v-for="document in documents" :key="document.id" :value="document.id">
          {{ document.filename }}
        </el-checkbox>
      </el-checkbox-group>
      <p>{{ selected.length }} of 5 selected</p>
      <el-button type="primary" :disabled="starting || selected.length < 1" @click="startChat">
        Start chat
      </el-button>
      <el-alert v-if="store.error" class="alert" :title="store.error" type="error" show-icon :closable="false" />
    </div>

    <div v-else class="thread">
      <h1>{{ currentTitle }}</h1>
      <p class="scope">{{ scopeLabel }}</p>
      <el-alert
        v-if="scopeMissing"
        class="alert"
        title="A selected document was deleted. Start a new chat."
        type="warning"
        show-icon
        :closable="false"
      />
      <div ref="thread" class="messages">
        <MessageItem
          v-for="message in store.messages"
          :key="message.id"
          :message="message"
          :available-ids="availableIds"
        />
        <MessageItem v-if="pendingUser" :message="pendingUser" :available-ids="availableIds" />
        <MessageItem v-if="pendingAssistant" :message="pendingAssistant" :available-ids="availableIds" />
      </div>
      <el-alert v-if="store.error" class="alert" :title="store.error" type="error" show-icon :closable="false" />
      <div class="composer">
        <el-input
          v-model="draft"
          type="textarea"
          :rows="3"
          maxlength="2000"
          show-word-limit
          placeholder="Ask a question about the selected documents"
          :disabled="store.generating || scopeMissing"
        />
        <el-button type="primary" :disabled="store.generating || scopeMissing || !draft.trim()" @click="send">
          Send
        </el-button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.chat-page {
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
  display: block;
  width: 100%;
  padding: 8px;
  overflow: hidden;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
  border: 0;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
}

.history-item.active {
  background: #ecf5ff;
}

.empty,
.scope {
  color: #606266;
}

.messages {
  max-height: calc(100vh - 320px);
  overflow: auto;
}

.composer {
  display: flex;
  gap: 8px;
  align-items: flex-end;
  margin-top: 12px;
}

.composer .el-input {
  flex: 1;
}

.alert {
  margin: 12px 0;
}
</style>
