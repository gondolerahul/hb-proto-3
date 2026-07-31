/**
 * The estate read model and the district room (VG-02, D5 §2; R-4 part P).
 *
 * One projection, two doors: `GET /ai/genui/estate` is the whole estate and
 * `GET /ai/genui/estate/district/{code}` is one district's block out of that
 * same projection with `as_of` stamped on it. The backend composes them from
 * one function, so this module declares one set of types and the district read
 * is `EstateDistrict & { as_of }` rather than a second vocabulary.
 *
 * **The field names here are the wire's, deliberately** (`in_1h`, not
 * `inPerHour`). The prototype fixtures camel-cased them, and the reconcile went
 * the fixture's way for one reason: the estate read model arrives over *two*
 * seams — this REST body and the SSE `traffic` frame, which carries the same
 * keys — so a client-side rename has to be applied in two places and stay
 * agreed forever. Renaming here would also re-derive the projection D5 §2 says
 * exists once, which is the shape of finding RD-6.
 *
 * **Weather is four states, not seven.** See `WEATHER_STATES`.
 */
import { api } from "./client";

/**
 * The weather vocabulary the backend can actually emit.
 *
 * `estate.py` computes storm > heat-shimmer > moonlit > clear and says in its
 * own docstring that **fog is a named absence**: D5 §2.1 derives fog from "the
 * KPI has been below target for N consecutive snapshots", and `KpiDefinition`
 * declares neither a target nor a direction — there is nothing to be below. The
 * prototype fixture also carried `busy` and `frost`, which no code path emits
 * either.
 *
 * So the union is closed at four. A client that kept `fog` would be carrying a
 * branch the server can never reach, which renders as a working feature over a
 * known platform gap — the thing DESIGN_CONTRACT §7.4 forbids. The gap belongs
 * to the KPI registry (a target and a direction per KPI); when it grows one,
 * `fog` is added on both sides in the same commit.
 */
export const WEATHER_STATES = ["clear", "storm", "heat-shimmer", "moonlit"] as const;

export type WeatherState = (typeof WEATHER_STATES)[number];

/** Narrow an unknown wire string. Anything else is an absence, not a default —
 * inventing `clear` over a state we do not understand is inventing calm. */
export function asWeatherState(value: unknown): WeatherState | null {
  return WEATHER_STATES.includes(value as WeatherState)
    ? (value as WeatherState)
    : null;
}

export interface EstateWeather {
  state: WeatherState;
  /** Icon name, `null` on `clear` — a calm district has nothing to show. */
  icon: string | null;
  sentence: string | null;
}

export interface EstateTraffic {
  in_1h: number;
  out_1h: number;
  parked: number;
}

/**
 * The budget envelope as the estate projects it.
 *
 * `reserve_protected` is a **boolean**, not an amount: the envelope row holds
 * `reserved_usd` but the projection only reports whether it is above zero. The
 * treasury gauge's protected-reserve seam therefore has a fact to state and no
 * width to draw to scale (gap R-4-P-1 in the report).
 */
export interface EstateTreasury {
  envelope_id: string;
  spent: number;
  cap: number;
  reserve_protected: boolean;
}

export interface EstateColleague {
  entity_id: string;
  name: string;
  autonomy: string;
  hand_raised: boolean;
  state: string;
}

/** One KPI on a district's plinth. `value` is `null` when the day was not
 * measurable, and `measurable` is `false` before the snapshot job ever ran —
 * two different absences, kept apart on the wire and kept apart here. */
export interface PlinthKpi {
  kpi_key: string;
  display_name: string;
  value: number | null;
  measurable: boolean;
  unit: string;
}

export interface EstateDistrict {
  process_code: string;
  name: string;
  quarter: string;
  colleagues: EstateColleague[];
  kpi: { plinth: PlinthKpi[] };
  treasury: EstateTreasury | null;
  weather: EstateWeather;
  traffic: EstateTraffic;
}

/** The door's trim of the consent registry (D8 E2). `GET /ai/consent` serves
 * the whole thing; a gatehouse shows the posture, the registry's own reason,
 * and the two counts of counterparties it would refuse. */
export interface EstateGateConsent {
  posture: "open" | "restricted" | "closed";
  reason: string;
  dnc: number;
  unsubscribed: number;
}

export interface EstateGatehouse {
  gateway_code: string;
  channel: string;
  health: string;
  inbound_today: number;
  parked: number;
  /** `null` when the registry was not asked about this channel — an absence,
   * never a cheerful "open" (the backend's own words). */
  consent: EstateGateConsent | null;
}

export interface EstateBridge {
  binding_id: string;
  connector: string;
  state: string;
  credentials_expire_at: string | null;
  conflicts_open: number;
}

export interface EstateBeacon {
  approval_id: string;
  district: string | null;
  checkpoint_key?: string | null;
  sla_seconds_left: number | null;
}

export interface EstateHall {
  module: string;
  objects: string[];
  records: number;
}

export interface EstateMonument {
  resolution_id: string;
  title: string | null;
  district: string | null;
  adopted_at: string;
}

export interface EstateSnapshot {
  estate: {
    loop_id: string | null;
    pulse: { beat_at: string | null; healthy: boolean };
    local_time: string;
    phase: string;
    standing: string | null;
  };
  quarters: { code: string; name: string; districts: string[] }[];
  districts: EstateDistrict[];
  gatehouses: EstateGatehouse[];
  bridges: EstateBridge[];
  halls: EstateHall[];
  monuments: EstateMonument[];
  beacons: EstateBeacon[];
  glasshouse: { open_scenarios: number; last_run_at: string | null };
  gallery: { versions: number; terminated: number };
  as_of: string;
}

export async function fetchEstate(): Promise<EstateSnapshot> {
  return (await api.get<EstateSnapshot>("/ai/genui/estate")).data;
}

/** One district's block, with the projection's own `as_of` on it. */
export type DistrictView = EstateDistrict & { as_of: string };

/**
 * One district (D6 §5). A 404 here means *this company has no such process* —
 * the same answer a cross-tenant probe gets, so a caller must not translate it
 * into "the district is empty".
 */
export async function fetchDistrict(processCode: string): Promise<DistrictView> {
  return (
    await api.get<DistrictView>(
      `/ai/genui/estate/district/${encodeURIComponent(processCode)}`,
    )
  ).data;
}
