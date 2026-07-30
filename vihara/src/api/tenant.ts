/**
 * The tenant-schema clients (DRIVER D3, D6 §7) — the strongest backend
 * that already exists: defs, records, CRUD with CAS, the certified bulk
 * endpoint, and pending proposals read off the signal bus.
 */
import { api } from "./client";

export interface EntityDefField {
  name: string;
  type: string;
  required?: boolean;
  values?: string[];
  [key: string]: unknown;
}

export interface EntityDef {
  name: string;
  module: string;
  domain_tag: string | null;
  owner_process_code: string | null;
  version: number;
  fields: EntityDefField[];
}

export interface TenantRecordOut {
  id: string;
  entity_def_id: string;
  data: Record<string, unknown>;
  version: number;
  def_version: number;
  deleted_at: string | null;
  created_at: string;
  sor: string | null;
  synced: boolean;
}

export interface WriteResult {
  status: string;
  record: TenantRecordOut | null;
  signal_id: string | null;
  reason: string | null;
}

export async function fetchDefs(): Promise<EntityDef[]> {
  return (await api.get<EntityDef[]>("/ai/tenant/defs")).data;
}

export async function fetchRecords(
  defName: string,
  limit = 200,
): Promise<TenantRecordOut[]> {
  const response = await api.get<TenantRecordOut[]>("/ai/tenant/records", {
    params: { def_name: defName, limit },
  });
  return response.data;
}

export async function createRecord(
  defName: string,
  data: Record<string, unknown>,
): Promise<WriteResult> {
  return (
    await api.post<WriteResult>("/ai/tenant/records", {
      def_name: defName,
      data,
    })
  ).data;
}

export async function updateRecord(
  recordId: string,
  data: Record<string, unknown>,
  expectedVersion: number,
): Promise<WriteResult> {
  return (
    await api.patch<WriteResult>(`/ai/tenant/records/${recordId}`, {
      data,
      expected_version: expectedVersion,
    })
  ).data;
}

export async function deleteRecord(recordId: string): Promise<void> {
  await api.delete(`/ai/tenant/records/${recordId}`);
}

export interface BulkResult {
  op: string;
  def_name: string;
  applied: number;
  results: { id: string; status: string; reason?: string }[];
}

/** The certified bulk act — `bulk_data_operation` is T2, so a plain
 * session gets a `step_up_required` refusal here; that refusal belongs to
 * `useCertifiedAct`, which turns it into the step-up ceremony (D6 §7). */
export async function bulkRecords(
  defName: string,
  op: "update" | "delete",
  recordIds: string[],
  data?: Record<string, unknown>,
): Promise<BulkResult> {
  return (
    await api.post<BulkResult>("/ai/tenant/records/bulk", {
      def_name: defName,
      op,
      record_ids: recordIds,
      ...(data !== undefined ? { data } : {}),
    })
  ).data;
}

export interface RecordProposal {
  signal_id: string;
  record_id: string | null;
  def_name: string | null;
  op: string | null;
  delta: Record<string, unknown>;
  actor: string | null;
  created_at: string | null;
}

interface SignalOut {
  id: string;
  type?: string;
  status?: string;
  payload?: Record<string, unknown> | null;
  created_at?: string | null;
}

/** Pending others-propose changes, read off the signal bus (the record
 * service emits `object.change_proposed`; nothing else stores them). */
export async function fetchProposals(): Promise<RecordProposal[]> {
  const response = await api.get<SignalOut[]>("/ai/signals", {
    params: { type_prefix: "object.change_proposed", limit: 100 },
  });
  return response.data.map((signal) => {
    const payload = signal.payload ?? {};
    return {
      signal_id: signal.id,
      record_id: typeof payload["record_id"] === "string" ? payload["record_id"] : null,
      def_name: typeof payload["def"] === "string" ? payload["def"] : null,
      op: typeof payload["op"] === "string" ? payload["op"] : null,
      delta:
        typeof payload["delta"] === "object" && payload["delta"] !== null
          ? (payload["delta"] as Record<string, unknown>)
          : {},
      actor: typeof payload["actor"] === "string" ? payload["actor"] : null,
      created_at: signal.created_at ?? null,
    };
  });
}
