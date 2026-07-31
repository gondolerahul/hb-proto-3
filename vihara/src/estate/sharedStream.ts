/**
 * One SSE connection per app (R-4 part S, S2–S3).
 *
 * The consolidation this replaces: the terrace, a district sheet and the tray
 * panel each opened their own stream, so an open tray panel doubled the
 * server's per-session diff work for no extra information. Reference-counted —
 * the wire opens with the first subscriber and closes with the last.
 *
 * **A dropped stream is stale, and says so.** The reconnect ladder runs
 * underneath, but the subscriber is told the moment the wire goes down and
 * told again when it comes back. Silence is not an option here: an estate that
 * failed to load and an estate with nothing happening render identically
 * unless something distinguishes them, and this is that something. The
 * reducer's `as_of` answers *when did anything last change*; `WireState`
 * answers *are we still watching*. Both are needed, and neither substitutes.
 */
import { isStreamEventType, type StreamEvent } from "./live";
import { openEstateWire, type Wire } from "./sse";

export type WireState =
  | { status: "connecting" }
  | { status: "live" }
  /** `retryInSeconds` is the delay actually scheduled, so a surface can count
   * down against a real number rather than a guessed one. */
  | { status: "stale"; reason: string; retryInSeconds: number | null };

export interface EstateStreamListener {
  onEvent: (event: StreamEvent) => void;
  onWire: (state: WireState) => void;
}

/**
 * The reconnect ladder, in seconds, held flat at the last rung.
 *
 * Jittered by ±20% on use. The herd this guards against is a backend restart,
 * which drops every session at the same instant; without jitter they would all
 * return together on the same rung and do it again. The ladder is capped at 30s
 * because the stream's own poll interval is 3s — a longer cap would make a
 * recovered backend feel broken for longer than it was.
 */
export const BACKOFF_SECONDS = [1, 2, 4, 8, 15, 30] as const;

function backoffMs(attempt: number): number {
  const index = Math.min(attempt, BACKOFF_SECONDS.length - 1);
  const rung = BACKOFF_SECONDS[index] ?? BACKOFF_SECONDS[BACKOFF_SECONDS.length - 1] ?? 30;
  return Math.round(rung * 1000 * (0.8 + Math.random() * 0.4));
}

const listeners = new Set<EstateStreamListener>();
let dispose: (() => void) | null = null;
let retryTimer: ReturnType<typeof setTimeout> | null = null;
let attempts = 0;
let wireFactory: Wire = openEstateWire;
let state: WireState = { status: "connecting" };

export function wireState(): WireState {
  return state;
}

function announce(next: WireState): void {
  state = next;
  // Copy first: a listener that unsubscribes mid-notification must not make
  // its neighbour miss the message.
  for (const listener of [...listeners]) listener.onWire(next);
}

function fanOut(event: StreamEvent): void {
  for (const listener of [...listeners]) listener.onEvent(event);
}

function connect(): void {
  announce({ status: "connecting" });
  dispose = wireFactory({
    onOpen: () => {
      attempts = 0;
      announce({ status: "live" });
    },
    onFrame: (frame) => {
      if (!isStreamEventType(frame.type)) return;
      let payload: unknown;
      try {
        payload = JSON.parse(frame.data);
      } catch {
        // A malformed frame loses one event; the next connect's snapshot heals
        // the beacons, and every other type is a sampled state a later tick
        // supersedes.
        return;
      }
      if (payload === null || typeof payload !== "object" || Array.isArray(payload)) {
        return;
      }
      fanOut({ type: frame.type, payload: payload as Record<string, unknown> });
    },
    onClosed: (reason) => {
      dispose = null;
      if (listeners.size === 0) return;
      const delay = backoffMs(attempts);
      attempts += 1;
      announce({
        status: "stale",
        reason,
        retryInSeconds: Math.round(delay / 1000),
      });
      retryTimer = setTimeout(() => {
        retryTimer = null;
        if (listeners.size > 0) connect();
      }, delay);
    },
  });
}

/**
 * Subscribe to the one shared stream. Returns an unsubscriber.
 *
 * `wire` is the injection point for tests and it is honoured **only when the
 * wire is not already open** — a second subscriber cannot swap the connection
 * out from under the first. Tests call `resetSharedStream()` between cases.
 */
export function subscribeEstateStream(
  listener: EstateStreamListener,
  wire?: Wire,
): () => void {
  const first = listeners.size === 0;
  listeners.add(listener);
  if (first) {
    if (wire !== undefined) wireFactory = wire;
    connect();
  } else {
    // A late subscriber is told where things stand rather than left blank
    // until the next transition — which on a healthy quiet estate could be
    // never.
    listener.onWire(state);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) closeWire();
  };
}

function closeWire(): void {
  if (retryTimer !== null) {
    clearTimeout(retryTimer);
    retryTimer = null;
  }
  dispose?.();
  dispose = null;
  attempts = 0;
  state = { status: "connecting" };
}

/** Test-only: drop the wire, every listener, and the injected factory. */
export function resetSharedStream(): void {
  listeners.clear();
  closeWire();
  wireFactory = openEstateWire;
}
