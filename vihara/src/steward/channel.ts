/**
 * The channel client (STEWARD S5) — the wire half of VG-07's contract.
 *
 * JSON frames are her events (presence, narration, navigation, trays,
 * transcripts); binary frames are her voice (24 kHz PCM). The socket
 * carries the token in the query — a browser cannot set WS headers — and
 * reconnects with a small backoff, because a steward who silently stops
 * listening is the "nothing happened" failure this repo keeps finding.
 *
 * Everything here is injectable: `makeSocket` for tests, and the handle
 * exposes typed senders so no caller builds a wire message by hand.
 */
import { getAccessToken } from "../api/client";

export interface StewardAnchor {
  kind: string;
  label: string;
  ref: string;
}

export interface StepUpAsk {
  tier: string | null;
  command_ref: string | null;
  oob: boolean;
}

export type StewardEvent =
  | { type: "presence"; state: "listening" | "speaking" | "working" | "away" }
  | {
      type: "narrate";
      text: string;
      anchors: StewardAnchor[];
      step_up?: StepUpAsk;
    }
  | { type: "focus"; target_ref: { kind: string; id: string }; narration?: string | null }
  | { type: "materialize"; surface_id: string; reason?: string }
  | { type: "transcript"; text: string; final: boolean }
  | { type: "deliver_tray"; tray: Record<string, unknown> }
  | { type: "echo_ack"; echo_id: string }
  | { type: "error"; reason: string };

/** Narrow a parsed frame to a StewardEvent, or null for garbage — a
 * malformed frame loses one event, never the wire. */
export function parseChannelEvent(raw: unknown): StewardEvent | null {
  if (raw === null || typeof raw !== "object") return null;
  const type = (raw as { type?: unknown }).type;
  if (typeof type !== "string") return null;
  const event = raw as Record<string, unknown>;
  switch (type) {
    case "presence":
      return typeof event["state"] === "string"
        ? ({ type: "presence", state: event["state"] } as StewardEvent)
        : null;
    case "narrate":
      return typeof event["text"] === "string"
        ? ({
            type: "narrate",
            text: event["text"],
            anchors: Array.isArray(event["anchors"])
              ? (event["anchors"] as StewardAnchor[])
              : [],
            ...(event["step_up"] !== undefined
              ? { step_up: event["step_up"] as StepUpAsk }
              : {}),
          } as StewardEvent)
        : null;
    case "focus":
      return event["target_ref"] !== undefined
        ? (raw as StewardEvent)
        : null;
    case "materialize":
      return typeof event["surface_id"] === "string"
        ? (raw as StewardEvent)
        : null;
    case "transcript":
      return typeof event["text"] === "string"
        ? ({
            type: "transcript",
            text: event["text"],
            final: event["final"] === true,
          } as StewardEvent)
        : null;
    case "deliver_tray":
      return event["tray"] !== null && typeof event["tray"] === "object"
        ? (raw as StewardEvent)
        : null;
    case "echo_ack":
    case "error":
      return raw as StewardEvent;
    default:
      return null;
  }
}

export interface SocketLike {
  send(data: string | ArrayBuffer): void;
  close(): void;
  addEventListener(type: string, listener: (event: unknown) => void): void;
  binaryType?: string;
}

export interface ChannelHandlers {
  onEvent: (event: StewardEvent) => void;
  onAudio?: (frame: ArrayBuffer) => void;
  onConnected?: (connected: boolean) => void;
}

export interface StewardHandle {
  say(text: string): void;
  reportViewport(contextRef: Record<string, unknown>): void;
  reportDepth(level: number): void;
  reportStepUp(tier: string | null, ok: boolean): void;
  micOpen(): void;
  micClosed(): void;
  sendAudio(frame: ArrayBuffer): void;
  close(): void;
}

const RECONNECT_DELAY_MS = 2000;

function defaultSocket(): SocketLike {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  const token = getAccessToken() ?? "";
  const socket = new WebSocket(
    `${scheme}://${window.location.host}/api/v1/ai/pragya/channel?token=${encodeURIComponent(token)}`,
  );
  socket.binaryType = "arraybuffer";
  return socket as unknown as SocketLike;
}

export function connectChannel(
  handlers: ChannelHandlers,
  makeSocket: () => SocketLike = defaultSocket,
): StewardHandle {
  let socket: SocketLike | null = null;
  let closedByUser = false;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  const open = (): void => {
    socket = makeSocket();
    socket.addEventListener("open", () => {
      handlers.onConnected?.(true);
    });
    socket.addEventListener("message", (raw) => {
      const data = (raw as MessageEvent).data;
      if (data instanceof ArrayBuffer) {
        handlers.onAudio?.(data);
        return;
      }
      try {
        const event = parseChannelEvent(JSON.parse(String(data)));
        if (event !== null) handlers.onEvent(event);
      } catch {
        // A malformed frame loses one event; the wire survives.
      }
    });
    socket.addEventListener("close", () => {
      handlers.onConnected?.(false);
      socket = null;
      if (!closedByUser) {
        reconnectTimer = setTimeout(open, RECONNECT_DELAY_MS);
      }
    });
  };
  open();

  const send = (message: Record<string, unknown>): void => {
    try {
      socket?.send(JSON.stringify(message));
    } catch {
      // A send on a closing socket is lost; the reconnect brings the
      // session context back (the session, not the socket, is the memory).
    }
  };

  return {
    say: (text) => send({ type: "utterance", text }),
    reportViewport: (contextRef) =>
      send({ type: "viewport", context_ref: contextRef }),
    reportDepth: (level) => send({ type: "depth_change", level }),
    reportStepUp: (tier, ok) =>
      send({ type: "step_up_result", tier, ok }),
    micOpen: () => send({ type: "mic", state: "open" }),
    micClosed: () => send({ type: "mic", state: "closed" }),
    sendAudio: (frame) => {
      try {
        socket?.send(frame);
      } catch {
        // A lost frame is a syllable, not a session.
      }
    },
    close: () => {
      closedByUser = true;
      if (reconnectTimer !== null) clearTimeout(reconnectTimer);
      socket?.close();
    },
  };
}
