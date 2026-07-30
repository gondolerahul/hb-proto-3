/**
 * One SSE connection per app (STEWARD S5) — the consolidation DRIVER's
 * build notes promised: the terrace, a district sheet and the tray panel
 * each opened their own EventSource, so an open tray panel doubled the
 * server's per-session diff work for no extra information.
 *
 * Reference-counted: the wire opens with the first subscriber and closes
 * with the last. The signature matches `connectEstateStream` so every
 * call site's injectable `stream:` field is untouched — tests keep
 * injecting their own fakes and never touch the singleton.
 */
import { connectEstateStream, type StreamEvent } from "./live";

let disposeWire: (() => void) | null = null;
const listeners = new Set<(event: StreamEvent) => void>();

export function subscribeEstateStream(
  onEvent: (event: StreamEvent) => void,
  makeSource?: () => EventSource,
): () => void {
  listeners.add(onEvent);
  if (disposeWire === null) {
    disposeWire = makeSource
      ? connectEstateStream(fanOut, makeSource)
      : connectEstateStream(fanOut);
  }
  return () => {
    listeners.delete(onEvent);
    if (listeners.size === 0 && disposeWire !== null) {
      disposeWire();
      disposeWire = null;
    }
  };
}

function fanOut(event: StreamEvent): void {
  // Copy first: a listener that unsubscribes mid-event must not skip its
  // neighbours.
  for (const listener of [...listeners]) {
    listener(event);
  }
}

/** Test-only: drop the wire and every listener. */
export function resetSharedStream(): void {
  if (disposeWire !== null) {
    disposeWire();
    disposeWire = null;
  }
  listeners.clear();
}
