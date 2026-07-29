/**
 * The wire schemas (D4 §1, §6) — what arrives over /ai/genui/manifest,
 * validated at the client boundary with Zod because a manifest is generated
 * content that chooses UI: it is checked, never trusted (D1 §2).
 */
import { z } from "zod";

export const BindingSchema = z.object({
  source: z.string(),
  params: z.record(z.unknown()).optional(),
});

export const HonestyGrade = z.enum([
  "replay",
  "forecast",
  "unknown",
  "untested",
]);

export const ComponentSchema = z.object({
  id: z.string().min(1),
  type: z.string().min(1),
  region: z.string().nullish(),
  props: z.record(z.unknown()).optional(),
  bindings: z.array(BindingSchema).optional(),
  honesty_grade: HonestyGrade.optional(),
  twin_run_id: z.string().nullish(),
});

export const ScaffoldSchema = z.object({
  part: z.literal("scaffold"),
  manifest_version: z.number(),
  surface_id: z.string().min(1),
  surface_version: z.number().optional(),
  renderer: z.enum(["S", "C", "W"]),
  plane: z.enum(["live", "twin"]).default("live"),
  depth: z.number().int().min(0).max(3),
  density: z.enum(["novice", "operator"]),
  layout: z.object({ kind: z.string(), regions: z.array(z.string()) }),
  components: z.array(ComponentSchema),
  sheet_equivalent: z.string().optional(),
  context_ref: z.unknown().optional(),
  issued_at: z.string(),
  ttl_seconds: z.number(),
});

export const FillSchema = z.object({
  part: z.literal("fill"),
  components: z.record(
    z.object({
      props: z.record(z.unknown()).optional(),
      bindings: z.array(BindingSchema).optional(),
    }),
  ),
});

export type WireBinding = z.infer<typeof BindingSchema>;
export type WireComponent = z.infer<typeof ComponentSchema>;
export type WireScaffold = z.infer<typeof ScaffoldSchema>;
export type WireFill = z.infer<typeof FillSchema>;

export type MergeResult =
  | { kind: "ok"; manifest: WireScaffold }
  | { kind: "rejected"; reason: string };

/**
 * Merge the fill into the scaffold (D4 §6). Two rules, both hard:
 * component identity is FIXED in the scaffold — a fill may not add, remove
 * or retype a component, only fill it — and certified components do not
 * stream, so a fill claiming one is a protocol violation, not data.
 */
export function mergeFill(
  scaffold: WireScaffold,
  fill: WireFill,
): MergeResult {
  const byId = new Map(scaffold.components.map((c) => [c.id, c]));
  for (const [id, patch] of Object.entries(fill.components)) {
    const component = byId.get(id);
    if (component === undefined) {
      return {
        kind: "rejected",
        reason: `fill names component ${id!} the scaffold never declared`,
      };
    }
    if (component.type.startsWith("certified.")) {
      return {
        kind: "rejected",
        reason: `certified component ${id!} may not stream (L5 has no partial mode)`,
      };
    }
    component.props = patch.props ?? component.props ?? {};
    component.bindings = patch.bindings ?? component.bindings ?? [];
  }
  return { kind: "ok", manifest: scaffold };
}
