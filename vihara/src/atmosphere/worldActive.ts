/**
 * The one-GL-context rule's signal (POLISH P2, 15_polish.md §4): when the
 * world canvas is live the atmosphere pauses and hides — the terrace
 * draws its own energy floor, and a second WebGL context under a full
 * scene is how the p75 floor (VG-22) dies. Same tiny store shape as the
 * echo ribbon's: last write wins, no queue.
 */
type Listener = (active: boolean) => void;

let active = false;
const listeners = new Set<Listener>();

export function setWorldCanvasActive(next: boolean): void {
  if (next === active) return;
  active = next;
  listeners.forEach((listener) => listener(active));
}

export function subscribeWorldCanvas(listener: Listener): () => void {
  listeners.add(listener);
  listener(active);
  return () => {
    listeners.delete(listener);
  };
}
