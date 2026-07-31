/**
 * Library clients (DRIVER D9, D6 §13) — documents with their LIB
 * provenance, per-document influence (the counter that matches the
 * sentence), and the citation passage read.
 */
import { api } from "./client";

export interface DocumentOut {
  id: string;
  filename: string;
  file_type: string;
  upload_status: string;
  created_at: string;
  source_kind: string | null;
  source_uri: string | null;
  effective_from: string | null;
  staleness_state: string | null;
  staleness_reason: string | null;
  superseded_by_id: string | null;
  memory_domain: string | null;
}

export async function fetchDocuments(): Promise<DocumentOut[]> {
  return (await api.get<DocumentOut[]>("/ai/documents")).data;
}

export interface InfluenceOut {
  document_id: string;
  window_days: number;
  retrievals: number;
  /** `distinct_queries` under its honest name — the counter that matches
   * "this document answered N questions", never the row count. */
  questions_answered: number;
  peak_distinct_colleagues: number;
  active_days: number;
}

export async function fetchInfluence(
  documentId: string,
): Promise<InfluenceOut> {
  return (
    await api.get<InfluenceOut>(`/ai/documents/${documentId}/influence`)
  ).data;
}

export interface PassageOut {
  document_id?: string;
  chunks?: { chunk_index: number; content: string; heading_path?: string | null }[];
  [key: string]: unknown;
}

export async function fetchPassage(
  documentId: string,
  chunk = 0,
): Promise<PassageOut> {
  return (
    await api.get<PassageOut>(`/ai/documents/${documentId}/passage`, {
      params: { chunk, context: 1 },
    })
  ).data;
}

/* ─────────────────────────────────────────────── R-4 part P: write and search */

/**
 * What an upload answers with — an id and a status, and nothing else.
 *
 * `upload_status` is the whole point: extraction and embedding happen after
 * the response, so a document is present before it is readable. A surface that
 * lists it as ready on the strength of a 200 is lying about a document nobody
 * can cite yet, and the influence counter would read zero for a reason that is
 * not "unused".
 */
export interface UploadAccepted {
  id: string;
  status: string;
}

/**
 * Upload a document (`POST /ai/documents/upload`).
 *
 * `multipart/form-data`, and the `Content-Type` is deliberately **not** set
 * here: the browser has to write the boundary parameter, and setting the
 * header by hand omits it and produces a 422 that reads like a bad file.
 */
export async function uploadDocument(
  file: File,
  entityId?: string,
): Promise<UploadAccepted> {
  const body = new FormData();
  body.append("file", file);
  return (
    await api.post<UploadAccepted>("/ai/documents/upload", body, {
      params: entityId !== undefined ? { entity_id: entityId } : {},
    })
  ).data;
}

/**
 * One retrieved chunk. `similarity` is the retriever's own score and is not a
 * confidence: it ranks these results against each other and says nothing about
 * whether the document answers the question.
 */
export interface SearchHit {
  chunk_id: string;
  document_id: string;
  filename: string;
  content: string;
  similarity: number;
}

/**
 * Search the library (`POST /ai/documents/search`).
 *
 * A POST whose arguments are **query parameters**, not a body — the shipped
 * signature, and the reason this wrapper exists rather than each caller
 * guessing. An empty result is a real answer: the library may hold the
 * document and not yet have embedded it (see `UploadAccepted`).
 */
export async function searchDocuments(
  query: string,
  options?: { entityId?: string; topK?: number },
): Promise<SearchHit[]> {
  const params: Record<string, string | number> = {
    query,
    top_k: options?.topK ?? 5,
  };
  if (options?.entityId !== undefined) params["entity_id"] = options.entityId;
  return (await api.post<SearchHit[]>("/ai/documents/search", null, { params })).data;
}
