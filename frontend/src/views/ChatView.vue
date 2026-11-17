<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { listDocuments } from "../api/documents";
import { createConversation, listConversations, listMessages, streamChat } from "../api/chat";
import MessageItem from "../components/MessageItem.vue";
import {
  cancelRecognition,
  finishLiveSpeech,
  finishRecognition,
  onSpeechError,
  pushLiveSpeech,
  recognitionSupported,
  startRecognition,
  stopSpeaking,
} from "../speech";
import { useChatStore } from "../stores/chat";
import type { DocumentOut, MessageOut } from "../types";

const STORAGE_KEY = "coursemate.chatId";
const ASK_KEY = "coursemate.askOnce";
const SPEAK_KEY = "coursemate.speech.speak";
const store = useChatStore();
const documents = ref<DocumentOut[]>([]);
const selected = ref<string[]>([]);
const draft = ref("");
const starting = ref(false);
const pendingUser = ref<MessageOut | null>(null);
const pendingAssistant = ref<MessageOut | null>(null);
const thread = ref<HTMLElement | null>(null);
const listening = ref(false);
const speechError = ref("");
const draftBeforeListen = ref("");
const readAnswers = ref(localStorage.getItem(SPEAK_KEY) === "1");
const voiceInputReady = recognitionSupported();
let listenSession = 0;
let alive = true;

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
  const ask = takeAsk();
  try {
    await Promise.all([loadDocuments(), loadConversations()]);
    if (ask) {
      await openConversation(ask.conversationId);
      await send(ask.text);
      return;
    }
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

watch(readAnswers, (enabled) => {
  localStorage.setItem(SPEAK_KEY, enabled ? "1" : "0");
  if (!enabled) {
    stopSpeaking();
  }
});

onMounted(() => {
  onSpeechError((message) => {
    speechError.value = message;
  });
});

onUnmounted(() => {
  alive = false;
  abandonListening();
  stopSpeaking();
});

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
  abandonListening();
  stopSpeaking();
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
  abandonListening();
  stopSpeaking();
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

function abandonListening() {
  listenSession += 1;
  listening.value = false;
  cancelRecognition();
}

function toggleMic() {
  if (listening.value) {
    finishRecognition();
    return;
  }
  if (!voiceInputReady || store.generating || scopeMissing.value) {
    return;
  }
  const session = listenSession + 1;
  listenSession = session;
  speechError.value = "";
  draftBeforeListen.value = draft.value;
  listening.value = true;
  stopSpeaking();
  startRecognition({
    onText(text) {
      if (session !== listenSession) {
        return;
      }
      draft.value = text;
    },
    onError(message) {
      if (session !== listenSession) {
        return;
      }
      speechError.value = message;
    },
    onEnd(finalText) {
      if (session !== listenSession) {
        return;
      }
      listening.value = false;
      draft.value = finalText || draftBeforeListen.value;
    },
  });
}

function takeAsk(): { conversationId: string; text: string } | null {
  const raw = sessionStorage.getItem(ASK_KEY);
  if (!raw) {
    return null;
  }
  sessionStorage.removeItem(ASK_KEY);
  try {
    const payload = JSON.parse(raw) as { conversationId?: unknown; text?: unknown };
    if (typeof payload.conversationId === "string" && typeof payload.text === "string" && payload.text.trim()) {
      return { conversationId: payload.conversationId, text: payload.text.trim() };
    }
  } catch {
    return null;
  }
  return null;
}

async function send(preset?: string) {
  const text = (preset ?? draft.value).trim();
  if (!store.currentId || store.generating || scopeMissing.value || !text || text.length > 2000) {
    return;
  }
  abandonListening();
  stopSpeaking();
  speechError.value = "";
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
  const outcome: { kind: "done" | "error" | "dropped" } = { kind: "dropped" };
  try {
    await streamChat(store.currentId, text, {
      onDelta(delta) {
        if (pendingAssistant.value) {
          pendingAssistant.value.content += delta;
          if (readAnswers.value) {
            pushLiveSpeech(pendingAssistant.value.content);
          }
        }
      },
      onDone() {
        outcome.kind = "done";
      },
      onError(error) {
        outcome.kind = "error";
        store.error = error.message;
      },
    });
  } catch (err) {
    outcome.kind = "dropped";
    store.error = err instanceof Error ? err.message : "The reply failed.";
  }
  const spoken = pendingAssistant.value?.content ?? "";
  if (outcome.kind === "done") {
    if (alive && readAnswers.value && spoken) {
      finishLiveSpeech(spoken);
    } else {
      stopSpeaking();
    }
    pendingUser.value = null;
    pendingAssistant.value = null;
    try {
      store.messages = await listMessages(store.currentId);
      await loadConversations();
    } catch (err) {
      store.error = err instanceof Error ? err.message : "Could not refresh the chat.";
    }
  } else {
    stopSpeaking();
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
        :title="item.title"
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
      <h1 :title="currentTitle">{{ currentTitle }}</h1>
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
          :speakable="true"
        />
        <MessageItem v-if="pendingUser" :message="pendingUser" :available-ids="availableIds" />
        <MessageItem v-if="pendingAssistant" :message="pendingAssistant" :available-ids="availableIds" />
      </div>
      <el-alert v-if="store.error" class="alert" :title="store.error" type="error" show-icon :closable="false" />
      <div class="composer">
        <el-alert v-if="speechError" class="alert" :title="speechError" type="warning" show-icon :closable="false" />
        <div class="composer-row">
          <el-input
            v-model="draft"
            type="textarea"
            :rows="2"
            maxlength="2000"
            :disabled="store.generating || scopeMissing"
          />
          <div class="read-toggle">
            <el-switch v-model="readAnswers" aria-label="Read" />
            <span @click="readAnswers = !readAnswers">Read</span>
          </div>
          <div class="composer-actions">
            <el-button
              :disabled="!voiceInputReady || store.generating || scopeMissing"
              :title="voiceInputReady ? (listening ? 'Stop voice input' : 'Start voice input') : 'Voice input needs a browser microphone.'"
              :aria-pressed="listening"
              @click="toggleMic"
            >
              {{ listening ? "Stop" : "Mic" }}
            </el-button>
            <el-button type="primary" :disabled="store.generating || scopeMissing || !draft.trim()" @click="send">
              Send
            </el-button>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
