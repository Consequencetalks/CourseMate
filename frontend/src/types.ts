export interface HealthResponse {
  status: string;
}

export interface ErrorBody {
  code: string;
  message: string;
}

export interface ErrorResponse {
  error: ErrorBody;
}

export interface DocumentOut {
  id: string;
  filename: string;
  page_count: number;
  chunk_count: number;
  created_at: string;
}

export interface DocumentCreated extends DocumentOut {
  warnings: string[];
}

export interface ConversationOut {
  id: string;
  title: string;
  document_ids: string[];
  created_at: string;
}

export interface Citation {
  source_id: string;
  document_id: string;
  filename: string;
  page: number;
  excerpt: string;
}

export interface MessageOut {
  id: string;
  role: string;
  content: string;
  citations: Citation[];
  created_at: string;
}

export interface ChatDone {
  message_id: string;
  citations: Citation[];
}

export interface ChatDelta {
  text: string;
}

export interface ChatError {
  code: string;
  message: string;
}

export interface PublicQuestion {
  id: string;
  stem: string;
  options: Record<string, string>;
}

export interface QuizCreated {
  id: string;
  questions: PublicQuestion[];
}

export interface QuizSummary {
  id: string;
  topic: string;
  language: string;
  created_at: string;
  submitted: boolean;
}

export interface QuestionResult extends PublicQuestion {
  selected_option: string;
  correct_option: string;
  correct: boolean;
  explanation: string;
  citations: Citation[];
}

export interface QuizResult {
  correct_count: number;
  total: number;
  questions: QuestionResult[];
}

export interface QuizDetail {
  id: string;
  topic: string;
  language: string;
  document_ids: string[];
  created_at: string;
  questions: PublicQuestion[];
  result: QuizResult | null;
}
