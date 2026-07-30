/**
 * The Study's remaining clients (DRIVER D12, D6 §15a) — identity, the
 * preference store (`notify.*` / `density.*` — namespaces LEARN already
 * governs; the Study adds no new store), and billing & wallet.
 */
import { api } from "./client";

export interface Me {
  id: string;
  email: string;
  full_name: string | null;
  company_id: string;
  role: string;
  [key: string]: unknown;
}

export async function fetchMe(): Promise<Me> {
  return (await api.get<Me>("/auth/me")).data;
}

export interface PreferenceValue {
  value: unknown;
  stated?: boolean;
  learned?: boolean;
  [key: string]: unknown;
}

export async function fetchPreferences(
  prefix?: string,
): Promise<Record<string, PreferenceValue>> {
  const response = await api.get<{ preferences: Record<string, PreferenceValue> }>(
    "/ai/learning/preferences",
    { params: prefix !== undefined ? { prefix } : {} },
  );
  return response.data.preferences;
}

/** Stating a preference clears any learned value — the store's own rule. */
export async function writePreference(
  key: string,
  value: unknown,
): Promise<void> {
  await api.put("/ai/learning/preferences", { key, value });
}

export async function observeDensity(
  surface: string,
  density: "novice" | "operator",
): Promise<void> {
  await api.post("/ai/learning/preferences/observe-density", {
    surface,
    density,
  });
}

export interface WalletBalance {
  balance?: number;
  currency?: string | null;
  [key: string]: unknown;
}

export async function fetchBalance(): Promise<WalletBalance> {
  return (await api.get<WalletBalance>("/credits/balance", { baseURL: "/api/v1" }))
    .data;
}

export interface SubscriptionInfo {
  status?: string | null;
  tier?: string | null;
  subscription_status?: string | null;
  [key: string]: unknown;
}

export async function fetchSubscription(): Promise<SubscriptionInfo> {
  return (
    await api.get<SubscriptionInfo>("/credits/subscriptions", {
      baseURL: "/api/v1",
    })
  ).data;
}
