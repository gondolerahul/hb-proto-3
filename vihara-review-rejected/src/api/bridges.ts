/**
 * Bridges & Gates clients (DRIVER D11, D6 §14) — the connector catalog
 * and bindings (bridges), the social connections (gates), and open
 * sync.conflict disputes read off the signal bus.
 */
import { api } from "./client";

export interface CatalogConnector {
  connector_id: string;
  domain: string;
  display_name: string;
  backend: string;
  auth: string;
  masters: string[];
  bindable: boolean;
}

export interface ConnectorBinding {
  connector_id?: string;
  status?: string;
  credentials_expire_at?: string | null;
  [key: string]: unknown;
}

export async function fetchCatalog(): Promise<CatalogConnector[]> {
  return (await api.get<CatalogConnector[]>("/ai/connectors/catalog")).data;
}

export async function fetchBindings(): Promise<ConnectorBinding[]> {
  return (await api.get<ConnectorBinding[]>("/ai/connectors/bindings")).data;
}

/** Certified (connector-binding, T2) — the refusal belongs to
 * `useCertifiedAct`. Credentials are passed through, never stored here. */
export async function bindConnector(
  connectorId: string,
  credentials: Record<string, string>,
): Promise<ConnectorBinding> {
  return (
    await api.post<ConnectorBinding>(`/ai/connectors/${connectorId}/bind`, {
      credentials,
    })
  ).data;
}

export interface SocialConnection {
  id?: string;
  platform?: string;
  status?: string;
  [key: string]: unknown;
}

/** The gates: social/broadcast platforms. Lives outside /api/v1. */
export async function fetchSocialConnections(): Promise<SocialConnection[]> {
  const response = await api.get<
    SocialConnection[] | { connections?: SocialConnection[] }
  >("/social-connections", { baseURL: "/api" });
  const data = response.data;
  if (Array.isArray(data)) return data;
  return data.connections ?? [];
}

export interface SyncConflict {
  signal_id: string;
  def_name: string | null;
  record_id: string | null;
  losing_delta: Record<string, unknown>;
  connector: string | null;
  created_at: string | null;
}

/** Disputes at the bridge: `sync.conflict` signals, master-wins already
 * applied — the dispute shows both versions, it does not re-fight them. */
export async function fetchSyncConflicts(): Promise<SyncConflict[]> {
  const response = await api.get<
    { id: string; payload?: Record<string, unknown> | null; created_at?: string | null }[]
  >("/ai/signals", { params: { type_prefix: "sync.conflict", limit: 50 } });
  return response.data.map((signal) => {
    const payload = signal.payload ?? {};
    return {
      signal_id: signal.id,
      def_name: typeof payload["def"] === "string" ? payload["def"] : null,
      record_id:
        typeof payload["record_id"] === "string" ? payload["record_id"] : null,
      losing_delta:
        typeof payload["losing_delta"] === "object" &&
        payload["losing_delta"] !== null
          ? (payload["losing_delta"] as Record<string, unknown>)
          : {},
      connector:
        typeof payload["connector"] === "string" ? payload["connector"] : null,
      created_at: signal.created_at ?? null,
    };
  });
}
