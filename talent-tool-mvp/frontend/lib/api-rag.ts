/**
 * T2701: RAG API client (TypeScript).
 *
 * Mirrors backend/api/rag.py — used by DocumentUpload, ChatWithCitations and
 * the (employer)/knowledge management page.
 */

export interface RagCollection {
  id: string;
  tenant_id: string;
  name: string;
  description?: string | null;
  embedding_model: string;
  embedding_dim: number;
  qdrant_collection: string;
  chunk_size: number;
  chunk_overlap: number;
  is_active: boolean;
  created_at: string;
}

export interface RagDocument {
  id: string;
  collection_id: string;
  name: string;
  display_name: string;
  source: string;
  mime_type?: string | null;
  size_bytes: number;
  status: string;
  total_chunks: number;
  total_tokens: number;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
}

export interface RagCitation {
  document_id: string;
  chunk_id: string;
  document_name: string;
  position: number;
  snippet: string;
  score: number;
  rerank_score?: number | null;
  token: string;
}

export interface RagQueryResponse {
  query: string;
  answer: string;
  citations: RagCitation[];
  retrieval_ms: number;
  rerank_ms: number;
  generation_ms: number;
  total_ms: number;
  metadata?: Record<string, unknown>;
}

const DEFAULT_BASE = "/api/rag";

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

export async function listCollections(
  apiBase: string = DEFAULT_BASE,
): Promise<RagCollection[]> {
  const res = await fetch(`${apiBase}/collections`, { credentials: "include" });
  return jsonOrThrow<RagCollection[]>(res);
}

export async function createCollection(
  body: {
    name: string;
    description?: string;
    embedding_model?: string;
    chunk_size?: number;
    chunk_overlap?: number;
    metadata?: Record<string, unknown>;
  },
  apiBase: string = DEFAULT_BASE,
): Promise<RagCollection> {
  const res = await fetch(`${apiBase}/collections`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow<RagCollection>(res);
}

export async function listDocuments(
  collectionId: string,
  apiBase: string = DEFAULT_BASE,
): Promise<RagDocument[]> {
  const res = await fetch(
    `${apiBase}/documents?collection_id=${encodeURIComponent(collectionId)}`,
    { credentials: "include" },
  );
  return jsonOrThrow<RagDocument[]>(res);
}

export async function getDocument(
  documentId: string,
  apiBase: string = DEFAULT_BASE,
): Promise<RagDocument> {
  const res = await fetch(`${apiBase}/documents/${documentId}`, {
    credentials: "include",
  });
  return jsonOrThrow<RagDocument>(res);
}

export async function uploadDocument(
  file: File,
  collectionId: string,
  apiBase: string = DEFAULT_BASE,
  displayName?: string,
): Promise<RagDocument> {
  const form = new FormData();
  form.append("file", file);
  form.append("collection_id", collectionId);
  form.append("display_name", displayName ?? file.name);
  form.append("source", "upload");
  const res = await fetch(`${apiBase}/documents`, {
    method: "POST",
    credentials: "include",
    body: form,
  });
  return jsonOrThrow<RagDocument>(res);
}

export async function queryRag(
  body: {
    query: string;
    collection_id: string;
    top_k?: number;
    mode?: "vector" | "bm25" | "hybrid";
    use_reranker?: boolean;
    use_citations?: boolean;
  },
  apiBase: string = DEFAULT_BASE,
): Promise<RagQueryResponse> {
  const res = await fetch(`${apiBase}/query`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ top_k: 5, mode: "hybrid", ...body }),
  });
  return jsonOrThrow<RagQueryResponse>(res);
}
