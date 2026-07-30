/**
 * Binding resolution (D5 / spec §9.4). A component's figures arrive ONLY
 * through bindings — props are labels and structure. The resolver maps a
 * binding to data the shell has fetched (the estate read model, trays);
 * an unresolved binding is `undefined`, and the component renders its
 * empty state WITH THE REASON (D4 §7) — never an empty region.
 */
import { createContext, useContext } from "react";

import type { WireBinding } from "../manifest/schema";

export type BindingResolver = (binding: WireBinding) => unknown;

const NOTHING: BindingResolver = () => undefined;

export const BindingContext = createContext<BindingResolver>(NOTHING);

export function useBindingValues(
  bindings: readonly WireBinding[] | undefined,
): unknown[] {
  const resolve = useContext(BindingContext);
  return (bindings ?? []).map((binding) => resolve(binding));
}

/** An estate-payload-backed resolver — enough for G0's round trip; richer
 * sources join as DRIVER's surfaces arrive. */
export function estateResolver(
  estate: Record<string, unknown> | null,
): BindingResolver {
  return (binding) => {
    if (estate === null) return undefined;
    switch (binding.source) {
      case "estate.pulse":
        return (estate["estate"] as { pulse?: unknown } | undefined)?.pulse;
      case "estate.beacon":
        return estate["beacons"];
      case "estate.district":
        return estate["districts"];
      case "estate.weather":
        return estate["districts"];
      default:
        return undefined;
    }
  };
}
