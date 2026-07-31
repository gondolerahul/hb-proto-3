import type { Depth } from "../shell/Shell";

/**
 * Surface identity as a URL (R-4 §4, N2) — hand-rolled, no router.
 *
 * Three decisions a reader would otherwise have to reverse-engineer:
 *
 *  1. **No router dependency.** What a router buys — nested layouts, loaders,
 *     lazy segments — this app does not use: there are fifteen leaves, one
 *     layout, and the depth ladder is not a URL tree. What it costs is a
 *     dependency in the initial graph of an app whose tier-C budget is already
 *     the thing D7 §3.3 protects. Two functions and a `popstate` listener are
 *     the whole feature.
 *
 *  2. **`above` is the only edge in the model.** Breadcrumbs, the seeded
 *     back-stack (N3) and the ladder the palette groups by are all read off it,
 *     so a trail cannot disagree with a rung — they are one fact stated once.
 *     `above` is *containment*, and `depth` is the rung, and they are not the
 *     same relation: the dossier sits inside the district room and both are
 *     depth 2, because D6's ladder has four rungs and rooms open onto rooms.
 *     What the model forbids is the reverse — a parent deeper than its child —
 *     which is the one shape that would stop Back from rising. `study.above` is
 *     the root rather than the terrace because the Study is the desk, not a
 *     place in the estate (D6 §7).
 *
 *  3. **A subject is only in the URL where the platform has one to name.**
 *     `/district/{code}` and `/tray/{id}` exist because L8 makes a push *a tray
 *     or nothing* and the Line's `notificationclick` has to be able to say which
 *     one. A surface with `named: false` silently drops a trailing segment
 *     rather than 404ing on it — the surface is what the URL is *for*, and the
 *     address bar is corrected on arrival so it never disagrees with the screen.
 */

export type SurfaceId =
  | "still"
  | "terrace"
  | "district"
  | "dossier"
  | "boardroom"
  | "standup"
  | "study"
  | "glasshouse"
  | "undercroft"
  | "library"
  | "bridges"
  | "talent"
  | "gallery"
  | "tray"
  | "hall";

export interface SurfaceDef {
  id: SurfaceId;
  /** The first path segment. The root surface owns `""`. */
  segment: string;
  /** As the palette prints it, and as the breadcrumb says it. */
  label: string;
  /** The palette's second column — what the place is for. */
  note: string;
  /** Words the palette matches on but never prints. */
  aka: string;
  depth: Depth;
  /** The surface one rung up. `null` only for the root. */
  above: SurfaceId | null;
  /** Whether a subject may follow the segment (`/district/P08`). */
  named: boolean;
  /** How much atmosphere this surface can carry without competing with itself. */
  intensity: "full" | "quiet" | "hushed";
}

/**
 * The fifteen. The Line's three are a second front door (`/line.html`), not
 * entries here — they are a different document with a different budget, which
 * is the whole reason `vite.config.ts` gives them a separate input.
 */
export const SURFACES: readonly SurfaceDef[] = [
  {
    id: "still",
    segment: "",
    label: "Still surface",
    note: "the front door",
    aka: "home start front quiet",
    depth: 0,
    above: null,
    named: false,
    intensity: "full",
  },
  {
    id: "terrace",
    segment: "terrace",
    label: "The Terrace",
    note: "the estate, seen whole",
    aka: "map districts territory overview",
    depth: 1,
    above: "still",
    named: false,
    intensity: "full",
  },
  {
    id: "standup",
    segment: "standup",
    label: "The Standup",
    note: "one voice, this morning",
    aka: "morning story briefing",
    depth: 1,
    above: "terrace",
    named: false,
    intensity: "hushed",
  },
  {
    id: "district",
    segment: "district",
    label: "District room",
    note: "one process, on its floor",
    aka: "collections process room floor",
    depth: 2,
    above: "terrace",
    named: true,
    intensity: "quiet",
  },
  {
    id: "dossier",
    segment: "dossier",
    label: "Dossier",
    note: "a colleague, one-on-one",
    aka: "colleague agent review seals",
    depth: 2,
    above: "district",
    named: true,
    intensity: "hushed",
  },
  {
    id: "hall",
    segment: "hall",
    label: "Registry Hall",
    note: "the records themselves",
    aka: "invoices records table ledger registry",
    depth: 2,
    above: "district",
    named: true,
    intensity: "hushed",
  },
  {
    id: "tray",
    segment: "tray",
    label: "The Tray",
    note: "what is waiting on you",
    aka: "approvals certified decisions waiting",
    depth: 2,
    above: "terrace",
    named: true,
    intensity: "quiet",
  },
  {
    id: "boardroom",
    segment: "boardroom",
    label: "The Boardroom",
    note: "strategy, argued out",
    aka: "brainstorm propositions minutes strategy",
    depth: 2,
    above: "terrace",
    named: false,
    intensity: "quiet",
  },
  {
    id: "study",
    segment: "study",
    label: "The Study",
    note: "your desk, your keys",
    aka: "settings account preferences credits passkey profile",
    depth: 2,
    above: "still",
    named: false,
    intensity: "hushed",
  },
  {
    id: "glasshouse",
    segment: "glasshouse",
    label: "The Glasshouse",
    note: "the twin, drained of colour",
    aka: "simulation scenario twin forecast",
    depth: 2,
    above: "terrace",
    named: false,
    intensity: "quiet",
  },
  {
    id: "library",
    segment: "library",
    label: "The Library",
    note: "what the estate has read",
    aka: "documents provenance uploads influence",
    depth: 2,
    above: "terrace",
    named: false,
    intensity: "hushed",
  },
  {
    id: "bridges",
    segment: "bridges",
    label: "Bridges & Gates",
    note: "the estate's edge",
    aka: "connectors consent integrations disputes",
    depth: 2,
    above: "terrace",
    named: false,
    intensity: "hushed",
  },
  {
    id: "talent",
    segment: "talent",
    label: "Talent Office",
    note: "who else could work here",
    aka: "hire hiring candidates roles brief",
    depth: 2,
    above: "terrace",
    named: false,
    intensity: "hushed",
  },
  {
    id: "gallery",
    segment: "gallery",
    label: "The Gallery",
    note: "who worked here before",
    aka: "alumni seasons history mandates past",
    depth: 2,
    above: "terrace",
    named: false,
    intensity: "hushed",
  },
  {
    id: "undercroft",
    segment: "undercroft",
    label: "The Undercroft",
    note: "the machinery, uncovered",
    aka: "manifest signals routing flags debug internals",
    depth: 3,
    above: "terrace",
    named: false,
    intensity: "hushed",
  },
];

const BY_ID = new Map<SurfaceId, SurfaceDef>(SURFACES.map((s) => [s.id, s]));

/** The root. `SURFACES[0]` is asserted rather than searched — an empty
 *  catalogue is a build error, not a runtime state. */
export const ROOT: SurfaceDef = SURFACES[0]!;

export function surfaceOf(id: SurfaceId): SurfaceDef {
  return BY_ID.get(id) ?? ROOT;
}

export interface Route {
  surface: SurfaceId;
  /** The subject the URL named, or `null`. Never invented: a surface that was
   *  reached without one is reached without one. */
  subject: string | null;
}

/**
 * A pathname → a route. Anything unrecognised is the root, and the caller
 * corrects the address bar so the two never disagree.
 */
export function parseRoute(pathname: string): Route {
  const parts = pathname.split("/").filter((p) => p.length > 0);
  const first = parts[0];
  if (first === undefined) return { surface: ROOT.id, subject: null };

  const def = SURFACES.find((s) => s.segment === first);
  if (def === undefined) return { surface: ROOT.id, subject: null };

  const rest = parts[1];
  if (!def.named || rest === undefined || rest.length === 0) {
    return { surface: def.id, subject: null };
  }
  return { surface: def.id, subject: decodeURIComponent(rest) };
}

/** A route → the pathname that names it. The inverse of `parseRoute` for every
 *  route the app can be in. */
export function pathOf(route: Route): string {
  const def = surfaceOf(route.surface);
  if (def.segment.length === 0) return "/";
  if (def.named && route.subject !== null && route.subject.length > 0) {
    return `/${def.segment}/${encodeURIComponent(route.subject)}`;
  }
  return `/${def.segment}`;
}

/**
 * The rungs above a route, root first — the ladder Back climbs (N3).
 *
 * Ancestors carry no subject: rising from `/dossier/ag-3` goes to *the*
 * district room, and which one that is is a fact the dossier holds, not one
 * the URL of the dossier can be read to imply.
 */
export function ancestorsOf(route: Route): Route[] {
  const chain: Route[] = [];
  let cursor = surfaceOf(route.surface).above;
  // The catalogue is a tree rooted at `still`, so this terminates; the guard is
  // against a future edit that makes it a cycle, not against today's data.
  const guard = new Set<SurfaceId>([route.surface]);
  while (cursor !== null && !guard.has(cursor)) {
    guard.add(cursor);
    chain.unshift({ surface: cursor, subject: null });
    cursor = surfaceOf(cursor).above;
  }
  return chain;
}
