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
  if (parsed.kind === "rejected") return parsed;
  return { manifest: parsed.manifest, assessment: assessManifest(parsed.manifest) };
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
