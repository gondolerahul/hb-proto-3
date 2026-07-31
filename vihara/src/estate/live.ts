/**
 * The live estate's reducer (VG-03, D5 §3; R-4 part S).
 *
 * `(estate, event) => estate`. Pure, one case per event type the backend's
 * `diff_estate` emits, and this module imports **no wire at all** — not the
 * fetch reader, not the client, not React. That is the property the whole part
 * hangs on: the protocol is testable by handing the reducer a frame.
 *
 * Three things carried across from the rejected build were corrected on the
 * way, and they are the same bug three times:
 *
 * **A missing field is not a zero.** The old reducer wrote
 * `Number(payload["in_1h"] ?? 0)`, `String(payload["state"] ?? "clear")` and
 * `payload["healthy"] === true`, so a truncated frame set a district's traffic
 * to nothing, its weather to calm, and the estate's pulse to unhealthy. Under
 * DESIGN_CONTRACT §7.1 a missing binding renders *nothing*; here that means
 * the previous reading stands, because "we did not hear" and "it is zero" are
 * different statements and only one of them is true.
 *
 * **Replay is snapshot-on-connect, not `Last-Event-ID`.** Every (re)connect
 * replays `beacon.raised` for every pending approval, so beacons are an
 * idempotent upsert keyed by approval id — at-least-once, safe to re-apply.
 * The upsert replaces **in place** rather than filter-then-append: a beacon
 * that keeps its position does not re-enter, and a list that reorders itself
 * every three seconds is a list nobody can point at.
 *
 * **`as_of` is when something last changed — not whether anyone is watching.**
 * Quiet ticks emit an SSE comment and no frame, so a calm estate's `as_of`
 * ages while the wire is perfectly healthy. Liveness is `WireState` in
 * `sharedStream.ts`, deliberately a separate reading: an estate that failed to
 * load and an estate with nothing happening look identical if only one of them
 * is designed.
 */
import {
  asWeatherState,
  type EstateBeacon,
  type EstateDistrict,
  type EstateSnapshot,
  type EstateTreasury,
} from "../api/estate";

/** Every event type `backend/src/ai/genui/stream.py` emits. */
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

export function isStreamEventType(value: string): value is StreamEventType {
  return (STREAM_EVENT_TYPES as readonly string[]).includes(value);
}

/* ── narrowing: absent means absent ─────────────────────────────────────── */

function asString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asBoolean(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

/* ── the reducer ────────────────────────────────────────────────────────── */

/** Replace one district in place, leaving the rest untouched. Returns the same
 * array identity when the district is unknown, so an event for a district this
 * session never loaded is a no-op rather than a phantom row. */
function withDistrict(
  estate: EstateSnapshot,
  code: string,
  change: (district: EstateDistrict) => EstateDistrict,
): EstateSnapshot {
  let touched = false;
  const districts = estate.districts.map((district) => {
    if (district.process_code !== code) return district;
    touched = true;
    return change(district);
  });
  return touched ? { ...estate, districts } : estate;
}

function applyBeaconRaised(
  estate: EstateSnapshot,
  payload: Record<string, unknown>,
): EstateSnapshot {
  const approvalId = asString(payload["approval_id"]);
  if (approvalId === null) return estate;
  const beacon: EstateBeacon = {
    approval_id: approvalId,
    district: asString(payload["district"]),
    checkpoint_key: asString(payload["checkpoint_key"]),
    sla_seconds_left: asNumber(payload["sla_seconds_left"]),
  };
  const at = estate.beacons.findIndex((b) => b.approval_id === approvalId);
  if (at === -1) return { ...estate, beacons: [...estate.beacons, beacon] };
  const beacons = [...estate.beacons];
  beacons[at] = beacon;
  return { ...estate, beacons };
}

function applyTraffic(
  district: EstateDistrict,
  payload: Record<string, unknown>,
): EstateDistrict {
  const traffic = { ...district.traffic };
  const inbound = asNumber(payload["in_1h"]);
  const outbound = asNumber(payload["out_1h"]);
  const parked = asNumber(payload["parked"]);
  if (inbound !== null) traffic.in_1h = inbound;
  if (outbound !== null) traffic.out_1h = outbound;
  if (parked !== null) traffic.parked = parked;
  return { ...district, traffic };
}

function applyWeather(
  district: EstateDistrict,
  payload: Record<string, unknown>,
): EstateDistrict {
  const state = asWeatherState(payload["state"]);
  // A word outside the vocabulary changes nothing. Falling back to `clear`
  // would report calm we were never told about — the one direction this
  // surface must never guess in.
  if (state === null) return district;
  return {
    ...district,
    weather: {
      state,
      icon: asString(payload["icon"]),
      sentence: asString(payload["sentence"]),
    },
  };
}

function applyEnvelopeBurn(
  district: EstateDistrict,
  payload: Record<string, unknown>,
): EstateDistrict {
  const previous = district.treasury;
  const envelopeId = asString(payload["envelope_id"]) ?? previous?.envelope_id;
  const spent = asNumber(payload["spent"]) ?? previous?.spent;
  const cap = asNumber(payload["cap"]) ?? previous?.cap;
  const reserveProtected =
    asBoolean(payload["reserve_protected"]) ?? previous?.reserve_protected;
  // A partial burn on a district that never had a treasury cannot invent one.
  // A gauge drawn from three of four fields is a gauge with a made-up axis.
  if (
    envelopeId === undefined ||
    spent === undefined ||
    cap === undefined ||
    reserveProtected === undefined
  ) {
    return district;
  }
  const treasury: EstateTreasury = {
    envelope_id: envelopeId,
    spent,
    cap,
    reserve_protected: reserveProtected,
  };
  return { ...district, treasury };
}

function applyRunState(
  district: EstateDistrict,
  payload: Record<string, unknown>,
): EstateDistrict {
  const entityId = asString(payload["entity_id"]);
  if (entityId === null) return district;
  const state = asString(payload["state"]);
  const handRaised = asBoolean(payload["hand_raised"]);
  return {
    ...district,
    colleagues: district.colleagues.map((colleague) =>
      colleague.entity_id !== entityId
        ? colleague
        : {
            ...colleague,
            ...(state !== null ? { state } : {}),
            ...(handRaised !== null ? { hand_raised: handRaised } : {}),
          },
    ),
  };
}

function applyBridgeState(
  estate: EstateSnapshot,
  payload: Record<string, unknown>,
): EstateSnapshot {
  const bindingId = asString(payload["binding_id"]);
  const state = asString(payload["state"]);
  if (bindingId === null || state === null) return estate;
  // Update-only, never insert: `diff_estate` emits this event solely for
  // bindings present in both reads, so an unknown id here means the estate
  // model this client holds predates the binding — and the next full read is
  // what should introduce it, with all its fields.
  return {
    ...estate,
    bridges: estate.bridges.map((bridge) =>
      bridge.binding_id !== bindingId ? bridge : { ...bridge, state },
    ),
  };
}

/**
 * Apply one frame. Unknown fields are ignored; known fields that are absent
 * leave the previous reading standing.
 */
export function applyStreamEvent(
  estate: EstateSnapshot,
  event: StreamEvent,
): EstateSnapshot {
  const { type, payload } = event;
  let next = estate;

  if (type === "beacon.raised") {
    next = applyBeaconRaised(estate, payload);
  } else if (type === "beacon.cleared") {
    const approvalId = asString(payload["approval_id"]);
    if (approvalId !== null) {
      next = {
        ...estate,
        beacons: estate.beacons.filter((b) => b.approval_id !== approvalId),
      };
    }
  } else if (type === "pulse") {
    const healthy = asBoolean(payload["healthy"]);
    if (healthy !== null) {
      next = {
        ...estate,
        estate: {
          ...estate.estate,
          pulse: {
            healthy,
            beat_at: asString(payload["beat_at"]) ?? estate.estate.pulse.beat_at,
          },
        },
      };
    }
  } else if (type === "bridge.state") {
    next = applyBridgeState(estate, payload);
  } else if (
    type === "traffic" ||
    type === "weather.changed" ||
    type === "envelope.burn" ||
    type === "run.state"
  ) {
    const code = asString(payload["district"]);
    if (code !== null) {
      next = withDistrict(estate, code, (district) => {
        if (type === "traffic") return applyTraffic(district, payload);
        if (type === "weather.changed") return applyWeather(district, payload);
        if (type === "envelope.burn") return applyEnvelopeBurn(district, payload);
        return applyRunState(district, payload);
      });
    }
  }
  // `tray.delivered` is ignored here, and ignoring a known type is a decision
  // rather than an accident: it mirrors `beacon.raised` for the estate model,
  // which has already been applied above, and the tray *list* is a separate
  // read that this reducer does not hold. The Tray surface subscribes to the
  // same stream and re-reads on it.

  // Every frame carries the projection's own read time. Advancing it here is
  // what lets a surface say "as of 09:41" truthfully — and what makes a quiet
  // estate's `as_of` legitimately old, which is why liveness is reported
  // separately (see the module note).
  const asOf = asString(payload["as_of"]);
  if (asOf !== null && asOf !== next.as_of) {
    next = { ...next, as_of: asOf };
  }
  return next;
}
