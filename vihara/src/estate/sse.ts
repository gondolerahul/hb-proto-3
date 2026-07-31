/**
 * A fetch-based SSE reader (R-4 part S, S1).
 *
 * **Why not the native `EventSource`.** `GET /ai/genui/stream` is guarded by
 * header-based `get_current_user`. An `EventSource` sends no custom headers,
 * so it cannot present the bearer token; and the refresh cookie is scoped to
 * `path=/api/v1/auth`, so it is not sent either. The connection simply 401s.
 *
 * There is a query-parameter-token precedent elsewhere in this codebase and it
 * is **not** followed here. Putting a bearer credential in a URL puts it in
 * proxy logs, in browser history and in the `Referer` of anything the page
 * subsequently loads — on the one surface that drives T2/T3 step-up. That
 * precedent predates VP-01 and undoes most of what VP-01 bought. Reading SSE
 * out of `fetch` costs the few dozen lines below and no security.
 *
 * Nothing is lost by leaving the native protocol behind: replay here is
 * snapshot-on-connect, not `Last-Event-ID`, so there is no cursor for the
 * browser to have been managing on our behalf. (D5 §3 says otherwise and is
 * stale — R-5.)
 *
 * This module opens **one attempt**. It does not retry; the reconnect ladder
 * belongs to `sharedStream.ts`, so the two are testable apart.
 */
import { getAccessToken, refreshAccessToken } from "../api/client";

/** Same origin as the rest of the client — the Vite proxy and the deployed
 * path-mount both collapse the app and the API onto one origin, which is what
 * `SameSite=Strict` on the refresh cookie already assumes. */
export const ESTATE_STREAM_URL = "/api/v1/ai/genui/stream";

export interface SseFrame {
  /** The `event:` field, or `"message"` when the server omitted it. */
  type: string;
  /** The `data:` field, joined with newlines when it spanned several lines. */
  data: string;
  id: string | null;
}

/**
 * A stateful SSE decoder: feed it decoded text, get whole frames back.
 *
 * Pure and network-free, so the protocol — multi-line `data`, `:` comment
 * keepalives, a frame split across two chunks — is testable by calling it.
 * Frames without a `data` field produce nothing, per the EventSource spec:
 * that is exactly what the server's `: keepalive` tick is.
 */
export function createSseDecoder(): (chunk: string) => SseFrame[] {
  let buffer = "";
  return (chunk: string): SseFrame[] => {
    buffer += chunk.replace(/\r\n?/g, "\n");
    const frames: SseFrame[] = [];
    let split = buffer.indexOf("\n\n");
    while (split !== -1) {
      const block = buffer.slice(0, split);
      buffer = buffer.slice(split + 2);
      const frame = parseSseBlock(block);
      if (frame !== null) frames.push(frame);
      split = buffer.indexOf("\n\n");
    }
    return frames;
  };
}

function parseSseBlock(block: string): SseFrame | null {
  let type = "message";
  let id: string | null = null;
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line === "" || line.startsWith(":")) continue;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") type = value;
    else if (field === "data") data.push(value);
    else if (field === "id") id = value;
  }
  if (data.length === 0) return null;
  return { type, data: data.join("\n"), id };
}

export interface WireHandlers {
  /** The connection is up and the server has accepted the credential. */
  onOpen: () => void;
  onFrame: (frame: SseFrame) => void;
  /** The connection ended, with a sentence a surface can show. Never called
   * after a deliberate dispose — closing the wire on purpose is not a fault. */
  onClosed: (reason: string) => void;
}

/** One connection attempt. Returns a disposer. */
export type Wire = (handlers: WireHandlers) => () => void;

function streamRequest(signal: AbortSignal): Promise<Response> {
  const token = getAccessToken();
  return fetch(ESTATE_STREAM_URL, {
    method: "GET",
    headers: {
      Accept: "text/event-stream",
      ...(token !== null ? { Authorization: `Bearer ${token}` } : {}),
    },
    // The company is fixed at connect from the session. There is no selector
    // on this URL to get wrong, which is the point of VG-05's rule.
    credentials: "include",
    cache: "no-store",
    signal,
  });
}

async function pump(signal: AbortSignal, handlers: WireHandlers): Promise<void> {
  let reason = "the estate stream ended";
  try {
    let response = await streamRequest(signal);
    if (response.status === 401) {
      // The axios interceptor never sees this request, so the one-shot refresh
      // is repeated here. A refresh that fails is a normal logged-out state
      // (part A's rule), so it closes the wire rather than raising.
      if (!(await refreshAccessToken())) {
        handlers.onClosed("the session expired");
        return;
      }
      response = await streamRequest(signal);
    }
    if (!response.ok) {
      handlers.onClosed(`the estate stream refused the connection (${response.status})`);
      return;
    }
    const body = response.body;
    if (body === null) {
      handlers.onClosed("the estate stream carried no body");
      return;
    }
    handlers.onOpen();
    const reader = body.getReader();
    const decoder = new TextDecoder();
    const feed = createSseDecoder();
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      for (const frame of feed(decoder.decode(value, { stream: true }))) {
        handlers.onFrame(frame);
      }
    }
  } catch {
    // An abort is us, not a fault.
    if (signal.aborted) return;
    reason = "the connection to the estate dropped";
  }
  if (!signal.aborted) handlers.onClosed(reason);
}

/**
 * Open the estate stream. The `Authorization` header rides the request, so the
 * stream authenticates with no backend change.
 */
export const openEstateWire: Wire = (handlers) => {
  const controller = new AbortController();
  void pump(controller.signal, handlers);
  return () => controller.abort();
};
