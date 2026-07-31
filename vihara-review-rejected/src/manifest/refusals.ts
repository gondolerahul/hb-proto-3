/**
 * The refusal ladder (D4 §7) — the client half. This repo's standing rule:
 * certified fails CLOSED, everything else fails VISIBLE, and nothing is
 * ever allowed to fail silent — a component quietly skipped is the class
 * of bug that reads as working from every other angle.
 *
 * | situation                          | disposition                      |
 * |------------------------------------|----------------------------------|
 * | unknown component type             | visible placeholder, named       |
 * | version < min_supported            | REFUSE the manifest (ask sheet)  |
 * | binding fails at runtime           | the component's own empty state  |
 * | certified schema violation         | REJECT the whole manifest        |
 * | any other schema violation         | placeholder; render the rest     |
 */
import { declaredSources, resolve } from "./registry";
import type { WireComponent, WireScaffold } from "./schema";

export type Disposition =
  | { kind: "render"; component: WireComponent }
  | { kind: "placeholder"; component: WireComponent; reason: string };

export type Assessment =
  | { verdict: "render"; dispositions: Disposition[] }
  | { verdict: "reject"; reason: string };

const SIMULATION_GRADES = new Set(["replay", "forecast", "unknown"]);

export function assessManifest(manifest: WireScaffold): Assessment {
  if (manifest.renderer === "W" && manifest.sheet_equivalent === undefined) {
    return { verdict: "reject", reason: "a W manifest must name its sheet (L9)" };
  }

  const dispositions: Disposition[] = [];
  for (const component of manifest.components) {
    const resolution = resolve(component.type);

    if (resolution.kind === "unsupported") {
      // The one non-certified case that refuses the whole manifest: a
      // client below min_supported must ask for the sheet equivalent,
      // never render a component it half-understands (D3 §4).
      return {
        verdict: "reject",
        reason:
          `${component.type} requires a newer client ` +
          `(min supported v${resolution.min_supported})`,
      };
    }

    if (resolution.kind === "unknown") {
      dispositions.push({
        kind: "placeholder",
        component,
        reason: `unknown component ${component.type} on ${manifest.surface_id}`,
      });
      continue;
    }

    const { entry } = resolution;
    const problems = componentProblems(component, entry, manifest);

    if (problems.length > 0 && entry.class === "certified") {
      // Reject, never sanitise: rendering a certified surface somebody
      // tried to modify is the attack succeeding quietly (D4 §2).
      return {
        verdict: "reject",
        reason: `${component.type}: ${problems.join("; ")}`,
      };
    }
    if (problems.length > 0) {
      dispositions.push({
        kind: "placeholder",
        component,
        reason: problems.join("; "),
      });
      continue;
    }
    dispositions.push({ kind: "render", component });
  }
  return { verdict: "render", dispositions };
}

function componentProblems(
  component: WireComponent,
  entry: ReturnType<typeof mustResolve>,
  manifest: WireScaffold,
): string[] {
  const problems: string[] = [];

  if (!entry.renderers.includes(manifest.renderer)) {
    problems.push(`not renderable in ${manifest.renderer}`);
  }

  if (entry.class === "certified") {
    if (manifest.plane === "twin") {
      problems.push("certified components may not sit on the twin plane (L5)");
    }
    if (component.honesty_grade !== undefined) {
      problems.push("a certified component carries no honesty_grade (L5)");
    }
    const declared = new Set(Object.keys(entry.props.properties ?? {}));
    const required = entry.props.required ?? [];
    const present = new Set(Object.keys(component.props ?? {}));
    for (const name of required) {
      if (!present.has(name)) problems.push(`missing required prop ${name}`);
    }
    for (const name of present) {
      if (!declared.has(name)) problems.push(`undeclared prop ${name} (L5)`);
    }
  }

  if (manifest.plane === "twin" && component.honesty_grade === undefined) {
    problems.push("twin-plane components require honesty_grade (L6)");
  }
  if (
    component.honesty_grade !== undefined &&
    SIMULATION_GRADES.has(component.honesty_grade) &&
    (component.twin_run_id === undefined || component.twin_run_id === null)
  ) {
    problems.push(
      `honesty_grade=${component.honesty_grade} asserts a simulation and requires twin_run_id (L6)`,
    );
  }

  const allowed = declaredSources(entry);
  if (allowed !== null) {
    for (const binding of component.bindings ?? []) {
      if (!allowed.has(binding.source)) {
        problems.push(`binding source ${binding.source} is not declared`);
      }
    }
  }

  // R7's client half: a narrative template may contain no digit — a figure
  // arrives through a binding or it does not arrive.
  if (entry.class === "narrative") {
    const template = (component.props ?? {})["template"];
    if (typeof template === "string" && /\d/.test(template)) {
      problems.push("a narrative template may not contain digits (R7)");
    }
  }

  return problems;
}

// Typing helper: componentProblems only ever receives a resolved entry.
function mustResolve(ref: string) {
  const resolution = resolve(ref);
  if (resolution.kind !== "ok") throw new Error(ref);
  return resolution.entry;
}
