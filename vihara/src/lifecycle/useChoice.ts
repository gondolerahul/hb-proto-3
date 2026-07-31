import { useCallback, useState } from "react";

/**
 * "Which one of these is open" — derived from the collection, never asserted
 * into it (R-4 part L, L1).
 *
 * Seven surfaces opened their first `useState` with a non-null-asserted index-0
 * read:
 *
 * ```ts
 * const [openId, setOpenId] = useState<string>(TRAY[0]!.id);   // TypeError
 * ```
 *
 * On an empty collection every one of them is a `TypeError` **before render** —
 * `TraySurface` throws at line 28 and never reaches the words "Nothing needs
 * you." eleven lines below it. `noUncheckedIndexedAccess` is on precisely to
 * catch this, and the `!` suppresses exactly the check it was added for. Which
 * mattered little while the collections were module constants, and matters a
 * great deal now that they are about to be a network response.
 *
 * The fix is not a longer assertion. It is to stop storing a fact about the
 * collection in state at all:
 *
 *  1. **State holds a *preference*, not an answer.** `wanted` is the id the
 *     person last clicked, or `null` if they have not clicked anything. The
 *     chosen item is re-derived from the live collection on every render, so
 *     there is no window in which the two disagree.
 *
 *  2. **Which fixes a second bug the assertion was hiding.** With the id in
 *     state, a fetch that replaces the collection leaves the stored id pointing
 *     at a row that no longer exists; the old `?? DOSSIERS[0]!` silently
 *     substituted a different colleague's dossier and printed it under the
 *     selection the person had made. Deriving means a vanished choice falls
 *     back visibly to the default, and an empty collection yields `undefined`.
 *
 *  3. **`undefined` is a real answer and the caller must handle it.** The
 *     return type says so, which is the whole point: the compiler now asks
 *     every one of the seven surfaces what it shows when there is nothing, and
 *     §7.3 already knew the answer is designed prose.
 *
 * `prefer` is for the surfaces that open on something other than the first row
 * — the Talent office opens on the recommended candidate, the Gallery on the
 * current season — so that intent stays a predicate over the collection rather
 * than an index someone has to keep true.
 */
export function useChoice<T>(
  items: readonly T[],
  idOf: (item: T) => string,
  prefer?: (item: T) => boolean,
): {
  /** The chosen item, or `undefined` when the collection is empty. */
  chosen: T | undefined;
  /** Its id, for the `data-selected` comparisons a list makes. */
  chosenId: string | undefined;
  choose: (id: string) => void;
} {
  const [wanted, setWanted] = useState<string | null>(null);
  const choose = useCallback((id: string) => setWanted(id), []);

  const chosen =
    (wanted === null ? undefined : items.find((item) => idOf(item) === wanted)) ??
    (prefer === undefined ? undefined : items.find(prefer)) ??
    items[0];

  return { chosen, chosenId: chosen === undefined ? undefined : idOf(chosen), choose };
}
