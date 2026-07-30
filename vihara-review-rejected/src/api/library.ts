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
