/**
 * The echo ribbon's store (shell chrome, D6 §1). An echo is emitted to the
 * bus for the platform (L10, `emitEcho`); this is the human's copy — the
 * sentence surfaces in the shell for four seconds so the act is seen to
 * have been heard. Deliberately tiny: one sentence at a time, last write
 * wins, no queue — the ribbon is a murmur, not a log.
 */
type Listener = (sentence: string | null) => void;

let current: string | null = null;
let timer: ReturnType<typeof setTimeout> | null = null;
const listeners = new Set<Listener>();

export const RIBBON_DWELL_MS = 4000;

export function announce(sentence: string): void {
  current = sentence;
  listeners.forEach((listener) => listener(current));
  if (timer !== null) clearTimeout(timer);
  timer = setTimeout(() => {
    current = null;
    timer = null;
    listeners.forEach((listener) => listener(current));
  }, RIBBON_DWELL_MS);
}

export function subscribeRibbon(listener: Listener): () => void {
  listeners.add(listener);
  listener(current);
  return () => listeners.delete(listener);
}
