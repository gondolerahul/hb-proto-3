/**
 * The GenUI seam clients (D5): registry, estate, manifests, trays, echo.
 * The manifest arrives as two NDJSON lines (scaffold, fill); parsing is a
 * pure function so the protocol is testable without a wire.
 */
import { assessManifest, type Assessment } from "../manifest/refusals";
import {
  FillSchema,
  ScaffoldSchema,
  mergeFill,
  type WireScaffold,
} from "../manifest/schema";
import { api } from "./client";

export type ParsedStream =
  | { kind: "ok"; manifest: WireScaffold }
  | { kind: "rejected"; reason: string };

/** Parse the two-part stream (D4 §6). Malformed wire data rejects loudly —
 * the refusal ladder governs *valid* manifests with bad content; a body
 * that is not even the protocol never reaches it. */
export function parseManifestStream(body: string): ParsedStream {
  const lines = body.split("\n").filter((line) => line.trim().length > 0);
  if (lines.length !== 2) {
    return { kind: "rejected", reason: `expected 2 stream parts, got ${lines.length}` };
  }
  let scaffoldRaw: unknown;
  let fillRaw: unknown;
  try {
    scaffoldRaw = JSON.parse(lines[0] ?? "");
    fillRaw = JSON.parse(lines[1] ?? "");
  } catch {
    return { kind: "rejected", reason: "stream part is not JSON" };
  }
  const scaffold = ScaffoldSchema.safeParse(scaffoldRaw);
  if (!scaffold.success) {
    return { kind: "rejected", reason: "scaffold failed schema validation" };
  }
  const fill = FillSchema.safeParse(fillRaw);
  if (!fill.success) {
    return { kind: "rejected", reason: "fill failed schema validation" };
  }
  const merged = mergeFill(scaffold.data, fill.data);
  if (merged.kind === "rejected") return merged;
  return { kind: "ok", manifest: merged.manifest };
}

export interface FetchedManifest {
  manifest: WireScaffold;
  assessment: Assessment;
}

/**
 * The manifest inspector's memory (DRIVER D10, D6 §15): every manifest
 * this session fetched, with what the inspector needs to answer "why did
 * she show me that" — surface, intent shape, verdict, issue time and TTL
 * (cache age is computed at read). In-memory only, newest first, capped.
 */
export interface ManifestLogEntry {
  surface: string;
  renderer: string;
  density: string;
  verdict: "render" | "reject" | "wire-reject";
  reason?: string;
  issued_at?: string;
  ttl_seconds?: number;
  manifest_version?: number;
  component_count?: number;
  fetched_at: string;
}

const manifestLog: ManifestLogEntry[] = [];
const MANIFEST_LOG_CAP = 50;

export function readManifestLog(): readonly ManifestLogEntry[] {
  return manifestLog;
}

function recordManifest(entry: ManifestLogEntry): void {
  manifestLog.unshift(entry);
  if (manifestLog.length > MANIFEST_LOG_CAP) manifestLog.pop();
}

export async function fetchManifest(
  surface: string,
  renderer: "S" | "C" | "W",
  density: "novice" | "operator" = "novice",
): Promise<FetchedManifest | { kind: "rejected"; reason: string }> {
  const response = await api.get<string>("/ai/genui/manifest", {
    params: { surface, renderer, density },
    responseType: "text",
    transformResponse: (data: string) => data,
  });
  const parsed = parseManifestStream(response.data);
  const fetchedAt = new Date().toISOString();
  if (parsed.kind === "rejected") {
    recordManifest({
      surface,
      renderer,
      density,
      verdict: "wire-reject",
      reason: parsed.reason,
      fetched_at: fetchedAt,
    });
    return parsed;
  }
  const assessment = assessManifest(parsed.manifest);
  recordManifest({
    surface,
    renderer,
    density,
    verdict: assessment.verdict === "reject" ? "reject" : "render",
    reason: assessment.verdict === "reject" ? assessment.reason : undefined,
    issued_at: parsed.manifest.issued_at,
    ttl_seconds: parsed.manifest.ttl_seconds,
    manifest_version: parsed.manifest.manifest_version,
    component_count: parsed.manifest.components.length,
    fetched_at: fetchedAt,
  });
  return { manifest: parsed.manifest, assessment };
}

export async function fetchEstate(): Promise<Record<string, unknown>> {
  return (await api.get<Record<string, unknown>>("/ai/genui/estate")).data;
}

export async function fetchTrays(): Promise<unknown[]> {
  return (await api.get<unknown[]>("/ai/genui/trays")).data;
}

export interface EchoInput {
  sentence: string;
  action_ref: { kind: string; surface_id?: string; params?: Record<string, unknown> };
  manifest_hash?: string;
  component_id?: string;
}

/** Fire-and-forget by contract (D5 §6): an echo that fails to record loses
 * training data, never work — so the caller is never made to care. */
export async function emitEcho(echo: EchoInput): Promise<void> {
  try {
    await api.post("/ai/genui/echo", {
      ...echo,
      occurred_at: new Date().toISOString(),
    });
  } catch {
    // deliberately swallowed — see the contract note above
  }
}
