import { defineStore } from "pinia";
import { ref } from "vue";
import type { ConversationOut, MessageOut } from "../types";

export const useChatStore = defineStore("chat", () => {
  const conversations = ref<ConversationOut[]>([]);
  const currentId = ref("");
  const messages = ref<MessageOut[]>([]);
  const generating = ref(false);
  const error = ref("");

  return { conversations, currentId, messages, generating, error };
});
