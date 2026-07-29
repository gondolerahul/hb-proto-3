/**
 * narrative.still-line — one sentence about the whole estate. The template
 * carries {slot} placeholders and MAY NOT contain digits (R7); every
 * figure arrives through a binding. An unresolvable slot renders an
 * em-dash rather than inventing a value — a wrong number in the one
 * sentence the owner always reads is the most expensive bug this
 * component could have.
 */
import type { ComponentProps } from "../primitive/basics";
import { useBindingValues } from "../../renderers/bindings";

export function StillLine({ component }: ComponentProps): JSX.Element {
  const template =
    typeof (component.props ?? {})["template"] === "string"
      ? ((component.props ?? {})["template"] as string)
      : "";
  const values = useBindingValues(component.bindings);

  const slots: Record<string, string> = {};
  const beacons = values.find(Array.isArray);
  if (beacons !== undefined) {
    slots["raised"] = String((beacons as unknown[]).length);
  }

  const text = template.replace(/\{(\w+)\}/g, (_match, name: string) =>
    slots[name] ?? "—",
  );
  return (
    <p className="vh-still-line" data-part="still-line">
      {text}
    </p>
  );
}
