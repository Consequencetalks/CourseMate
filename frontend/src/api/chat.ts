import { ApiError } from "./client";
import type { ChatDelta, ChatDone, ChatError, ConversationOut, MessageOut } from "../types";

export function createConversation(documentIds: string[]): Promise<ConversationOut> {
  return requestJson<ConversationOut>("/api/conversations", {
    method: "POST",
    body: JSON.stringify({ document_ids: documentIds }),
  });
}

export function listConversations(): Promise<ConversationOut[]> {
  return requestJson<ConversationOut[]>("/api/conversations");
}

export function listMessages(conversationId: string): Promise<MessageOut[]> {
  return requestJson<MessageOut[]>(`/api/conversations/${conversationId}/messages`);
}

export interface ChatHandlers {
  onDelta: (text: string) => void;
  onDone: (done: ChatDone) => void;
  onError: (error: ChatError) => void;
}

export async function streamChat(
  conversationId: string,
  message: string,
  handlers: ChatHandlers,
): Promise<void> {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conversation_id: conversationId, message }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(
      body?.error?.message ?? response.statusText,
      response.status,
      body?.error?.code ?? "ERROR",
    );
  }
  if (!response.body) {
    throw new ApiError("The reply ended before it finished.", 0, "STREAM_ERROR");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finished = false;

  const consume = (block: string) => {
    const parsed = parseBlock(block);
    if (!parsed) {
      return;
    }
    if (parsed.event === "delta") {
      handlers.onDelta((JSON.parse(parsed.data) as ChatDelta).text);
      return;
    }
    if (parsed.event === "done") {
      finished = true;
      handlers.onDone(JSON.parse(parsed.data) as ChatDone);
      return;
    }
    if (parsed.event === "error") {
      finished = true;
      handlers.onError(JSON.parse(parsed.data) as ChatError);
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      consume(part);
    }
  }
  buffer += decoder.decode();
  if (buffer.trim()) {
    consume(buffer);
  }
  if (!finished) {
    throw new ApiError("The reply ended before it finished.", 0, "STREAM_ERROR");
  }
}

function parseBlock(block: string): { event: string; data: string } | null {
  let event = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    const trimmed = line.replace(/\r$/, "");
    if (!trimmed || trimmed.startsWith(":")) {
      continue;
    }
    if (trimmed.startsWith("event:")) {
      event = trimmed.slice(6).trim();
    } else if (trimmed.startsWith("data:")) {
      data.push(trimmed.slice(5).trim());
    }
  }
  if (!data.length) {
    return null;
  }
  return { event, data: data.join("\n") };
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(
      body?.error?.message ?? response.statusText,
      response.status,
      body?.error?.code ?? "ERROR",
    );
  }
  return response.json() as Promise<T>;
}
