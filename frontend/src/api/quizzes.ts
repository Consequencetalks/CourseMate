import { request } from "./client";
import type { QuizCreated, QuizDetail, QuizResult, QuizSummary } from "../types";

export function createQuiz(
  documentIds: string[],
  topic: string,
  language: "zh" | "en",
): Promise<QuizCreated> {
  return request<QuizCreated>("/api/quizzes", {
    method: "POST",
    body: JSON.stringify({ document_ids: documentIds, topic, language }),
  });
}

export function listQuizzes(): Promise<QuizSummary[]> {
  return request<QuizSummary[]>("/api/quizzes");
}

export function getQuiz(id: string): Promise<QuizDetail> {
  return request<QuizDetail>(`/api/quizzes/${id}`);
}

export function submitQuiz(
  id: string,
  answers: { question_id: string; option: string }[],
): Promise<QuizResult> {
  return request<QuizResult>(`/api/quizzes/${id}/submit`, {
    method: "POST",
    body: JSON.stringify({ answers }),
  });
}
