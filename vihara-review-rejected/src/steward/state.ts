/**
 * The steward's client state — a pure reducer over channel events
 * (STEWARD S6), the estate stream's own pattern: (state, event) → state,
 * one case per event type, each testable alone.
 */
import type { StewardAnchor, StepUpAsk, StewardEvent } from "./channel";

export type Presence = "off" | "listening" | "speaking" | "working" | "away";

export interface NarrationLine {
  text: string;
  anchors: StewardAnchor[];
  kind: "narration" | "error";
}

export interface StewardState {
  connected: boolean;
  presence: Presence;
  lines: NarrationLine[];
  /** The live partial while she is hearing the human (voice leg). */
  transcript: { text: string; final: boolean } | null;
  /** A ceremony she asked for on the last narration, if any. */
  stepUpAsk: StepUpAsk | null;
  /** Trays delivered over the channel this session (count only — the tray
   * panel owns the real list through its own loader + shared stream). */
  traysDelivered: number;
}

export const INITIAL_STEWARD_STATE: StewardState = {
  connected: false,
  presence: "off",
  lines: [],
  transcript: null,
  stepUpAsk: null,
  traysDelivered: 0,
};

/** Narrations kept on screen. The session's memory is server-side; this is
 * a view, not a log. */
export const LINE_LIMIT = 20;

export function reduceSteward(
  state: StewardState,
  event: StewardEvent,
): StewardState {
  if (event.type === "presence") {
    return { ...state, presence: event.state };
  }
  if (event.type === "narrate") {
    const line: NarrationLine = {
      text: event.text,
      anchors: event.anchors,
      kind: "narration",
    };
    return {
      ...state,
      lines: [...state.lines, line].slice(-LINE_LIMIT),
      transcript: null,
      stepUpAsk: event.step_up ?? null,
    };
  }
  if (event.type === "transcript") {
    return { ...state, transcript: { text: event.text, final: event.final } };
  }
  if (event.type === "error") {
    const line: NarrationLine = {
      text: event.reason,
      anchors: [],
      kind: "error",
    };
    return { ...state, lines: [...state.lines, line].slice(-LINE_LIMIT) };
  }
  if (event.type === "deliver_tray") {
    return { ...state, traysDelivered: state.traysDelivered + 1 };
  }
  // focus / materialize are navigation — the dock forwards them to the
  // shell rather than storing them; echo_ack needs no view.
  return state;
}

export function setConnected(
  state: StewardState,
  connected: boolean,
): StewardState {
  return {
    ...state,
    connected,
    presence: connected ? state.presence : "off",
  };
}
