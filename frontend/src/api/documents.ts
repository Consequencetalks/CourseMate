import { request } from "./client";
import type { DocumentCreated, DocumentOut } from "../types";

export function uploadDocument(file: File): Promise<DocumentCreated> {
  const body = new FormData();
  body.append("file", file);
  return request<DocumentCreated>("/api/documents", { method: "POST", body });
}

export function listDocuments(): Promise<DocumentOut[]> {
  return request<DocumentOut[]>("/api/documents");
}

export function documentFileUrl(id: string): string {
  return `/api/documents/${id}/file`;
}

export function deleteDocument(id: string): Promise<void> {
  return request<void>(`/api/documents/${id}`, { method: "DELETE" });
}
