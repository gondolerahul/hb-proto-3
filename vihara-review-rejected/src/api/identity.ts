/**
 * The HUD's one identity read (POLISH L3): the wireframes put the
 * TENANT's name in the top-left — "Northwind Co.", not "Vihara" — because
 * the estate is theirs, not ours. Fail-soft to null; the HUD falls back
 * to the wordmark rather than blocking on a lookup.
 */
import { api } from "./client";

export async function fetchCompanyName(): Promise<string | null> {
  try {
    const me = await api.get<{ company_id?: unknown }>("/auth/me");
    const companyId = me.data.company_id;
    if (typeof companyId !== "string") return null;
    // A tenant reads its own company through the scoped list — the
    // by-id route is not readable at tenant level.
    const companies = await api.get<{ id?: unknown; name?: unknown }[]>(
      "/companies",
    );
    const own = companies.data.find((company) => company.id === companyId);
    return typeof own?.name === "string" ? own.name : null;
  } catch {
    return null;
  }
}
