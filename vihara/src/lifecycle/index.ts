/**
 * The fetch lifecycle (R-4 part L).
 *
 * Five things every surface has to do once its collections come off a network
 * rather than out of a module, and which none of them could do before this
 * round:
 *
 * | | | |
 * |---|---|---|
 * | L1 | `useChoice` | derive the open row from the collection, never assert into it |
 * | L2 | `Empty` | designed prose for "nothing here", never an empty chart (§7.3) |
 * | L3 | `Failed` | a load that failed says so, in a different material from empty |
 * | L4 | `SurfaceBoundary` | one room cannot take the shell down |
 * | L5 | `Scaffold` + `useResource` | layout first, data second (D7 §3.1) |
 *
 * Nothing here reaches the network. Wiring is part W.
 */
export { Empty } from "./Empty";
export { Failed } from "./Failed";
export { Scaffold, Bar, Lines } from "./Scaffold";
export { SurfaceBoundary } from "./SurfaceBoundary";
export { useChoice } from "./useChoice";
export { useResource, reasonOf, UNANSWERED, type Resource } from "./useResource";
