/**
 * The territory layout (WORLD W3) — pure. The estate read model in, a
 * deterministic scene description out: where every district, gatehouse,
 * road and beacon sits, and what the light is doing. The r3f layer is a
 * thin mapper over this; keeping the geometry pure is what makes the
 * world testable without a GPU (the repo's rule: drive the real seams
 * deterministically, leave prose — here pixels — to eval).
 *
 * Determinism is a product property, not a convenience: L4 says one
 * geography, and "the same estate lays out the same way every visit" is
 * what makes the map memorable. Placement derives only from sorted codes —
 * never from insertion order, never from a clock.
 */

export interface EstateDistrict {
  process_code: string;
  name: string;
  quarter: string;
  colleagues: Array<{
    entity_id: string;
    name: string;
    autonomy: string;
    hand_raised: boolean;
    state: string;
  }>;
  weather: { state: string; icon: string | null; sentence: string | null };
  traffic: { in_1h: number; out_1h: number; parked: number };
  treasury: { spent: number; cap: number } | null;
}

export interface EstateSnapshot {
  estate: { phase: string; pulse: { healthy: boolean } };
  districts: EstateDistrict[];
  gatehouses: Array<{
    gateway_code: string;
    channel: string;
    inbound_today: number;
    parked: number;
  }>;
  beacons: Array<{
    approval_id: string;
    district: string | null;
    sla_seconds_left: number | null;
  }>;
}

export type Vec2 = readonly [number, number];

export interface PlacedDistrict extends EstateDistrict {
  position: Vec2;
}

export interface PlacedGatehouse {
  gateway_code: string;
  channel: string;
  inbound_today: number;
  parked: number;
  position: Vec2;
}

export interface Road {
  from: Vec2;
  to: Vec2;
  /** 0..1 — normalised traffic for the dot flow. */
  intensity: number;
}

export interface PlacedBeacon {
  approval_id: string;
  district: string | null;
  position: Vec2;
  sla_seconds_left: number | null;
}

export interface Lighting {
  phase: "day" | "night";
  /** High-key warm gold-white daylight, or low-key lamplit pools —
   * day–night survives as LUMINANCE, never as palette (charter decision 3). */
  keyIntensity: number;
  keyColor: string;
  ambientIntensity: number;
  lampIntensity: number;
}

export interface TerritoryLayout {
  districts: PlacedDistrict[];
  gatehouses: PlacedGatehouse[];
  roads: Road[];
  beacons: PlacedBeacon[];
  lighting: Lighting;
  /** Half-extent of the ground plane the layout occupies. */
  bounds: number;
}

const DISTRICT_RING_RADIUS = 10;
const GATEHOUSE_Z = 15;
const BOUNDS = 20;

/** Quarters own fixed angular sectors on the ring, assigned by sorted
 * quarter code — a quarter added later cannot reshuffle the others'
 * homes beyond its own arc. */
function quarterSectors(quarters: string[]): Map<string, [number, number]> {
  const sorted = [...quarters].sort();
  const sectors = new Map<string, [number, number]>();
  // The territory opens toward the gatehouses (south): districts occupy
  // the northern 240°, leaving the approach clear.
  const start = Math.PI * -1.17;
  const span = Math.PI * 1.34;
  const width = span / Math.max(1, sorted.length);
  sorted.forEach((quarter, index) => {
    sectors.set(quarter, [start + index * width, start + (index + 1) * width]);
  });
  return sectors;
}

function roundVec(x: number, z: number): Vec2 {
  return [Math.round(x * 100) / 100, Math.round(z * 100) / 100];
}

export function placeTerritory(estate: EstateSnapshot): TerritoryLayout {
  const quarters = [...new Set(estate.districts.map((d) => d.quarter))];
  const sectors = quarterSectors(quarters);

  const byQuarter = new Map<string, EstateDistrict[]>();
  for (const district of [...estate.districts].sort((a, b) =>
    a.process_code.localeCompare(b.process_code),
  )) {
    const bucket = byQuarter.get(district.quarter) ?? [];
    bucket.push(district);
    byQuarter.set(district.quarter, bucket);
  }

  const districts: PlacedDistrict[] = [];
  for (const [quarter, members] of byQuarter) {
    const sector = sectors.get(quarter);
    if (sector === undefined) continue;
    const [from, to] = sector;
    members.forEach((district, index) => {
      const t = (index + 1) / (members.length + 1);
      const angle = from + t * (to - from);
      districts.push({
        ...district,
        position: roundVec(
          Math.cos(angle) * DISTRICT_RING_RADIUS,
          Math.sin(angle) * DISTRICT_RING_RADIUS,
        ),
      });
    });
  }

  const gatehouses: PlacedGatehouse[] = [...estate.gatehouses]
    .sort((a, b) => a.channel.localeCompare(b.channel))
    .map((gatehouse, index, all) => ({
      ...gatehouse,
      position: roundVec(
        (index - (all.length - 1) / 2) * 4,
        GATEHOUSE_Z,
      ),
    }));

  const maxTraffic = Math.max(
    1,
    ...districts.map((d) => d.traffic.in_1h + d.traffic.out_1h),
  );
  const hub: Vec2 = [0, 0];
  const roads: Road[] = [
    ...gatehouses.map((gatehouse) => ({
      from: gatehouse.position,
      to: hub,
      intensity:
        gatehouse.inbound_today > 0
          ? Math.min(1, gatehouse.inbound_today / 50)
          : 0,
    })),
    ...districts.map((district) => ({
      from: hub,
      to: district.position,
      intensity: (district.traffic.in_1h + district.traffic.out_1h) / maxTraffic,
    })),
  ];

  const districtPosition = new Map(
    districts.map((d) => [d.process_code, d.position]),
  );
  const beacons: PlacedBeacon[] = estate.beacons.map((beacon) => ({
    approval_id: beacon.approval_id,
    district: beacon.district,
    sla_seconds_left: beacon.sla_seconds_left,
    position:
      (beacon.district !== null
        ? districtPosition.get(beacon.district)
        : undefined) ?? hub,
  }));

  const phase = estate.estate.phase === "night" ? "night" : "day";
  // Night is the brand's default look and must be READABLE, not void —
  // the wireframe's night renders every ghost volume clearly (POLISH L4;
  // the first screenshot round found a black screen). Day–night stays a
  // luminance shift, but the night floor is lifted well off zero.
  const lighting: Lighting =
    phase === "day"
      ? {
          phase,
          keyIntensity: 1.6,
          keyColor: "#fff3dc",
          ambientIntensity: 0.55,
          lampIntensity: 0.15,
        }
      : {
          phase,
          keyIntensity: 0.5,
          keyColor: "#fff3dc",
          ambientIntensity: 0.38,
          lampIntensity: 1.1,
        };

  return { districts, gatehouses, roads, beacons, lighting, bounds: BOUNDS };
}
