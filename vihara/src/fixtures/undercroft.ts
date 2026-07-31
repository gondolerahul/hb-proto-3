/**
 * The Undercroft (D6 §15) — depth 3, the engine room.
 *
 * Bound to `signals/*`, `loop/envelope`, `intelligence/*`,
 * `tenant-schema/defs` and `genui/manifest` — all shipped except the last, which
 * SEAM added.
 *
 * Everything here already exists somewhere in the platform. The Undercroft's job
 * is not to compute anything; it is to be the one place an operator can look
 * without knowing which subsystem to ask. Pinned to operator density regardless
 * of the learned value (art bible §6): depth 3's audience is operators.
 */

export type BayKey =
  | "manifest"
  | "signals"
  | "triggers"
  | "envelopes"
  | "traces"
  | "schema"
  | "routing"
  | "consent"
  | "flags";

export interface Bay {
  key: BayKey;
  label: string;
  /** What this bay is for, in an operator's terms. */
  purpose: string;
  /** The endpoint behind it, so a reader knows where the data came from. */
  source: string;
  count: number | null;
}

export const BAYS: Bay[] = [
  {
    key: "manifest",
    label: "Manifest inspector",
    purpose: "What she rendered, why, and what it resolved against",
    source: "GET /ai/genui/manifest",
    count: null,
  },
  { key: "signals", label: "Signals", purpose: "The bus, live", source: "GET /ai/signals", count: 1_284 },
  { key: "triggers", label: "Trigger registry", purpose: "What fires what", source: "GET /ai/signals/triggers", count: 41 },
  { key: "envelopes", label: "Envelopes", purpose: "Budget, spend, holds, reserve", source: "GET /ai/loop/envelope", count: 7 },
  { key: "traces", label: "Run traces", purpose: "Step-by-step, per run", source: "GET /ai/executions", count: 3_912 },
  { key: "schema", label: "Schema browser", purpose: "Entity defs and their versions", source: "GET /ai/tenant-schema/defs", count: 35 },
  { key: "routing", label: "Routing", purpose: "Which model, why, at what cost", source: "GET /ai/intelligence/routing", count: 8_440 },
  { key: "consent", label: "Consent & DNC", purpose: "Who asked us to stop", source: "GET /ai/consent", count: 12 },
  { key: "flags", label: "Feature flags", purpose: "What is on, for whom", source: "GET /ai/flags", count: 23 },
];

/**
 * The manifest inspector's payload.
 *
 * This is the bay that makes the rest of the product debuggable: without it,
 * "why did she show me that" has **no answer anywhere**. So it carries the
 * manifest as served, its `intent_shape`, its cache age, and the registry
 * versions it resolved against — the four things you need to reproduce a render.
 */
export const MANIFEST = {
  surface: "district.room",
  intentShape: "district.room:P08:operator:v3",
  servedAt: "09:41:22",
  cacheAgeSeconds: 47,
  /** The cache is keyed on shape, never on tenant — a tenant-dependent key would
      leak one tenant's manifest into another's render. */
  cacheKey: "shape:district.room|dens:operator|entdef:35@v3|reg:1.4.2",
  honestyGrade: "replay" as const,
  registry: [
    { component: "world.plinth", version: "1.4.2", certified: false },
    { component: "world.treasury-gauge", version: "1.4.2", certified: false },
    { component: "primitive.register", version: "1.4.0", certified: false },
    { component: "certified.step-up", version: "1.2.0", certified: true },
  ],
  refusals: [
    {
      at: "09:41:22",
      what: "narrative.story-card@2.0.0",
      why: "version not in the served registry — rendered 1.4.2 instead",
    },
  ],
  json: `{
  "surface": "district.room",
  "intent_shape": "district.room:P08:operator:v3",
  "honesty_grade": "replay",
  "regions": [
    { "id": "place", "components": [
      { "ref": "world.plinth@1.4.2", "bind": "estate.district.P08.kpi" },
      { "ref": "world.treasury-gauge@1.4.2", "bind": "loop.envelope.P08" }
    ] },
    { "id": "work", "components": [
      { "ref": "primitive.register@1.4.0", "bind": "executions?district=P08&state=running" }
    ] }
  ]
}`,
};

export interface SignalRow {
  id: string;
  kind: string;
  at: string;
  state: "delivered" | "parked" | "dead" | "in-flight";
  attempts: number;
  /** null until the dispatcher has claimed it. Never rendered as 0. */
  latencyMs: number | null;
}

export const SIGNALS: SignalRow[] = [
  { id: "sig-9f21", kind: "email.inbound", at: "09:41:18", state: "delivered", attempts: 1, latencyMs: 142 },
  { id: "sig-9f20", kind: "payment.received", at: "09:40:52", state: "delivered", attempts: 1, latencyMs: 96 },
  { id: "sig-9f1e", kind: "call.completed", at: "09:38:04", state: "parked", attempts: 3, latencyMs: 5_512 },
  { id: "sig-9f1d", kind: "invoice.overdue", at: "09:37:41", state: "delivered", attempts: 2, latencyMs: 388 },
  { id: "sig-9f1c", kind: "whatsapp.inbound", at: "09:36:12", state: "in-flight", attempts: 1, latencyMs: null },
  { id: "sig-9f19", kind: "sync.conflict", at: "09:31:55", state: "dead", attempts: 5, latencyMs: 12_004 },
];

export interface RoutingRow {
  runId: string;
  task: string;
  model: string;
  why: string;
  costINR: number;
  /** Where the router downshifted because the wallet was thin. */
  downshifted: boolean;
}

export const ROUTING: RoutingRow[] = [
  { runId: "4f2a", task: "compose chase", model: "sonnet-5", why: "complexity 0.62 · default band", costINR: 0.4, downshifted: false },
  { runId: "9c11", task: "match payment", model: "haiku-4.5", why: "complexity 0.18 · cheap band", costINR: 0.05, downshifted: false },
  { runId: "b207", task: "summarise call", model: "haiku-4.5", why: "wallet under threshold · downshifted from sonnet-5", costINR: 0.06, downshifted: true },
  { runId: "7d40", task: "reconcile split", model: "opus-5", why: "complexity 0.91 · escalated band", costINR: 2.1, downshifted: false },
];

export const FLAGS = [
  { key: "genui.world.tierA", on: true, scope: "this tenant" },
  { key: "genui.line.push", on: true, scope: "this tenant" },
  { key: "twin.promotion.canary", on: true, scope: "platform" },
  { key: "sega.tool_synthesis", on: false, scope: "platform" },
  { key: "fleet.glm.optin", on: false, scope: "this tenant" },
];
