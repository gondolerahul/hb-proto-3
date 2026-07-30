/**
 * The echo ribbon's store (shell chrome, D6 §1). An echo is emitted to the
 * bus for the platform (L10, `emitEcho`); this is the human's copy — the
 * sentence surfaces in the shell for four seconds so the act is seen to
 * have been heard. Deliberately tiny: one sentence at a time, last write
 * wins, no queue — the ribbon is a murmur, not a log.
 */
import { useEffect, useState } from "react";

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

export const RIBBON_EXIT_MS = 400;

/**
 * The shell's view of the ribbon with the 400ms leave (art bible §9):
 * when the store says "gone", `leaving` flips first and the sentence
 * stays mounted for the out animation before clearing.
 */
export function useRibbon(): { sentence: string | null; leaving: boolean } {
  const [sentence, setSentence] = useState<string | null>(null);
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    let exitTimer: ReturnType<typeof setTimeout> | null = null;
    const unsubscribe = subscribeRibbon((next) => {
      if (next === null) {
        setLeaving(true);
        exitTimer = setTimeout(() => {
          setSentence(null);
          setLeaving(false);
          exitTimer = null;
        }, RIBBON_EXIT_MS);
      } else {
        if (exitTimer !== null) {
          clearTimeout(exitTimer);
          exitTimer = null;
        }
        setSentence(next);
        setLeaving(false);
      }
    });
    return () => {
      unsubscribe();
      if (exitTimer !== null) clearTimeout(exitTimer);
    };
  }, []);

  return { sentence, leaving };
}
