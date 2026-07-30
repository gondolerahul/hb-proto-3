/**
 * The client-side registry (D3 §1, §7). The four JSON files beside this
 * module are the AUTHORED source of truth; the backend serves a mirror of
 * the same files and a backend test enforces byte-equality, so validating
 * against this copy is validating against the service's own contract.
 */
import certified from "./registry/certified.json";
import narrative from "./registry/narrative.json";
import primitive from "./registry/primitive.json";
import world from "./registry/world.json";

export type ComponentClass = "primitive" | "certified" | "world" | "narrative";
export type Renderer = "S" | "C" | "W";

export interface RegistryEntry {
  type: string;
  class: ComponentClass;
  version: number;
  min_supported: number;
  renderers: Renderer[];
  density_variants: string[];
  props: {
    properties?: Record<string, unknown>;
    required?: string[];
    additionalProperties?: boolean;
  };
  bindings: unknown;
  a11y: { role: string; label_from: string | null };
  certified?: {
    intent_kind: string | null;
    gate: string;
    goldens: string[];
    ceremony?: boolean;
  };
}

const ENTRIES: RegistryEntry[] = [
  ...(primitive as RegistryEntry[]),
  ...(certified as RegistryEntry[]),
  ...(world as RegistryEntry[]),
  ...(narrative as RegistryEntry[]),
];

const BY_TYPE = new Map<string, RegistryEntry>(
  ENTRIES.map((entry) => [entry.type, entry]),
);

export function allEntries(): readonly RegistryEntry[] {
  return ENTRIES;
}

export type Resolution =
  | { kind: "ok"; entry: RegistryEntry }
  | { kind: "unknown"; ref: string }
  | { kind: "unsupported"; ref: string; min_supported: number };

/**
 * Resolve a manifest's `type@version` reference (D3 §4). A version below
 * `min_supported` is `unsupported` — the caller must refuse the whole
 * manifest and ask for the sheet equivalent, never render a component it
 * half-understands.
 */
export function resolve(ref: string): Resolution {
  const [bare, versionText] = ref.split("@");
  const entry = bare === undefined ? undefined : BY_TYPE.get(bare);
  if (entry === undefined) return { kind: "unknown", ref };
  const version =
    versionText === undefined ? entry.version : Number(versionText);
  if (Number.isNaN(version) || version > entry.version) {
    return { kind: "unknown", ref };
  }
  if (version < entry.min_supported) {
    return { kind: "unsupported", ref, min_supported: entry.min_supported };
  }
  return { kind: "ok", entry };
}

/** The binding sources an entry declares, or null when it declares none. */
export function declaredSources(entry: RegistryEntry): Set<string> | null {
  const bindings = entry.bindings as
    | { items?: { properties?: { source?: { enum?: string[] } } } }
    | undefined;
  const sources = bindings?.items?.properties?.source?.enum;
  return Array.isArray(sources) ? new Set(sources) : null;
}
