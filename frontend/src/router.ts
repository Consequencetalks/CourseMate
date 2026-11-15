import { createRouter, createWebHistory } from "vue-router";
import DocumentsView from "./views/DocumentsView.vue";
import ChatView from "./views/ChatView.vue";
import QuizView from "./views/QuizView.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/documents" },
    { path: "/documents", component: DocumentsView },
    { path: "/chat", component: ChatView },
    { path: "/quiz", component: QuizView },
  ],
});
