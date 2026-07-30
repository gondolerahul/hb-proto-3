/**
 * The live estate (WORLD W5) — the SSE stream's client half (VG-03).
 *
 * The reducer is pure: (estate, event) → estate, one case per event type
 * the stream emits, each testable alone. The wire wrapper feeds it from an
 * EventSource whose reconnect story is the server's snapshot-on-connect
 * (SEAM's delta): every (re)connect replays all pending beacons, so the
 * reducer treats `beacon.raised` as an idempotent upsert — at-least-once
 * delivery, keyed by approval id, safe to re-apply.
 */
import type { EstateSnapshot } from "../renderers/world/layout";

export const STREAM_EVENT_TYPES = [
  "beacon.raised",
  "beacon.cleared",
  "tray.delivered",
  "traffic",
  "weather.changed",
  "run.state",
  "envelope.burn",
  "pulse",
  "bridge.state",
] as const;

export type StreamEventType = (typeof STREAM_EVENT_TYPES)[number];

export interface StreamEvent {
  type: StreamEventType;
  payload: Record<string, unknown>;
}

export function applyStreamEvent(
  estate: EstateSnapshot,
  event: StreamEvent,
): EstateSnapshot {
  const { type, payload } = event;

  if (type === "beacon.raised") {
    const approvalId = String(payload["approval_id"] ?? "");
    if (approvalId === "") return estate;
    const beacon = {
      approval_id: approvalId,
      district:
        typeof payload["district"] === "string" ? payload["district"] : null,
      sla_seconds_left:
        typeof payload["sla_seconds_left"] === "number"
          ? payload["sla_seconds_left"]
          : null,
    };
    return {
      ...estate,
      beacons: [
        ...estate.beacons.filter((b) => b.approval_id !== approvalId),
        beacon,
      ],
    };
  }

  if (type === "beacon.cleared") {
    const approvalId = String(payload["approval_id"] ?? "");
    return {
      ...estate,
      beacons: estate.beacons.filter((b) => b.approval_id !== approvalId),
    };
  }

  if (type === "pulse") {
    return {
      ...estate,
      estate: {
        ...estate.estate,
        pulse: { healthy: payload["healthy"] === true },
      },
    };
  }

  if (type === "traffic" || type === "weather.changed" || type === "envelope.burn") {
    const district = String(payload["district"] ?? "");
    return {
      ...estate,
      districts: estate.districts.map((d) => {
        if (d.process_code !== district) return d;
        if (type === "traffic") {
          return {
            ...d,
            traffic: {
              in_1h: Number(payload["in_1h"] ?? 0),
              out_1h: Number(payload["out_1h"] ?? 0),
              parked: Number(payload["parked"] ?? 0),
            },
          };
        }
        if (type === "weather.changed") {
          return {
            ...d,
            weather: {
              state: String(payload["state"] ?? "clear"),
              icon:
                typeof payload["icon"] === "string" ? payload["icon"] : null,
              sentence:
                typeof payload["sentence"] === "string"
                  ? payload["sentence"]
                  : null,
            },
          };
        }
        return {
          ...d,
          treasury: {
            spent: Number(payload["spent"] ?? 0),
            cap: Number(payload["cap"] ?? 0),
          },
        };
      }),
    };
  }

  if (type === "run.state") {
    const district = String(payload["district"] ?? "");
    const entityId = String(payload["entity_id"] ?? "");
    return {
      ...estate,
      districts: estate.districts.map((d) =>
        d.process_code !== district
          ? d
          : {
              ...d,
              colleagues: d.colleagues.map((c) =>
                c.entity_id !== entityId
                  ? c
                  : {
                      ...c,
                      state: String(payload["state"] ?? c.state),
                      hand_raised: payload["hand_raised"] === true,
                    },
              ),
            },
      ),
    };
  }

  // tray.delivered mirrors beacon.raised for surfaces that show trays;
  // bridge.state belongs to the Bridges board (DRIVER). Both are ignored
  // here on purpose — ignoring a known type is a decision, not an accident.
  return estate;
}

/** Connect the wire. Returns a disposer. Injectable EventSource for tests. */
export function connectEstateStream(
  onEvent: (event: StreamEvent) => void,
  makeSource: () => EventSource = () =>
    new EventSource("/api/v1/ai/genui/stream"),
): () => void {
  const source = makeSource();
  for (const type of STREAM_EVENT_TYPES) {
    source.addEventListener(type, (raw) => {
      try {
        onEvent({
          type,
          payload: JSON.parse((raw as MessageEvent<string>).data) as Record<
            string,
            unknown
          >,
        });
      } catch {
        // A malformed frame loses one event; the next snapshot heals it.
      }
    });
  }
  return () => source.close();
}
